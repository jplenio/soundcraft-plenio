/** Songs alike: shared genre and mood words, tempo, key, language, model and brief template. */
import type { SongSummary } from './api'
import { words } from './search'

function overlap(a: string[], b: string[]): number {
  if (!a.length || !b.length) return 0
  const set = new Set(a)
  const shared = b.filter((w) => set.has(w)).length
  return shared / Math.max(a.length, b.length)
}

const tokens = (text: string): string[] => words(text).flatMap((w) => w.split(/\s+/)).filter((w) => w.length > 2)

export function similarity(a: SongSummary, b: SongSummary): number {
  if (a.id === b.id) return 0
  let total = 3 * overlap(tokens(a.genre), tokens(b.genre)) + 2 * overlap(tokens(a.mood), tokens(b.mood))
  if (a.bpm && b.bpm) total += Math.max(0, 1 - Math.abs(a.bpm - b.bpm) / 40)
  if (a.score_key && a.score_key === b.score_key) total += 0.5
  if (a.language && a.language === b.language) total += 0.5
  if (a.instrumental === b.instrumental) total += 0.5
  if (a.template && a.template === b.template) total += 1
  if (a.model && a.model === b.model) total += 0.3
  return total
}

export function similarSongs(song: SongSummary, songs: SongSummary[], limit = 8): SongSummary[] {
  return songs
    .filter((s) => s.id !== song.id && s.takes_key !== song.takes_key)
    .map((s) => [s, similarity(song, s)] as const)
    .filter(([, value]) => value > 0.8)
    .sort((x, y) => y[1] - x[1])
    .slice(0, limit)
    .map(([s]) => s)
}

/** The other takes of a song: the same title, lyrics and score, rendered again. */
export function takesOf(song: SongSummary, songs: SongSummary[]): SongSummary[] {
  if (!song.takes_key) return []
  return songs.filter((s) => s.takes_key === song.takes_key && s.id !== song.id)
}
