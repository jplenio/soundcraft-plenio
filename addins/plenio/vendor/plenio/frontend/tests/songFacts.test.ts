import { describe, expect, it } from 'vitest'

import type { SongSummary } from '../src/player/api'
import { OPEN, songFacts } from '../src/player/songFacts'

function song(over: Partial<SongSummary>): SongSummary {
  return {
    id: 'a',
    title: 'River',
    created: '2026-10-01T10:00:00',
    year: '2026',
    seconds: 182,
    model: 'YuE2',
    kind: 'song',
    brief: {},
    genre: '',
    mood: '',
    language: '',
    vocals: 'sung',
    instrumental: false,
    arrangement: 'off',
    template: '',
    style: '',
    lyrics: '',
    loudness: { lufs: -14, true_peak: -1, range: 6 },
    tags: {},
    plenio: '1.0.0',
    folder: '',
    file: 'a',
    takes_key: '',
    has: { audio: true, original: false, cover: false, pdf: false, lines: false, notes: false, stems: false, timing: false, score: true },
    seeds: {},
    writer: 'gemma-4-e4b',
    ...over,
  }
}

const row = (facts: ReturnType<typeof songFacts>, label: string) => facts.find((f) => f.label === label)

describe('the song page shows every field of the brief', () => {
  // owner's request 2026-10-17: also the arrangement, genre, mood … - left empty with the default, marked
  it('marks defaults, the template and what the writer chose', () => {
    const facts = songFacts(
      song({
        genre: 'indie pop',
        bpm: 112,
        score_key: 'G',
        score_meter: '4/4',
        brief: {
          kind: 'song',
          mode: 'new song every run',
          genre: 'indie pop',
          mood: 'warm',
          tempo: '',
          length: 'standard (about 3:00)',
          vocals: 'sung',
          arrangement: 'off',
          closeness: 70,
          lines_under_singing: false,
          sources: { mode: 'default', genre: 'typed', mood: 'template', tempo: 'default', key: 'default', length: 'default', vocals: 'default', arrangement: 'default', closeness: 'default', lines_under_singing: 'default', template: 'default' },
        },
      })
    )
    expect(row(facts, 'Genre')).toEqual({ label: 'Genre', value: 'indie pop', note: '' })
    expect(row(facts, 'Mood')?.note).toBe('from the template')
    expect(row(facts, 'Arrangement')).toEqual({ label: 'Arrangement', value: 'off', note: 'default' })
    expect(row(facts, 'Genre closeness')).toEqual({ label: 'Genre closeness', value: '70', note: 'default' })
    expect(row(facts, 'Tempo')).toEqual({ label: 'Tempo', value: '112 BPM', note: 'default - the writer chose' })
    expect(row(facts, 'Voice')).toEqual({ label: 'Voice', value: OPEN, note: 'default' })
    expect(row(facts, 'Template')).toEqual({ label: 'Template', value: 'none', note: 'default' })
    expect(row(facts, 'Lines under the singing')?.value).toBe('off')
    expect(row(facts, 'Length')?.value).toBe('3:02')
    expect(row(facts, 'Melody')).toBeUndefined() // sung
  })

  it('a cover has its own fields, an instrumental its melody', () => {
    const cover = songFacts(song({ kind: 'cover', brief: { kind: 'cover', vocals: 'new lyrics', language: 'English', harmony: 'new accompaniment', arrangement: 'dramatic', closeness: 40, lyrics_closeness: 0, sources: { language: 'default', harmony: 'default', arrangement: 'typed', closeness: 'typed', lyrics_closeness: 'default' } } }))
    expect(row(cover, 'Song flow closeness')).toEqual({ label: 'Song flow closeness', value: '40', note: '' })
    expect(row(cover, 'Lyrics closeness')?.note).toBe('default')
    expect(row(cover, 'Harmony')?.note).toBe('default')
    expect(row(cover, 'Target length')).toBeUndefined()
    const instrumental = songFacts(song({ instrumental: true, brief: { kind: 'song', vocals: 'instrumental', melody: 'instrument plays the lead', sources: { melody: 'default' } } }))
    expect(row(instrumental, 'Melody')?.note).toBe('default')
    expect(row(instrumental, 'Lead instrument')?.value).toBe(OPEN)
    expect(row(instrumental, 'Voice')).toBeUndefined()
  })

  it('a recording and other music show only what they have', () => {
    const other = songFacts(song({ other: true, kind: 'other', model: '', writer: '', artist: 'Someone', genre: 'jazz' }))
    expect(other.map((f) => f.label)).toEqual(['Genre', 'Length', 'Artist', 'Year', 'Kind'])
  })
})
