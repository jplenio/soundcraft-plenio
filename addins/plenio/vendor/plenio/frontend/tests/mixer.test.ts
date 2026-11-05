/** The change from one visual to the next (owner's requests 2026-10-18: softly, to choose, one that brings both
 * together - organic and soft whatever the kind): both play on while the new one comes in. */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { Frame } from '../src/player/visuals/analysis'
import { quietFrame } from '../src/player/visuals/analysis'
import { withDefaults } from '../src/player/visuals/chooser'
import { FADE_STYLES, SceneMixer, ease, fadeWithDefaults, meltAt, noiseField, strokes, swirlAt, weights, type FadeStyle } from '../src/player/visuals/mixer'
import type { Colors, Preset } from '../src/player/visuals/presets'

/** A canvas context that does nothing but count its drawings (every method there, as on a real one). */
function fakeContext(): CanvasRenderingContext2D & { draws: number } {
  const state: Record<string, unknown> = { draws: 0, globalAlpha: 1, globalCompositeOperation: 'source-over' }
  return new Proxy(state, {
    get(target, key: string) {
      if (key in target) return target[key]
      if (key === 'drawImage' || key === 'fillRect') return () => void (target.draws = (target.draws as number) + 1)
      if (key === 'createImageData') return (w: number, h: number) => ({ data: new Uint8ClampedArray(w * h * 4) })
      if (key === 'createLinearGradient') return () => ({ addColorStop() {} })
      return () => undefined
    },
    set(target, key: string, value) {
      target[key] = value
      return true
    },
  }) as unknown as CanvasRenderingContext2D & { draws: number }
}

function preset(id: string, kind?: 'drop'): Preset & { frames: number } {
  const made = { id, name: id, blurb: '', suits: [], kind, frames: 0, create: () => ({ draw: () => void (made.frames += 1) }) }
  return made
}

const frame = (time: number, beat = false): Frame => ({ ...quietFrame(), time, dt: 1 / 30, beat, playing: true })
const colors = {} as Colors

beforeEach(() => {
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockImplementation(() => fakeContext() as never)
})
afterEach(() => vi.restoreAllMocks())

describe('the shapes of a change', () => {
  it('is slow at both ends', () => {
    expect([ease(0), ease(0.5), ease(1)]).toEqual([0, 0.5, 1])
    expect(ease(0.1)).toBeLessThan(0.1)
  })

  it('fades, zooms and slides the layers', () => {
    expect(strokes('fade', 0.5)).toEqual([{ layer: 'old', alpha: 1, scale: 1, shift: 0 }, { layer: 'new', alpha: 0.5, scale: 1, shift: 0 }])
    expect(strokes('slide', 1)[1]).toMatchObject({ layer: 'new', shift: 0 })
    expect(strokes('zoom', 0)[1]).toMatchObject({ alpha: 0, scale: 0.82 })
  })

  it('morphs with as much light all the way through - each as bright as the other half way', () => {
    for (const p of [0, 0.2, 0.5, 0.8, 1]) {
      const w = weights(p)
      expect(w.old ** 2 + w.new ** 2).toBeCloseTo(1)
    }
    expect(weights(0.5).old).toBeCloseTo(weights(0.5).new)
    expect(weights(0)).toEqual({ old: 1, new: 0 })
  })

  it('swirls a soft change most half way, never at its ends, and never a cut or a flash', () => {
    expect(swirlAt('blend', 0.5)).toBeCloseTo(0.5)
    expect(swirlAt('fade', 0.5)).toBeGreaterThan(0)
    expect(swirlAt('blend', 0)).toBe(0)
    expect(swirlAt('blend', 1)).toBe(0)
    expect(swirlAt('cut', 0.5)).toBe(0)
    expect(swirlAt('flash', 0.5)).toBe(0)
  })

  it('melts through a soft cloud: blots of several sizes, low places first, nothing before and all after', () => {
    let seed = 1
    const random = () => ((seed = (seed * 16807) % 2147483647) / 2147483647)
    const cloud = noiseField(64, 36, random)
    expect(Math.min(...cloud)).toBe(0)
    expect(Math.max(...cloud)).toBe(1)
    // neighbours are close (soft blots), not noise
    let jump = 0
    for (let i = 1; i < 64; i++) jump = Math.max(jump, Math.abs(cloud[i] - cloud[i - 1]))
    expect(jump).toBeLessThan(0.2)
    expect(meltAt(0, 0)).toBe(0)
    expect(meltAt(1, 1)).toBe(1)
    expect(meltAt(0.2, 0.5)).toBeGreaterThan(meltAt(0.8, 0.5))
    expect(meltAt(0.5, 0.5)).toBeCloseTo(0.5)
  })

  it('is kept with the visuals’ settings, checked - morph by default', () => {
    expect(fadeWithDefaults('melt', 4)).toEqual({ style: 'melt', seconds: 4 })
    expect(fadeWithDefaults('wipe', 99)).toEqual({ style: 'blend', seconds: 10 })
    expect(withDefaults(null)).toMatchObject({ fade: 'blend', fadeSeconds: 3 })
    expect(withDefaults({ fade: 'slide', fadeSeconds: 0.1 })).toMatchObject({ fade: 'slide', fadeSeconds: 0.3 })
  })
})

