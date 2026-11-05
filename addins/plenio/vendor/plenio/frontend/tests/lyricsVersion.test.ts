/**
 * Which lyrics to follow (owner's requests 2026-10-23): as written, or as the take sings them - as sung only where
 * the listener chooses it (owner's request 2026-10-30), switched per song like master and original.
 */
import { describe, expect, it } from 'vitest'

import type { SongDetail, SungLyrics, TimedLine } from '../src/player/api'
import { choiceOf, choicesOf, chooseFor, type LyricsPrefs, linesFor, ruleFor, sectionsNotSung, sungNote, sungOf, versionFor, versionOf } from '../src/player/lyricsVersion'
import { settings } from '../src/player/store'
import { videoWithDefaults } from '../src/player/video/make'

const written: TimedLine[] = [{ text: 'Walking down the river side', start: 1, end: 3, units: [[1, 7, 0.5]] }]
const sung: SungLyrics = {
  lines: [
    { text: 'Walking down the riverside', start: 1, end: 3, units: [[1, 7]] },
    { text: 'oh baby baby', start: 7, end: 8.3, units: [[7, 2]] },
  ],
  text: '[Verse]\nWalking down the riverside\noh baby baby',
  written_heard: 0.667,
  extra_words: 3,
  not_sung: ['to the light we made'],
  sections: [
    { tag: 'Verse', words: 9, heard: 8 },
    { tag: 'Chorus', words: 9, heard: 2 },
  ],
}
const detail = (extra: Partial<SongDetail>): SongDetail => ({ id: 'a', lines: written, ...extra }) as SongDetail

describe('lyricsVersion', () => {
  it('follows the sung lines when chosen and there, else the written ones', () => {
    expect(linesFor(detail({ sung }), 'sung')).toBe(sung.lines)
    expect(linesFor(detail({ sung }), 'written')).toBe(written)
    // a song exported before: its written lines, whatever was chosen
    expect(linesFor(detail({ sung: {} }), 'sung')).toBe(written)
    expect(linesFor(detail({}), 'sung')).toBe(written)
    expect(sungOf(detail({ sung: {} }))).toBeNull()
    expect(linesFor(null, 'sung')).toEqual([])
  })

  it('says how far the take follows its lyrics', () => {
    expect(sungNote(sung)).toBe("This take sings 67 % of its lyrics' words as written, 3 words they do not have, 1 line not heard.")
    // the words the writer model found misheard (Check Sung Words)
    expect(sungNote({ ...sung, corrected: [{ line: 1, heard: 'doun', word: 'down' }] })).toContain('1 misheard word corrected by the writer model: “doun” → “down”.')
    expect(sectionsNotSung(sung)).toEqual(['Chorus'])
    expect(sungNote({ ...sung, written_heard: 1, extra_words: 0, not_sung: [] })).toBe("This take sings 100 % of its lyrics' words as written.")
  })

  it('keeps a saved choice and the video starts with the player’s', () => {
    expect(versionOf('sung')).toBe('sung')
    expect(versionOf('other')).toBe('written')
    expect(videoWithDefaults({}, null, 'sung').lyricsVersion).toBe('sung')
    expect(videoWithDefaults({ lyricsVersion: 'written' }, null, 'sung').lyricsVersion).toBe('written')
    expect(videoWithDefaults(null).lyricsVersion).toBe('written')
  })

  it('shows every song as written, as sung only where the listener chooses it (owner’s request 2026-10-30)', () => {
    // even a take far from its lyrics: 'Take a Chance On Me' (owner's covers, 2026-10-23) sang 58 % of the words as
    // written, 189 of 490 its own - what the ASR heard of it is not always the word sung
    const far = { ...sung, written_heard: 0.58, extra_words: 7 }
    expect(settings.lyricsChoice).toBe('written')
    const prefs: LyricsPrefs = { lyricsChoice: choiceOf(undefined), lyricsFor: {} }
    expect(versionFor(detail({ sung: far }), prefs)).toBe('written')
    expect(versionFor(detail({ sung }), prefs)).toBe('written')
    // the rule of before, Auto, is as written now; as sung stays where it was chosen
    expect(choiceOf('auto')).toBe('written')
    expect(choiceOf('sung')).toBe('sung')
    expect(versionFor(detail({ sung: far }), { lyricsChoice: 'written', lyricsFor: { a: 'sung' } })).toBe('sung')
    expect(versionFor(detail({ sung }), { lyricsChoice: 'sung', lyricsFor: {} })).toBe('sung')
    expect(versionFor(detail({}), { lyricsChoice: 'sung', lyricsFor: { a: 'sung' } })).toBe('written') // nothing sung kept
    expect(ruleFor(detail({ sung }), 'sung')).toBe('sung')
    expect(ruleFor(detail({}), 'sung')).toBe('written')
  })

  it('keeps the listener’s choice for a song only where it differs from the rule', () => {
    const prefs: LyricsPrefs = { lyricsChoice: 'written', lyricsFor: {} }
    const song = detail({ sung })
    chooseFor(song, 'sung', prefs)
    expect(prefs.lyricsFor).toEqual({ a: 'sung' })
    expect(versionFor(song, prefs)).toBe('sung')
    chooseFor(song, 'written', prefs) // the rule's own: nothing to keep
    expect(prefs.lyricsFor).toEqual({})
    expect(versionFor(song, prefs)).toBe('written')
    expect(choiceOf('written')).toBe('written')
    expect(choiceOf(undefined)).toBe('written')
    expect(choicesOf({ a: 'sung', b: 'loud', c: 3 })).toEqual({ a: 'sung' })
  })
})
