/**
 * Two pages saving at once (owner's request 2026-10-18: the player from the network - a phone and this computer,
 * or two tabs - open together): the player's server counts the changes, and a page that saved from an old one
 * is told so with what is saved now. It then merges three states - the one it started from (``base``), its own
 * (``mine``) and the saved one (``theirs``): what only one side changed is taken from that side, a playlist both
 * changed keeps this page's, favourites and tags take both sides' additions and removals, plays add up.
 */
import type { PlayerState, Playlist } from './api'

const same = (a: unknown, b: unknown): boolean => JSON.stringify(a) === JSON.stringify(b)

/** A value both sides may have changed: the side that changed it - this page's when both did. */
function pick<T>(base: T | undefined, mine: T | undefined, theirs: T | undefined): T | undefined {
  if (same(mine, base)) return theirs
  return mine
}

/** A list used as a set: the saved one, with this page's additions (first) and without its removals. */
export function mergeSet(base: string[] = [], mine: string[] = [], theirs: string[] = []): string[] {
  const added = mine.filter((x) => !base.includes(x) && !theirs.includes(x))
  const removed = new Set(base.filter((x) => !mine.includes(x)))
  return [...added, ...theirs.filter((x) => !removed.has(x))]
}

function mergePlaylists(base: Playlist[], mine: Playlist[], theirs: Playlist[]): Playlist[] {
  const byId = (list: Playlist[]) => new Map(list.map((p) => [p.id, p]))
  const b = byId(base)
  const m = byId(mine)
  const t = byId(theirs)
  const out: Playlist[] = []
  const decide = (id: string): Playlist | undefined => {
    const [pb, pm, pt] = [b.get(id), m.get(id), t.get(id)]
    if (!pm && !pt) return undefined
    if (!pm) return pb && same(pt, pb) ? undefined : pt // removed here (unless changed there since)
    if (!pt) return pb && same(pm, pb) ? undefined : pm // removed there (unless changed here since)
    return pick(pb, pm, pt)
  }
  // the saved order, then the playlists new on this page
  for (const p of theirs) {
    const kept = decide(p.id)
    if (kept) out.push(kept)
  }
  for (const p of mine) {
    if (t.has(p.id)) continue
    const kept = decide(p.id)
    if (kept) out.push(kept)
  }
  return out
}

function mergeRecord<T>(base: Record<string, T>, mine: Record<string, T>, theirs: Record<string, T>, each: (b: T | undefined, m: T | undefined, t: T | undefined) => T | undefined): Record<string, T> {
  const out: Record<string, T> = {}
  for (const key of new Set([...Object.keys(theirs), ...Object.keys(mine), ...Object.keys(base)])) {
    const value = each(base[key], mine[key], theirs[key])
    if (value !== undefined) out[key] = value
  }
  return out
}

export function mergeState(base: PlayerState, mine: PlayerState, theirs: PlayerState): PlayerState {
  return {
    playlists: mergePlaylists(base.playlists ?? [], mine.playlists ?? [], theirs.playlists ?? []),
    favorites: mergeSet(base.favorites, mine.favorites, theirs.favorites),
    // plays add up: the saved count and what this page counted since
    plays: mergeRecord(base.plays ?? {}, mine.plays ?? {}, theirs.plays ?? {}, (b, m, t) => {
      const total = (t ?? 0) + Math.max(0, (m ?? 0) - (b ?? 0))
      return total > 0 ? total : undefined
    }),
    last_played: mergeRecord(base.last_played ?? {}, mine.last_played ?? {}, theirs.last_played ?? {}, (_b, m, t) => (m && (!t || m > t) ? m : t)),
    tags: mergeRecord(base.tags ?? {}, mine.tags ?? {}, theirs.tags ?? {}, (b, m, t) => {
      const list = mergeSet(b, m, t)
      return list.length ? list : undefined
    }),
    // each setting: the side that changed it (this page's view, volume, where it stopped ... stay its own)
    settings: mergeRecord(base.settings ?? {}, mine.settings ?? {}, theirs.settings ?? {}, pick),
    // each song's stars: the side that gave them (this page's when both did)
    ratings: mergeRecord(base.ratings ?? {}, mine.ratings ?? {}, theirs.ratings ?? {}, pick),
  }
}
