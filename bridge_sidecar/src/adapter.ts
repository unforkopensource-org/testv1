// Platform adapter interface.
//
// Each supported vendor (Retell, Vapi, ...) has one Adapter implementation.
// The Adapter owns the headless browser page and the official browser SDK
// running inside it. The Server module is platform-neutral and only talks to
// adapters through this interface.

import type { Browser, BrowserContext, Page } from "playwright";

export interface AdapterOptions {
  agentId: string;
  credentials: Record<string, unknown>;
  sampleRate: number;
  metadata: Record<string, unknown>;
  timeouts: { connectMs: number; idleAudioMs: number };
}

export interface AdapterEvents {
  onAgentAudio: (pcm16: Buffer) => void;
  onAgentTranscript: (text: string, isFinal: boolean) => void;
  onToolCall: (data: Record<string, unknown>) => void;
  onToolResult: (data: Record<string, unknown>) => void;
  onInterruption: (data: Record<string, unknown>) => void;
  onTurnEnd: (data: Record<string, unknown>) => void;
  onMetadata: (data: Record<string, unknown>) => void;
  onError: (code: string, message: string, fatal: boolean) => void;
}

export interface ConnectResult {
  sessionId: string;
  sampleRate: number;
}

export interface PlatformAdapter {
  readonly platform: "retell" | "vapi";
  readonly capabilities: {
    supportedSampleRates: number[];
    events: string[];
    browserSdkVersion: string;
  };

  connect(
    browser: Browser,
    context: BrowserContext,
    options: AdapterOptions,
    events: AdapterEvents,
  ): Promise<ConnectResult>;

  sendCallerAudio(pcm16: Buffer): Promise<void>;
  endCallerTurn(): Promise<void>;
  disconnect(reason: string): Promise<void>;

  // For diagnostics — return the underlying Playwright page if any.
  page(): Page | null;
}
