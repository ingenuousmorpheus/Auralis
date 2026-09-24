/* Microphone recorder for voice capture.

   Records raw PCM through an AudioWorklet (ScriptProcessor as a fallback)
   with the browser's echo cancellation, noise suppression and auto gain OFF,
   so the take is the singer's real sound. The take is encoded as a 16-bit
   mono WAV in the browser; nothing is uploaded anywhere but the local engine. */

const WORKLET = `
class Tap extends AudioWorkletProcessor {
  process(inputs) {
    const ch = inputs[0] && inputs[0][0];
    if (ch) this.port.postMessage(ch.slice(0));
    return true;
  }
}
registerProcessor("auralis-tap", Tap);`;

export async function listMics() {
  if (!navigator.mediaDevices?.enumerateDevices) return [];
  const devices = await navigator.mediaDevices.enumerateDevices();
  return devices.filter(d => d.kind === "audioinput");
}

export function encodeWav(chunks, sampleRate) {
  const length = chunks.reduce((n, c) => n + c.length, 0);
  const buffer = new ArrayBuffer(44 + length * 2);
  const view = new DataView(buffer);
  const text = (offset, s) => { for (let i = 0; i < s.length; i++) view.setUint8(offset + i, s.charCodeAt(i)); };
  text(0, "RIFF"); view.setUint32(4, 36 + length * 2, true); text(8, "WAVE");
  text(12, "fmt "); view.setUint32(16, 16, true); view.setUint16(20, 1, true); view.setUint16(22, 1, true);
  view.setUint32(24, sampleRate, true); view.setUint32(28, sampleRate * 2, true);
  view.setUint16(32, 2, true); view.setUint16(34, 16, true);
  text(36, "data"); view.setUint32(40, length * 2, true);
  let offset = 44;
  for (const c of chunks) {
    for (let i = 0; i < c.length; i++, offset += 2) {
      const s = Math.max(-1, Math.min(1, c[i]));
      view.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7fff, true);
    }
  }
  return new Blob([buffer], { type: "audio/wav" });
}

/* start({deviceId, onLevel}) → a recorder with stop() → {blob, seconds, sampleRate, peaks}.
   onLevel receives {rms, peak, clipped, seconds} about 20 times a second. */
export async function startRecording({ deviceId, onLevel } = {}) {
  if (!navigator.mediaDevices?.getUserMedia) throw new Error("This browser cannot use a microphone here.");
  const stream = await navigator.mediaDevices.getUserMedia({
    audio: {
      deviceId: deviceId ? { exact: deviceId } : undefined,
      echoCancellation: false, noiseSuppression: false, autoGainControl: false, channelCount: 1,
    },
  });
  const ctx = new AudioContext();
  const source = ctx.createMediaStreamSource(stream);
  const chunks = [];
  const peaks = [];
  let samples = 0, clippedTotal = 0, lastReport = 0, winPeak = 0, winSq = 0, winN = 0;

  const take = data => {
    chunks.push(data);
    samples += data.length;
    for (let i = 0; i < data.length; i++) {
      const a = Math.abs(data[i]);
      if (a > winPeak) winPeak = a;
      winSq += data[i] * data[i];
      if (a >= 0.999) clippedTotal++;
    }
    winN += data.length;
    if (samples - lastReport >= ctx.sampleRate / 20) {
      const rms = Math.sqrt(winSq / Math.max(1, winN));
      peaks.push(winPeak);
      onLevel?.({ rms, peak: winPeak, clipped: clippedTotal > 0, seconds: samples / ctx.sampleRate });
      lastReport = samples; winPeak = 0; winSq = 0; winN = 0;
    }
  };

  // Some browsers only run nodes the graph pulls, so route through a muted gain.
  const mute = ctx.createGain();
  mute.gain.value = 0;
  mute.connect(ctx.destination);
  let node;
  try {
    const url = URL.createObjectURL(new Blob([WORKLET], { type: "application/javascript" }));
    await ctx.audioWorklet.addModule(url);
    URL.revokeObjectURL(url);
    node = new AudioWorkletNode(ctx, "auralis-tap");
    node.port.onmessage = e => take(e.data);
    source.connect(node);
    node.connect(mute);
  } catch {
    node = ctx.createScriptProcessor(4096, 1, 1);
    node.onaudioprocess = e => take(new Float32Array(e.inputBuffer.getChannelData(0)));
    source.connect(node);
    node.connect(mute);
  }

  let closed = false;
  const shutdown = () => {
    if (closed) return false;
    closed = true;
    try { source.disconnect(); node.disconnect(); } catch { /* already disconnected */ }
    stream.getTracks().forEach(t => t.stop());
    if (ctx.state !== "closed") ctx.close().catch(() => {});
    return true;
  };

  return {
    sampleRate: ctx.sampleRate,
    async stop() {
      shutdown();
      return { blob: encodeWav(chunks, ctx.sampleRate), seconds: samples / ctx.sampleRate,
        sampleRate: ctx.sampleRate, peaks, clipped: clippedTotal > 0 };
    },
    cancel() { shutdown(); },     // safe to call after stop()
  };
}
