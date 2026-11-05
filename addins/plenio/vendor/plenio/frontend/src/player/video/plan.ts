/**
 * The video's visual plan (owner's request 2026-10-25): one visual all the way, a new one at every section, or a
 * new one every so many seconds - and for each section or span of seconds the visual chosen, or one at random.
 * The random ones come from a seed, so that the preview, the timeline and the video show the same; sections of one
 * name (every chorus) can share their visual. Pure: the dialog and the video use it alike.
 */
import type { TimedSection } from '../timing'

export type ChangeMode = 'never' | 'section' | 'interval'
export type RandomFrom = 'pool' | 'all' | 'match'

export interface Slot {
  index: number
  /** Where it starts and ends, in song seconds. */
  start: number
  end: number
  /** ``Chorus 2``, ``0:20 - 0:40``. */
  label: string
  /** What sections of one kind share: ``chorus`` (the section's name without its number). */
  kind: string
}

const pretty = (s: number): string => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}`

/** ``Chorus 2`` -> ``chorus``; ``Verse`` -> ``verse``. */
export function sectionKind(label: string): string {
  return label
    .replace(/\d+/g, '')
    .replace(/[^\p{L} ]/gu, ' ')
    .trim()
    .toLowerCase()
    .replace(/\s+/g, ' ')
}

/** The plan's slots for the part of the song from ``start`` for ``length`` seconds. ``name``: a section's label as
 * shown (``[chorus]`` -> ``Chorus``). */
export function slotsOf(
  change: ChangeMode,
  interval: number,
  sections: TimedSection[],
  start: number,
  length: number,
  name: (label: string) => string = (label) => label
): Slot[] {
  const end = start + Math.max(0, length)
  if (change === 'never' || length <= 0) return [{ index: 0, start, end, label: 'The whole video', kind: 'all' }]
  if (change === 'interval') {
    const step = Math.max(3, interval)
    const out: Slot[] = []
    for (let at = start, k = 0; at < end - 0.25 && k < 400; at += step, k++) {
      const to = Math.min(end, at + step)
      out.push({ index: k, start: at, end: to, label: `${pretty(at)} - ${pretty(to)}`, kind: `span ${k}` })
    }
    return out
  }
  // each section from where it starts in the song (``at``) to where the next starts
  const spans = sections.map((s, k) => ({ label: s.label, from: s.at, to: k + 1 < sections.length ? sections[k + 1].at : Infinity }))
  const inside = spans.filter((s) => s.to > start + 0.25 && s.from < end - 0.25)
  if (!inside.length) return [{ index: 0, start, end, label: 'The whole video', kind: 'all' }]
  return inside.map((s, k) => {
    const label = name(s.label)
    return {
      index: k,
      start: k === 0 ? start : Math.max(start, s.from),
      end: k === inside.length - 1 ? end : Math.min(end, s.to),
      label,
      kind: sectionKind(label) || `section ${k}`,
    }
  })
}

/** The slot at song time ``t`` (``-1``: before the first). */
export function slotAt(slots: Slot[], t: number): number {
  let found = -1
  for (const slot of slots) if (t >= slot.start - 1e-6) found = slot.index
  return found
}

/** Numbers from a seed, the same for the same seed (mulberry32). */
export function seeded(seed: number): () => number {
  let a = seed >>> 0
  return () => {
    a = (a + 0x6d2b79f5) >>> 0
    let t = a
    t = Math.imul(t ^ (t >>> 15), t | 1)
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61)
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

/** Each slot's visual: the one chosen for it - else, with ``repeats``, the one of the first slot of its kind - else
 * one at random from ``pool``, never the one just before (nor, where it can, the one chosen right after). */
export function resolvePlan(slots: Slot[], picks: string[], pool: string[], seed: number, repeats: boolean, exists: (id: string) => boolean): string[] {
  const random = seeded(seed)
  const byKind = new Map<string, string>()
  const chosen = (i: number): string => (picks[i] && exists(picks[i]) ? picks[i] : '')
  const out: string[] = []
  for (const slot of slots) {
    let id = chosen(slot.index)
    if (!id && repeats && byKind.has(slot.kind)) id = byKind.get(slot.kind) ?? ''
    if (!id) {
      const before = out[out.length - 1]
      const after = chosen(slot.index + 1)
      const choices = pool.filter((p) => exists(p))
      const fresh = choices.filter((p) => p !== before && p !== after)
      const from = fresh.length ? fresh : choices.filter((p) => p !== before)
      const list = from.length ? from : choices
      id = list.length ? list[Math.floor(random() * list.length) % list.length] : ''
    } else random() // the next random choices stay where they were when one is chosen by hand
    if (repeats && !byKind.has(slot.kind)) byKind.set(slot.kind, id)
    out.push(id)
  }
  return out
}

/** The picks after one is set: with ``repeats``, every slot of its kind takes it. */
export function setPick(slots: Slot[], picks: string[], index: number, id: string, repeats: boolean): string[] {
  const out = slots.map((_, k) => picks[k] ?? '')
  const kind = slots[index]?.kind
  for (const slot of slots) if (slot.index === index || (repeats && slot.kind === kind)) out[slot.index] = id
  return out
}
