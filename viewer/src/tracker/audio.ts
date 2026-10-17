// Microphone capture (16 kHz 16-bit PCM, what Gemini Live expects) and playback of Gemini's
// 24 kHz 16-bit PCM replies.

const WORKLET = `
class PcmCapture extends AudioWorkletProcessor {
  constructor() { super(); this.buf = new Int16Array(1600); this.n = 0 }
  process(inputs) {
    const ch = inputs[0][0]
    if (!ch) return true
    for (let i = 0; i < ch.length; i++) {
      const s = Math.max(-1, Math.min(1, ch[i]))
      this.buf[this.n++] = s < 0 ? s * 0x8000 : s * 0x7fff
      if (this.n === this.buf.length) { this.port.postMessage(this.buf.slice().buffer, []); this.n = 0 }
    }
    return true
  }
}
registerProcessor('pcm-capture', PcmCapture)
`

export function toBase64(bytes: ArrayBuffer | Uint8Array): string {
  const u8 = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes)
  let s = ''
  for (let i = 0; i < u8.length; i += 0x8000) s += String.fromCharCode(...u8.subarray(i, i + 0x8000))
  return btoa(s)
}

export class MicCapture {
  private ctx?: AudioContext
  private node?: AudioWorkletNode
  private source?: MediaStreamAudioSourceNode
  muted = false

  async start(stream: MediaStream, onChunk: (base64Pcm: string) => void) {
    this.ctx = new AudioContext({ sampleRate: 16000 })
    const url = URL.createObjectURL(new Blob([WORKLET], { type: 'text/javascript' }))
    await this.ctx.audioWorklet.addModule(url)
    URL.revokeObjectURL(url)
    this.source = this.ctx.createMediaStreamSource(stream)
    this.node = new AudioWorkletNode(this.ctx, 'pcm-capture')
    this.node.port.onmessage = (e: MessageEvent<ArrayBuffer>) => {
      if (!this.muted) onChunk(toBase64(e.data))
    }
    this.source.connect(this.node)
  }

  stop() {
    this.source?.disconnect()
    this.node?.disconnect()
    void this.ctx?.close()
  }
}

export class PcmPlayer {
  private ctx = new AudioContext({ sampleRate: 24000 })
  private nextTime = 0
  private playing = new Set<AudioBufferSourceNode>()
  muted = false

  play(base64Pcm: string) {
    if (this.muted) return
    void this.ctx.resume()
    const raw = atob(base64Pcm)
    const samples = new Int16Array(raw.length / 2)
    for (let i = 0; i < samples.length; i++) {
      samples[i] = raw.charCodeAt(i * 2) | (raw.charCodeAt(i * 2 + 1) << 8)
    }
    const buffer = this.ctx.createBuffer(1, samples.length, 24000)
    const ch = buffer.getChannelData(0)
    for (let i = 0; i < samples.length; i++) ch[i] = samples[i] / 0x8000
    const src = this.ctx.createBufferSource()
    src.buffer = buffer
    src.connect(this.ctx.destination)
    this.nextTime = Math.max(this.nextTime, this.ctx.currentTime + 0.02)
    src.start(this.nextTime)
    this.nextTime += buffer.duration
    this.playing.add(src)
    src.onended = () => this.playing.delete(src)
  }

  /** Gemini was interrupted (the user started talking): drop what's queued. */
  flush() {
    for (const src of this.playing) src.stop()
    this.playing.clear()
    this.nextTime = 0
  }

  close() {
    this.flush()
    void this.ctx.close()
  }
}
