/**
 * The marks of a long list's rail (owner's request 2026-10-26: no long scrolling - in thousands of songs a jump to any
 * place): sorted by title its letters, by date its months (its years when there are too many), by length its minutes,
 * by tempo its tens. Each mark is where its songs begin in the list.
 */
import type { SongSummary } from './api'
import type { SortKey } from './search'

export interface IndexMark {
  /** What the rail shows (``A``, ``Oct``, ``Sep 25``, ``3′``, ``120``). */
  label: string
  /** What it stands for, said in full (the mark's tooltip). */
  title: string
  /** Where its songs begin in the list. */
  at: number
  /** How many songs it has. */
  count: number
}

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
const MONTH_NAMES = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']

function letterOf(title: string): string {
  const first = title.normalize('NFKD').replace(/[̀-ͯ]/g, '').trim().charAt(0).toUpperCase()
  return /[A-Z]/.test(first) ? first : '#'
}

/** The key a song belongs to under ``sort`` (``null``: the sort has no marks). */
function keyOf(song: SongSummary, sort: SortKey, byYear: boolean): [string, string, string] | null {
  switch (sort) {
    case 'title': {
      const letter = letterOf(song.title)
      return [letter, letter, letter === '#' ? 'Numbers and signs' : letter]
    }
    case 'newest':
    case 'oldest': {
      const year = song.created.slice(0, 4)
      const month = Number(song.created.slice(5, 7))
      if (!/^\d{4}$/.test(year) || !(month >= 1 && month <= 12)) return ['?', '?', 'No date']
      if (byYear) return [year, year, year]
      const thisYear = String(new Date().getFullYear())
      const label = year === thisYear ? MONTHS[month - 1] : `${MONTHS[month - 1]} ${year.slice(2)}`
      return [`${year}-${month}`, label, `${MONTH_NAMES[month - 1]} ${year}`]
    }
    case 'length': {
      const minutes = Math.floor(song.seconds / 60)
      return [String(minutes), `${minutes}′`, `${minutes} to ${minutes + 1} minutes`]
    }
    case 'bpm': {
      if (!song.bpm) return ['?', '?', 'No tempo']
      const tens = Math.floor(song.bpm / 10) * 10
      return [String(tens), String(tens), `${tens}-${tens + 9} BPM`]
    }
    default:
      return null
  }
}

/** The rail's marks for ``songs`` as sorted by ``sort``; at most ``most`` (months become years, then every few). */
export function indexMarks(songs: SongSummary[], sort: SortKey, most = 26): IndexMark[] {
  const build = (byYear: boolean): IndexMark[] => {
    const marks: IndexMark[] = []
    let last = ''
    songs.forEach((song, at) => {
      const key = keyOf(song, sort, byYear)
      if (!key) return
      if (key[0] !== last) {
        marks.push({ label: key[1], title: key[2], at, count: 1 })
        last = key[0]
      } else marks[marks.length - 1].count += 1
    })
    return marks
  }
  let marks = build(false)
  if (marks.length > most && (sort === 'newest' || sort === 'oldest')) marks = build(true)
  if (marks.length <= most) return marks
  // too many for the rail: every few marks one, each holding the songs up to the next one shown
  const step = Math.ceil(marks.length / most)
  const kept: IndexMark[] = []
  marks.forEach((mark, k) => {
    if (k % step === 0) kept.push({ ...mark })
    else kept[kept.length - 1].count += mark.count
  })
  return kept
}
