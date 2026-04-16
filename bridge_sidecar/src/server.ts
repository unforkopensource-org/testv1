#!/usr/bin/env node
// Decibench bridge sidecar entry point.
//
// Boots a WebSocket server on 127.0.0.1, accepts a single client per
// process, launches headless Chromium via Playwright, and routes the
// platform-neutral bridge protocol to the right adapter (Retell / Vapi).
//
// Stdout is reserved for the single handshake line:
//   BRIDGE_LISTENING port=<n>
// Everything else is structured JSON on stderr.

import { WebSocketServer, WebSocket } from "ws";
import { chromium } from "playwright";
import type { Browser, BrowserContext } from "playwright";

import {
  BRIDGE_PROTOCOL_VERSION,
  ErrorCode,
  MsgType,
  envelope,
  nowMs,
} from "./protocol.js";
import type { BridgeEnvelope, ConnectPayload, ConnectedPayload, ErrorPayload } from "./protocol.js";
import { log } from "./log.js";
import type { AdapterEvents, PlatformAdapter } from "./adapter.js";
import { RetellAdapter, BridgeAdapterError } from "./adapters/retell.js";
import { VapiAdapter } from "./adapters/vapi.js";

const HOST = "127.0.0.1";
const DEFAULT_PORT = 0; // dynamic — printed via BRIDGE_LISTENING

class Session {
  private adapter: PlatformAdapter | null = null;
  private browser: Browser | null = null;
  private context: BrowserContext | null = null;
  private pendingAudioBytes = 0;
  private idleTimer: NodeJS.Timeout | null = null;
  private idleTimeoutMs = 30_000;

  constructor(private readonly ws: WebSocket) {}

  async handleMessage(raw: WebSocket.RawData, isBinary: boolean): Promise<void> {
    if (isBinary) {
      // Binary frame: this is the PCM payload promised by a prior
      // `send_audio_chunk` envelope. Forward to the adapter.
      const buffer = Buffer.isBuffer(raw)
        ? raw
        : Buffer.from(raw as ArrayBuffer | Uint8Array);
      if (this.pendingAudioBytes <= 0) {
        log.warn("unsolicited binary frame from client", { bytes: buffer.length });
        return;
      }
      this.pendingAudioBytes = 0;
      if (!this.adapter) {
        log.warn("audio chunk arrived before connect()");
        return;
      }
      try {
        await this.adapter.sendCallerAudio(buffer);
      } catch (e) {
        this.sendError(ErrorCode.INTERNAL, `sendCallerAudio failed: ${String(e)}`, false);
      }
      this.resetIdleTimer();
      return;
    }

    let env: BridgeEnvelope;
    try {
      env = JSON.parse(raw.toString()) as BridgeEnvelope;
    } catch (e) {
      this.sendError(ErrorCode.PROTOCOL_VIOLATION, `invalid JSON: ${String(e)}`, false);
      return;
    }

    switch (env.type) {
      case MsgType.CONNECT:
        await this.onConnect(env.data as unknown as ConnectPayload);
        break;
      case MsgType.SEND_AUDIO_CHUNK:
        this.pendingAudioBytes = Number((env.data as { bytes: number }).bytes ?? 0);
        break;
      case MsgType.END_TURN:
        try {
          await this.adapter?.endCallerTurn();
        } catch (e) {
          this.sendError(ErrorCode.INTERNAL, `endCallerTurn failed: ${String(e)}`, false);
        }
        break;
      case MsgType.DISCONNECT:
        await this.onDisconnect(String((env.data as { reason?: string }).reason ?? "client_request"));
        break;
      case MsgType.HEALTH:
        this.send(MsgType.HEALTH_OK, { uptime_ms: process.uptime() * 1000 });
        break;
      case MsgType.CAPABILITIES_QUERY:
        this.send(MsgType.CAPABILITIES, {
          platform: this.adapter?.platform ?? null,
          supported_sample_rates: this.adapter?.capabilities.supportedSampleRates ?? [16000],
          events: this.adapter?.capabilities.events ?? [],
          browser_sdk_version: this.adapter?.capabilities.browserSdkVersion ?? "",
          bridge_version: BRIDGE_PROTOCOL_VERSION,
        });
        break;
      default:
        this.sendError(ErrorCode.PROTOCOL_VIOLATION, `unknown message type: ${env.type}`, false);
    }
  }

