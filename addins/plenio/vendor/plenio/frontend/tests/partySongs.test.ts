/** Party songs (owner's request 2026-10-25): the simple form's logic - a template fills every field, the lists, the
 * fields a song or a cover asks, what is still missing, the request - and how a song in the making is told. */
import { describe, expect, it } from 'vitest'

import {
  againStudio,
  applies,
  clock,
  creditMoment,
  driftAt,
  fromTemplate,
  grouped,
  missing,
  nearestLength,
  optionsFor,
  partyMaker,
  progressOf,
  requestOf,
  retryRequest,
  stateOf,
  studioApplies,
  studioGroups,
  studioStart,
  summary,
  surprise,
  timeOfDay,
  untilText,
  type ApiField,
  type Draft,
  type FormData,
  type MakeJob,
  type Remake,
  type SongDocuments,
  type StudioSpec,
  type StyleTemplate,
} from '../src/player/make/form'

const LENGTHS = ['very short (about 1:00)', 'short (about 1:30)', 'about 2:00', 'about 2:30', 'standard (about 3:00)', 'about 3:30', 'about 4:00']
const FORM: FormData = {
  source: 'package',
  templates: [],
  values: { genre: ['jazz', 'synthwave'], mood: ['warm, hopeful'], voice: ['warm female vocal'] },
  song: { fields: [], choices: { length: LENGTHS, vocals: ['sung', 'sparse vocals', 'instrumental'] }, defaults: { length: 'short (about 1:30)', vocals: 'sung' } },
  cover: { fields: [], choices: { vocals: ['original lyrics', 'new lyrics', 'instrumental'] }, defaults: { vocals: 'original lyrics' } },
  limits: { description: 1500, text: 120, source_mb: 100, max_length: 'about 4:00' },
  covers: true,
}
const SYNTH: StyleTemplate = {
  id: 'electronic/synthwave',
  name: 'Synthwave',
  group: 'Electronic',
  fields: { genre: 'synthwave', tempo: '110  BPM', length: 'long (about 4:30)', vocals: 'sung', voice: 'warm female vocal', language: 'English', description: 'Neon\nnights' },
}
const SAX: StyleTemplate = { id: 'jazz/sax', name: 'Sax', group: 'Jazz', fields: { genre: 'jazz', vocals: 'instrumental', length: 'about 2:00' } }

