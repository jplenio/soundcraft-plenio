/** More for a song's video (owner's request 2026-10-18): the cover always - in its place, size and shape; lyrics
 * word by word, in a place of their own or a new one every line, coming in as chosen and on the beat; the title,
 * the lyrics and the cover in the visual itself (Plenio Drop's pictures). */
import { describe, expect, it } from 'vitest'

import type { TimedLine } from '../src/player/api'
import { compilePreset, FormulaError } from '../src/player/visuals/drop/format'
import { BUILTIN } from '../src/player/visuals/drop/builtin'
import { DEFAULTS, mixParams, paramsOf, type Music } from '../src/player/visuals/drop/renderer'
import { storySprites, wordsSung } from '../src/player/visuals/drop/story'
import { videoWithDefaults } from '../src/player/video/make'
import { coverAt, entranceAt, entranceOf, linePlace } from '../src/player/video/overlay'

const LINE: TimedLine = { text: 'Blue light pooling', start: 10, end: 12.5, units: [[10, 5], [10.6, 11], [11.4, 18]] }

function music(over: Partial<Music> = {}): Music {
  return {
    bass: 1, mid: 1, treb: 1, bassAtt: 1, midAtt: 1, trebAtt: 1, vol: 0.5, beat: false, pulse: 0.5, time: 3, dt: 1 / 60, frame: 1, aspect: 16 / 9,
    songTime: 4, lineOn: 1, lineAge: 0.25,
    wave: new Float32Array(512), left: new Float32Array(512), right: new Float32Array(512), spec: new Float32Array(128), ...over,
  } // prettier-ignore
}

describe('the cover in the video', () => {
  it('stands in its place, inside the picture, and a drifting one moves', () => {
    const look = { place: 'bottom-right' as const, size: 0.2, shape: 'rounded' as const, pulse: true }
    const at = coverAt(look, 1920, 1080, 0)
    expect(at.side).toBeCloseTo(216)
    expect(at.x + at.side / 2).toBeLessThan(1920)
    expect(at.y + at.side / 2).toBeLessThan(1080)
    expect(at.x).toBeGreaterThan(1920 / 2)
    expect(coverAt({ ...look, place: 'center' }, 1920, 1080, 0)).toMatchObject({ x: 960, y: 540 })
    const drift = { ...look, place: 'drift' as const }
    const a = coverAt(drift, 1920, 1080, 1)
    const b = coverAt(drift, 1920, 1080, 6)
    expect(Math.hypot(a.x - b.x, a.y - b.y)).toBeGreaterThan(50)
    for (let s = 0; s < 120; s += 3) {
      const d = coverAt(drift, 1920, 1080, s)
      expect(d.x - d.side / 2).toBeGreaterThanOrEqual(0)
      expect(d.y + d.side / 2).toBeLessThanOrEqual(1080)
    }
  })
})

