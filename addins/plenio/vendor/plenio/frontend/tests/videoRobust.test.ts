import { describe, expect, it } from 'vitest'

import { retryable, videoError } from '../src/player/jobs'

describe('a video that failed (owner 2026-10-28: "out of memory" now and then)', () => {
  it('is tried once more unless the browser cannot encode at all', () => {
    expect(retryable(new Error('Out of memory'))).toBe(true)
    expect(retryable(new DOMException('Encoding error', 'EncodingError'))).toBe(true)
    expect(retryable(new Error('This browser cannot encode H.264 at 3840 × 2160, 60 frames a second.'))).toBe(false)
    expect(retryable(new Error('This browser cannot encode video (WebCodecs): use a current Chrome or Edge.'))).toBe(false)
  })
  it('says what to do when the memory ran out', () => {
    expect(videoError(new Error('Out of memory'))).toMatch(/smaller size|Close other tabs/)
    expect(videoError(new Error('the song could not be read'))).toBe('the song could not be read')
  })
})
