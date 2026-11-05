/** The video's visual plan (owner's request 2026-10-25): its slots - one, every section, every so many seconds -
 * each slot's visual chosen or at random from a seed, sections of one name alike; and the new looks' settings. */
import { describe, expect, it } from 'vitest'

import { fadeAt, barHeight, lookWithDefaults } from '../src/player/video/looks'
import { resolvePlan, sectionKind, seeded, setPick, slotAt, slotsOf, type Slot } from '../src/player/video/plan'
import { videoWithDefaults } from '../src/player/video/make'
import type { TimedSection } from '../src/player/timing'

const SECTIONS: TimedSection[] = [
  { label: 'intro', start: 0, bar: 1, at: 0 },
  { label: 'verse 1', start: 8, bar: 5, at: 9 },
  { label: 'chorus 1', start: 30, bar: 16, at: 31 },
  { label: 'verse 2', start: 50, bar: 26, at: 52 },
  { label: 'chorus 2', start: 70, bar: 36, at: 73 },
  { label: 'outro', start: 90, bar: 46, at: 95 },
]
const name = (label: string): string => label.replace(/^\w/, (c) => c.toUpperCase())

describe('the plan of the visuals', () => {
  it('makes one slot, a slot per section, or one every so many seconds', () => {
    expect(slotsOf('never', 20, SECTIONS, 0, 120)).toEqual([{ index: 0, start: 0, end: 120, label: 'The whole video', kind: 'all' }])
    const sections = slotsOf('section', 20, SECTIONS, 0, 120, name)
    expect(sections.map((s) => [s.label, s.start, s.end, s.kind])).toEqual([
      ['Intro', 0, 9, 'intro'],
      ['Verse 1', 9, 31, 'verse'],
      ['Chorus 1', 31, 52, 'chorus'],
      ['Verse 2', 52, 73, 'verse'],
      ['Chorus 2', 73, 95, 'chorus'],
      ['Outro', 95, 120, 'outro'],
    ])
    // a part of the song: the sections in it, the first from the part's start
    const part = slotsOf('section', 20, SECTIONS, 40, 40, name)
    expect(part.map((s) => [s.label, s.start, s.end])).toEqual([['Chorus 1', 40, 52], ['Verse 2', 52, 73], ['Chorus 2', 73, 80]])
    const spans = slotsOf('interval', 25, SECTIONS, 10, 60)
    expect(spans.map((s) => [s.start, s.end, s.label])).toEqual([[10, 35, '0:10 - 0:35'], [35, 60, '0:35 - 1:00'], [60, 70, '1:00 - 1:10']])
    // no sections: one slot
    expect(slotsOf('section', 20, [], 0, 50)).toHaveLength(1)
  })

  it('finds the slot of a moment and the kind of a section', () => {
    const slots = slotsOf('section', 20, SECTIONS, 0, 120, name)
    expect([slotAt(slots, 0), slotAt(slots, 30.9), slotAt(slots, 31), slotAt(slots, 119)]).toEqual([0, 1, 2, 5])
    expect([sectionKind('Chorus 2'), sectionKind('Pre-Chorus'), sectionKind('Verse')]).toEqual(['chorus', 'pre chorus', 'verse'])
  })

  it('takes the visuals chosen and draws the others from the seed, never the one just before', () => {
    const slots: Slot[] = slotsOf('section', 20, SECTIONS, 0, 120, name)
    const pool = ['a', 'b', 'c', 'd']
    const exists = (id: string) => pool.includes(id) || id === 'mine'
    const plan = resolvePlan(slots, [], pool, 7, false, exists)
    expect(plan).toHaveLength(6)
    expect(plan.every((id, k) => k === 0 || id !== plan[k - 1])).toBe(true)
    expect(resolvePlan(slots, [], pool, 7, false, exists)).toEqual(plan) // the same seed, the same visuals
    expect(resolvePlan(slots, [], pool, 8, false, exists)).not.toEqual(plan)
    const chosen = resolvePlan(slots, ['', 'mine', '', '', '', ''], pool, 7, false, exists)
    expect(chosen[1]).toBe('mine')
    // a visual chosen keeps the others where they were
    expect([chosen[0], chosen[3], chosen[5]]).toEqual([plan[0], plan[3], plan[5]])
    // a visual that no longer exists counts as at random
    expect(resolvePlan(slots, ['gone'], pool, 7, false, exists)[0]).toBe(plan[0])
  })

  it('gives sections of one name one visual', () => {
    const slots = slotsOf('section', 20, SECTIONS, 0, 120, name)
    const plan = resolvePlan(slots, [], ['a', 'b', 'c', 'd', 'e'], 3, true, () => true)
    expect(plan[3]).toBe(plan[1]) // verse 2 as verse 1
    expect(plan[4]).toBe(plan[2]) // chorus 2 as chorus 1
    const picks = setPick(slots, [], 4, 'x', true)
    expect(picks).toEqual(['', '', 'x', '', 'x', ''])
    expect(setPick(slots, picks, 2, 'y', false)).toEqual(['', '', 'y', '', 'x', ''])
  })

  it('draws numbers from a seed', () => {
    const a = seeded(42)
    const b = seeded(42)
    const first = [a(), a(), a()]
    expect([b(), b(), b()]).toEqual(first)
    expect(first.every((x) => x >= 0 && x < 1)).toBe(true)
  })
})

describe('the video settings', () => {
  it('keep what was set before and check the new ones', () => {
    const old = videoWithDefaults({ visual: 'plasma', change: 'section', interval: 12 })
    expect(old).toMatchObject({ visual: 'plasma', change: 'section', interval: 12, picks: [], randomFrom: 'pool', repeats: true, changeOnBeat: true })
    expect(old.look).toEqual(lookWithDefaults(null))
    const odd = videoWithDefaults({ picks: ['a', 3, 'b'], randomFrom: 'x', seed: -1, look: { backdrop: 4, reactivity: 0.1, bars: 1 } })
    expect(odd.picks).toEqual(['a', '', 'b'])
    expect(odd.randomFrom).toBe('pool')
    expect(odd.seed).toBe(1)
    expect(odd.look).toMatchObject({ backdrop: 1, reactivity: 0.5, bars: true, fades: true })
  })

  it('fade from and to black, and cinema bars on a wide picture only', () => {
    expect(fadeAt(0, 60)).toBe(1)
    expect(fadeAt(0.6, 60)).toBeCloseTo(0.5)
    expect(fadeAt(30, 60)).toBe(0)
    expect(fadeAt(59, 60)).toBeCloseTo(0.5)
    expect(barHeight(1920, 1080)).toBe(138)
    expect(barHeight(1080, 1920)).toBe(0)
  })
})
