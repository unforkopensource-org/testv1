// Bridge protocol — TypeScript mirror of decibench/bridge/protocol.py.
// MUST stay aligned with the Python side. Any change here requires a matching
// change there.

export const BRIDGE_PROTOCOL_VERSION = "1.0.0";

export const enum MsgType {
  // client → server
  CONNECT = "connect",
  SEND_AUDIO_CHUNK = "send_audio_chunk",
  END_TURN = "end_turn",
  DISCONNECT = "disconnect",
  HEALTH = "health",
  CAPABILITIES_QUERY = "capabilities_query",

  // server → client
  CONNECTED = "connected",
  AGENT_AUDIO = "agent_audio",
  AGENT_TRANSCRIPT = "agent_transcript",
  TOOL_CALL = "tool_call",
  TOOL_RESULT = "tool_result",
  INTERRUPTION = "interruption",
  TURN_END = "turn_end",
  METADATA = "metadata",
  ERROR = "error",
  DISCONNECTED = "disconnected",
  HEALTH_OK = "health_ok",
  CAPABILITIES = "capabilities",
}

export const enum ErrorCode {
  VENDOR_AUTH_FAILED = "vendor_auth_failed",
  VENDOR_REJECTED = "vendor_rejected",
  BROWSER_CRASHED = "browser_crashed",
  TIMEOUT = "timeout",
  PROTOCOL_VIOLATION = "protocol_violation",
  INTERNAL = "internal",
}

export interface BridgeEnvelope<T = Record<string, unknown>> {
  type: MsgType;
  id: string;
  ts_ms: number;
  data: T;
}

export interface ConnectPayload {
  platform: "retell" | "vapi";
  agent_id: string;
  credentials?: Record<string, unknown>;
  audio?: { sample_rate: number; encoding: string; channels: number };
  options?: {
    metadata?: Record<string, unknown>;
    timeouts?: { connect_ms?: number; idle_audio_ms?: number };
    client_protocol_version?: string;
  };
}

export interface ConnectedPayload {
  session_id: string;
  audio: { sample_rate: number; encoding: string; channels: number };
}

export interface ErrorPayload {
  code: ErrorCode | string;
  message: string;
  fatal: boolean;
}

export function nowMs(): number {
  return performance.now();
}

export function envelope<T>(type: MsgType, data: T): BridgeEnvelope<T> {
  return {
    type,
    id: `evt_${Math.random().toString(36).slice(2, 14)}`,
    ts_ms: nowMs(),
    data,
  };
}
