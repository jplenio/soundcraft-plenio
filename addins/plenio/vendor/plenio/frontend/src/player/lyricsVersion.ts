/**
 * Which lyrics the player follows (owner's requests 2026-10-23): the lyrics **as written** - the song's lyrics,
 * timed by listening - or **as sung** - what the take really sings, as the lyrics ASR heard it when the song was
 * exported (``core.subtitles.time_sung``). A music model does not always sing what it was given: it repeats a
 * line, makes one up, leaves one out. Every song shows its lyrics as written, and as sung only where the listener
 * chooses it (owner's request 2026-10-30) - for a song, like master and original (the choice is kept for that
 * song), or in Settings for every song; never by itself: the ASR does not always hear the word sung (a rare word, a
 * name), and unasked its words would puzzle. The notation always follows the score: only the written syllables
 * have a note.
 */
import type { SongDetail, SungLyrics, TimedLine } from './api'

export type LyricsVersion = 'written' | 'sung'
/** The listener's rule for every song: as written unless they choose as sung. */
export type LyricsChoice = LyricsVersion

export const LYRICS_VERSIONS: { id: LyricsVersion; label: string; title: string }[] = [
  { id: 'written', label: 'As written', title: "The song's lyrics, at the times they are sung" },
  { id: 'sung', label: 'As sung', title: 'What the take really sings, as heard when the song was exported' }
]

export const LYRICS_CHOICES: { id: LyricsChoice; label: string; title: string }[] = [
  { id: 'written', label: 'As written', title: "Every song's lyrics as written (a song's own choice aside)" },
  { id: 'sung', label: 'As sung', title: "Every song as its take sings it, where the song was exported with that (a song's own choice aside)" }
]

export function versionOf(raw: unknown): LyricsVersion {
  return raw === 'sung' ? 'sung' : 'written'
}

/** The rule kept: as sung only where it was chosen so - anything else, the *Auto* of before 1.4.1 too, as written. */
export function choiceOf(raw: unknown): LyricsChoice {
  return raw === 'sung' ? 'sung' : 'written'
}

/** The listener's choices for single songs, as kept (anything else is dropped). */
export function choicesOf(raw: unknown): Record<string, LyricsVersion> {
  const out: Record<string, LyricsVersion> = {}
  if (raw && typeof raw === 'object') {
    for (const [id, v] of Object.entries(raw as Record<string, unknown>)) if (v === 'sung' || v === 'written') out[id] = v
  }
  return out
}

/** What the take sings, when the song was exported with it (songs exported before have none). */
export function sungOf(detail: SongDetail | null | undefined): SungLyrics | null {
  const sung = detail?.sung
  return sung && Array.isArray(sung.lines) && sung.lines.length ? (sung as SungLyrics) : null
}

export interface LyricsPrefs {
  lyricsChoice: LyricsChoice
  lyricsFor: Record<string, LyricsVersion>
}

/** The version a song follows by the rule alone (``choice``): written for a song without what its take sings. */
export function ruleFor(detail: SongDetail | null | undefined, choice: LyricsChoice): LyricsVersion {
  return sungOf(detail) ? choice : 'written'
}

/** The version a song follows: the listener's choice for it, else the rule. */
export function versionFor(detail: SongDetail | null | undefined, prefs: LyricsPrefs): LyricsVersion {
  if (!sungOf(detail)) return 'written'
  return (detail && prefs.lyricsFor[detail.id]) || ruleFor(detail, prefs.lyricsChoice)
}

/** Keeps the listener's choice for a song - only where it differs from the rule. */
export function chooseFor(detail: SongDetail, version: LyricsVersion, prefs: LyricsPrefs): void {
  if (version === ruleFor(detail, prefs.lyricsChoice)) delete prefs.lyricsFor[detail.id]
  else prefs.lyricsFor[detail.id] = version
}

/** The lines to follow: the sung ones when chosen and there, else the written ones. */
export function linesFor(detail: SongDetail | null | undefined, version: LyricsVersion): TimedLine[] {
  const sung = version === 'sung' ? sungOf(detail) : null
  return sung ? sung.lines : detail?.lines ?? []
}

/** How far the take follows its lyrics, in a sentence. */
export function sungNote(sung: SungLyrics): string {
  const parts: string[] = []
  if (typeof sung.written_heard === 'number') parts.push(`sings ${Math.round(sung.written_heard * 100)} % of its lyrics' words as written`)
  if (typeof sung.extra_words === 'number' && sung.extra_words > 0) parts.push(`${sung.extra_words} word${sung.extra_words === 1 ? '' : 's'} they do not have`)
  const missing = sung.not_sung.length
  if (missing) parts.push(`${missing} line${missing === 1 ? '' : 's'} not heard`)
  const fixed = sung.corrected ?? []
  const said = parts.length ? `This take ${parts.join(', ')}.` : ''
  if (!fixed.length) return said
  const words = fixed.slice(0, 4).map((c) => `“${c.heard}” → “${c.word}”`).join(', ')
  return `${said} ${fixed.length} misheard word${fixed.length === 1 ? '' : 's'} corrected by the writer model: ${words}${fixed.length > 4 ? ' …' : ''}.`.trim()
}

/** The lyrics sections the take did not sing as written (fewer than 40 % of their words heard). */
export function sectionsNotSung(sung: SungLyrics): string[] {
  return sung.sections.filter((s) => s.words >= 4 && s.heard < 0.4 * s.words).map((s) => s.tag)
}
