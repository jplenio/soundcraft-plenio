/**
 * The change from one visual to the next (owner's requests 2026-10-18: a soft crossfade to the new one, not a
 * sudden start, to choose - and one that brings both together, organic and soft whatever the kind). While the
 * change lasts, both visuals play on, each on a layer of its own, and the two are mixed:
 *
 *  - **morph**: both play together - their light added, each as bright as the other half way - and melt into
 *    one another in a soft swirl, until only the new one is left;
 *  - **melt**: the new one flows in through soft blots that drift and grow, like ink spreading in water;
 *  - **fade**: the new one comes up over the old one;
 *  - **zoom**: the old one swells away, the new one grows in;
 *  - **slide**: the new one pushes in from the side behind a soft edge;
 *  - **flash**: the old one plays on to the next beat, then the new one in a soft glow;
 *  - **random**: one of morph, melt, fade, zoom and slide, another each time; **cut**: at once.
 *
 * Every soft change also has a swirl: the mixed picture of the frame before, drawn again a little larger and
 * turned over the new one, strongest half way - so the two flow into each other like smoke instead of simply
 * lying on top. Between two Plenio Drop presets the renderer glides by itself (the picture stays, its motion
 * turns into the new one) over the same time.
 *
 * Used by the player's visual (VisualCanvas.vue) and by a song's video (video/make.ts).
 */
import type { Frame } from './analysis'
import type { Colors, Preset, Scene } from './presets'

export type FadeStyle = 'blend' | 'melt' | 'fade' | 'zoom' | 'slide' | 'flash' | 'random' | 'cut'

export interface Fade {
  style: FadeStyle
  /** How long the change takes (a flash: how long its glow fades). */
  seconds: number
}

export const FADE_STYLES: [FadeStyle, string, string][] = [
  ['blend', 'Morph - both into one', 'Both visuals play together and melt into one another in a soft swirl, until the new one stays'],
  ['melt', 'Melt', 'The new visual flows in through soft, drifting blots - like ink spreading in water'],
  ['fade', 'Soft fade', 'The new visual comes up over the old one'],
  ['zoom', 'Zoom through', 'The old visual swells away in a swirl, the new one grows in'],
  ['slide', 'Slide', 'The new visual pushes in from the side behind a soft edge'],
  ['flash', 'Flash on the beat', 'The old visual plays on to the next beat, then the new one in a soft glow'],
  ['random', 'A different one each time', 'Morph, melt, fade, zoom or slide - another one at every change'],
  ['cut', 'Cut', 'At once, no crossfade'],
]
export const DEFAULT_FADE: Fade = { style: 'blend', seconds: 3 }
/** The changes ``random`` picks from. */
const ORGANIC: FadeStyle[] = ['blend', 'melt', 'fade', 'zoom', 'slide']
/** A flash waits this long for a beat at most. */
const BEAT_WAIT = 2

export function fadeWithDefaults(style: unknown, seconds: unknown): Fade {
  return {
    style: FADE_STYLES.some(([id]) => id === style) ? (style as FadeStyle) : DEFAULT_FADE.style,
    seconds: Math.min(10, Math.max(0.3, Number(seconds) || DEFAULT_FADE.seconds)),
  }
}

// --- the shapes of a change (pure, tested) ------------------------------------------------------------------

/** 0..1, slow at both ends. */
export const ease = (t: number): number => {
  const x = Math.min(1, Math.max(0, t))
  return x * x * (3 - 2 * x)
}

const smoothstep = (a: number, b: number, x: number): number => ease((x - a) / (b - a || 1))

/** One layer drawn onto the picture: which, how opaque, how large (around the middle), how far to the right. */
export interface Stroke {
  layer: 'old' | 'new'
  alpha: number
  scale: number
  /** As a share of the width. */
  shift: number
}

/** How fade, zoom and slide draw the two layers at ``p`` (0: only the old one, 1: only the new one) - bottom
 * first. */
export function strokes(style: FadeStyle, p: number): Stroke[] {
  const e = ease(p)
  switch (style) {
    case 'zoom':
      return [
        { layer: 'old', alpha: 1, scale: 1 + 0.45 * e, shift: 0 },
        { layer: 'new', alpha: e, scale: 0.82 + 0.18 * e, shift: 0 },
      ]
    case 'slide':
      return [
        { layer: 'old', alpha: 1, scale: 1, shift: -0.3 * e },
        { layer: 'new', alpha: 1, scale: 1, shift: 1 - e },
      ]
    default:
      return [
        { layer: 'old', alpha: 1, scale: 1, shift: 0 },
        { layer: 'new', alpha: e, scale: 1, shift: 0 },
      ]
  }
}

