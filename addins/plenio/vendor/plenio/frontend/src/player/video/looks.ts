/**
 * More for a video's look (owner's request 2026-10-25: more settings that make videos more attractive and more
 * varied): the cover glowing through the visual from behind, slowly drifting; the picture breathing with the beat;
 * a vignette; film grain; cinema bars; the section's name as it begins; a fade in from black and out to black; and
 * an end card with the song. Each a small drawing step on the video's canvas.
 */
import type { TitleInfo } from './overlay'

const FONT = '"Segoe UI", "Inter", system-ui, -apple-system, sans-serif'

export interface Look {
  /** The cover behind the visual: 0 off ... 1 strong. */
  backdrop: number
  /** The picture breathes with the beat: 0 off ... 1 strong. */
  zoom: number
  vignette: boolean
  /** Film grain: 0 off ... 1 strong. */
  grain: number
  /** Cinema bars (2.39:1) on a wide video. */
  bars: boolean
  /** In from black at the start, out to black at the end. */
  fades: boolean
  /** The section's name for a moment when it begins. */
  sections: boolean
  /** The song again at the end: cover, title, who made it. */
  endCard: boolean
  /** Another colour scheme at every change of the visual. */
  cycleColors: boolean
  /** How strongly the visuals react to the music: 0.5 ... 2. */
  reactivity: number
}

export const DEFAULT_LOOK: Look = {
  backdrop: 0,
  zoom: 0,
  vignette: false,
  grain: 0,
  bars: false,
  fades: true,
  sections: false,
  endCard: false,
  cycleColors: false,
  reactivity: 1,
}

const clamp = (x: number, low: number, high: number): number => Math.min(high, Math.max(low, Number.isFinite(x) ? x : low))

export function lookWithDefaults(raw: unknown): Look {
  const given = (raw && typeof raw === 'object' ? raw : {}) as Partial<Look>
  return {
    backdrop: clamp(Number(given.backdrop ?? 0), 0, 1),
    zoom: clamp(Number(given.zoom ?? 0), 0, 1),
    vignette: !!given.vignette,
    grain: clamp(Number(given.grain ?? 0), 0, 1),
    bars: !!given.bars,
    fades: given.fades !== false,
    sections: !!given.sections,
    endCard: !!given.endCard,
    cycleColors: !!given.cycleColors,
    reactivity: clamp(Number(given.reactivity ?? 1), 0.5, 2),
  }
}

/** How long the end card shows at the end of a video of ``length`` seconds: six seconds, a fifth of a short one. */
export function endCardSeconds(length: number): number {
  return Math.min(6, Math.max(2.5, length * 0.2))
}

/** Cached pictures the looks draw again every frame. */
export class LookCache {
  private blurred: HTMLCanvasElement | null = null
  private noise: HTMLCanvasElement | null = null
  private copy: HTMLCanvasElement | null = null
  private vignetteKey = ''
  private vignetteGradient: CanvasGradient | null = null

  /** The cover small and blurred (scaled up it blurs more, for nothing). */
  backdropOf(image: HTMLImageElement): HTMLCanvasElement {
    if (!this.blurred) {
      const canvas = document.createElement('canvas')
      canvas.width = 96
      canvas.height = 96
      const ctx = canvas.getContext('2d') as CanvasRenderingContext2D
      ctx.filter = 'blur(6px)'
      ctx.drawImage(image, -8, -8, 112, 112)
      this.blurred = canvas
    }
    return this.blurred
  }

  noiseTile(): HTMLCanvasElement {
    if (!this.noise) {
      const canvas = document.createElement('canvas')
      canvas.width = 192
      canvas.height = 192
      const ctx = canvas.getContext('2d') as CanvasRenderingContext2D
      const data = ctx.createImageData(192, 192)
      for (let i = 0; i < data.data.length; i += 4) {
        const v = Math.floor(Math.random() * 256)
        data.data[i] = v
        data.data[i + 1] = v
        data.data[i + 2] = v
        data.data[i + 3] = 255
      }
      ctx.putImageData(data, 0, 0)
      this.noise = canvas
    }
    return this.noise
  }

