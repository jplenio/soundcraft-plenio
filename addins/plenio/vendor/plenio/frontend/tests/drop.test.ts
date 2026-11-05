/**
 * Plenio Drop (owner's request 2026-10-16): MilkDrop-like visuals of Plenio's own, and a preset format simple
 * enough to write one's own - formulas in a small language of its own, never script. In Node (no page needed),
 * which also reads the guide's examples from the docs.
 *
 * @vitest-environment node
 */
import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

import { withDefaults } from '../src/player/visuals/chooser'
import { BUILTIN, randomPreset } from '../src/player/visuals/drop/builtin'
import { MILKDROP } from '../src/player/visuals/drop/milkdrop'
import { FormulaError, compileFormula, compilePreset, readPreset, type PresetFile } from '../src/player/visuals/drop/format'
import { DEFAULTS, mixParams, paramsOf, type DropParams, type Music } from '../src/player/visuals/drop/renderer'
import { PRESETS } from '../src/player/visuals/presets'

const NAMES = new Set(['bass', 'mid', 'x', 'y'])
const calc = (source: string, scope: Record<string, number> = {}) => compileFormula(source, NAMES)(scope)

function music(over: Partial<Music> = {}): Music {
  return {
    bass: 1.2, mid: 0.9, treb: 1.1, bassAtt: 1.1, midAtt: 1, trebAtt: 1, vol: 0.5, beat: false, pulse: 0.3, time: 12.5, dt: 1 / 60, frame: 750, aspect: 16 / 9, songTime: 3, lineOn: 1, lineAge: 0.5,
    wave: new Float32Array(512), left: new Float32Array(512), right: new Float32Array(512), spec: new Float32Array(128), ...over,
  } // prettier-ignore
}

describe('the formula language', () => {
  it('computes as arithmetic does', () => {
    expect(calc('1 + 2 * 3')).toBe(7)
    expect(calc('(1 + 2) * 3')).toBe(9)
    expect(calc('-2^2')).toBe(-4)
    expect(calc('2^3^2')).toBe(512)
    expect(calc('10 - 4 - 3')).toBe(3)
    expect(calc('7 % 4 + 1.5e1')).toBe(18)
    expect(calc('2 * -3')).toBe(-6)
    expect(calc('bass * 2 + mid', { bass: 1.5, mid: 0.25 })).toBe(3.25)
  })

  it('compares, chooses and has the usual functions', () => {
    expect(calc('1 < 2 ? 5 : 6')).toBe(5)
    expect(calc('bass > 1.5 && mid < 1 ? 1 : 0', { bass: 2, mid: 0.5 })).toBe(1)
    expect(calc('!x || y', { x: 1, y: 0 })).toBe(0)
    expect(calc('x == 2 ? 1 : x == 3 ? 2 : 3', { x: 3 })).toBe(2)
    expect(calc('clamp(5, 0, 1) + mix(0, 10, 0.25) + max(1, 4, 2) + min(3, -1)')).toBe(1 + 2.5 + 4 - 1)
    expect(calc('sin(pi / 2) + cos(0) + abs(-2) + floor(2.7) + fract(1.25)')).toBeCloseTo(1 + 1 + 2 + 2 + 0.25)
    expect(calc('smoothstep(0, 1, 0.5) + step(1, 2)')).toBe(1.5)
  })

  it('never fails while drawing: dividing by zero gives 0, not infinity', () => {
    expect(calc('1 / 0')).toBe(0)
    expect(calc('x % 0', { x: 3 })).toBe(0)
    expect(calc('sqrt(-4) + log(0) * 0')).toBe(0)
    expect(calc('x')).toBe(0) // a variable not set yet
  })

  it('says what is wrong in a formula', () => {
    const wrong = (source: string) => {
      try {
        calc(source)
      } catch (error) {
        expect(error).toBeInstanceOf(FormulaError)
        return (error as Error).message
      }
      return 'no error'
    }
    expect(wrong('bas * 2')).toBe('unknown name "bas"')
    expect(wrong('sine(1)')).toBe('unknown function "sine"')
    expect(wrong('clamp(1, 2)')).toBe('clamp() takes 3 values, not 2')
    expect(wrong('1 +')).toBe('the formula ends too soon')
    expect(wrong('(1 + 2')).toBe('")" expected')
    expect(wrong('1 2')).toBe('unexpected "2"')
    expect(wrong('1 $ 2')).toBe('cannot read "$ 2"')
    expect(wrong('')).toBe('the formula is empty')
    // what is no formula cannot run: no property access, no calls of anything but the functions
    expect(wrong('constructor.constructor("alert(1)")()')).toBe('cannot read ".constructor"')
    expect(wrong('constructor')).toBe('unknown name "constructor"')
    expect(wrong('this')).toBe('unknown name "this"')
  })
})

