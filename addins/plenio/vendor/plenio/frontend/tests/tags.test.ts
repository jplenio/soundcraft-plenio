/** Tags of your own and the filters (owner's request 2026-10-18): every genre of the templates among the filter
 * chips, a chip that leaves songs out, ranges for tempo and length, suggestions while typing - and tags per song,
 * given again from the list of the ones given before. */
import { beforeEach, describe, expect, it } from 'vitest'

import type { SongSummary } from '../src/player/api'
import { FACETS, chipParts, facetOf, facetValues, filterRows, matching, parseQuery, score, suggest, toggleFilterChip, valueLabel } from '../src/player/search'
import { addTag, allTags, cleanTag, deleteTag, removeTag, renameTag, settings, songTags, state, tagsOf } from '../src/player/store'

function song(over: Partial<SongSummary> & { id: string }): SongSummary {
  return {
    title: over.id, created: '2026-10-01T10:00:00', year: '2026', seconds: 180, model: 'YuE2', kind: 'song', brief: {}, genre: '', mood: '',
    language: 'English', vocals: 'female', instrumental: false, arrangement: 'off', template: '', style: '', lyrics: '',
    loudness: { lufs: -14, true_peak: -1, range: 6 }, tags: {}, plenio: '1.0.0', folder: '', file: over.id, takes_key: '',
    has: { audio: true, original: false, cover: false, pdf: false, lines: false, notes: false, stems: false, timing: false, score: false }, seeds: {}, writer: '',
    ...over,
  } // prettier-ignore
}

const SONGS = [
  song({ id: 'a', title: 'Midnight Train', genre: 'jazz, swing', bpm: 96, seconds: 150 }),
  song({ id: 'b', title: 'Neon Run', genre: 'synthwave, dance', bpm: 128, seconds: 250, has: { audio: true, original: false, cover: false, pdf: false, lines: true, notes: false, stems: false, timing: false, score: false } }),
  song({ id: 'c', title: 'Sufi Night', genre: 'qawwali, sufi devotional', bpm: 150, seconds: 400 }),
]
const context = { favorites: new Set<string>(), tags: { a: ['Party', 'road trip'], b: ['party'] }, plays: { a: 2 } }
const find = (query: string): string[] => SONGS.filter((s) => score(s, parseQuery(query), context) > 0).map((s) => s.id)

