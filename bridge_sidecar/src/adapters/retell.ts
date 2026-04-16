// Retell adapter — drives the official Retell Web Client SDK inside a
// headless Chromium page.
//
// Token / web-call bootstrap:
//   1. POST https://api.retellai.com/v2/create-web-call with the agent_id and
//      credentials.api_key. The response includes `access_token` and
//      `call_id`.
//   2. Open a static HTML page (browser/retell.html) that loads
//      retell-client-js-sdk from a CDN, exposes window.Decibench bindings,
//      and starts a call using `access_token`.
//   3. The browser code captures incoming agent audio via AudioWorklet,
//      base64-encodes PCM16 chunks, and posts them back to Node via
//      page.exposeFunction("decibenchOnAudio").
//   4. Caller audio (PCM16 from Decibench) is fed to the SDK by writing into
//      a MediaStreamTrack constructed from a generated MediaStream.
//
// This adapter is intentionally narrow. It does NOT try to be a general
// Retell SDK wrapper — only what Decibench needs for end-to-end testing.

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

const RETELL_CREATE_WEB_CALL_URL = "https://api.retellai.com/v2/create-web-call";

const __dirname = dirname(fileURLToPath(import.meta.url));
// During build the sidecar copies browser/*.html into dist/browser/ via the
// tsconfig include + a small post-build step. Resolve from both locations.
function resolveBrowserAsset(name: string): string {
  const candidates = [
    resolve(__dirname, "../browser", name),
    resolve(__dirname, "../../browser", name),
  ];
  for (const c of candidates) {
    try {
      // statSync is fine here — startup-only path.
      // eslint-disable-next-line @typescript-eslint/no-require-imports
      const fs = require("node:fs");
      if (fs.existsSync(c)) return c;
    } catch {
      // ignore
    }
  }
  return candidates[0];
}

interface CreateWebCallResponse {
  access_token: string;
  call_id: string;
  agent_id?: string;
  sample_rate?: number;
}

export class RetellAdapter implements PlatformAdapter {
  readonly platform = "retell" as const;
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
    browserSdkVersion: "retell-client-js-sdk",
  };

  private _page: Page | null = null;
  private _callId: string | null = null;

  async connect(
    _browser: Browser,
    context: BrowserContext,
    options: AdapterOptions,
    events: AdapterEvents,
  ): Promise<ConnectResult> {
    const apiKey = String(options.credentials.api_key ?? "");
    if (!apiKey) {
      throw new BridgeAdapterError(
        ErrorCode.VENDOR_AUTH_FAILED,
        "Retell adapter requires credentials.api_key",
      );
    }

    // Step 1: bootstrap the web call.
    const webCall = await this.createWebCall(apiKey, options.agentId, options.metadata);
    this._callId = webCall.call_id;
    log.info("retell: created web call", { call_id: webCall.call_id });

    // Step 2: open the browser page.
    const page = await context.newPage();
    this._page = page;

    // Surface page console output to the sidecar log for debugging.
    page.on("console", (msg) => log.debug(`retell page console: ${msg.text()}`));
    page.on("pageerror", (err) => {
      log.error("retell page error", { error: String(err) });
      events.onError(ErrorCode.BROWSER_CRASHED, String(err), true);
    });

    // Bind Node-side callbacks the page can invoke.
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
            log.debug("retell unknown event", { kind, data });
        }
      },
    );
    await page.exposeFunction(
      "decibenchOnError",
      (code: string, message: string, fatal: boolean) => {
        events.onError(code || ErrorCode.INTERNAL, message, !!fatal);
      },
    );

    // Step 3: load the bridge page.
    const htmlPath = resolveBrowserAsset("retell.html");
    await page.goto(`file://${htmlPath}`);

    // Step 4: kick off the call inside the page.
    const sampleRate = options.sampleRate ?? 16000;
    try {
      await page.evaluate(
        async ({ accessToken, sampleRate }) => {
          // The page's start() function is defined in browser/retell.html.
          // It returns a promise that resolves once the call is in progress.
          // @ts-expect-error - injected by the page
          await window.decibenchStart({ accessToken, sampleRate });
        },
        { accessToken: webCall.access_token, sampleRate },
      );
    } catch (e) {
      throw new BridgeAdapterError(
        ErrorCode.VENDOR_REJECTED,
        `Retell SDK failed to start: ${String(e)}`,
      );
    }

    return { sessionId: webCall.call_id, sampleRate };
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
        log.warn("retell: page stop() threw", { error: String(e) });
      }
      try {
        await this._page.close();
      } catch (e) {
        log.warn("retell: page close threw", { error: String(e) });
      }
      this._page = null;
    }
  }

  page(): Page | null {
    return this._page;
  }

  // --------------------------------------------------------------- internals

  private async createWebCall(
    apiKey: string,
    agentId: string,
    metadata: Record<string, unknown>,
  ): Promise<CreateWebCallResponse> {
    const body = {
      agent_id: agentId,
      metadata,
    };
    let res: Response;
    try {
      res = await fetch(RETELL_CREATE_WEB_CALL_URL, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${apiKey}`,
        },
        body: JSON.stringify(body),
      });
    } catch (e) {
      throw new BridgeAdapterError(
        ErrorCode.VENDOR_REJECTED,
        `Retell create-web-call network error: ${String(e)}`,
      );
    }
    if (!res.ok) {
      const text = await res.text();
      const code =
        res.status === 401 || res.status === 403
          ? ErrorCode.VENDOR_AUTH_FAILED
          : ErrorCode.VENDOR_REJECTED;
      throw new BridgeAdapterError(
        code,
        `Retell create-web-call returned ${res.status}: ${text.slice(0, 400)}`,
      );
    }
    const data = (await res.json()) as CreateWebCallResponse;
    if (!data.access_token || !data.call_id) {
      throw new BridgeAdapterError(
        ErrorCode.VENDOR_REJECTED,
        `Retell create-web-call response missing access_token/call_id: ${JSON.stringify(data)}`,
      );
    }
    return data;
  }
}

export class BridgeAdapterError extends Error {
  constructor(
    public readonly code: string,
    message: string,
  ) {
    super(`[${code}] ${message}`);
  }
}
