import { beforeEach, describe, expect, it } from 'vitest'

import type { SongSummary } from '../src/player/api'
import { carryOut, shownToGuests, wishedAt } from '../src/player/guests'
import { qrModules } from '../src/player/qr'
import { index, library, queue, settings } from '../src/player/store'

function song(id: string): SongSummary {
  return { id, title: id.toUpperCase(), created: '', year: '', seconds: 120, model: 'YuE2', kind: 'song', brief: {}, genre: 'pop', mood: '', language: '', vocals: '', instrumental: false, arrangement: 'off', template: '', style: '', lyrics: '', loudness: { lufs: null, true_peak: null, range: null }, tags: {}, plenio: '1.0.0', folder: '', file: id, takes_key: '', has: { audio: true, original: false, cover: false, pdf: false, lines: false, notes: false, stems: false, timing: false, score: false }, seeds: {}, writer: '' }
}

describe("the guests' wishes, carried out by the player's page", () => {
  // owner's request 2026-10-17: guests in the network move, take out and add songs of the live playlist
  beforeEach(() => {
    library.value = ['aaaaaaaaaaaa', 'bbbbbbbbbbbb', 'cccccccccccc', 'dddddddddddd', 'eeeeeeeeeeee'].map(song)
    queue.value = ['aaaaaaaaaaaa', 'bbbbbbbbbbbb', 'cccccccccccc', 'dddddddddddd']
    index.value = 1 // b plays
    settings.live.on = true
  })

  it('moves, takes out and adds - never the song that plays or one already played', () => {
    expect(carryOut({ n: 1, op: 'up', id: 'dddddddddddd', at: 3 })).toBe('one up, by a guest')
    expect(queue.value).toEqual(['aaaaaaaaaaaa', 'bbbbbbbbbbbb', 'dddddddddddd', 'cccccccccccc'])
    expect(carryOut({ n: 2, op: 'up', id: 'dddddddddddd', at: 2 })).toBe('') // right after the song that plays
    expect(carryOut({ n: 3, op: 'down', id: 'dddddddddddd', at: 2 })).toBe('one down, by a guest')
    expect(carryOut({ n: 4, op: 'remove', id: 'aaaaaaaaaaaa', at: 0 })).toBe('') // played already
    expect(carryOut({ n: 5, op: 'remove', id: 'bbbbbbbbbbbb', at: 1 })).toBe('') // plays now
    expect(carryOut({ n: 6, op: 'remove', id: 'cccccccccccc', at: 2 })).toBe('taken out by a guest')
    expect(queue.value).toEqual(['aaaaaaaaaaaa', 'bbbbbbbbbbbb', 'dddddddddddd'])
    expect(carryOut({ n: 7, op: 'add', id: 'eeeeeeeeeeee', where: 'next' })).toBe('added by a guest, plays next')
    expect(queue.value).toEqual(['aaaaaaaaaaaa', 'bbbbbbbbbbbb', 'eeeeeeeeeeee', 'dddddddddddd'])
    expect(index.value).toBe(1)
  })

  it('finds a song that moved since the guest saw it, and does nothing while Live Play is off', () => {
    expect(wishedAt({ n: 1, op: 'up', id: 'dddddddddddd', at: 2 }, queue.value, index.value)).toBe(3)
    expect(wishedAt({ n: 1, op: 'up', id: 'aaaaaaaaaaaa', at: 0 }, queue.value, index.value)).toBe(-1)
    settings.live.on = false
    expect(carryOut({ n: 1, op: 'remove', id: 'dddddddddddd', at: 3 })).toBe('')
    expect(queue.value).toHaveLength(4)
  })

  it('tells the guests ids and places only', () => {
    const shown = shownToGuests() as { now: { id: string; at: number }; next: { id: string; at: number }[]; played: { id: string; at: number }[] }
    expect(shown.now).toEqual({ id: 'bbbbbbbbbbbb', at: 1 })
    expect(shown.next.map((x) => [x.id, x.at])).toEqual([['cccccccccccc', 2], ['dddddddddddd', 3]])
    expect(shown.played).toEqual([{ id: 'aaaaaaaaaaaa', at: 0 }])
    expect(JSON.stringify(shown)).not.toContain('CCCCCCCCCCCC') // no titles: the player adds them
  })
})

describe('QR codes', () => {
  it('a guests address fits a small code with its finder patterns and format', () => {
    const url = 'http://192.168.178.23:8770/AbCdEfGhIjKlMnOp/'
    const m = qrModules(url) as boolean[][]
    expect(m.length).toBe(33) // version 4 at level M (4 x 4 + 17 modules)
    // the three finder patterns: dark ring, light ring, dark core
    for (const [x, y] of [[0, 0], [m.length - 7, 0], [0, m.length - 7]]) {
      expect(m[y][x] && m[y + 6][x + 6] && !m[y + 1][x + 1] && m[y + 3][x + 3]).toBe(true)
    }
    // the timing patterns alternate, and the dark module is there
    for (let i = 8; i < m.length - 8; i++) expect(m[6][i]).toBe(i % 2 === 0)
    expect(m[m.length - 8][8]).toBe(true)
    expect(qrModules('x'.repeat(214))).toBeNull()
    expect(qrModules('x'.repeat(213))?.length).toBe(57) // version 10
  })
})