describe('the filters', () => {
  it('offer every genre, also the rare ones of a template, with how many songs have it', () => {
    const genre = FACETS.find((f) => f.id === 'genre')!
    const values = facetValues(SONGS, genre, context)
    expect(values.map(([v]) => v)).toEqual(expect.arrayContaining(['qawwali', 'sufi devotional', 'jazz', 'synthwave']))
    expect(values).toHaveLength(6)
    expect(find('genre:qawwali')).toEqual(['c'])
  })

  it('have ranges for the tempo and the length, and marks', () => {
    const tempo = FACETS.find((f) => f.id === 'bpm')!
    expect(facetValues(SONGS, tempo, context)).toEqual([['90-119', 1], ['120-139', 1], ['>=140', 1]])
    expect(find('bpm:"90-119"')).toEqual(['a'])
    expect(valueLabel(tempo, '>=140')).toBe('fast, 140 and up')
    const length = FACETS.find((f) => f.id === 'len')!
    expect(facetValues(SONGS, length, context)).toEqual([['<3', 1], ['3-5', 1], ['>5', 1]])
    expect(find('has:timing')).toEqual(['b']) // timed lyrics from subtitle files count
    expect(find('is:unplayed')).toEqual(['b', 'c'])
    expect(find('is:played')).toEqual(['a'])
    expect(find('is:untagged')).toEqual(['c'])
  })

  it('leave songs out with a chip of their own, which takes the place of the other kind', () => {
    let chips = toggleFilterChip([], 'genre', 'jazz')
    chips = toggleFilterChip(chips, 'genre', 'jazz', true)
    expect(chips).toEqual(['-genre:"jazz"'])
    expect(find(chips.join(' '))).toEqual(['b', 'c'])
    expect(chipParts(chips[0])).toEqual({ key: 'genre', value: 'jazz', exclude: true })
    expect(toggleFilterChip(chips, 'genre', 'jazz', true)).toEqual([])
    // a tempo takes several ranges; only the Plenio version is one choice at a time
    expect(toggleFilterChip(['bpm:"<90"'], 'bpm', '>=140')).toEqual(['bpm:"<90"', 'bpm:">=140"'])
    expect(toggleFilterChip(['plenio:"from 0.8.0"'], 'plenio', 'from 1.0.0')).toEqual(['plenio:"from 1.0.0"'])
    // the two rows that set is: are told apart by their values
    expect(facetOf('is', 'other')?.id).toBe('made')
    expect(facetOf('is', 'unplayed')?.id).toBe('played')
  })

  it('take several values of a row as alternatives, and every row and every chip that leaves songs out', () => {
    const ids = (chips: string[], query = ''): string[] => matching(SONGS, query, chips, context).map((s) => s.id)
    expect(ids(['genre:"jazz"', 'genre:"synthwave"'])).toEqual(['a', 'b'])
    expect(ids(['bpm:"90-119"', 'bpm:">=140"'])).toEqual(['a', 'c'])
    expect(ids(['tag:"Party"', 'tag:"road trip"'])).toEqual(['a', 'b'])
    // rows must all match, a chip that leaves songs out always does, and so does every word of the search
    expect(ids(['genre:"jazz"', 'genre:"synthwave"', 'len:"<3"'])).toEqual(['a'])
    expect(ids(['genre:"jazz"', 'genre:"synthwave"', '-tag:"road trip"'])).toEqual(['b'])
    expect(ids(['genre:"jazz"', 'genre:"synthwave"'], 'neon')).toEqual(['b'])
    // a row counts without its own chips: its other values say how many songs they add
    const genre = filterRows(SONGS, '', ['genre:"jazz"'], context).find((r) => r.id === 'genre')
    expect(genre?.all).toEqual(expect.arrayContaining([['jazz', 1], ['synthwave', 1], ['qawwali', 1]]))
    expect(genre?.total).toBe(3)
  })

  it('count the songs the filters leave: after "from 1.0.0" instrumental says how many of those are instrumental', () => {
    // owner's report 2026-10-18: the numbers were always of every song
    const made = (id: string, plenio: string, instrumental: boolean, genre: string) => song({ id, plenio, instrumental, vocals: instrumental ? 'instrumental' : 'female', genre })
    const archive = [
      made('o1', '0.8.0', true, 'ambient'), made('o2', '0.8.0', true, 'ambient'), made('o3', '0.8.1', true, 'drone'),
      made('n1', '1.0.0', true, 'jazz'), made('n2', '1.0.0', true, 'jazz'), made('n3', '1.0.0', false, 'jazz'),
    ] // prettier-ignore
    const row = (rows: ReturnType<typeof filterRows>, id: string) => rows.find((r) => r.id === id)
    const before = filterRows(archive, '', [], context)
    expect(row(before, 'vocals')?.all).toEqual([['instrumental', 5], ['sung', 1]])
    expect(row(before, 'plenio')?.all).toEqual([['from 1.0.0', 3], ['from 0.8.1', 4], ['from 0.8.0', 6]])
    const chips = toggleFilterChip([], 'plenio', 'from 1.0.0')
    const after = filterRows(archive, '', chips, context)
    expect(row(after, 'vocals')?.all).toEqual([['instrumental', 2], ['sung', 1]])
    // a genre none of the songs left has is gone; a row that cannot narrow them is left out
    expect(row(after, 'genre')).toBeUndefined()
    // the version, one choice at a time, still offers the others to switch to
    expect(row(after, 'plenio')?.all.map(([v]) => v)).toEqual(['from 1.0.0', 'from 0.8.1', 'from 0.8.0'])
    // with a search and a chip that leaves songs out
    const sung = filterRows(archive, '', [...chips, '-vocals:"instrumental"'], context)
    expect(row(sung, 'vocals')?.all).toEqual([['sung', 1], ['instrumental', 0]])
    // both ambient songs are 0.8.0: the version row could not narrow them
    expect(row(filterRows(archive, 'genre:ambient', [], context), 'plenio')).toBeUndefined()
    expect(row(filterRows(archive, 'genre:jazz', [], context), 'vocals')?.all).toEqual([['instrumental', 2], ['sung', 1]])
  })

  it('suggest fields, their values and your tags while you type', () => {
    expect(suggest('gen', SONGS, context).map((s) => s.label)).toContain('genre:')
    const genres = suggest('genre:qa', SONGS, context)
    expect(genres[0]).toMatchObject({ label: 'genre:qawwali', hint: '1 song', query: 'genre:qawwali ' })
    expect(suggest('night genre:sufi', SONGS, context)[0].query).toBe('night genre:"sufi devotional" ')
    expect(suggest('#pa', SONGS, context)[0]).toMatchObject({ label: '#Party', hint: '2 songs', query: 'tag:Party ' })
    expect(suggest('is:un', SONGS, context).map((s) => s.label)).toEqual(['is:unplayed', 'is:untagged'])
    expect(suggest('genre:qa ', SONGS, context)).toEqual([])
  })
})