/** Morph: how much of each visual's light (added together) - as much light all the way through, each as
 * bright as the other half way. */
export function weights(p: number): { old: number; new: number } {
  const e = ease(p)
  return { old: Math.cos((e * Math.PI) / 2), new: Math.sin((e * Math.PI) / 2) }
}

/** The swirl over a soft change: how strongly the frame before shows again - nothing at the ends, most half
 * way (morph and zoom swirl more). */
export function swirlAt(style: FadeStyle, p: number): number {
  if (style === 'cut' || style === 'flash' || p <= 0 || p >= 1) return 0
  const peak = style === 'blend' ? 0.5 : style === 'zoom' ? 0.4 : 0.28
  return peak * Math.sin(Math.PI * Math.min(1, Math.max(0, p)))
}

/** A soft cloud of ``width`` x ``height`` values 0..1: three octaves of smooth random lattices (blots of
 * several sizes). */
export function noiseField(width: number, height: number, random: () => number = Math.random): Float32Array {
  const out = new Float32Array(width * height)
  let total = 0
  for (const [cells, weight] of [[3, 0.55], [7, 0.3], [15, 0.15]] as const) {
    const gw = cells + 1
    const gh = Math.max(2, Math.round((cells * height) / width) + 1)
    const lattice = Float32Array.from({ length: gw * gh }, random)
    for (let y = 0; y < height; y++) {
      const fy = (y / Math.max(1, height - 1)) * (gh - 1)
      const y0 = Math.min(gh - 2, Math.floor(fy))
      const ty = ease(fy - y0)
      for (let x = 0; x < width; x++) {
        const fx = (x / Math.max(1, width - 1)) * (gw - 1)
        const x0 = Math.min(gw - 2, Math.floor(fx))
        const tx = ease(fx - x0)
        const a = lattice[y0 * gw + x0] + (lattice[y0 * gw + x0 + 1] - lattice[y0 * gw + x0]) * tx
        const b = lattice[(y0 + 1) * gw + x0] + (lattice[(y0 + 1) * gw + x0 + 1] - lattice[(y0 + 1) * gw + x0]) * tx
        out[y * width + x] += weight * (a + (b - a) * ty)
      }
    }
    total += weight
  }
  // spread to the whole range, so that the change starts and ends within its time
  let low = Infinity
  let high = -Infinity
  for (const v of out) {
    low = Math.min(low, v)
    high = Math.max(high, v)
  }
  for (let i = 0; i < out.length; i++) out[i] = high > low ? (out[i] - low) / (high - low) : out[i] / total
  return out
}

/** Melt: how much of the new visual shows where the cloud is ``n`` at ``p`` - low places first, a soft edge. */
export function meltAt(n: number, p: number, soft = 0.14): number {
  return smoothstep(n - soft, n + soft, p * (1 + 2 * soft) - soft)
}

// --- the mixer --------------------------------------------------------------------------------------------

interface Layer {
  preset: Preset
  scene: Scene
  canvas: HTMLCanvasElement
}

const canvasOf = (old?: HTMLCanvasElement | null): HTMLCanvasElement => old ?? document.createElement('canvas')

function sized(canvas: HTMLCanvasElement, w: number, h: number): CanvasRenderingContext2D | null {
  if (canvas.width !== w || canvas.height !== h) {
    canvas.width = w
    canvas.height = h
  }
  return canvas.getContext('2d')
}

const MELT_WIDTH = 64

export class SceneMixer {
  private now: Layer | null = null
  private old: Layer | null = null
  private fade: Fade = DEFAULT_FADE
  /** The kind of the change under way (``random`` resolved). */
  private style: FadeStyle = DEFAULT_FADE.style
  private lastRandom: FadeStyle | null = null
  /** When the change began (the visual's clock; -1: at its first frame), and when a flash went off. */
  private started = -1
  private flashed = -1
  /** The mixed picture and the one before (the swirl), a scratch layer, the melt's cloud and mask. */
  private mixes: [HTMLCanvasElement | null, HTMLCanvasElement | null] = [null, null]
  private scratch: HTMLCanvasElement | null = null
  private cloud: { width: number; height: number; field: Float32Array; phase: Float32Array } | null = null
  private mask: HTMLCanvasElement | null = null
  private turn = 1

  /** ``make``: a new scene of a preset (Drop presets with the renderer they should draw with). */
  constructor(
    private readonly make: (preset: Preset) => Scene,
    private readonly random: () => number = Math.random
  ) {}

