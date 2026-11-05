/**
 * Time in a song: which lyrics line is sung, how far it is painted, and where the song is in its score.
 * Pure functions on the song's timed lines (measured by listening when it was exported, plenio.core.subtitles).
 */
import type { Section, TimedLine } from './api'

export function formatTime(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) return '0:00'
  const whole = Math.floor(seconds)
  return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, '0')}`
}

/** ``1 song``, ``3 songs``. */
export const countOf = (n: number, one: string, many = `${one}s`): string => `${n} ${n === 1 ? one : many}`

/** The index of the line sung at ``t`` (the last line that started, while it lasts or until the next one
 * starts), or -1 before the first. */
export function lineAt(lines: TimedLine[], t: number): number {
  let low = 0
  let high = lines.length - 1
  let found = -1
  while (low <= high) {
    const mid = (low + high) >> 1
    if (lines[mid].start <= t) {
      found = mid
      low = mid + 1
    } else high = mid - 1
  }
  return found
}

/** Whether line ``index`` is still on at ``t`` (it ended and the next has not begun: a gap). */
export function lineOn(lines: TimedLine[], index: number, t: number): boolean {
  return index >= 0 && t <= lines[index].end + 0.15
}

export interface Chunk {
  text: string
  /** 0..1: how much of the chunk is sung at the moment. */
  fill: number
}

/**
 * The line in chunks - one per syllable (or word) as it is sung - each with how much of it is painted at
 * ``t``: a chunk fills from its start to the next chunk's start (the last one by the line's end), so the
 * colour runs through the line like a karaoke wipe.
 */
export function chunksAt(line: TimedLine, t: number): Chunk[] {
  const units = line.units.length ? line.units : [[line.start, line.text.length]]
  const chunks: Chunk[] = []
  let from = 0
  for (let k = 0; k < units.length; k++) {
    const [start, cut] = units[k]
    const next = k + 1 < units.length ? units[k + 1][0] : Math.max(line.end, start + 0.3)
    const span = Math.max(0.05, Math.min(next - start, 1.6))
    const fill = t <= start ? 0 : Math.min(1, (t - start) / span)
    const end = Math.max(from, Math.min(line.text.length, Math.round(cut)))
    if (end > from) chunks.push({ text: line.text.slice(from, end), fill })
    from = end
  }
  if (from < line.text.length) chunks.push({ text: line.text.slice(from), fill: t >= line.end ? 1 : 0 })
  return chunks
}

/** The ``(audio, score)`` time pairs of a song's sung syllables, in order (both rising). */
export function anchorsOf(lines: TimedLine[]): [number, number][] {
  const pairs: [number, number][] = []
  for (const line of lines) {
    for (const unit of line.units) {
      if (unit.length >= 3 && Number.isFinite(unit[2])) {
        const pair: [number, number] = [unit[0], unit[2]]
        const last = pairs[pairs.length - 1]
        if (!last || (pair[0] > last[0] && pair[1] > last[1])) pairs.push(pair)
      }
    }
  }
  return pairs
}

/** The song's ``(audio, score)`` pairs, both rising: the score's path through the music the player found
 * (plenio/player/align.py) - it follows the instrumental parts, where sung syllables are few and uncertain
 * (owner's report 2026-10-23) - else the measured syllables. */
export function songAnchors(lines: TimedLine[], notation?: { anchors?: [number, number][] } | null): [number, number][] {
  if (!notation?.anchors?.length) return anchorsOf(lines)
  const pairs: [number, number][] = []
  for (const [t, s] of notation.anchors) {
    const last = pairs[pairs.length - 1]
    if (!last || (t > last[0] && s > last[1])) pairs.push([t, s])
  }
  return pairs
}

/**
 * Song time -> score time: between two sung syllables by interpolation, outside them along the warp
 * (``t_audio = a * t_score + b``, measured for the whole song) - or 1:1 when nothing is known.
 */
export function audioToScore(t: number, anchors: [number, number][], warp?: [number, number] | null): number {
  const a = warp?.[0] ?? 1
  const b = warp?.[1] ?? 0
  if (!anchors.length) return (t - b) / a
  if (t <= anchors[0][0]) return anchors[0][1] - (anchors[0][0] - t) / a
  const last = anchors[anchors.length - 1]
  if (t >= last[0]) return last[1] + (t - last[0]) / a
  let low = 0
  let high = anchors.length - 1
  while (high - low > 1) {
    const mid = (low + high) >> 1
    if (anchors[mid][0] <= t) low = mid
    else high = mid
  }
  const [t0, s0] = anchors[low]
  const [t1, s1] = anchors[high]
  return s0 + ((t - t0) / (t1 - t0)) * (s1 - s0)
}

/** Score time -> song time (the inverse of ``audioToScore``). */
export function scoreToAudio(s: number, anchors: [number, number][], warp?: [number, number] | null): number {
  const a = warp?.[0] ?? 1
  const b = warp?.[1] ?? 0
  if (!anchors.length) return a * s + b
  if (s <= anchors[0][1]) return anchors[0][0] - (anchors[0][1] - s) * a
  const last = anchors[anchors.length - 1]
  if (s >= last[1]) return last[0] + (s - last[1]) * a
  let low = 0
  let high = anchors.length - 1
  while (high - low > 1) {
    const mid = (low + high) >> 1
    if (anchors[mid][1] <= s) low = mid
    else high = mid
  }
  const [t0, s0] = anchors[low]
  const [t1, s1] = anchors[high]
  return t0 + ((s - s0) / (s1 - s0)) * (t1 - t0)
}

export interface TimedSection extends Section {
  /** Where the section starts in the song (seconds). */
  at: number
}

/** The score's sections on the song's time line. */
export function sectionsInSong(sections: Section[] | undefined, anchors: [number, number][], warp?: [number, number] | null, duration = Infinity): TimedSection[] {
  return (sections ?? [])
    .map((section) => ({ ...section, at: Math.max(0, scoreToAudio(section.start, anchors, warp)) }))
    .filter((section) => section.at < duration)
}

export function sectionAt(sections: TimedSection[], t: number): TimedSection | null {
  let found: TimedSection | null = null
  for (const section of sections) if (section.at <= t + 0.05) found = section
  return found
}

/** Pretty section names: "chorus 2" -> "Chorus 2". */
export function sectionName(label: string): string {
  return label.replace(/[-_]/g, ' ').replace(/^\w/, (c) => c.toUpperCase())
}