  private async onConnect(payload: ConnectPayload): Promise<void> {
    if (this.adapter) {
      this.sendError(ErrorCode.PROTOCOL_VIOLATION, "session already connected", true);
      return;
    }

    const platform = payload.platform;
    let adapter: PlatformAdapter;
    if (platform === "retell") {
      adapter = new RetellAdapter();
    } else if (platform === "vapi") {
      adapter = new VapiAdapter();
    } else {
      this.sendError(ErrorCode.PROTOCOL_VIOLATION, `unsupported platform: ${platform}`, true);
      return;
    }

    const sampleRate = payload.audio?.sample_rate ?? 16000;
    const connectMs = payload.options?.timeouts?.connect_ms ?? 15_000;
    this.idleTimeoutMs = payload.options?.timeouts?.idle_audio_ms ?? 30_000;

    try {
      this.browser = await chromium.launch({
        headless: true,
        args: [
          "--use-fake-ui-for-media-stream",
          "--use-fake-device-for-media-stream",
          "--autoplay-policy=no-user-gesture-required",
        ],
      });
      this.context = await this.browser.newContext({
        permissions: ["microphone"],
      });
    } catch (e) {
      this.sendError(
        ErrorCode.BROWSER_CRASHED,
        `failed to launch headless Chromium: ${String(e)}`,
        true,
      );
      await this.cleanupBrowser();
      return;
    }

    const events: AdapterEvents = {
      onAgentAudio: (pcm16) => this.sendAgentAudio(pcm16),
      onAgentTranscript: (text, isFinal) =>
        this.send(MsgType.AGENT_TRANSCRIPT, { text, is_final: isFinal }),
      onToolCall: (data) => this.send(MsgType.TOOL_CALL, data),
      onToolResult: (data) => this.send(MsgType.TOOL_RESULT, data),
      onInterruption: (data) => this.send(MsgType.INTERRUPTION, data),
      onTurnEnd: (data) => this.send(MsgType.TURN_END, data),
      onMetadata: (data) => this.send(MsgType.METADATA, data),
      onError: (code, message, fatal) => this.sendError(code, message, fatal),
    };

    let connectResult;
    try {
      connectResult = await Promise.race([
        adapter.connect(
          this.browser,
          this.context,
          {
            agentId: payload.agent_id,
            credentials: payload.credentials ?? {},
            sampleRate,
            metadata: payload.options?.metadata ?? {},
            timeouts: {
              connectMs,
              idleAudioMs: this.idleTimeoutMs,
            },
          },
          events,
        ),
        timeoutPromise(connectMs, ErrorCode.TIMEOUT, "adapter connect timed out"),
      ]);
    } catch (e) {
      const code = e instanceof BridgeAdapterError ? e.code : ErrorCode.INTERNAL;
      this.sendError(code, String(e instanceof Error ? e.message : e), true);
      await this.cleanupBrowser();
      return;
    }

    this.adapter = adapter;
    const connectedPayload: ConnectedPayload = {
      session_id: connectResult.sessionId,
      audio: {
        sample_rate: connectResult.sampleRate,
        encoding: "pcm_s16le",
        channels: 1,
      },
    };
    this.send(MsgType.CONNECTED, connectedPayload as unknown as Record<string, unknown>);
    this.resetIdleTimer();
  }

