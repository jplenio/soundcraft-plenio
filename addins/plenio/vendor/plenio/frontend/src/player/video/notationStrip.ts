/**
 * The notation in a video: the score drawn once by abcjs (as on the song's page), turned into a picture, and
 * for every frame the line of music sounding then, shown in a strip with a cursor at the notes that sound
 * and those notes aglow. The song's time becomes score time through the measured syllables, as on the page.
 */
import abcjs from 'abcjs'

import type { Notation, TimedLine } from '../api'
import { audioToScore, songAnchors } from '../timing'

interface Box {
  x: number
  y: number
  w: number
  h: number
}

interface Moment {
  ms: number
  line: number
  bar: number
  notes: Box[]
}

export class NotationStrip {
  private image: HTMLImageElement | null = null
  private moments: Moment[] = []
  private systems = new Map<number, Box>()
  private width = 0
  private height = 0
  private anchors: [number, number][]
  private warp: [number, number] | null | undefined

  private constructor(
    private readonly notation: Notation,
    lines: TimedLine[]
  ) {
    this.anchors = songAnchors(lines, notation)
    this.warp = notation.warp
  }

  /** The strip for a score, laid out ``width`` pixels wide (``null``: no notation, or it cannot be drawn). */
  static async create(notation: Notation, lines: TimedLine[], width: number): Promise<NotationStrip | null> {
    if (!notation.abc) return null
    const strip = new NotationStrip(notation, lines)
    try {
      await strip.layout(width)
    } catch (error) {
      console.warn('notation for the video:', error)
      return null
    }
    return strip.moments.length ? strip : null
  }

  private async layout(width: number): Promise<void> {
    const host = document.createElement('div')
    host.style.cssText = `position:fixed;left:-20000px;top:0;width:${width}px;background:transparent`
    document.body.appendChild(host)
    try {
      const tunes = abcjs.renderAbc(host, this.notation.abc ?? '', {
        add_classes: true,
        foregroundColor: '#f4f2fa',
        staffwidth: Math.max(520, width - 40),
        wrap: { minSpacing: 1.8, maxSpacing: 2.7, preferredMeasuresPerLine: 4 },
      })
      const svg = host.querySelector('svg')
      if (!svg) return
      const base = svg.getBoundingClientRect()
      this.width = base.width
      this.height = base.height
      const box = (el: Element): Box => {
        const r = el.getBoundingClientRect()
        return { x: r.left - base.left, y: r.top - base.top, w: r.width, h: r.height }
      }
      // each line of music (both staves): its staff lines' extent
      for (const staff of svg.querySelectorAll('.abcjs-staff')) {
        const line = lineOf(staff)
        if (line < 0) continue
        const b = box(staff)
        const known = this.systems.get(line)
        if (!known) this.systems.set(line, b)
        else {
          const top = Math.min(known.y, b.y)
          const bottom = Math.max(known.y + known.h, b.y + b.h)
          this.systems.set(line, { x: Math.min(known.x, b.x), y: top, w: Math.max(known.w, b.w), h: bottom - top })
        }
      }
      const timer = new abcjs.TimingCallbacks(tunes[0], { qpm: this.notation.tempo ?? 100 })
      const events = timer.noteTimings.filter((e) => e.type === 'event' && e.elements?.length)
      const byMs = new Map<number, Moment>()
      for (const event of events) {
        const elements = (event.elements ?? []).flat() as Element[]
        const notes = elements.filter((el) => el.classList.contains('abcjs-note'))
        const line = lineOf(elements[0])
        const ms = Math.round(event.milliseconds)
        const moment = byMs.get(ms) ?? { ms, line, bar: barOf(elements[0]), notes: [] }
        for (const note of notes) {
          // the note heads and stems, without the lyrics under them and the chord above
          const parts = [...note.children].filter((c) => c.tagName.toLowerCase() !== 'text')
          for (const part of parts.length ? parts : [note]) moment.notes.push(box(part))
        }
        byMs.set(ms, moment)
      }
      this.moments = [...byMs.values()].sort((a, b) => a.ms - b.ms)
      // the picture of the whole score
      const copy = svg.cloneNode(true) as SVGSVGElement
      copy.setAttribute('xmlns', 'http://www.w3.org/2000/svg')
      copy.setAttribute('width', String(this.width))
      copy.setAttribute('height', String(this.height))
      const text = new XMLSerializer().serializeToString(copy)
      const url = URL.createObjectURL(new Blob([text], { type: 'image/svg+xml' }))
      try {
        this.image = await new Promise<HTMLImageElement>((resolve, reject) => {
          const img = new Image()
          img.onload = () => resolve(img)
          img.onerror = () => reject(new Error('the score could not be drawn as a picture'))
          img.src = url
        })
      } finally {
        URL.revokeObjectURL(url)
      }
    } finally {
      host.remove()
    }
  }

