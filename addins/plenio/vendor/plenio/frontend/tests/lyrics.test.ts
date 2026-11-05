/** How the lyrics look (owner's request 2026-10-16): fonts, colours, sizes and effects, kept sane; a line shows
 * each syllable as sung, being sung or to come, and breaks between words only. */
import { afterEach, describe, expect, it } from 'vitest'
import { type App, createApp, h, nextTick } from 'vue'

import type { TimedLine } from '../src/player/api'
import LyricLine from '../src/player/components/LyricLine.vue'
import { EFFECTS, FONTS, fontOf, litColor, lyricsWithDefaults } from '../src/player/lyricsStyle'

// "walking down the river": syllables wal-king at 1.0 / 1.3, down 1.6, the 2.0, ri-ver 2.4 / 2.8
const LINE: TimedLine = {
  text: 'walking down the river',
  start: 1,
  end: 3.2,
  units: [[1.0, 3], [1.3, 8], [1.6, 13], [2.0, 17], [2.4, 19], [2.8, 22]],
}

let app: App | null = null
afterEach(() => {
  app?.unmount()
  app = null
  document.body.innerHTML = ''
})

async function line(time: number, effect: string): Promise<HTMLElement> {
  const host = document.createElement('div')
  document.body.appendChild(host)
  app = createApp({ render: () => h(LyricLine, { line: LINE, time, effect, pulse: 0 }) })
  app.mount(host)
  await nextTick()
  return host
}

describe('the lyrics’ look', () => {
  it('keeps its settings sane', () => {
    expect(lyricsWithDefaults(null)).toEqual({ font: 'clean', own: '', effect: 'sweep', color: 'white', size: 1 })
    expect(lyricsWithDefaults({ font: 'comic', effect: 'explode', color: 'mud', size: 9 })).toMatchObject({ font: 'clean', effect: 'sweep', color: 'white', size: 1.6 })
    expect(lyricsWithDefaults({ font: 'own', own: 'Bauhaus 93"; color: red' }).own).toBe('Bauhaus 93 color: red')
    expect(fontOf(lyricsWithDefaults({ font: 'own', own: 'Bauhaus 93' })).stack.startsWith('"Bauhaus 93", ')).toBe(true)
    expect(fontOf(lyricsWithDefaults({ font: 'own', own: '' })).stack).toBe(FONTS[0].stack)
    expect(litColor(lyricsWithDefaults({ color: 'song' }), '#123456')).toBe('#123456')
    expect(litColor(lyricsWithDefaults({ color: 'gold' }), '#123456')).toBe('#ffd36b')
    expect(EFFECTS.length).toBeGreaterThanOrEqual(10)
  })

  it('shows each syllable as sung, being sung or to come', async () => {
    const host = await line(1.7, 'bounce')
    const states = [...host.querySelectorAll('.chunk')].map((c) => `${c.textContent}:${[...c.classList].find((k) => k !== 'chunk')}`)
    expect(states).toEqual(['wal:sung', 'king:sung', 'down:singing', 'the:unsung', 'ri:unsung', 'ver:unsung'])
    expect(host.querySelector('.lyric')?.classList.contains('fx-bounce')).toBe(true)
  })

  it('breaks between words only: the syllables of a word stay together', async () => {
    const host = await line(2.5, 'sweep')
    const words = [...host.querySelectorAll('.word')].map((w) => w.textContent)
    expect(words).toEqual(['walking', 'down', 'the', 'river'])
    expect(host.querySelector('.lyric')?.textContent).toBe('walking down the river')
  })

  it('types the line letter by letter as it is sung', async () => {
    const host = await line(1.45, 'typewriter')
    const lit = [...host.querySelectorAll('.letter.lit')].map((l) => l.textContent).join('')
    expect(lit.startsWith('wal')).toBe(true)
    expect(lit.length).toBeLessThan('walking'.length + 1)
    expect(host.querySelectorAll('.letter.last')).toHaveLength(1)
  })
})
