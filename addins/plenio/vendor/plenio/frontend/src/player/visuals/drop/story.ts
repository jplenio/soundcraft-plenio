/**
 * The song for Plenio Drop's pictures (owner's request 2026-10-18: text and the cover in the visual): its cover,
 * its title, the line sung now and the word sung now as pictures the presets' sprites draw into the feedback,
 * and where the song is (seconds into it, whether a line is sung and since when) for their formulas. The player's
 * visual and a song's video feed their renderer with it every frame; a picture is uploaded only when it changes.
 */
import type { TimedLine } from '../../api'
import { chunksAt, lineAt } from '../../timing'
import type { DropRenderer, Sprite } from './renderer'

const FONT = '"Segoe UI", "Inter", system-ui, -apple-system, sans-serif'
const pictures = new Map<string, HTMLCanvasElement>()

/** Text as a picture: white with a soft glow, on nothing, 128 pixels high - kept for the texts used last. */
export function textPicture(text: string, weight = 800): HTMLCanvasElement {
  const key = `${weight}|${text}`
  const known = pictures.get(key)
  if (known) return known
  const size = 96
  const canvas = document.createElement('canvas')
  const ctx = canvas.getContext('2d')
  if (!ctx) return canvas
  ctx.font = `${weight} ${size}px ${FONT}`
  const width = Math.min(4096, Math.ceil(ctx.measureText(text).width) + size)
  canvas.width = Math.max(2, width)
  canvas.height = 128
  ctx.font = `${weight} ${size}px ${FONT}`
  ctx.textAlign = 'center'
  ctx.textBaseline = 'middle'
  ctx.shadowColor = 'rgba(255, 255, 255, 0.9)'
  ctx.shadowBlur = 18
  ctx.fillStyle = '#ffffff'
  ctx.fillText(text, canvas.width / 2, 68)
  if (pictures.size > 40) pictures.delete(pictures.keys().next().value as string)
  pictures.set(key, canvas)
  return canvas
}

/** The words of ``line`` sung by ``t`` - the last one is the word sung now. */
export function wordsSung(line: TimedLine, t: number): string[] {
  const reached = chunksAt(line, t)
    .filter((c) => c.fill > 0)
    .map((c) => c.text)
    .join('')
  return reached.trim() ? reached.trim().split(/\s+/) : []
}

export interface SongStory {
  id: string
  title: string
  cover: HTMLImageElement | null
  lines: TimedLine[]
}

/** The song at ``t`` seconds for the renderer: its pictures and where it is. */
export function tellRenderer(renderer: DropRenderer, song: SongStory | null, t: number): void {
  if (!song) {
    renderer.story.songTime = t
    renderer.story.lineOn = 0
    return
  }
  const i = lineAt(song.lines, t)
  const line = i >= 0 ? song.lines[i] : null
  const on = !!line && t <= line.end + 0.3
  renderer.story.songTime = t
  renderer.story.lineOn = on ? 1 : 0
  renderer.story.lineAge = line ? Math.max(0, t - line.start) : 0
  if (song.cover && song.cover.naturalWidth) renderer.setSource('cover', song.cover, `cover/${song.id}`, song.cover.naturalWidth / song.cover.naturalHeight)
  else renderer.setSource('cover', null, '', 1)
  const title = textPicture(song.title)
  renderer.setSource('title', title, `title/${song.title}`, title.width / title.height)
  if (on && line) {
    const text = textPicture(line.text, 700)
    renderer.setSource('line', text, `line/${line.text}`, text.width / text.height)
    const word = wordsSung(line, t).pop() ?? ''
    if (word) {
      const picture = textPicture(word)
      renderer.setSource('word', picture, `word/${word}`, picture.width / picture.height)
    }
  }
}

/** A video's choice of the song in any Drop visual: the title at the start, the line sung, the cover - drawn
 * into the feedback, so they melt and swirl with it. Laid over, not added: a visual that zooms or keeps its
 * picture long would add a picture drawn every frame up into a white streak. */
export function storySprites(into: { title: boolean; lyrics: boolean; cover: boolean }, elapsed: number, pulse: number, lineOn: number): Sprite[] {
  const out: Sprite[] = []
  const base = { x: 0, angle: 0, hue: 0, tint: 0 }
  if (into.cover) out.push({ ...base, source: 'cover', y: 0, size: 0.17 + 0.03 * pulse, alpha: 0.32, additive: 0 })
  if (into.title) {
    const alpha = Math.min(1, elapsed / 0.8) * Math.max(0, 1 - elapsed / 8)
    if (alpha > 0) out.push({ ...base, source: 'title', y: 0.08, size: 0.11, alpha: alpha * 0.4, tint: 0.25, additive: 0 })
  }
  if (into.lyrics && lineOn) out.push({ ...base, source: 'line', y: -0.5, size: 0.065, alpha: 0.3, tint: 0.35, additive: 0 })
  return out
}
