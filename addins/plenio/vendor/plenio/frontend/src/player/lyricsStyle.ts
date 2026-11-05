/**
 * How the lyrics look (owner's request 2026-10-16): a font, a size, a colour for what is sung, and an effect
 * that brings each syllable in as it is sung - in the player (the lyrics, Now playing, the subtitles over the
 * visual) and in a song's video.
 *
 * The fonts are the computer's own (no download): each choice names fonts that Windows, macOS and Linux have,
 * the first one found is used; *Your own font* takes any installed font's name.
 */

export interface FontChoice {
  id: string
  label: string
  /** CSS font-family list, the first installed one is used. */
  stack: string
  weight: number
}

export const FONTS: FontChoice[] = [
  { id: 'clean', label: 'Clean', stack: '"Segoe UI", "Helvetica Neue", Inter, Roboto, Arial, system-ui, sans-serif', weight: 700 },
  { id: 'condensed', label: 'Condensed', stack: '"Bahnschrift SemiBold Condensed", "Bahnschrift Condensed", "Arial Narrow", "Roboto Condensed", "Helvetica Neue Condensed Bold", sans-serif', weight: 700 },
  { id: 'poster', label: 'Poster', stack: 'Impact, Haettenschweiler, "Arial Black", "Franklin Gothic Heavy", "Helvetica Neue", sans-serif', weight: 400 },
  { id: 'rounded', label: 'Rounded', stack: '"Arial Rounded MT Bold", "Segoe UI Variable Display", Nunito, "Varela Round", "Segoe UI", sans-serif', weight: 700 },
  { id: 'elegant', label: 'Elegant serif', stack: 'Georgia, "Palatino Linotype", "Book Antiqua", Palatino, Didot, "Times New Roman", serif', weight: 700 },
  { id: 'classic', label: 'Classic serif', stack: 'Cambria, "Times New Roman", Times, "Liberation Serif", serif', weight: 700 },
  { id: 'hand', label: 'Handwritten', stack: '"Segoe Print", "Ink Free", "Bradley Hand", "Marker Felt", "Comic Sans MS", cursive', weight: 700 },
  { id: 'script', label: 'Script', stack: '"Segoe Script", Gabriola, "Brush Script MT", "Snell Roundhand", "Apple Chancery", cursive', weight: 700 },
  { id: 'typewriter', label: 'Typewriter', stack: '"American Typewriter", "Courier New", Courier, "Liberation Mono", monospace', weight: 700 },
  { id: 'mono', label: 'Code', stack: 'Consolas, Menlo, "Cascadia Code", "DejaVu Sans Mono", monospace', weight: 700 },
  { id: 'gothic', label: 'Blackletter', stack: '"Old English Text MT", "Goudy Text MT", "UnifrakturMaguntia", Georgia, serif', weight: 400 },
]

export interface EffectChoice {
  id: string
  label: string
  blurb: string
}

export const EFFECTS: EffectChoice[] = [
  { id: 'sweep', label: 'Sweep', blurb: 'The colour runs through each syllable as it is sung' },
  { id: 'glow', label: 'Glow', blurb: 'What is sung lights up and glows' },
  { id: 'bounce', label: 'Bounce', blurb: 'Each syllable hops as it is sung' },
  { id: 'pop', label: 'Pop', blurb: 'The syllable sung swells and settles' },
  { id: 'wave', label: 'Wave', blurb: 'The letters ripple like water; the sung ones lit' },
  { id: 'typewriter', label: 'Typewriter', blurb: 'The line types itself, letter by letter, as it is sung' },
  { id: 'rise', label: 'Rise', blurb: 'Syllables float up and fade in as they are sung' },
  { id: 'focus', label: 'Focus', blurb: 'Blurred until sung, then sharp' },
  { id: 'neon', label: 'Neon', blurb: 'Neon outlines that flick on as they are sung' },
  { id: 'rainbow', label: 'Rainbow', blurb: 'What is sung shimmers in moving rainbow colours' },
  { id: 'beat', label: 'On the beat', blurb: 'The line pulses with the beat' },
]

export const COLORS: { id: string; label: string; value: string }[] = [
  { id: 'white', label: 'White', value: '#ffffff' },
  { id: 'song', label: 'The song’s colour', value: '' },
  { id: 'gold', label: 'Gold', value: '#ffd36b' },
  { id: 'ice', label: 'Ice', value: '#9fe6ff' },
  { id: 'pink', label: 'Pink', value: '#ff7ad9' },
  { id: 'lime', label: 'Lime', value: '#b8ff5a' },
]

export interface LyricsStyle {
  font: string
  /** The font's name for ``font: 'own'``. */
  own: string
  effect: string
  color: string
  /** 0.7 .. 1.6 of the usual size. */
  size: number
}

export const DEFAULT_LYRICS: LyricsStyle = { font: 'clean', own: '', effect: 'sweep', color: 'white', size: 1 }

export function lyricsWithDefaults(raw: unknown): LyricsStyle {
  const given = (raw && typeof raw === 'object' ? raw : {}) as Partial<LyricsStyle>
  const out = { ...DEFAULT_LYRICS, ...given }
  if (out.font !== 'own' && !FONTS.some((f) => f.id === out.font)) out.font = 'clean'
  if (!EFFECTS.some((e) => e.id === out.effect)) out.effect = 'sweep'
  if (!COLORS.some((c) => c.id === out.color)) out.color = 'white'
  out.size = Math.min(1.6, Math.max(0.7, Number(out.size) || 1))
  out.own = typeof out.own === 'string' ? out.own.replace(/["\\;{}<>]/g, '').slice(0, 60) : ''
  return out
}

/** The CSS font-family list and weight of a style. */
export function fontOf(style: LyricsStyle): { stack: string; weight: number } {
  if (style.font === 'own' && style.own.trim()) return { stack: `"${style.own.trim()}", ${FONTS[0].stack}`, weight: 700 }
  const choice = FONTS.find((f) => f.id === style.font) ?? FONTS[0]
  return { stack: choice.stack, weight: choice.weight }
}

/** The colour of what is sung (``accent``: the song's colour, for *The song's colour*). */
export function litColor(style: LyricsStyle, accent: string): string {
  return COLORS.find((c) => c.id === style.color)?.value || accent
}