describe('the song form', () => {
  it('fills every field from a template, as the lists have them', () => {
    const fields = fromTemplate(SYNTH, 'song', FORM)
    expect(fields).toMatchObject({ template: 'electronic/synthwave', genre: 'synthwave', tempo: '110 BPM', vocals: 'sung', voice: 'warm female vocal', mood: '', key: '' })
    expect(fields.description).toBe('Neon\nnights')
    // longer than the host allows: the longest offered
    expect(fields.length).toBe('about 4:00')
    expect(fromTemplate(SAX, 'song', FORM).length).toBe('about 2:00')
    expect(fromTemplate(null, 'song', FORM)).toMatchObject({ template: 'none', length: 'short (about 1:30)', vocals: 'sung', genre: '' })
  })

  it('makes a sung template a cover with the original lyrics, an instrumental one an instrumental cover', () => {
    expect(fromTemplate(SYNTH, 'cover', FORM).vocals).toBe('original lyrics')
    expect(fromTemplate(SAX, 'cover', FORM).vocals).toBe('instrumental')
    expect(fromTemplate(SYNTH, 'cover', FORM, { vocals: 'new lyrics' }).vocals).toBe('new lyrics')
    expect('tempo' in fromTemplate(SYNTH, 'cover', FORM)).toBe(false)
  })

  it('asks only what applies', () => {
    const song: Draft = { kind: 'song', fields: { vocals: 'instrumental' }, source: null }
    expect(['language', 'voice', 'theme'].map((n) => applies(n, song))).toEqual([false, false, false])
    expect(applies('tempo', song) && applies('key', song)).toBe(true)
    const cover: Draft = { kind: 'cover', fields: { vocals: 'original lyrics' }, source: null }
    expect(['tempo', 'length', 'key', 'meter', 'theme', 'language'].some((n) => applies(n, cover))).toBe(false)
    expect(applies('voice', cover)).toBe(true)
    expect(applies('theme', { ...cover, fields: { vocals: 'new lyrics' } }) && applies('language', { ...cover, fields: { vocals: 'new lyrics' } })).toBe(true)
  })

  it('offers the templates values, the choices of length and vocals', () => {
    const draft: Draft = { kind: 'song', fields: {}, source: null }
    expect(optionsFor('genre', draft, FORM)).toEqual(['jazz', 'synthwave'])
    expect(optionsFor('length', draft, FORM)).toEqual(LENGTHS)
    expect(optionsFor('vocals', { ...draft, kind: 'cover' }, FORM)).toEqual(['original lyrics', 'new lyrics', 'instrumental'])
    expect(optionsFor('theme', draft, FORM)).toEqual([])
  })

  it('finds the nearest length', () => {
    expect(nearestLength('2:10', LENGTHS)).toBe('about 2:00')
    expect(nearestLength('very long (about 6:00)', LENGTHS)).toBe('about 4:00')
    expect(nearestLength('', LENGTHS)).toBe('standard (about 3:00)')
  })

  it('says what is missing and sends what applies', () => {
    expect(missing({ kind: 'song', fields: { template: 'none' }, source: null })).toEqual(['a style, a genre or a description'])
    expect(missing({ kind: 'song', fields: { template: 'none', genre: 'ska' }, source: null })).toEqual([])
    expect(missing({ kind: 'cover', fields: { template: 'pop/x' }, source: null })).toEqual(['the original recording'])
    const draft: Draft = { kind: 'song', fields: { template: 'none', genre: 'jazz', vocals: 'instrumental', voice: 'left over', length: 'about 2:00', description: '' }, source: null }
    expect(requestOf(draft)).toEqual({ fields: { template: 'none', genre: 'jazz', vocals: 'instrumental', length: 'about 2:00', description: '' } })
    const cover: Draft = { kind: 'cover', fields: { template: 'none', genre: 'jazz', vocals: 'original lyrics', tempo: '90' }, source: { id: 'abc', name: 'a.mp3', title: 'A', seconds: 100 } }
    expect(requestOf(cover)).toEqual({ fields: { template: 'none', genre: 'jazz', vocals: 'original lyrics' }, source: 'abc' })
  })

  it('says in one line what the song will be', () => {
    expect(summary({ kind: 'song', fields: { genre: 'synthwave', length: 'standard (about 3:00)', vocals: 'sung', voice: 'warm female vocal', language: 'English' }, source: null })).toBe('synthwave · about 3:00 · warm female vocal · English')
    expect(summary({ kind: 'cover', fields: { genre: 'jazz', vocals: 'instrumental' }, source: { id: 'a', name: 'a.mp3', title: 'Hey Jude', seconds: 1 } })).toBe('jazz · cover of Hey Jude · instrumental')
  })

  it('groups and finds the templates, and surprises', () => {
    expect(grouped([SYNTH, SAX]).map(([g]) => g)).toEqual(['Electronic', 'Jazz'])
    expect(grouped([SYNTH, SAX], 'sax')).toEqual([['Jazz', [SAX]]])
    expect(surprise([SYNTH, SAX], 'song', () => 0.6)).toBe(SAX)
    expect(surprise([], 'song')).toBeNull()
  })
})

describe('songs in the making', () => {
  const now = new Date(2026, 9, 25, 21, 12, 30).getTime() / 1000
  const job = (over: Partial<MakeJob>): MakeJob => ({
    id: 'a',
    kind: 'song',
    status: 'waiting',
    owner: { kind: 'guest', name: 'Guest' },
    mine: true,
    label: 'synthwave · 3:00',
    description: '',
    created: now - 60,
    started: null,
    finished: null,
    position: 2,
    eta: now + 25 * 60,
    starts: now + 18 * 60,
    estimate: 420,
    stage: null,
    progress: null,
    result: null,
    error: '',
    note: '',
    can: { edit: true, up: true, down: false, delete: true },
    ...over,
  })

  it('tells where a song is', () => {
    expect(stateOf(job({}), now)).toEqual({ title: '#2 in line', detail: 'ready about 21:40', tone: 'wait' })
    const running = stateOf(job({ status: 'running', started: now - 192, stage: { group: '5 · RENDER', text: 'singing and playing' } }), now)
    expect(running.title).toBe('Singing and playing …')
    expect(running.detail).toMatch(/^3:12 · ready about/)
    expect(stateOf(job({ status: 'done', finished: now, result: { title: 'Neon', song: 'abc' } }), now)).toMatchObject({ title: 'Ready 21:12', tone: 'done' })
    expect(stateOf(job({ status: 'failed', error: 'a model file is missing' }), now)).toEqual({ title: 'That did not work', detail: 'a model file is missing', tone: 'bad' })
  })

  it('rounds the time of day to five minutes, never into the past', () => {
    expect(timeOfDay(now + 25 * 60, true, now)).toBe('21:40')
    expect(timeOfDay(now - 600, true, now)).toBe('21:15')
    expect(timeOfDay(now)).toBe('21:12')
  })

  it('says how long, and how far', () => {
    expect(untilText(now + 25 * 60, now)).toBe('about 25 min')
    expect(untilText(now + 70 * 60, now)).toBe('about 1 h 10 min')
    expect(untilText(now + 30, now)).toBe('in a moment')
    expect(clock(192)).toBe('3:12')
    expect(clock(3725)).toBe('1:02:05')
    expect(progressOf(job({ status: 'running', started: now - 210 }), now)).toBeCloseTo(0.5)
    expect(progressOf(job({ status: 'running', started: now - 5000 }), now)).toBe(0.96)
    expect(progressOf(job({ status: 'done' }), now)).toBe(1)
  })
})

