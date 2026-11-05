/** What is being made (owner's request 2026-10-18): videos one after the other in this page, shared players by
 * the server - both in one list with how far each is, and a stop for each. */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { SongSummary } from '../src/player/api'

type Run = { song: string; resolve: (v: { file: string; size: number; folder: string }) => void; reject: (e: unknown) => void; progress: (p: object) => void }
const runs: Run[] = []

vi.mock('../src/player/video/make', () => ({
  makeVideo: (song: { id: string }, _options: unknown, progress: (p: object) => void, signal: AbortSignal) =>
    new Promise((resolve, reject) => {
      runs.push({ song: song.id, resolve, reject, progress })
      signal.addEventListener('abort', () => reject(new DOMException('stopped', 'AbortError')))
    }),
}))

const song = (id: string): SongSummary => ({ id, title: id.toUpperCase(), seconds: 200 }) as SongSummary
const OPTIONS = { width: 1920, height: 1080, fps: 30, start: 0, length: 0 } as never
const tick = () => new Promise((r) => setTimeout(r, 0))

beforeEach(() => {
  runs.length = 0
  vi.resetModules()
})
afterEach(() => vi.unstubAllGlobals())

describe('the queue', () => {
  it('makes videos one after the other, the oldest first, and stops a waiting one or the one at work', async () => {
    const { jobs, queueVideo, stopJob, videosAtWork, progressText } = await import('../src/player/jobs')
    const a = queueVideo(song('a'), OPTIONS)
    const b = queueVideo(song('b'), OPTIONS)
    const c = queueVideo(song('c'), OPTIONS)
    await tick()
    expect([a.state, b.state, c.state]).toEqual(['working', 'waiting', 'waiting'])
    expect(runs.map((r) => r.song)).toEqual(['a'])
    expect(videosAtWork.value).toBe(true)
    expect(a.detail).toBe('1920 × 1080 · 30 fps · the whole song')
    runs[0].progress({ stage: 'Drawing and encoding', frame: 30, total: 300, speed: 2, left: 10 })
    expect(progressText(a)).toBe('Drawing and encoding · frame 30 of 300')
    // a waiting one stopped never starts
    await stopJob(b)
    expect(b.state).toBe('stopped')
    runs[0].resolve({ file: 'A (1920x1080).mp4', size: 9, folder: 'videos' })
    await tick()
    await tick()
    expect(a.state).toBe('done')
    expect(a.file).toBe('A (1920x1080).mp4')
    expect(runs.map((r) => r.song)).toEqual(['a', 'c'])
    // the one at work stops
    await stopJob(c)
    await tick()
    await tick()
    expect(c.state).toBe('stopped')
    expect(videosAtWork.value).toBe(false)
    expect(jobs.value.map((j) => j.title)).toEqual(['A', 'B', 'C'])
  })

  it('puts shared players in the server’s queue and follows them', async () => {
    const answers: Record<string, unknown> = {
      'POST /api/package': { job: '0123456789abcdef' },
      'GET /api/package-jobs': { jobs: [{ job: '0123456789abcdef', state: 'working', stage: 'packing', done: 1, total: 2 }] },
    }
    const calls: string[] = []
    vi.stubGlobal('fetch', async (url: string, init?: RequestInit) => {
      const key = `${init?.method ?? 'GET'} ${url}`
      calls.push(key)
      return new Response(JSON.stringify(answers[key] ?? { ok: true }), { status: 200 })
    })
    vi.useFakeTimers()
    const { queuePackage, stopJob, progressText, progressOf } = await import('../src/player/jobs')
    const job = await queuePackage({ songs: ['a', 'b'], title: 'Party', bitrate: 160, pdf: false })
    expect(job).toMatchObject({ kind: 'package', title: 'Party', state: 'waiting', detail: '2 songs · MP3 160 kbit/s' })
    await vi.advanceTimersByTimeAsync(800)
    expect(job.state).toBe('working')
    expect(progressText(job)).toBe('packing song 2 of 2')
    expect(progressOf(job)).toBeCloseTo(0.55)
    await stopJob(job)
    expect(calls).toContain('POST /api/package/0123456789abcdef/cancel')
    answers['GET /api/package-jobs'] = { jobs: [{ job: '0123456789abcdef', state: 'stopped', done: 1, total: 2 }] }
    await vi.advanceTimersByTimeAsync(800)
    expect(job.state).toBe('stopped')
    vi.useRealTimers()
  })
})
