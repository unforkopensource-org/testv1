// Structured stderr logger — one JSON object per line, as documented in
// docs/bridge-protocol.md. The Python BridgeClient parses these lines into
// CallSummary.platform_metadata.bridge_logs.

type Level = "debug" | "info" | "warn" | "error";

function emit(level: Level, msg: string, ctx?: Record<string, unknown>): void {
  const line = JSON.stringify({
    level,
    msg,
    ts: new Date().toISOString(),
    ctx: ctx ?? {},
  });
  // stderr is the bridge's diagnostic channel. stdout is reserved for the
  // single `BRIDGE_LISTENING port=<n>` handshake line.
  process.stderr.write(line + "\n");
}

export const log = {
  debug: (msg: string, ctx?: Record<string, unknown>) => emit("debug", msg, ctx),
  info: (msg: string, ctx?: Record<string, unknown>) => emit("info", msg, ctx),
  warn: (msg: string, ctx?: Record<string, unknown>) => emit("warn", msg, ctx),
  error: (msg: string, ctx?: Record<string, unknown>) => emit("error", msg, ctx),
};