  private async onDisconnect(reason: string): Promise<void> {
    try {
      await this.adapter?.disconnect(reason);
    } catch (e) {
      log.warn("adapter.disconnect threw", { error: String(e) });
    }
    this.adapter = null;
    await this.cleanupBrowser();
    this.send(MsgType.DISCONNECTED, { reason });
    setImmediate(() => {
      try {
        this.ws.close();
      } catch {
        // ignore
      }
    });
  }

  private sendAgentAudio(pcm16: Buffer): void {
    if (this.ws.readyState !== WebSocket.OPEN) return;
    // JSON envelope first, then the binary frame — exactly as documented.
    this.send(MsgType.AGENT_AUDIO, { bytes: pcm16.length });
    this.ws.send(pcm16, { binary: true });
    this.resetIdleTimer();
  }

  private send(type: MsgType, data: Record<string, unknown>): void {
    if (this.ws.readyState !== WebSocket.OPEN) return;
    this.ws.send(JSON.stringify(envelope(type, data)));
  }

  private sendError(code: string, message: string, fatal: boolean): void {
    log.error("bridge error", { code, message, fatal });
    const payload: ErrorPayload = { code, message, fatal };
    this.send(MsgType.ERROR, payload as unknown as Record<string, unknown>);
    if (fatal) {
      setImmediate(() => {
        try {
          this.ws.close();
        } catch {
          // ignore
        }
      });
    }
  }

  private resetIdleTimer(): void {
    if (this.idleTimer) clearTimeout(this.idleTimer);
    this.idleTimer = setTimeout(() => {
      this.sendError(ErrorCode.TIMEOUT, "idle audio timeout", false);
    }, this.idleTimeoutMs);
  }

  async cleanup(): Promise<void> {
    if (this.idleTimer) {
      clearTimeout(this.idleTimer);
      this.idleTimer = null;
    }
    try {
      await this.adapter?.disconnect("cleanup");
    } catch {
      // ignore
    }
    this.adapter = null;
    await this.cleanupBrowser();
  }

  private async cleanupBrowser(): Promise<void> {
    try {
      await this.context?.close();
    } catch {
      // ignore
    }
    try {
      await this.browser?.close();
    } catch {
      // ignore
    }
    this.context = null;
    this.browser = null;
  }
}

function timeoutPromise(ms: number, code: string, message: string): Promise<never> {
  return new Promise((_, reject) => {
    setTimeout(() => reject(new BridgeAdapterError(code, message)), ms);
  });
}

function main(): void {
  const portEnv = Number(process.env.DECIBENCH_BRIDGE_PORT ?? DEFAULT_PORT);
  const wss = new WebSocketServer({ host: HOST, port: portEnv });

  wss.on("listening", () => {
    const addr = wss.address();
    if (addr && typeof addr === "object") {
      // Stdout: the single line the Python BridgeClient scrapes.
      process.stdout.write(`BRIDGE_LISTENING port=${addr.port}\n`);
      log.info("bridge listening", { port: addr.port, version: BRIDGE_PROTOCOL_VERSION });
    }
  });

  wss.on("connection", (ws) => {
    log.info("client connected");
    const session = new Session(ws);

    ws.on("message", (raw, isBinary) => {
      void session.handleMessage(raw, isBinary).catch((e) => {
        log.error("message handler crashed", { error: String(e) });
      });
    });

    ws.on("close", () => {
      log.info("client disconnected");
      void session.cleanup();
    });

    ws.on("error", (err) => {
      log.error("ws error", { error: String(err) });
    });
  });

  // Graceful shutdown so Python can `terminate()` cleanly.
  for (const sig of ["SIGINT", "SIGTERM"] as const) {
    process.on(sig, () => {
      log.info("received signal, shutting down", { signal: sig });
      wss.close(() => process.exit(0));
      // Force-exit if anything hangs.
      setTimeout(() => process.exit(1), 5000).unref();
    });
  }
}

main();

export { Session };
export { nowMs };