  get preset(): Preset | null {
    return this.now?.preset ?? null
  }

  /** Let the pictures go (a video's or a preview's mixer when it is done). */
  dispose(): void {
    for (const canvas of [...this.mixes, this.scratch, this.mask]) {
      if (canvas) canvas.width = canvas.height = 0
    }
    this.mixes = [null, null]
    this.scratch = this.mask = null
    this.cloud = null
    this.now = this.old = null
  }

  /** Whether a change is under way. */
  get changing(): boolean {
    return this.old !== null
  }

  /** The kind of the change under way (or the last one). */
  get kind(): FadeStyle {
    return this.style
  }

  /** Change to ``preset`` (``again``: the same one anew - its file was saved). */
  use(preset: Preset, fade: Fade, again = false): void {
    if (this.now?.preset.id === preset.id && !again) return
    const scene = this.make(preset)
    const before = this.now
    const glide = before?.preset.kind === 'drop' && preset.kind === 'drop'
    if (!before || glide || again || fade.style === 'cut') {
      // the first visual, a cut - or Drop to Drop, which the renderer glides by itself on the same layer
      this.now = { preset, scene, canvas: canvasOf(before?.canvas) }
      if (!glide) this.old = null
      return
    }
    // a change while one is under way: the newer one leaves, what was leaving goes
    this.old = before
    this.now = { preset, scene, canvas: canvasOf() }
    this.fade = fade
    this.style = fade.style === 'random' ? this.pickRandom() : fade.style
    this.started = -1
    this.flashed = -1
    this.cloud = null
    this.turn = -this.turn
  }

  private pickRandom(): FadeStyle {
    const choices = ORGANIC.filter((s) => s !== this.lastRandom)
    const pick = choices[Math.floor(this.random() * choices.length) % choices.length]
    this.lastRandom = pick
    return pick
  }

  /** One frame: the visual(s) on their layers, mixed onto ``ctx``. */
  draw(ctx: CanvasRenderingContext2D, frame: Frame, w: number, h: number, colors: Colors): void {
    if (!this.now) return
    const clock = frame.time
    if (this.old && this.started < 0) this.started = clock
    if (this.old && this.style === 'flash') {
      // the old one plays on to the next beat (or for two seconds), then the new one in a glow
      if (frame.beat || clock - this.started >= BEAT_WAIT) {
        this.old = null
        this.flashed = clock
      } else {
        this.paint(this.old, frame, w, h, colors)
        ctx.drawImage(this.old.canvas, 0, 0, w, h)
        return
      }
    }
    this.paint(this.now, frame, w, h, colors)
    const p = this.old ? (clock - this.started) / Math.max(0.05, this.fade.seconds) : 1
    if (!this.old || p >= 1) {
      this.old = null
      this.mixes = [null, null]
      ctx.drawImage(this.now.canvas, 0, 0, w, h)
      this.glow(ctx, clock, w, h)
      return
    }
    this.paint(this.old, frame, w, h, colors)
    // the mix on a canvas of its own, so that the next frame can swirl it
    const [current, before] = this.mixes
    const target = canvasOf(current)
    const m = sized(target, w, h)
    if (!m) return
    m.save()
    m.globalCompositeOperation = 'source-over'
    m.globalAlpha = 1
    if (this.style === 'blend') this.morph(m, p, w, h)
    else if (this.style === 'melt') this.melt(m, p, w, h, clock)
    else this.layered(m, p, w, h)
    const swirl = swirlAt(this.style, p)
    if (before && swirl > 0) {
      // the frame before, a little larger and turned, over it: the two flow into each other
      m.globalCompositeOperation = 'screen'
      m.globalAlpha = swirl
      m.translate(w / 2, h / 2)
      m.rotate(this.turn * (this.style === 'blend' ? 0.022 : 0.012))
      const grow = this.style === 'zoom' ? 1.06 : 1.035
      m.scale(grow, grow)
      m.drawImage(before, -w / 2, -h / 2, w, h)
    }
    m.restore()
    ctx.drawImage(target, 0, 0, w, h)
    this.mixes = [before ?? null, target]
  }

