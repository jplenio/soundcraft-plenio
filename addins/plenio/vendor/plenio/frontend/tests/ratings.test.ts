/** Every song rated 0 to 5 (owner's request 2026-10-29): the listener's own stars, given by ear and kept with their
 * state - two pages saving at once keep each side's - and the measured ones as a faded pre-fill until then. */
import { type App, createApp, h, nextTick, ref } from 'vue'
import { afterEach, describe, expect, it } from 'vitest'

import type { PlayerState } from '../src/player/api'
import Stars from '../src/player/components/Stars.vue'
import { mergeState } from '../src/player/stateMerge'
import { ratingsOf, setRating, state } from '../src/player/store'

const empty = (over: Partial<PlayerState>): PlayerState => ({ playlists: [], favorites: [], plays: {}, last_played: {}, tags: {}, settings: {}, ratings: {}, ...over })

let app: App | null = null
afterEach(() => {
  app?.unmount()
  app = null
  document.body.innerHTML = ''
})

function mount(rating: number | null, measured: number | null) {
  const given = ref<(number | null)[]>([])
  const host = document.createElement('div')
  document.body.append(host)
  app = createApp({ render: () => h(Stars, { rating, measured, editable: true, onRate: (v: number | null) => given.value.push(v) }) })
  app.mount(host)
  return { host, given }
}

describe('the stars', () => {
  it('keeps each song’s stars from the side that gave them', () => {
    const merged = mergeState(empty({ ratings: { s1: 3, s2: 4 } }), empty({ ratings: { s1: 3.5, s2: 4 } }), empty({ ratings: { s1: 3, s3: 5 } }))
    // s1 changed here, s3 given there, s2 taken back there
    expect(merged.ratings).toEqual({ s1: 3.5, s3: 5 })
  })

  it('keeps them 0 to 5 in halves', () => {
    expect(ratingsOf({ a: 3.3, b: 0, c: 7, d: 'x', e: -1 })).toEqual({ a: 3.5, b: 0 })
    expect(ratingsOf(null)).toEqual({})
    setRating('s9', 4.24)
    expect(state.ratings?.s9).toBe(4)
    setRating('s9', null)
    expect(state.ratings?.s9).toBeUndefined()
  })

  it('shows the measured stars faded until the listener gives their own', async () => {
    const { host, given } = mount(null, 3.5)
    const box = host.querySelector('.stars') as HTMLElement
    expect(box.classList.contains('faded')).toBe(true)
    const fills = [...host.querySelectorAll('.fill')].map((f) => (f as HTMLElement).style.width)
    expect(fills).toEqual(['100%', '100%', '100%', '50%', '0%'])
    // a click on the fourth star's right half: four stars; its left half: three and a half
    const fourth = host.querySelectorAll('.star')[3] as HTMLElement
    fourth.getBoundingClientRect = () => ({ left: 100, width: 20, top: 0, height: 20, right: 120, bottom: 20, x: 100, y: 0, toJSON: () => ({}) })
    fourth.dispatchEvent(new MouseEvent('click', { clientX: 115, bubbles: true }))
    fourth.dispatchEvent(new MouseEvent('click', { clientX: 104, bubbles: true }))
    ;(host.querySelector('.zero') as HTMLElement).click()
    await nextTick()
    expect(given.value).toEqual([4, 3.5, 0])
  })

  it('shows the listener’s own stars clearly, with a way to take them back', () => {
    const { host, given } = mount(2, 4.5)
    expect((host.querySelector('.stars') as HTMLElement).classList.contains('faded')).toBe(false)
    expect([...host.querySelectorAll('.fill')].map((f) => (f as HTMLElement).style.width)).toEqual(['100%', '100%', '0%', '0%', '0%'])
    ;(host.querySelector('.clear') as HTMLElement).click()
    expect(given.value).toEqual([null])
  })
})
