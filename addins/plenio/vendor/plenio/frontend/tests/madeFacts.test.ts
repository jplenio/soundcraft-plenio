import { describe, expect, it } from 'vitest'

import type { SongSummary } from '../src/player/api'
import { dateTime, madeFacts, spanOf } from '../src/player/songFacts'

const song = (made: SongSummary['made'], created = '2026-10-28T14:05:09+0100') => ({ created, made, other: false }) as unknown as SongSummary

describe('how a song was made (owner 2026-10-28)', () => {
  it('names the date and time, how long it took, on what and the lyrics fidelity', () => {
    const facts = madeFacts(
      song({
        started: '2026-10-28T14:00:36+0100',
        seconds: 273,
        on: { device: 'gpu', gpu: 'NVIDIA GeForce RTX 5060 Ti', vram_gb: 15.9, cpu: 'AMD Ryzen 9 7950X', cores: 32, ram_gb: 61.6 },
        lyrics_fidelity: 'high',
      })
    )
    const by = Object.fromEntries(facts.map((f) => [f.label, f.value]))
    expect(by['Made']).toMatch(/2026/)
    expect(by['Making took']).toBe('4 min 33 s')
    expect(by['Graphics card']).toBe('NVIDIA GeForce RTX 5060 Ti · 15.9 GB')
    expect(by['Processor']).toBe('AMD Ryzen 9 7950X · 32 threads')
    expect(by['Memory (RAM)']).toBe('61.6 GB')
    expect(by['Lyrics fidelity']).toMatch(/^high/)
  })
  it('says a song made on the processor alone, and an older song has its saving time', () => {
    expect(madeFacts(song({ on: { device: 'cpu', cpu: 'Intel' } })).find((f) => f.label === 'Graphics card')?.value).toMatch(/processor alone/)
    const older = madeFacts(song(undefined))
    expect(older).toHaveLength(1)
    expect(older[0].note).toBe('when it was saved')
  })
  it('reads the records times and spans', () => {
    expect(dateTime('2026-10-28T14:05:09+0100')).not.toBe('')
    expect(dateTime('nonsense')).toBe('nonsense')
    expect(spanOf(45)).toBe('45 s')
    expect(spanOf(3900)).toBe('1 h 05 min')
  })
})

describe('a party song says when its party was (owner 2026-10-28: not "this party")', async () => {
  const { partyWhen, partyMaker } = await import('../src/player/make/form')
  it('names the date of the party, and nothing for another song', () => {
    const tags = { album: 'Party-Song 2026-10-27', artist: 'Guest' }
    expect(partyMaker(tags)).toBe('Guest')
    expect(partyWhen(tags)).toMatch(/^on .*2026/)
    expect(partyWhen({ album: 'My album' })).toBe('')
  })
})
