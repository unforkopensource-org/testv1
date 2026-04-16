// Shared AudioWorklet processor that:
//   - takes incoming PCM16 chunks pushed via the main thread (caller audio
//     from Decibench) and converts them to Float32, then plays them out as
//     the local microphone for the SDK to capture.
//   - captures outgoing audio (agent voice from the SDK's <audio> element /
//     remote stream) and converts it back to PCM16 for Decibench.
//
// Decibench always negotiates 16 kHz mono PCM16. The AudioContext default is
// usually 48 kHz; we therefore SR-convert with a simple linear resampler.
// This is intentional — DSP-quality resampling is the SDK's job, not ours.

class DecibenchPlaybackProcessor extends AudioWorkletProcessor {
  constructor(opts) {
    super();
    this._queue = []; // array of Float32Array blocks at sampleRate (context rate)
    this._readOffset = 0;
    this._targetRate = (opts && opts.processorOptions && opts.processorOptions.targetRate) || 16000;
    this._contextRate = sampleRate; // worklet global

    this.port.onmessage = (e) => {
      const msg = e.data;
      if (msg && msg.type === "push") {
        // msg.pcm16 is an Int16Array at this._targetRate.
        const float32 = this._upsample(msg.pcm16, this._targetRate, this._contextRate);
        this._queue.push(float32);
      } else if (msg && msg.type === "flush") {
        this._queue = [];
        this._readOffset = 0;
      }
    };
  }

  _upsample(int16, fromRate, toRate) {
    const ratio = toRate / fromRate;
    const outLen = Math.floor(int16.length * ratio);
    const out = new Float32Array(outLen);
    for (let i = 0; i < outLen; i++) {
      const srcIdx = i / ratio;
      const i0 = Math.floor(srcIdx);
      const i1 = Math.min(i0 + 1, int16.length - 1);
      const frac = srcIdx - i0;
      const s0 = int16[i0] / 32768;
      const s1 = int16[i1] / 32768;
      out[i] = s0 + (s1 - s0) * frac;
    }
    return out;
  }

  process(_inputs, outputs) {
    const out = outputs[0];
    if (!out || !out[0]) return true;
    const channel = out[0];
    let written = 0;
    while (written < channel.length && this._queue.length > 0) {
      const head = this._queue[0];
      const remaining = head.length - this._readOffset;
      const needed = channel.length - written;
      const copyLen = Math.min(remaining, needed);
      channel.set(head.subarray(this._readOffset, this._readOffset + copyLen), written);
      written += copyLen;
      this._readOffset += copyLen;
      if (this._readOffset >= head.length) {
        this._queue.shift();
        this._readOffset = 0;
      }
    }
    // Pad remainder with silence (very common when the queue underruns).
    if (written < channel.length) channel.fill(0, written);
    return true;
  }
}

class DecibenchCaptureProcessor extends AudioWorkletProcessor {
  constructor(opts) {
    super();
    this._targetRate = (opts && opts.processorOptions && opts.processorOptions.targetRate) || 16000;
    this._contextRate = sampleRate;
    this._chunkMs = 20;
    this._chunkSamples = Math.round((this._targetRate * this._chunkMs) / 1000);
    this._accum = new Int16Array(this._chunkSamples);
    this._accumLen = 0;
  }

  _downsample(float32, fromRate, toRate) {
    const ratio = toRate / fromRate;
    const outLen = Math.max(1, Math.floor(float32.length * ratio));
    const out = new Int16Array(outLen);
    for (let i = 0; i < outLen; i++) {
      const srcIdx = i / ratio;
      const i0 = Math.floor(srcIdx);
      const i1 = Math.min(i0 + 1, float32.length - 1);
      const frac = srcIdx - i0;
      const s = float32[i0] + (float32[i1] - float32[i0]) * frac;
      const clamped = Math.max(-1, Math.min(1, s));
      out[i] = clamped < 0 ? Math.round(clamped * 32768) : Math.round(clamped * 32767);
    }
    return out;
  }

  process(inputs) {
    const input = inputs[0];
    if (!input || !input[0]) return true;
    const float32 = input[0];
    const int16 = this._downsample(float32, this._contextRate, this._targetRate);
    let i = 0;
    while (i < int16.length) {
      const space = this._accum.length - this._accumLen;
      const take = Math.min(space, int16.length - i);
      this._accum.set(int16.subarray(i, i + take), this._accumLen);
      this._accumLen += take;
      i += take;
      if (this._accumLen >= this._accum.length) {
        // Post a copy because the buffer is reused.
        this.port.postMessage({ type: "chunk", pcm16: this._accum.slice(0) }, []);
        this._accumLen = 0;
      }
    }
    return true;
  }
}

registerProcessor("decibench-playback", DecibenchPlaybackProcessor);
registerProcessor("decibench-capture", DecibenchCaptureProcessor);
