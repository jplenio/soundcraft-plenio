/** A song as a video (owner's request 2026-10-16): the music's frames worked out from the decoded song, as
 * the live analyser gives them; the H.264 level for the size; the saved settings. */
import { describe, expect, it } from 'vitest'

import { levels, QUALITIES, SIZES, videoBitrate, videoSize, videoWithDefaults } from '../src/player/video/make'
import { OfflineAnalysis } from '../src/player/video/offline'

function tone(hz: number, seconds = 2, rate = 48000, amplitude = 0.5): { left: Float32Array; right: Float32Array; rate: number } {
  const left = new Float32Array(rate * seconds)
  for (let i = 0; i < left.length; i++) left[i] = amplitude * Math.sin((2 * Math.PI * hz * i) / rate)
  return { left, right: new Float32Array(left), rate }
}

describe('the video', () => {
  it('hears a song frame by frame as the live analyser would', () => {
    const analysis = new OfflineAnalysis(tone(440), 30)
    let frame = analysis.frame(0.5, 1 / 30, 0)
    for (let k = 1; k < 10; k++) frame = analysis.frame(0.5 + k / 30, 1 / 30, k / 30)
    // 440 Hz in a 2048-point FFT at 48 kHz: bin 18.8
    const peak = frame.freq.indexOf(Math.max(...frame.freq))
    expect(peak).toBeGreaterThanOrEqual(18)
    expect(peak).toBeLessThanOrEqual(19)
    expect(frame.freq[200]).toBeLessThan(frame.freq[peak] / 2)
    expect(Math.max(...frame.wave)).toBeGreaterThan(180)
    expect(Math.min(...frame.wave)).toBeLessThan(76)
    expect(frame.time).toBeCloseTo(9 / 30)
    expect(frame.playing).toBe(true)
    // silence before the song starts
    const quiet = new OfflineAnalysis(tone(440), 30).frame(0, 1 / 30, 0)
    expect(Math.max(...quiet.freq)).toBe(0)
    expect(quiet.bass).toBe(0)
  })

  it('asks the encoder for the H.264 level the size and frame rate need', () => {
    expect(levels(1920, 1080, 30)[0]).toBe('28')
    expect(levels(1920, 1080, 60)[0]).toBe('2A')
    expect(levels(1080, 1920, 30)[0]).toBe('28')
    expect(levels(3840, 2160, 30)[0]).toBe('33')
    expect(levels(3840, 2160, 60)).toEqual(['34'])
  })

  it('keeps its settings sane, and the part is chosen anew each time', () => {
    const kept = videoWithDefaults({ width: 1080, height: 1920, fps: 60, lyrics: 'karaoke', start: 30, length: 10 })
    expect(kept).toMatchObject({ width: 1080, height: 1920, fps: 60, lyrics: 'karaoke', start: 0, length: 0 })
    expect(videoWithDefaults({ width: 1234, height: 77, fps: 13, lyrics: 'loud', quality: 'max' })).toMatchObject({ width: 1920, height: 1080, fps: 30, lyrics: 'subtitles', quality: 'standard' })
    // a new visual every few seconds; settings of before (a new visual at every section) carry over
    expect(videoWithDefaults({ eachSection: true })).toMatchObject({ change: 'section' })
    expect(videoWithDefaults({ change: 'interval', interval: 1 })).toMatchObject({ change: 'interval', interval: 3 })
    expect(videoWithDefaults({ change: 'sometimes' }).change).toBe('never')
    // the lyrics' look: the video's own, else the player's
    expect(videoWithDefaults({}, { effect: 'neon', font: 'poster' }).lyricsStyle).toMatchObject({ effect: 'neon', font: 'poster' })
    expect(videoWithDefaults({ lyricsStyle: { effect: 'wave' } }, { effect: 'neon' }).lyricsStyle.effect).toBe('wave')
  })

  it('has quality levels from low to best and a bitrate of its own (owner’s request 2026-10-29)', () => {
    // settings of before: standard and high stay what they were
    const full = { width: 1920, height: 1080, fps: 30 }
    expect(videoBitrate({ ...full, quality: 'standard', bitrate: 0 })).toBe(Math.round(1920 * 1080 * 30 * 0.085))
    expect(videoBitrate({ ...full, quality: 'high', bitrate: 0 })).toBe(Math.round(1920 * 1080 * 30 * 0.15))
    const steps = QUALITIES.filter((q) => q.id !== 'custom').map((q) => videoBitrate({ ...full, quality: q.id, bitrate: 0 }))
    expect(steps).toEqual([...steps].sort((a, b) => a - b))
    expect(steps[0]).toBeLessThan(2.5e6)
    // a bitrate of one's own, kept within what H.264 at these sizes takes
    expect(videoBitrate({ ...full, quality: 'custom', bitrate: 8 })).toBe(8e6)
    expect(videoWithDefaults({ quality: 'custom', bitrate: 9999 }).bitrate).toBe(200)
    expect(videoWithDefaults({ quality: 'custom', bitrate: 'x' }).bitrate).toBe(12)
    expect(videoWithDefaults({ keyframes: 3, encoder: 'gpu', audio: 64 })).toMatchObject({ keyframes: 2, encoder: 'auto', audio: 192 })
    expect(videoWithDefaults({ keyframes: 8, encoder: 'software', audio: 320, constant: true })).toMatchObject({ keyframes: 8, encoder: 'software', audio: 320, constant: true })
    // the file's size: a constant rate keeps its aim, a variable one stays below it; the sound counts too
    const minute = (o: object) => videoSize({ ...full, quality: 'custom', bitrate: 8, constant: false, audio: 192, ...o }, 60)
    expect(minute({ constant: true })).toBe(((8e6 + 192000) * 60) / 8)
    expect(minute({})).toBeLessThan(minute({ constant: true }))
    expect(minute({ audio: 320 })).toBeGreaterThan(minute({}))
  })

  it('offers sizes the H.264 levels take', () => {
    for (const size of SIZES) {
      for (const fps of [24, 25, 30, 50, 60]) expect(levels(size.width, size.height, fps).length, `${size.id} at ${fps}`).toBeGreaterThan(0)
    }
    expect(videoWithDefaults({ width: 1080, height: 1350 })).toMatchObject({ width: 1080, height: 1350 })
    expect(videoWithDefaults({ width: 2160, height: 3840, fps: 25 })).toMatchObject({ width: 2160, height: 3840, fps: 25 })
  })
})
