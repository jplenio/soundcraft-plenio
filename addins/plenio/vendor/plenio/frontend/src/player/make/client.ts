/**
 * The party songs' server routes (plenio/player/maker.py): the player's own (``/api/make``) or, on the party
 * guests' page, the guests' server's below its token (``../api/make``). Errors carry the server's words.
 */
import type { FormData, MakeJob, MakeRequest, MakeStatus, Remake, Source } from './form'

export interface MakeClient {
  status(everyone?: boolean): Promise<MakeStatus>
  form(): Promise<FormData>
  /** What the form starts from to make a song again. */
  remake(songId: string): Promise<Remake>
  create(body: MakeRequest): Promise<MakeJob>
  update(id: string, body: MakeRequest): Promise<MakeJob>
  move(id: string, by: -1 | 1): Promise<MakeJob>
  remove(id: string): Promise<MakeJob | { id: string; removed: true }>
  source(file: File): Promise<Source>
  settings(changes: Record<string, unknown>): Promise<{ settings: MakeStatus['settings'] }>
  /** A song waiting to be released: released (by its maker; approved by an admin), or not. */
  release(id: string): Promise<MakeJob>
  discard(id: string): Promise<MakeJob>
  /** Where a waiting song is heard first, and its cover. */
  listen(id: string): string
  cover(id: string): string
}

async function answer<T>(response: Response, what: string): Promise<T> {
  const data = await response.json().catch(() => null)
  if (!response.ok) throw new Error(typeof data?.error === 'string' ? data.error : `${what} (${response.status})`)
  return data as T
}

/** ``base``: where the routes are (``/api/make``, ``../api/make``); ``uploadHeader``: the header a recording is
 * sent with (the page's own, which another site's page cannot send). */
export function makeClient(base: string, uploadHeader: Record<string, string>): MakeClient {
  const send = (method: string, path: string, body?: unknown) =>
    fetch(`${base}${path}`, {
      method,
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
    })
  return {
    status: async (everyone = false) => answer<MakeStatus>(await fetch(`${base}${everyone ? '?all=1' : ''}`, { cache: 'no-store', credentials: 'same-origin' }), 'the songs could not be read'),
    form: async () => answer<FormData>(await fetch(`${base}/form`, { cache: 'no-store', credentials: 'same-origin' }), 'the form could not be read'),
    remake: async (songId) => answer<Remake>(await fetch(`${base}/from/${encodeURIComponent(songId)}`, { cache: 'no-store', credentials: 'same-origin' }), 'the song could not be read'),
    create: async (body) => answer<MakeJob>(await send('POST', '/jobs', body), 'the song could not be ordered'),
    update: async (id, body) => answer<MakeJob>(await send('PUT', `/jobs/${id}`, body), 'the song could not be changed'),
    move: async (id, by) => answer<MakeJob>(await send('POST', `/jobs/${id}/move`, { by }), 'the song could not move'),
    remove: async (id) => answer<MakeJob | { id: string; removed: true }>(await send('DELETE', `/jobs/${id}`), 'the song could not be removed'),
    source: async (file) =>
      answer<Source>(
        await fetch(`${base}/sources?name=${encodeURIComponent(file.name)}`, {
          method: 'POST',
          credentials: 'same-origin',
          headers: { 'Content-Type': 'application/octet-stream', ...uploadHeader },
          body: file,
        }),
        'the recording could not be sent'
      ),
    settings: async (changes) => answer<{ settings: MakeStatus['settings'] }>(await send('PUT', '/settings', changes), 'the settings could not be saved'),
    release: async (id) => answer<MakeJob>(await send('POST', `/jobs/${id}/release`, {}), 'the song could not be released'),
    discard: async (id) => answer<MakeJob>(await send('POST', `/jobs/${id}/discard`, {}), 'the song could not be set aside'),
    listen: (id) => `${base}/jobs/${id}/audio`,
    cover: (id) => `${base}/jobs/${id}/cover`,
  }
}