  scratch(w: number, h: number): HTMLCanvasElement {
    if (!this.copy || this.copy.width !== w || this.copy.height !== h) {
      this.copy = document.createElement('canvas')
      this.copy.width = w
      this.copy.height = h
    }
    return this.copy
  }

  vignette(ctx: CanvasRenderingContext2D, w: number, h: number): CanvasGradient {
    const key = `${w}x${h}`
    if (!this.vignetteGradient || this.vignetteKey !== key) {
      const r = Math.hypot(w, h) / 2
      const gradient = ctx.createRadialGradient(w / 2, h / 2, r * 0.45, w / 2, h / 2, r)
      gradient.addColorStop(0, 'rgba(0, 0, 0, 0)')
      gradient.addColorStop(1, 'rgba(0, 0, 0, 0.62)')
      this.vignetteGradient = gradient
      this.vignetteKey = key
    }
    return this.vignetteGradient
  }
}

/** The cover glowing through the visual: blurred, slowly drifting and zooming (it lights the dark of the visual,
 * the visual's light stays). */
export function drawBackdrop(ctx: CanvasRenderingContext2D, cache: LookCache, image: HTMLImageElement, amount: number, elapsed: number, w: number, h: number, pulse: number): void {
  if (amount <= 0) return
  const picture = cache.backdropOf(image)
  const side = Math.max(w, h) * (1.25 + 0.06 * Math.sin(elapsed / 9) + 0.02 * pulse)
  const x = w / 2 - side / 2 + Math.sin(elapsed / 13) * w * 0.05
  const y = h / 2 - side / 2 + Math.cos(elapsed / 17) * h * 0.05
  ctx.save()
  ctx.globalCompositeOperation = 'screen'
  ctx.globalAlpha = 0.25 + 0.75 * amount
  ctx.drawImage(picture, x, y, side, side)
  ctx.restore()
}

/** The picture breathes with the beat: a little larger on each beat, back between them. */
export function drawBeatZoom(ctx: CanvasRenderingContext2D, cache: LookCache, amount: number, pulse: number, w: number, h: number): void {
  if (amount <= 0 || pulse <= 0.01) return
  const scale = 1 + 0.075 * amount * pulse
  const copy = cache.scratch(w, h)
  const c = copy.getContext('2d') as CanvasRenderingContext2D
  c.drawImage(ctx.canvas, 0, 0)
  const sw = w * scale
  const sh = h * scale
  ctx.drawImage(copy, (w - sw) / 2, (h - sh) / 2, sw, sh)
}

export function drawVignette(ctx: CanvasRenderingContext2D, cache: LookCache, w: number, h: number): void {
  ctx.save()
  ctx.fillStyle = cache.vignette(ctx, w, h)
  ctx.fillRect(0, 0, w, h)
  ctx.restore()
}

export function drawGrain(ctx: CanvasRenderingContext2D, cache: LookCache, amount: number, w: number, h: number): void {
  if (amount <= 0) return
  const tile = cache.noiseTile()
  const pattern = ctx.createPattern(tile, 'repeat')
  if (!pattern) return
  // a new grain every frame: the pattern moved by a random amount
  pattern.setTransform(new DOMMatrix().translate(Math.random() * 192, Math.random() * 192).scale(Math.max(1, Math.min(w, h) / 1080)))
  ctx.save()
  ctx.globalCompositeOperation = 'overlay'
  ctx.globalAlpha = 0.08 + 0.3 * amount
  ctx.fillStyle = pattern
  ctx.fillRect(0, 0, w, h)
  ctx.restore()
}

/** The height of each cinema bar at 2.39:1 (``0``: the video is not wide enough for bars). */
export function barHeight(w: number, h: number): number {
  if (w < h * 1.3) return 0
  return Math.max(0, Math.round((h - w / 2.39) / 2))
}

export function drawBars(ctx: CanvasRenderingContext2D, w: number, h: number): void {
  const bar = barHeight(w, h)
  if (!bar) return
  ctx.save()
  ctx.fillStyle = '#000'
  ctx.fillRect(0, 0, w, bar)
  ctx.fillRect(0, h - bar, w, bar)
  ctx.restore()
}