describe('the mixer', () => {
  it('plays both visuals while the new one comes in, over the time set, then only the new one', () => {
    for (const [style] of FADE_STYLES.filter(([s]) => s !== 'cut' && s !== 'flash')) {
      const mixer = new SceneMixer((p) => p.create())
      const a = preset('a')
      const b = preset('b')
      const ctx = fakeContext()
      mixer.use(a, { style: style as FadeStyle, seconds: 2 })
      mixer.draw(ctx, frame(10), 100, 50, colors)
      mixer.use(b, { style: style as FadeStyle, seconds: 2 })
      expect(mixer.changing).toBe(true)
      for (const t of [11, 11.5, 12, 12.5]) mixer.draw(ctx, frame(t), 100, 50, colors)
      expect([a.frames, b.frames]).toEqual([5, 4]) // the old one played on
      mixer.draw(ctx, frame(13.1), 100, 50, colors)
      expect(mixer.changing).toBe(false)
      mixer.draw(ctx, frame(13.2), 100, 50, colors)
      expect([a.frames, b.frames]).toEqual([5, 6])
      expect(ctx.draws).toBe(7) // one picture a frame
    }
  })

  it('picks another organic change each time for "a different one each time"', () => {
    const picks = [0.1, 0.9, 0.5, 0.3]
    const mixer = new SceneMixer((p) => p.create(), () => picks.shift() ?? 0)
    mixer.use(preset('a'), { style: 'random', seconds: 1 })
    const kinds: string[] = []
    for (const id of ['b', 'c', 'd', 'e']) {
      mixer.use(preset(id), { style: 'random', seconds: 1 })
      kinds.push(mixer.kind)
    }
    expect(kinds.every((k) => ['blend', 'melt', 'fade', 'zoom', 'slide'].includes(k))).toBe(true)
    for (let i = 1; i < kinds.length; i++) expect(kinds[i]).not.toBe(kinds[i - 1])
  })

  it('cuts at once, glides from Drop to Drop on one layer, and flashes on the next beat', () => {
    const mixer = new SceneMixer((p) => p.create())
    mixer.use(preset('a'), { style: 'blend', seconds: 2 })
    mixer.use(preset('b'), { style: 'cut', seconds: 2 })
    expect(mixer.changing).toBe(false)
    mixer.use(preset('d1', 'drop'), { style: 'cut', seconds: 2 })
    mixer.use(preset('d2', 'drop'), { style: 'blend', seconds: 2 })
    expect(mixer.changing).toBe(false) // the renderer glides by itself
    const old = preset('old')
    const next = preset('next')
    mixer.use(old, { style: 'cut', seconds: 1 })
    mixer.use(next, { style: 'flash', seconds: 1 })
    const ctx = fakeContext()
    mixer.draw(ctx, frame(0), 10, 10, colors)
    mixer.draw(ctx, frame(0.5), 10, 10, colors)
    expect([old.frames, next.frames]).toEqual([2, 0]) // waiting for a beat
    mixer.draw(ctx, frame(0.6, true), 10, 10, colors)
    expect(next.frames).toBe(1)
    expect(ctx.draws).toBe(4) // the new one and its glow
  })
})
