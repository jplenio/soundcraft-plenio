/** Two pages saving at once (owner's request 2026-10-18: the player on a phone from the network and on this
 * computer together): what each side changed is kept. */
import { describe, expect, it } from 'vitest'

import type { PlayerState, Playlist } from '../src/player/api'
import { mergeSet, mergeState } from '../src/player/stateMerge'

const list = (id: string, songs: string[], name = id): Playlist => ({ id, name, songs, created: '2026-10-18' })
const state = (over: Partial<PlayerState>): PlayerState => ({ playlists: [], favorites: [], plays: {}, last_played: {}, tags: {}, settings: {}, ratings: {}, ...over })

describe('merging two pages’ changes', () => {
  it('keeps both sides’ favourites added and taken out', () => {
    expect(mergeSet(['a', 'b'], ['x', 'a', 'b'], ['a', 'b', 'y'])).toEqual(['x', 'a', 'b', 'y'])
    expect(mergeSet(['a', 'b'], ['b'], ['a', 'b', 'y'])).toEqual(['b', 'y'])
    expect(mergeSet(['a'], ['a'], [])).toEqual([])
  })

  it('takes a playlist from the side that changed it, new ones from both, and gone where one removed it', () => {
    const base = state({ playlists: [list('p1', ['a']), list('p2', ['b']), list('p3', ['c'])] })
    const mine = state({ playlists: [list('p1', ['a', 'z']), list('p2', ['b']), list('mine', ['m'])] }) // p3 removed here
    const theirs = state({ playlists: [list('p1', ['a']), list('p2', ['b'], 'Renamed'), list('p3', ['c']), list('theirs', ['t'])] })
    const merged = mergeState(base, mine, theirs).playlists
    expect(merged.map((p) => p.id)).toEqual(['p1', 'p2', 'theirs', 'mine'])
    expect(merged[0].songs).toEqual(['a', 'z'])
    expect(merged[1].name).toBe('Renamed')
  })

  it('adds up the plays counted on each side, and keeps the later last play', () => {
    const merged = mergeState(
      state({ plays: { a: 3 }, last_played: { a: '2026-10-18T10:00' } }),
      state({ plays: { a: 4, b: 1 }, last_played: { a: '2026-10-18T11:00', b: '2026-10-18T11:30' } }),
      state({ plays: { a: 5 }, last_played: { a: '2026-10-18T12:00' } })
    )
    expect(merged.plays).toEqual({ a: 6, b: 1 })
    expect(merged.last_played).toEqual({ a: '2026-10-18T12:00', b: '2026-10-18T11:30' })
  })

  it('keeps each side’s tags and each setting from the side that changed it', () => {
    const merged = mergeState(
      state({ tags: { s1: ['party'] }, settings: { volume: 0.5, sort: 'newest', view: 'grid' } }),
      state({ tags: { s1: ['party', 'road'], s2: ['calm'] }, settings: { volume: 0.9, sort: 'newest', view: 'grid' } }),
      state({ tags: { s1: [] }, settings: { volume: 0.5, sort: 'title', view: 'grid' } })
    )
    // party was taken off there, road given here
    expect(merged.tags).toEqual({ s1: ['road'], s2: ['calm'] })
    expect(merged.settings).toEqual({ volume: 0.9, sort: 'title', view: 'grid' })
  })

  it('changes nothing when only the other side changed', () => {
    const base = state({ favorites: ['a'], settings: { volume: 0.5 } })
    const theirs = state({ favorites: ['b', 'a'], playlists: [list('p', ['x'])], settings: { volume: 0.2 } })
    expect(mergeState(base, base, theirs)).toEqual(theirs)
  })
})