describe('the lyrics in the video', () => {
  it('take a new place every line - never the one before - the same for the same line', () => {
    const places = Array.from({ length: 40 }, (_, k) => linePlace(k, 'random', 1920, 1080, 7))
    for (let k = 1; k < places.length; k++) expect([places[k].x, places[k].y]).not.toEqual([places[k - 1].x, places[k - 1].y])
    expect(linePlace(5, 'random', 1920, 1080, 7)).toEqual(places[5])
    expect(new Set(places.map((p) => `${p.x},${p.y}`)).size).toBeGreaterThan(5)
    expect(linePlace(3, 'top', 1920, 1080)).toEqual({ x: 960, y: 216, tilt: 0 })
  })

  it('come in as chosen and are fully there at the end of their beat', () => {
    for (const kind of ['fade', 'rise', 'zoom', 'drop', 'blur', 'wipe', 'glitch', 'none'] as const) {
      const end = entranceAt(kind, 0.5, 0.5)
      expect(end.alpha).toBeCloseTo(1)
      expect(end.scale).toBeCloseTo(1)
      expect(Math.abs(end.dy)).toBeLessThan(0.01)
      expect(end.blur).toBeCloseTo(0)
      expect(end.wipe).toBeCloseTo(1)
      expect(end.glitch).toBeCloseTo(0)
    }
    expect(entranceAt('fade', 0, 0.5).alpha).toBe(0)
    expect(entranceAt('rise', 0, 0.5).dy).toBeGreaterThan(0.5)
    expect(entranceAt('drop', 0, 0.5).dy).toBeLessThan(-1)
    expect(entranceAt('zoom', 0.3, 0.5).scale).toBeGreaterThan(1) // a little past, then back
    expect(entranceAt('wipe', 0.1, 0.5).wipe).toBeLessThan(1)
    // a different one every line, the same for the same line
    const kinds = Array.from({ length: 20 }, (_, k) => entranceOf('random', k, 3))
    expect(new Set(kinds).size).toBeGreaterThan(3)
    expect(entranceOf('random', 4, 3)).toBe(kinds[4])
    expect(kinds).not.toContain('random')
  })

  it('know the words sung so far', () => {
    expect(wordsSung(LINE, 9)).toEqual([])
    expect(wordsSung(LINE, 10.1)).toEqual(['Blue'])
    expect(wordsSung(LINE, 11.5)).toEqual(['Blue', 'light', 'pooling'].slice(0, 3))
  })

  it('keep their choices, checked', () => {
    const fresh = videoWithDefaults(null)
    expect(fresh).toMatchObject({ lyricsPlace: 'bottom', lyricsIn: 'fade', onBeat: true, into: { title: false, lyrics: false, cover: false } })
    expect(fresh.cover).toEqual({ show: false, place: 'bottom-right', size: 0.2, shape: 'rounded', pulse: true })
    const odd = videoWithDefaults({ lyrics: 'words', lyricsPlace: 'sideways', lyricsIn: 'spin', cover: { show: true, place: 'moon', size: 9, shape: 'star' }, into: { title: 1, lyrics: true } })
    expect(odd.lyrics).toBe('words')
    expect(odd.lyricsPlace).toBe('bottom')
    expect(odd.lyricsIn).toBe('fade')
    expect(odd.cover).toEqual({ show: true, place: 'bottom-right', size: 0.6, shape: 'rounded', pulse: true })
    expect(odd.into).toEqual({ title: true, lyrics: true, cover: false })
  })
})

describe('the song in the visual', () => {
  it('Plenio Drop presets draw pictures of the cover, the title, the line and the word sung', () => {
    const def = compilePreset({
      name: 'Pictures',
      sprites: [
        { source: 'cover', size: '0.2 + 0.1 * pulse', angle: 'time', blend: 'over' },
        { source: 'title', alpha: 'clamp(1 - songtime / 8, 0, 1)', repeat: 2, x: 'i * 0.5 - 0.25' },
        { source: 'word', alpha: 'line_on * line_age' },
      ],
    })
    const p = paramsOf(def, music(), {})
    expect(p.sprites.map((s) => s.source)).toEqual(['cover', 'title', 'title', 'word'])
    expect(p.sprites[0]).toMatchObject({ size: 0.25, angle: 3, additive: 0 })
    expect(p.sprites[1]).toMatchObject({ alpha: 0.5, x: -0.25, additive: 1 })
    expect(p.sprites[3].alpha).toBe(0.25)
    expect(() => compilePreset({ name: 'Bad', sprites: [{ source: 'moon' }] })).toThrow(FormulaError)
    expect(() => compilePreset({ name: 'Bad', sprites: [{ colour: 1 }] })).toThrow(/not a field/)
    // a change of preset fades the pictures as it fades the shapes
    const mixed = mixParams({ ...DEFAULTS, sprites: p.sprites }, { ...DEFAULTS }, 0.5)
    expect(mixed.sprites[0].alpha).toBeCloseTo(0.4)
  })

  it('five built-in presets show the song, and a video can put it into any of them', () => {
    const named = ['Cover Galaxy', 'Title Smoke', 'Lyric Tunnel', 'Album Kaleido', 'Cover Echo']
    for (const name of named) {
      const file = BUILTIN.find((f) => f.name === name)
      expect(file?.sprites?.length).toBeGreaterThan(0)
      expect(paramsOf(compilePreset(file!), music(), {}).sprites.length).toBeGreaterThan(0)
    }
    const sprites = storySprites({ title: true, lyrics: true, cover: true }, 2, 0.5, 1)
    expect(sprites.map((s) => s.source)).toEqual(['cover', 'title', 'line'])
    expect(storySprites({ title: true, lyrics: true, cover: false }, 9, 0, 0)).toEqual([]) // the title has gone, nothing sung
  })
})