describe('tags of your own', () => {
  beforeEach(() => {
    state.tags = {}
    settings.filters = { all: { query: '', chips: ['tag:"party"', 'genre:"jazz"'] } }
    settings.savedFilters = [{ id: 'f1', name: 'Parties', query: '', chips: ['-tag:"party"'] }]
  })

  it('are found by tag:, by #, and by a free word', () => {
    expect(find('tag:party')).toEqual(['a', 'b'])
    expect(find('#road')).toEqual([]) // a tag is matched whole
    expect(find('"#road trip"')).toEqual([])
    expect(find('tag:"road trip"')).toEqual(['a'])
    expect(find('road')).toEqual(['a'])
    expect(find('-#party')).toEqual(['c'])
  })

  it('are given once per song, spelled as the first time, and offered again from the list', () => {
    expect(addTag(['a', 'b'], '  Summer   2026 ')).toBe('Summer 2026')
    expect(addTag(['c'], 'summer 2026')).toBe('Summer 2026')
    addTag(['a'], 'SUMMER 2026')
    expect(songTags('a')).toEqual(['Summer 2026'])
    addTag(['a'], 'calm')
    expect(allTags.value).toEqual([['Summer 2026', 3], ['calm', 1]])
    removeTag(['a', 'b'], 'summer 2026')
    expect(state.tags).toEqual({ a: ['calm'], c: ['Summer 2026'] })
    expect(cleanTag('"#a, b"')).toBe('a b')
  })

  it('are renamed and deleted on every song, and the filters follow', () => {
    addTag(['a', 'b'], 'party')
    addTag(['b'], 'dance')
    renameTag('party', 'Dance')
    expect(state.tags).toEqual({ a: ['dance'], b: ['dance'] })
    expect(settings.filters.all.chips).toEqual(['tag:"dance"', 'genre:"jazz"'])
    expect(settings.savedFilters[0].chips).toEqual(['-tag:"dance"'])
    deleteTag('dance')
    expect(state.tags).toEqual({})
    expect(settings.filters.all.chips).toEqual(['genre:"jazz"'])
    expect(settings.savedFilters[0].chips).toEqual([])
  })

  it('are read back checked', () => {
    expect(tagsOf({ a: ['x', 'X', '', 3, 'y'], b: 'no', c: [] })).toEqual({ a: ['x', 'y'] })
    expect(tagsOf(null)).toEqual({})
  })
})

describe('the stars among the filters (owner’s request 2026-10-30)', () => {
  const rated = { ...context, ratings: { a: 4.5, b: 2 }, measured: { a: 3, c: 5, b: null } }
  const ids = (chips: string[], query = ''): string[] => matching(SONGS, query, chips, rated).map((s) => s.id)

  it('filter by your own stars and by the measured ones, each in steps, and by none', () => {
    const mine = FACETS.find((f) => f.id === 'stars')!
    expect(facetValues(SONGS, mine, rated)).toEqual([['4-4.5', 1], ['2-2.5', 1], ['none', 1]])
    expect(valueLabel(mine, 'none')).toBe('not rated yet')
    const measured = FACETS.find((f) => f.id === 'measured')!
    expect(facetValues(SONGS, measured, rated)).toEqual([['5', 1], ['3-3.5', 1], ['none', 1]])
    expect(valueLabel(measured, 'none')).toBe('not measured yet')
    expect(ids(['stars:"4-4.5"'])).toEqual(['a'])
    expect(ids(['stars:"4-4.5"', 'stars:"2-2.5"'])).toEqual(['a', 'b']) // one row: alternatives
    expect(ids(['measured:"none"'])).toEqual(['b']) // measured, without stars
    expect(ids(['stars:"4-4.5"', 'measured:"3-3.5"'])).toEqual(['a']) // two rows: both
    expect(ids(['-measured:"5"'])).toEqual(['a', 'b'])
    // typed
    expect(ids([], 'stars:>=4')).toEqual(['a'])
    expect(ids([], 'rating:none')).toEqual(['c'])
    expect(ids([], 'measured:<4')).toEqual(['a'])
    expect(suggest('stars:', SONGS, rated).length).toBeGreaterThan(0)
    // the rows show once there are stars to tell songs apart
    const rows = filterRows(SONGS, '', [], rated).map((r) => r.id)
    expect(rows).toEqual(expect.arrayContaining(['stars', 'measured']))
    expect(filterRows(SONGS, '', [], context).map((r) => r.id)).not.toContain('stars')
  })
})