describe('the preset format', () => {
  const file: PresetFile = {
    name: 'Test Preset',
    base: { decay: 0.9, family: 'swirl', mirror: 'both', famB: 'bass * 2' },
    init: { spin: 10 },
    frame: { spin: 'spin + 1', rot: 'spin / 100', zoom: 'decay + 0.1' },
    waves: [{ mode: 'circle', scale: 'bass', hue: 'time' }],
    shapes: [{ repeat: 3, sides: 'i + 3', x: 'i / n', alpha: 0.5 }],
  }

  it('starts every frame from the base, then works through the frame lines in order', () => {
    const def = compilePreset(file)
    expect(def.id).toBe('drop-test-preset')
    const vars = {}
    const first = paramsOf(def, music({ bass: 1.5 }), vars)
    expect(first.decay).toBe(0.9)
    expect(first.family).toBe(1) // swirl
    expect(first.mirror).toBe(3) // both
    expect(first.famB).toBe(3)
    expect(first.zoom).toBeCloseTo(1.0) // the frame reads the base's decay
    expect(first.gamma).toBe(DEFAULTS.gamma) // what the preset leaves alone
    expect(first.rot).toBeCloseTo(0.11)
    // the preset's own variables carry over from frame to frame
    expect(paramsOf(def, music(), vars).rot).toBeCloseTo(0.12)
    expect(paramsOf(def, music(), vars).rot).toBeCloseTo(0.13)
  })

  it('works out waves and shapes, a shape repeated with i and n', () => {
    const p = paramsOf(compilePreset(file), music({ bass: 0.8 }), {})
    expect(p.waves).toHaveLength(1)
    expect(p.waves[0]).toMatchObject({ mode: 0, scale: 0.8, hue: 12.5, alpha: 0.9 })
    expect(p.shapes.map((s) => [s.sides, s.x, s.alpha])).toEqual([
      [3, 0, 0.5],
      [4, 1 / 3, 0.5],
      [5, 2 / 3, 0.5],
    ])
  })

  it('says where a preset is wrong', () => {
    const wrong = (text: string) => {
      try {
        readPreset(text)
      } catch (error) {
        return (error as Error).message
      }
      return 'no error'
    }
    expect(wrong('{"name": "A", "frame": {"zoom": "1 + bas"}}')).toBe('frame.zoom: unknown name "bas"')
    expect(wrong('{"name": "A", "base": {"zom": 1}}')).toMatch(/^base: "zom" is no parameter/)
    expect(wrong('{"name": "A", "base": {"family": "helix"}}')).toBe('family: "helix" is none of plain, swirl, waves, tunnel, kaleidoscope, ripple, twist, fold, lens, tiles, spiral, drain')
    expect(wrong('{"name": "A", "waves": [{"mode": "circle", "colour": 1}]}')).toMatch(/^waves\[0\]: "colour" is not a field/)
    expect(wrong('{"name": "A", "shapes": [{"x": "1 +"}]}')).toBe('shapes[0].x: the formula ends too soon')
    expect(wrong('{"base": {}}')).toBe('"name" is missing')
    expect(wrong('{"name": "A", "init": {"q": "1"}}')).toBe('init.q: a number')
    expect(wrong('{"name": "A",}')).toMatch(/^not valid JSON/)
    expect(wrong('{"name": "A", "frame": {"zoom": [1]}}')).toMatch(/^frame.zoom: a number or a formula/)
    expect(wrong('{"name": "A", "frame": {"constructor": "1"}}')).toMatch(/^"constructor" cannot be a variable's name/)
    expect(wrong('{"name": "A", "init": {"bass": 1}}')).toMatch(/^"bass" cannot be a variable's name/)
  })

  it('has its own presets in that format, each one working', () => {
    expect(BUILTIN.length).toBeGreaterThanOrEqual(16)
    const ids = new Set<string>()
    for (const preset of BUILTIN) {
      const def = compilePreset(preset)
      ids.add(def.id)
      const vars = {}
      for (const m of [music(), music({ beat: true, pulse: 1, bass: 2.5 }), music({ bass: 0, mid: 0, treb: 0, vol: 0 })]) {
        const p = paramsOf(def, m, vars)
        for (const [key, value] of Object.entries(p)) if (typeof value === 'number') expect(Number.isFinite(value), `${preset.name}.${key}`).toBe(true)
        expect(p.waves.length + p.shapes.length, preset.name).toBeGreaterThan(0)
        expect(p.decay, preset.name).toBeLessThan(1)
      }
    }
    expect(ids.size).toBe(BUILTIN.length)
    // they are visuals like the others, chosen the same way
    for (const id of ids) expect(PRESETS.some((p) => p.id === id && p.kind === 'drop')).toBe(true)
    expect(PRESETS.some((p) => p.id === 'drop-random')).toBe(true)
  })

  it('has thirty more after MilkDrop’s classics, each working, with the new warp families', () => {
    expect(MILKDROP).toHaveLength(30)
    const families = new Set<number>()
    for (const preset of MILKDROP) {
      const def = compilePreset(preset)
      const vars = {}
      for (const m of [music(), music({ beat: true, pulse: 1, bass: 2.5 }), music({ bass: 0, mid: 0, treb: 0, vol: 0 })]) {
        const p = paramsOf(def, m, vars)
        for (const [key, value] of Object.entries(p)) if (typeof value === 'number') expect(Number.isFinite(value), `${preset.name}.${key}`).toBe(true)
        expect(p.waves.length + p.shapes.length + p.sprites.length, preset.name).toBeGreaterThan(0)
        expect(p.decay, preset.name).toBeLessThan(1)
        families.add(p.family)
      }
      expect(preset.suits?.length, preset.name).toBeGreaterThan(0)
      expect(PRESETS.some((p) => p.id === def.id && p.kind === 'drop'), preset.name).toBe(true)
    }
    for (const family of [6, 7, 8, 9, 10, 11]) expect(families.has(family), `family ${family}`).toBe(true)
    expect(new Set(MILKDROP.map((p) => p.name)).size).toBe(30)
  })

  it('makes up a working preset every time for Drop · Random', () => {
    let seed = 7
    const random = () => ((seed = (seed * 16807) % 2147483647) - 1) / 2147483646
    const families = new Set<number>()
    for (let k = 0; k < 60; k++) {
      const p = paramsOf(compilePreset(randomPreset(random)), music(), {})
      families.add(p.family)
      expect(p.decay).toBeGreaterThan(0.9)
      expect(p.waves).toHaveLength(1)
    }
    expect(families.size).toBeGreaterThan(3)
  })
})

describe('changing presets', () => {
  const a: DropParams = { ...DEFAULTS, zoom: 1, family: 1, famA: 0.4, mirror: 1, waves: [{ mode: 0, scale: 1, x: 0, y: 0, thick: 0.01, alpha: 1, hue: 0 }] }
  const b: DropParams = { ...DEFAULTS, zoom: 1.2, family: 3, famA: 0.2, mirror: 0, waves: [] }

  it('glides: numbers mixed, the family switching half way where its strength is nothing', () => {
    expect(mixParams(a, b, 0).zoom).toBe(1)
    expect(mixParams(a, b, 0.5).zoom).toBeCloseTo(1.1)
    expect(mixParams(a, b, 1).zoom).toBeCloseTo(1.2)
    expect(mixParams(a, b, 0.25)).toMatchObject({ family: 1, mirror: 1 })
    expect(mixParams(a, b, 0.25).famA).toBeCloseTo(0.2)
    expect(mixParams(a, b, 0.75)).toMatchObject({ family: 3, mirror: 0 })
    expect(mixParams(a, b, 0.75).famA).toBeCloseTo(0.1)
    // the old waves fade out
    expect(mixParams(a, b, 0.75).waves[0].alpha).toBeCloseTo(0.25)
  })
})

describe('the visuals settings with Plenio Drop', () => {
  it('offers the Drop presets once to settings saved before them, and keeps the listener’s own', () => {
    const old = withDefaults({ pool: ['bars', 'scope', 'my-nebula', 'gone'] })
    expect(old.pool.slice(0, 3)).toEqual(['bars', 'scope', 'my-nebula'])
    expect(old.pool).toContain('drop-nebula-swirl')
    expect(old.pool).not.toContain('gone')
    expect(old.dropsOffered).toBe(true)
    // once offered, a listener who unticks them keeps them unticked
    const after = withDefaults({ pool: ['bars'], dropsOffered: true, moreOffered: true, novaOffered: true })
    expect(after.pool).toEqual(['bars'])
    // the visuals of 2026-10-23 join a pool saved before them once, as the Drop presets did
    const before = withDefaults({ pool: ['bars'], dropsOffered: true, novaOffered: true })
    expect(before.pool).toContain('matrix')
    expect(before.pool).toContain('drop-hypno-disc')
    expect(before.pool).not.toContain('drop-nebula-swirl')
    expect(before.moreOffered).toBe(true)
    // and so do Plenio Nova's (2026-10-29)
    const novaBefore = withDefaults({ pool: ['bars'], dropsOffered: true, moreOffered: true })
    expect(novaBefore.pool).toEqual(expect.arrayContaining(['bars', 'nova-hyperspace', 'nova-black-hole', 'nova-pulsar']))
    expect(novaBefore.pool).not.toContain('matrix')
    expect(novaBefore.novaOffered).toBe(true)
    expect(withDefaults({ dropScale: 3 }).dropScale).toBe(0.75)
  })
})

describe('the guide to writing presets', () => {
  it('has examples that work as they are written', () => {
    const guide = readFileSync(new URL('../../docs/user/concepts/player-visuals.md', import.meta.url), 'utf-8')
    const blocks = [...guide.matchAll(/```json\n([\s\S]*?)```/g)].map((m) => m[1].trim())
    expect(blocks.length).toBeGreaterThanOrEqual(5)
    for (const block of blocks) {
      // a whole preset, or a part of one (keys to put into a preset)
      const text = block.startsWith('{') ? block : `{ "name": "Example", ${block} }`
      const def = readPreset(text)
      const p = paramsOf(def, music({ beat: true, pulse: 1 }), {})
      for (const value of Object.values(p)) if (typeof value === 'number') expect(Number.isFinite(value)).toBe(true)
    }
  })
})
