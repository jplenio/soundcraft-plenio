/**
 * The music's frames for a video, worked out from the decoded song instead of listened to while it plays:
 * the same spectrum, waveforms, bands and beats the player's analyser gives the visuals live (engine.ts) -
 * a 2048-point FFT with a Blackman window, the analyser's smoothing and decibel scale - for any moment, as
 * fast as the computer can, frame by frame.
 */
import { BeatDetector, band, type Frame } from '../visuals/analysis'

const SIZE = 2048
const BINS = SIZE / 2
const MIN_DB = -100
const MAX_DB = -30
/** The live analyser's smoothing, per frame at about 60 frames a second. */
const SMOOTHING = 0.72

/** A real FFT of ``SIZE`` samples (radix 2, in place): the magnitudes of the first ``BINS`` bins. */
class FFT {
  private readonly re = new Float64Array(SIZE)
  private readonly im = new Float64Array(SIZE)
  private readonly reverse = new Uint32Array(SIZE)
  private readonly cos = new Float64Array(SIZE / 2)
  private readonly sin = new Float64Array(SIZE / 2)

  constructor() {
    const bits = Math.log2(SIZE)
    for (let i = 0; i < SIZE; i++) {
      let r = 0
      for (let b = 0; b < bits; b++) r |= ((i >> b) & 1) << (bits - 1 - b)
      this.reverse[i] = r
    }
    for (let i = 0; i < SIZE / 2; i++) {
      this.cos[i] = Math.cos((-2 * Math.PI * i) / SIZE)
      this.sin[i] = Math.sin((-2 * Math.PI * i) / SIZE)
    }
  }

  magnitudes(input: Float32Array, out: Float32Array): void {
    const { re, im, reverse } = this
    for (let i = 0; i < SIZE; i++) {
      re[reverse[i]] = input[i]
      im[reverse[i]] = 0
    }
    for (let size = 2; size <= SIZE; size <<= 1) {
      const half = size >> 1
      const step = SIZE / size
      for (let start = 0; start < SIZE; start += size) {
        for (let j = 0; j < half; j++) {
          const k = j * step
          const a = start + j
          const b = a + half
          const tr = re[b] * this.cos[k] - im[b] * this.sin[k]
          const ti = re[b] * this.sin[k] + im[b] * this.cos[k]
          re[b] = re[a] - tr
          im[b] = im[a] - ti
          re[a] += tr
          im[a] += ti
        }
      }
    }
    for (let i = 0; i < BINS; i++) out[i] = Math.hypot(re[i], im[i]) / SIZE
  }
}

export class OfflineAnalysis {
  private readonly left: Float32Array
  private readonly right: Float32Array
  private readonly rate: number
  private readonly fft = new FFT()
  private readonly window = new Float32Array(SIZE)
  private readonly block = new Float32Array(SIZE)
  private readonly magnitude = new Float32Array(BINS)
  private readonly smooth = new Float32Array(BINS)
  private readonly smoothing: number
  private readonly beats = new BeatDetector()
  private readonly freq = new Uint8Array(BINS)
  private readonly wave = new Uint8Array(SIZE)
  private readonly waveL = new Uint8Array(SIZE)
  private readonly waveR = new Uint8Array(SIZE)

  constructor(audio: { left: Float32Array; right: Float32Array; rate: number }, fps: number, readonly sensitivity = 1) {
    this.left = audio.left
    this.right = audio.right
    this.rate = audio.rate
    // the analyser smooths once per frame it is asked: the same fading per second at the video's rate
    this.smoothing = Math.pow(SMOOTHING, 60 / fps)
    for (let i = 0; i < SIZE; i++) {
      const x = i / SIZE
      this.window[i] = 0.42 - 0.5 * Math.cos(2 * Math.PI * x) + 0.08 * Math.cos(4 * Math.PI * x)
    }
  }

  /** The music at ``t`` seconds into the song (the last 2048 samples before it, as the analyser hears
   * them); ``elapsed``: seconds since the video started, the visuals' clock. */
  frame(t: number, dt: number, elapsed: number): Frame {
    const end = Math.round(t * this.rate)
    const from = end - SIZE
    for (let i = 0; i < SIZE; i++) {
      const k = from + i
      const l = k >= 0 && k < this.left.length ? this.left[k] : 0
      const r = k >= 0 && k < this.right.length ? this.right[k] : 0
      const mono = (l + r) / 2
      this.block[i] = mono * this.window[i]
      this.wave[i] = byte(mono)
      this.waveL[i] = byte(l)
      this.waveR[i] = byte(r)
    }
    this.fft.magnitudes(this.block, this.magnitude)
    const s = this.sensitivity
    for (let i = 0; i < BINS; i++) {
      this.smooth[i] = this.smoothing * this.smooth[i] + (1 - this.smoothing) * this.magnitude[i]
      const db = 20 * Math.log10(this.smooth[i] + 1e-12)
      const value = Math.floor(((db - MIN_DB) * 255) / (MAX_DB - MIN_DB))
      this.freq[i] = Math.max(0, Math.min(255, value * s))
    }
    const bass = Math.min(1, band(this.freq, 1, 10) * s)
    const mid = Math.min(1, band(this.freq, 10, 90) * s)
    const treble = Math.min(1, band(this.freq, 90, 500) * s * 1.4)
    const beat = this.beats.step(bass, elapsed, dt)
    return {
      freq: this.freq,
      wave: this.wave,
      left: this.waveL,
      right: this.waveR,
      bass,
      mid,
      treble,
      level: (bass + mid + treble) / 3,
      beat,
      pulse: this.beats.pulse,
      time: elapsed,
      dt,
      playing: true,
    }
  }
}

function byte(sample: number): number {
  return Math.max(0, Math.min(255, Math.round(128 + sample * 128)))
}