  /** Fade, zoom, slide: the layers one over the other (a slide behind a soft edge). */
  private layered(m: CanvasRenderingContext2D, p: number, w: number, h: number): void {
    for (const stroke of strokes(this.style, p)) {
      const source = stroke.layer === 'old' ? this.old!.canvas : this.now!.canvas
      const sw = w * stroke.scale
      const sh = h * stroke.scale
      const x = (w - sw) / 2 + stroke.shift * w
      const y = (h - sh) / 2
      if (this.style === 'slide' && stroke.layer === 'new') {
        // the incoming edge fades over a sixth of the width
        const s = sized((this.scratch = canvasOf(this.scratch)), w, h)
        if (!s) continue
        s.save()
        s.globalCompositeOperation = 'source-over'
        s.clearRect(0, 0, w, h)
        s.drawImage(source, x, y, sw, sh)
        s.globalCompositeOperation = 'destination-in'
        const edge = s.createLinearGradient(x, 0, x + w / 6, 0)
        edge.addColorStop(0, 'rgba(0,0,0,0)')
        edge.addColorStop(1, 'rgba(0,0,0,1)')
        s.fillStyle = edge
        s.fillRect(0, 0, w, h)
        s.restore()
        m.globalAlpha = 1
        m.drawImage(this.scratch, 0, 0, w, h)
        continue
      }
      m.globalAlpha = stroke.alpha
      m.drawImage(source, x, y, sw, sh)
    }
    m.globalAlpha = 1
  }

  /** Morph: both visuals' light added - each fading as the other comes - over black. */
  private morph(m: CanvasRenderingContext2D, p: number, w: number, h: number): void {
    const weight = weights(p)
    m.fillStyle = '#000'
    m.fillRect(0, 0, w, h)
    m.globalCompositeOperation = 'lighter'
    m.globalAlpha = weight.old
    m.drawImage(this.old!.canvas, 0, 0, w, h)
    m.globalAlpha = weight.new
    m.drawImage(this.now!.canvas, 0, 0, w, h)
    m.globalCompositeOperation = 'source-over'
    m.globalAlpha = 1
  }

  /** Melt: the new visual through a soft mask of drifting blots, over the old one. */
  private melt(m: CanvasRenderingContext2D, p: number, w: number, h: number, clock: number): void {
    const gw = MELT_WIDTH
    const gh = Math.max(2, Math.round((MELT_WIDTH * h) / w))
    if (!this.cloud || this.cloud.width !== gw || this.cloud.height !== gh) {
      this.cloud = { width: gw, height: gh, field: noiseField(gw, gh, this.random), phase: Float32Array.from({ length: gw * gh }, () => this.random() * Math.PI * 2) }
    }
    const maskCanvas = (this.mask = canvasOf(this.mask))
    const k = sized(maskCanvas, gw, gh)
    const s = sized((this.scratch = canvasOf(this.scratch)), w, h)
    if (!k || !s) return this.layered(m, p, w, h)
    const image = k.createImageData(gw, gh)
    const { field, phase } = this.cloud
    for (let i = 0; i < field.length; i++) {
      // the blots drift a little while they grow
      const n = field[i] * 0.86 + 0.07 + 0.07 * Math.sin(clock * 0.9 + phase[i])
      image.data[i * 4] = image.data[i * 4 + 1] = image.data[i * 4 + 2] = 255
      image.data[i * 4 + 3] = Math.round(meltAt(n, p) * 255)
    }
    k.putImageData(image, 0, 0)
    s.save()
    s.globalCompositeOperation = 'source-over'
    s.clearRect(0, 0, w, h)
    s.drawImage(this.now!.canvas, 0, 0, w, h)
    s.globalCompositeOperation = 'destination-in'
    s.imageSmoothingEnabled = true
    s.drawImage(maskCanvas, 0, 0, w, h)
    s.restore()
    m.drawImage(this.old!.canvas, 0, 0, w, h)
    m.drawImage(this.scratch, 0, 0, w, h)
  }

  /** A layer's scene drawn on its own canvas (it keeps its picture from frame to frame: trails, feedback). */
  private paint(target: Layer, frame: Frame, w: number, h: number, colors: Colors): void {
    const ctx = sized(target.canvas, w, h)
    if (!ctx) return
    ctx.save()
    target.scene.draw(ctx, frame, w, h, colors)
    ctx.restore()
  }

  /** After a flash: a soft white glow over the new visual, fading. */
  private glow(ctx: CanvasRenderingContext2D, clock: number, w: number, h: number): void {
    if (this.flashed < 0) return
    const q = (clock - this.flashed) / Math.min(2, Math.max(0.3, this.fade.seconds / 2))
    if (q >= 1) {
      this.flashed = -1
      return
    }
    ctx.save()
    ctx.globalCompositeOperation = 'screen'
    ctx.globalAlpha = 0.85 * (1 - ease(q))
    ctx.fillStyle = '#fff'
    ctx.fillRect(0, 0, w, h)
    ctx.restore()
  }
}
