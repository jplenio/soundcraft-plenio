/** Live Play's settings and where a new song goes (live.ts plays it; this part imports nothing). */

export type Insert = 'next' | 'end' | 'random'

export interface LiveSettings {
  /** Live Play is on (kept, so a page opened again goes on). */
  on: boolean
  /** Where a new song goes. */
  insert: Insert
  /** New songs from ComfyUI join by themselves. */
  auto: boolean
  /** At the end: from the top again, or wait for the next new song. */
  atEnd: 'again' | 'wait'
  /** The guests' way in (QR code, address) also over the visual on the whole screen, in which corner, how large
   * (owner's request 2026-10-18). */
  overVisual: boolean
  wayInCorner: WayInCorner
  wayInSize: 's' | 'm' | 'l'
}

export type WayInCorner = 'top-right' | 'top-left' | 'bottom-right' | 'bottom-left'
export const WAY_IN_CORNERS: WayInCorner[] = ['top-right', 'top-left', 'bottom-right', 'bottom-left']
/** The QR code's side in the corner, by size. */
export const WAY_IN_SIDES = { s: 104, m: 170, l: 250 } as const

export const DEFAULT_LIVE: LiveSettings = { on: false, insert: 'next', auto: true, atEnd: 'again', overVisual: true, wayInCorner: 'top-right', wayInSize: 'm' }

/** Saved live settings, checked (a file edited by hand or an older version may hold anything). */
export function liveWithDefaults(raw: unknown): LiveSettings {
  const given = (raw && typeof raw === 'object' ? raw : {}) as Partial<LiveSettings>
  const out = { ...DEFAULT_LIVE, ...given }
  if (!['next', 'end', 'random'].includes(out.insert)) out.insert = 'next'
  if (!['again', 'wait'].includes(out.atEnd)) out.atEnd = 'again'
  out.on = !!out.on
  out.auto = out.auto !== false
  out.overVisual = out.overVisual !== false
  if (!WAY_IN_CORNERS.includes(out.wayInCorner)) out.wayInCorner = 'top-right'
  if (!['s', 'm', 'l'].includes(out.wayInSize)) out.wayInSize = 'm'
  return out
}

/** Where the ``k``-th of the new songs that arrived together goes in a queue of ``length`` where the song at
 * ``now`` plays: next (in the order they came), at the end, or anywhere after the song that plays. */
export function insertAt(insert: Insert, now: number, length: number, k: number, random: () => number = Math.random): number {
  if (now < 0) return length
  if (insert === 'next') return Math.min(length, now + 1 + k)
  if (insert === 'end') return length
  const first = now + 1
  return first + Math.floor(random() * (length - first + 1))
}