describe('who made a party song', () => {
  it('is the artist of a song on a Party-Song album, Guest without one; other songs have none', () => {
    expect(partyMaker({ album: 'Party-Song 2026-10-25', artist: 'Anna' })).toBe('Anna')
    expect(partyMaker({ album: 'Party-Song 2026-10-25' })).toBe('Guest')
    expect(partyMaker({ album: 'Party songs', artist: 'Anna' })).toBeNull()
    expect(partyMaker({ artist: 'Anna' })).toBeNull()
    expect(partyMaker(undefined)).toBeNull()
  })

  it('is large as the song begins, at every new section and as it ends - a badge between', () => {
    const sections = [{ at: 0, label: 'intro' }, { at: 30, label: 'verse' }, { at: 60, label: 'chorus' }]
    expect(creditMoment(2, 120, sections)?.kind).toBe('intro')
    expect(creditMoment(15, 120, sections)).toBeNull()
    expect(creditMoment(31, 120, sections)).toEqual({ kind: 'section', label: 'verse' })
    expect(creditMoment(65, 120, sections)).toBeNull()
    expect(creditMoment(115, 120, sections)?.kind).toBe('outro')
  })

  it('drifts over the picture, the same at the same moment, never off it', () => {
    expect(driftAt(42)).toEqual(driftAt(42))
    for (let t = 0; t < 600; t += 7) {
      const at = driftAt(t)
      expect(at.x).toBeGreaterThan(15)
      expect(at.x).toBeLessThan(85)
      expect(at.y).toBeGreaterThan(15)
      expect(at.y).toBeLessThan(77)
    }
  })
})

// --- again from a song; the whole studio (owner's request 2026-10-26) ------------------------------------------

const field = (id: string, type: ApiField['type'], extra: Partial<ApiField> = {}): ApiField => ({
  id,
  label: id,
  type,
  default: '',
  description: `${id} does something.`,
  group: '1 · SONG',
  ...extra,
})
const STUDIO: StudioSpec = {
  template: 'yue2-song',
  documents: ['title', 'style', 'lyrics', 'score', 'artwork_prompt'],
  fields: [
    field('mode', 'choice', { default: 'new song every run', fixed: true }),
    field('genre', 'string', { default: 'pop' }),
    field('vocals', 'choice', { default: 'sung', choices: ['sung', 'instrumental'] }),
    field('vocals.voice', 'string', { default: 'warm', when: { vocals: ['sung', 'sparse vocals'] } }),
    field('writer.model', 'choice', { default: 'qwen.gguf', choices: ['qwen.gguf', 'other.gguf'] }),
    field('finish.hq_mastering', 'boolean', { default: false }),
    field('finish.cover_art', 'boolean', { default: true }),
    field('creativity', 'integer', { default: 60, minimum: 0, maximum: 100 }),
    field('excerpt.enabled', 'boolean', { default: false }),
    field('excerpt.start_index', 'integer', { default: 0, when: { 'excerpt.enabled': ['true'] } }),
    field('source.audio', 'upload', { default: '' }),
  ],
  release: [
    field('folder', 'string', { default: 'plenio', group: 'release' }),
    field('mp3', 'boolean', { default: false, group: 'release' }),
    field('wav', 'boolean', { default: false, group: 'release' }),
    field('tags', 'boolean', { default: false, group: 'release' }),
    field('album', 'string', { default: '', group: 'release', when: { tags: ['true'] } }),
    field('naming', 'choice', { default: 'title', group: 'release', fixed: true }),
  ],
}
const SONG_START = { id: 'abc123', title: 'Neon', genre: 'synthwave', seconds: 64, cover: true, other: false, model: 'YuE2', kind: 'song' }
const STUDIO_VALUES = { fields: { 'finish.hq_mastering': true, 'writer.model': 'other.gguf' }, release: { mp3: true } }