/** The section's name as it begins: in for a moment, then away (``age``: seconds since it began). */
export function drawSectionName(ctx: CanvasRenderingContext2D, name: string, age: number, accent: string, w: number, h: number, top: number): void {
  const shown = 2.6
  if (age < 0 || age > shown || !name) return
  const alpha = Math.min(1, age / 0.35, (shown - age) / 0.6)
  const unit = Math.min(w, h)
  const size = Math.round(unit * 0.034)
  const x = Math.round(unit * 0.05)
  const y = top + Math.round(unit * 0.05) - (1 - Math.min(1, age / 0.35)) * size * 0.6
  ctx.save()
  ctx.globalAlpha = alpha
  ctx.font = `800 ${size}px ${FONT}`
  ctx.textBaseline = 'top'
  ctx.shadowColor = 'rgba(0, 0, 0, 0.7)'
  ctx.shadowBlur = size * 0.4
  const text = name.toUpperCase().split('').join(' ')
  ctx.fillStyle = '#fff'
  ctx.fillText(text, x, y)
  const width = ctx.measureText(text).width
  ctx.shadowBlur = 0
  ctx.fillStyle = accent
  ctx.fillRect(x, y + size * 1.25, width * Math.min(1, age / 0.6), Math.max(2, Math.round(size * 0.12)))
  ctx.restore()
}

/** The song again at the end: the picture darker, the cover, the title, who made it (``left``: seconds to the end,
 * ``shown``: how long the card shows). */
export function drawEndCard(ctx: CanvasRenderingContext2D, info: TitleInfo, byline: string, left: number, shown: number, w: number, h: number): void {
  if (left > shown || left < 0) return
  const into = shown - left
  const alpha = Math.min(1, into / 0.9)
  const unit = Math.min(w, h)
  ctx.save()
  ctx.globalAlpha = alpha * 0.6
  ctx.fillStyle = '#000'
  ctx.fillRect(0, 0, w, h)
  ctx.globalAlpha = alpha
  const cover = info.image ? Math.round(unit * 0.3) : 0
  const titleSize = Math.round(unit * 0.062)
  const subSize = Math.round(unit * 0.03)
  let y = h / 2 - (cover + titleSize * 1.4 + subSize * 3.4) / 2 + (1 - alpha) * unit * 0.02
  ctx.shadowColor = 'rgba(0, 0, 0, 0.7)'
  ctx.shadowBlur = titleSize * 0.3
  if (cover && info.image) {
    ctx.drawImage(info.image, w / 2 - cover / 2, y, cover, cover)
    y += cover + unit * 0.035
  }
  ctx.textAlign = 'center'
  ctx.textBaseline = 'top'
  ctx.fillStyle = '#fff'
  ctx.font = `800 ${titleSize}px ${FONT}`
  ctx.fillText(info.title, w / 2, y, w * 0.9)
  ctx.font = `600 ${subSize}px ${FONT}`
  ctx.fillStyle = info.accent
  if (byline) ctx.fillText(byline, w / 2, y + titleSize * 1.3, w * 0.9)
  ctx.fillStyle = 'rgba(255, 255, 255, 0.7)'
  ctx.font = `500 ${Math.round(subSize * 0.8)}px ${FONT}`
  ctx.fillText('made with Plenio', w / 2, y + titleSize * 1.3 + subSize * 1.7, w * 0.9)
  ctx.restore()
}

/** The whole picture faded from or to black (``alpha`` 0: as it is ... 1: black). */
export function drawBlack(ctx: CanvasRenderingContext2D, alpha: number, w: number, h: number): void {
  if (alpha <= 0) return
  ctx.save()
  ctx.globalAlpha = Math.min(1, alpha)
  ctx.fillStyle = '#000'
  ctx.fillRect(0, 0, w, h)
  ctx.restore()
}

/** How black the picture is at ``elapsed`` of a video of ``length`` seconds: in over 1.2 s, out over 2 s. */
export function fadeAt(elapsed: number, length: number): number {
  const fadeIn = Math.max(0, 1 - elapsed / 1.2)
  const fadeOut = Math.max(0, 1 - (length - elapsed) / 2)
  return Math.min(1, Math.max(fadeIn, fadeOut))
}