  /** The strip at ``t`` seconds into the song, into the rectangle (a dark glass panel behind it); ``shift``:
   * seconds the listener moved the notes for this song. */
  draw(ctx: CanvasRenderingContext2D, t: number, x: number, y: number, w: number, h: number, accent: string, shift = 0): void {
    if (!this.image) return
    const ms = (audioToScore(t, this.anchors, this.warp) + shift) * 1000
    let low = 0
    let high = this.moments.length - 1
    let found = -1
    while (low <= high) {
      const mid = (low + high) >> 1
      if (this.moments[mid].ms <= ms + 1) {
        found = mid
        low = mid + 1
      } else high = mid - 1
    }
    const moment = this.moments[Math.max(0, found)]
    const system = this.systems.get(moment.line)
    if (!system) return
    ctx.save()
    ctx.fillStyle = 'rgba(8, 6, 16, 0.62)'
    roundRect(ctx, x, y, w, h, Math.min(18, h * 0.08))
    ctx.fill()
    // the line of music, scaled to fit the strip with a little room above (chords) and below (lyrics)
    const top = Math.max(0, system.y - 30)
    const bottom = Math.min(this.height, system.y + system.h + 46)
    const sourceH = bottom - top
    const scale = Math.min((w - 24) / this.width, (h - 16) / sourceH)
    const drawW = this.width * scale
    const ox = x + (w - drawW) / 2
    const oy = y + (h - sourceH * scale) / 2
    ctx.drawImage(this.image, 0, top, this.width, sourceH, ox, oy, drawW, sourceH * scale)
    // the cursor points at notes (as on the song's page): where only rests sound, at the bar's next note
    let pointed = moment
    if (!moment.notes.length) {
      for (let k = found + 1; k < this.moments.length && this.moments[k].bar === moment.bar; k++) {
        if (this.moments[k].notes.length) {
          pointed = this.moments[k]
          break
        }
      }
    }
    if (found >= 0 && pointed.notes.length) {
      // the notes sounding aglow, and the cursor at them
      ctx.globalCompositeOperation = 'lighter'
      ctx.fillStyle = accent
      ctx.globalAlpha = 0.45
      for (const note of moment.notes) {
        const cx = ox + (note.x + note.w / 2) * scale
        const cy = oy + (note.y + note.h / 2 - top) * scale
        const r = Math.max(6, Math.max(note.w, Math.min(note.h, 14)) * scale * 0.9)
        const glow = ctx.createRadialGradient(cx, cy, 0, cx, cy, r)
        glow.addColorStop(0, accent)
        glow.addColorStop(1, 'rgba(0,0,0,0)')
        ctx.fillStyle = glow
        ctx.fillRect(cx - r, cy - r, r * 2, r * 2)
      }
      ctx.globalCompositeOperation = 'source-over'
      ctx.globalAlpha = 0.85
      const first = pointed.notes[0]
      const cx = ox + (first.x + first.w / 2) * scale
      ctx.fillStyle = accent
      ctx.fillRect(cx - 1.5, oy + (system.y - top - 14) * scale, 3, (system.h + 28) * scale)
    }
    ctx.restore()
  }
}

function barOf(el: Element | undefined): number {
  const mark = el ? [...el.classList].find((c) => /^abcjs-mm\d+$/.test(c)) : undefined
  return mark ? Number(mark.slice('abcjs-mm'.length)) : -1
}

function lineOf(el: Element | undefined): number {
  const mark = el ? [...el.classList].find((c) => /^abcjs-l\d+$/.test(c)) : undefined
  return mark ? Number(mark.slice('abcjs-l'.length)) : -1
}

function roundRect(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, r: number): void {
  ctx.beginPath()
  ctx.moveTo(x + r, y)
  ctx.arcTo(x + w, y, x + w, y + h, r)
  ctx.arcTo(x + w, y + h, x, y + h, r)
  ctx.arcTo(x, y + h, x, y, r)
  ctx.arcTo(x, y, x + w, y, r)
  ctx.closePath()
}