const JOB_BASE: MakeJob = {
  id: 'j1',
  kind: 'song',
  status: 'waiting',
  owner: { kind: 'user', name: 'Anna' },
  mine: true,
  label: 'jazz · 1:00',
  description: '',
  created: 0,
  started: null,
  finished: null,
  position: null,
  eta: null,
  starts: null,
  estimate: 300,
  stage: null,
  progress: null,
  result: null,
  error: 'ComfyUI stopped',
  note: '',
  can: { edit: false, up: false, down: false, delete: true },
}
const find = (id: string): ApiField => STUDIO.fields.find((f) => f.id === id) ?? STUDIO.release.find((f) => f.id === id)!

describe('the whole studio', () => {
  it('shows a field by the choice it depends on - the form’s own first, then the studio’s, then the template’s', () => {
    const voice = find('vocals.voice')
    const sung: Draft = { kind: 'song', fields: { vocals: 'sung' }, source: null }
    expect(studioApplies(voice, {}, sung, STUDIO.fields)).toBe(true)
    expect(studioApplies(voice, {}, { ...sung, fields: { vocals: 'instrumental' } }, STUDIO.fields)).toBe(false)
    // the studio's value wins over the form's; the template's default when neither says
    expect(studioApplies(voice, { vocals: 'instrumental' }, sung, STUDIO.fields)).toBe(false)
    expect(studioApplies(voice, {}, { kind: 'song', fields: {}, source: null }, STUDIO.fields)).toBe(true)
    const album = find('album')
    expect(studioApplies(album, { tags: true }, sung, STUDIO.release)).toBe(true)
    expect(studioApplies(album, { tags: false }, sung, STUDIO.release)).toBe(false)
    expect(studioApplies(album, {}, sung, STUDIO.release)).toBe(false)
  })

  it('starts from the template, then the party’s defaults, then the song’s own values', () => {
    const started = studioStart(
      STUDIO,
      { fields: { 'finish.hq_mastering': true, genre: 'rock' }, release: { album: 'Party-Song 2026-10-26' } },
      { fields: { 'writer.model': 'other.gguf' }, release: { folder: 'plenio/Neon', mp3: true } }
    )
    expect(started.fields).toEqual({
      'finish.hq_mastering': true,
      'finish.cover_art': true,
      'writer.model': 'other.gguf',
      creativity: 60,
      'excerpt.enabled': false,
      'excerpt.start_index': 0,
    })
    expect(started.release).toEqual({ folder: 'plenio/Neon', mp3: true, wav: false, tags: false, album: 'Party-Song 2026-10-26' })
    // fixed fields and the simple form's own fields are not the studio's (unknown names are left out)
    expect(started.fields).not.toHaveProperty('mode')
    expect(started.fields).not.toHaveProperty('genre')
    expect(started.release).not.toHaveProperty('naming')
    expect(studioGroups(STUDIO).map((g) => g.title)).toEqual(['The studio', 'The Song Brief', 'An excerpt of the original', 'Export Release - folder, formats, tags'])
  })

  it('sends a new take’s documents as changed, the song it comes from and the studio’s values that apply', () => {
    const original: SongDocuments = { title: 'Neon', style: 'synthwave · warm', lyrics: '[verse]\nCity lights' }
    const draft: Draft = {
      kind: 'song',
      again: 'take',
      base: SONG_START,
      fields: { vocals: 'sung' },
      source: null,
      documents: { title: 'Neon (live)', style: 'synthwave · warm', lyrics: '[verse]\nCity rain' },
      studio: STUDIO_VALUES,
    }
    const body = requestOf(draft, STUDIO, original)
    expect(body.from).toEqual({ song: 'abc123', as: 'take' })
    expect(body.fields).toEqual({})
    expect(body.documents).toEqual({ title: 'Neon (live)', lyrics: '[verse]\nCity rain' })
    expect(body.studio).toEqual({
      fields: {
        'finish.hq_mastering': true,
        'finish.cover_art': true,
        'writer.model': 'other.gguf',
        creativity: 60,
        'excerpt.enabled': false,
      },
      release: { folder: 'plenio', mp3: true, wav: false, tags: false },
    })
    // the song as it is: nothing changed, nothing sent
    expect(requestOf({ ...draft, documents: { ...original } }, STUDIO, original).documents).toEqual({})
  })

  it('makes a new song like it, and a cover of it, without the recording uploaded', () => {
    const song: Draft = { kind: 'song', again: 'song', base: SONG_START, source: null, fields: { template: 'none', genre: 'italo disco', vocals: 'instrumental', language: 'English', description: '' } }
    expect(requestOf(song, STUDIO)).toEqual({
      fields: { template: 'none', genre: 'italo disco', vocals: 'instrumental', description: '' },
      from: { song: 'abc123', as: 'song' },
    })
    const cover: Draft = { kind: 'cover', again: 'cover', base: SONG_START, source: null, fields: { template: 'none', genre: 'bossa nova', vocals: 'original lyrics', tempo: '120', theme: 'left over' } }
    expect(requestOf(cover, STUDIO)).toEqual({
      fields: { template: 'none', genre: 'bossa nova', vocals: 'original lyrics' },
      from: { song: 'abc123', as: 'cover' },
    })
    // a cover of a file one sends is still the recording's id
    const uploaded: Draft = { kind: 'cover', source: { id: 'up-1', name: 'a.mp3', title: 'A', seconds: 90 }, fields: { template: 'none', genre: 'jazz', vocals: 'original lyrics' } }
    expect(requestOf(uploaded).source).toBe('up-1')
  })

  it('starts a new take from the song’s release, a new song like it from the party’s - its settings both', () => {
    const remake: Remake = {
      song: SONG_START,
      can: { take: true, song: true, cover: true },
      why: { take: '', song: '', cover: '' },
      start: 'take',
      kind: 'song',
      fields: { genre: 'synthwave' },
      documents: { title: 'Neon', style: 'synthwave', lyrics: '[verse]' },
      studio: { template: 'yue2-song', warnings: [], fields: { 'writer.model': 'other.gguf' }, release: { folder: 'plenio/Neon', album: 'Night drives' } },
    }
    expect(againStudio('take', remake)?.release).toEqual({ folder: 'plenio/Neon', album: 'Night drives' })
    const like = againStudio('song', remake)
    expect(like).toEqual({ fields: { 'writer.model': 'other.gguf' }, release: {} })
    expect(studioStart(STUDIO, { fields: {}, release: { folder: 'plenio/Party-Songs-2026-10-26' } }, like).release.folder).toBe('plenio/Party-Songs-2026-10-26')
    expect(againStudio('cover', remake)).toBeNull()
    expect(againStudio('take', { ...remake, studio: null })).toBeNull()
  })

  it('orders a song that failed again as it was ordered', () => {
    const job = (extra: Partial<MakeJob>): MakeJob => ({ ...JOB_BASE, status: 'failed', fields: { genre: 'jazz' }, ...extra })
    // a new take, with its documents and the studio's values
    expect(retryRequest(job({ again: 'take', from: { song: 'abc123', title: 'Neon', seconds: 64 }, documents: { title: 'Neon (live)' }, studio: STUDIO_VALUES }))).toEqual({
      fields: { genre: 'jazz' },
      from: { song: 'abc123', as: 'take' },
      documents: { title: 'Neon (live)' },
      studio: STUDIO_VALUES,
    })
    // a cover of a song of the library: no recording of its own to send
    expect(retryRequest(job({ kind: 'cover', again: 'cover', from: { song: 'abc123', title: 'Neon', seconds: 64 }, source: { id: '', name: '', title: 'Neon', seconds: 64 } }))).toEqual({
      fields: { genre: 'jazz' },
      from: { song: 'abc123', as: 'cover' },
    })
    // a cover of an uploaded recording, and a plain song, as before
    expect(retryRequest(job({ kind: 'cover', source: { id: 'up-1', name: 'a.mp3', title: 'A', seconds: 90 } }))).toEqual({ fields: { genre: 'jazz' }, source: 'up-1' })
    expect(retryRequest(job({ documents: {}, studio: null }))).toEqual({ fields: { genre: 'jazz' } })
  })
})
