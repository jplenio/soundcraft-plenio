/** Live Play (owner's request 2026-10-16): where a song ComfyUI makes during a party goes in the live playlist. */
import { describe, expect, it } from 'vitest'

import { insertAt, liveWithDefaults } from '../src/player/liveSettings'

describe('Live Play', () => {
  it('puts new songs next in the order they came, at the end, or anywhere after the song that plays', () => {
    // a playlist of 6, the third (index 2) plays
    expect([0, 1, 2].map((k) => insertAt('next', 2, 6, k))).toEqual([3, 4, 5])
    expect(insertAt('end', 2, 6, 0)).toBe(6)
    expect(insertAt('next', 5, 6, 0)).toBe(6) // the last one plays: next is the end
    const places = new Set<number>()
    for (let k = 0; k < 200; k++) places.add(insertAt('random', 2, 6, 0))
    expect([...places].sort()).toEqual([3, 4, 5, 6]) // never before or in place of the song that plays
    expect(insertAt('random', 2, 6, 0, () => 0)).toBe(3)
    expect(insertAt('random', 2, 6, 0, () => 0.999)).toBe(6)
    // nothing plays: at the end
    expect(insertAt('next', -1, 0, 0)).toBe(0)
  })

  it('keeps its settings sane', () => {
    const way = { overVisual: true, wayInCorner: 'top-right', wayInSize: 'm' }
    expect(liveWithDefaults(null)).toEqual({ on: false, insert: 'next', auto: true, atEnd: 'again', ...way })
    expect(liveWithDefaults({ on: true, insert: 'sideways', atEnd: 'never', auto: false })).toEqual({ on: true, insert: 'next', auto: false, atEnd: 'again', ...way })
    // the guests' way in over the visual (owner's request 2026-10-18): on by default, its corner and size checked
    expect(liveWithDefaults({ overVisual: false, wayInCorner: 'middle', wayInSize: 'xl' })).toMatchObject({ overVisual: false, wayInCorner: 'top-right', wayInSize: 'm' })
    expect(liveWithDefaults({ wayInCorner: 'bottom-left', wayInSize: 'l' })).toMatchObject({ wayInCorner: 'bottom-left', wayInSize: 'l' })
    expect(liveWithDefaults({ insert: 'random', atEnd: 'wait' })).toMatchObject({ insert: 'random', atEnd: 'wait', auto: true })
  })
})
