// Vapi adapter — drives the official Vapi Web SDK inside a headless Chromium
// page. Same architecture as RetellAdapter; only the bootstrap and SDK glue
// differ.
//
// Vapi web calls run on Daily.co under the hood. The Vapi Web SDK takes a
// public key + assistant id (or assistant overrides) and handles the WebRTC
// negotiation transparently.

import type { Browser, BrowserContext, Page } from "playwright";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

import type {
  AdapterEvents,
  AdapterOptions,
  ConnectResult,
  PlatformAdapter,
} from "../adapter.js";
import { ErrorCode } from "../protocol.js";
import { log } from "../log.js";
import { BridgeAdapterError } from "./retell.js";

const __dirname = dirname(fileURLToPath(import.meta.url));

function resolveBrowserAsset(name: string): string {
  const candidates = [
    resolve(__dirname, "../browser", name),
    resolve(__dirname, "../../browser", name),
  ];
  for (const c of candidates) {
    try {
      // eslint-disable-next-line @typescript-eslint/no-require-imports
      const fs = require("node:fs");
      if (fs.existsSync(c)) return c;
    } catch {
      // ignore
    }
  }
  return candidates[0];
}

export class VapiAdapter implements PlatformAdapter {
  readonly platform = "vapi" as const;
  readonly capabilities = {
    supportedSampleRates: [16000, 24000],
    events: [
      "agent_audio",
      "agent_transcript",
      "tool_call",
      "tool_result",
      "interruption",
      "turn_end",
      "metadata",
    ],
    browserSdkVersion: "@vapi-ai/web",
  };

  private _page: Page | null = null;
  private _callId: string | null = null;

  async connect(
    _browser: Browser,
    context: BrowserContext,
    options: AdapterOptions,
    events: AdapterEvents,
  ): Promise<ConnectResult> {
    const publicKey = String(options.credentials.public_key ?? options.credentials.api_key ?? "");
    if (!publicKey) {
      throw new BridgeAdapterError(
        ErrorCode.VENDOR_AUTH_FAILED,
        "Vapi adapter requires credentials.public_key (or api_key)",
      );
    }

    const page = await context.newPage();
    this._page = page;

    page.on("console", (msg) => log.debug(`vapi page console: ${msg.text()}`));
    page.on("pageerror", (err) => {
      log.error("vapi page error", { error: String(err) });
      events.onError(ErrorCode.BROWSER_CRASHED, String(err), true);
    });

    await page.exposeFunction("decibenchOnAudio", (b64: string) => {
      try {
        events.onAgentAudio(Buffer.from(b64, "base64"));
      } catch (e) {
        log.warn("decoding agent audio failed", { error: String(e) });
      }
    });
    await page.exposeFunction("decibenchOnTranscript", (text: string, isFinal: boolean) => {
      events.onAgentTranscript(text, !!isFinal);
    });
    await page.exposeFunction(
      "decibenchOnEvent",
      (kind: string, data: Record<string, unknown>) => {
        switch (kind) {
          case "tool_call":
            events.onToolCall(data);
            return;
          case "tool_result":
            events.onToolResult(data);
            return;
          case "interruption":
            events.onInterruption(data);
            return;
          case "turn_end":
            events.onTurnEnd(data);
            return;
          case "metadata":
            events.onMetadata(data);
            return;
          default:
            log.debug("vapi unknown event", { kind, data });
        }
      },
    );
    await page.exposeFunction(
      "decibenchOnError",
      (code: string, message: string, fatal: boolean) => {
        events.onError(code || ErrorCode.INTERNAL, message, !!fatal);
      },
    );

    const htmlPath = resolveBrowserAsset("vapi.html");
    await page.goto(`file://${htmlPath}`);

    const sampleRate = options.sampleRate ?? 16000;
    let sessionId: string;
    try {
      sessionId = await page.evaluate(
        async ({ publicKey, assistantId, sampleRate, metadata }) => {
          // @ts-expect-error - injected by the page
          return await window.decibenchStart({ publicKey, assistantId, sampleRate, metadata });
        },
        {
          publicKey,
          assistantId: options.agentId,
          sampleRate,
          metadata: options.metadata,
        },
      );
    } catch (e) {
      throw new BridgeAdapterError(
        ErrorCode.VENDOR_REJECTED,
        `Vapi SDK failed to start: ${String(e)}`,
      );
    }

    this._callId = sessionId;
    return { sessionId, sampleRate };
  }

  async sendCallerAudio(pcm16: Buffer): Promise<void> {
    if (!this._page) return;
    const b64 = pcm16.toString("base64");
    await this._page.evaluate((b: string) => {
      // @ts-expect-error - injected by the page
      window.decibenchPushAudio(b);
    }, b64);
  }

  async endCallerTurn(): Promise<void> {
    if (!this._page) return;
    await this._page.evaluate(() => {
      // @ts-expect-error - injected by the page
      window.decibenchEndTurn?.();
    });
  }

  async disconnect(_reason: string): Promise<void> {
    if (this._page) {
      try {
        await this._page.evaluate(() => {
          // @ts-expect-error - injected by the page
          window.decibenchStop?.();
        });
      } catch (e) {
        log.warn("vapi: page stop() threw", { error: String(e) });
      }
      try {
        await this._page.close();
      } catch (e) {
        log.warn("vapi: page close threw", { error: String(e) });
      }
      this._page = null;
    }
  }

  page(): Page | null {
    return this._page;
  }
}
