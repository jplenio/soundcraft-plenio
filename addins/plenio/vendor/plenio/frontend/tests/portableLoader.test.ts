/** A large shared player (owner's request 2026-10-18: a 2 GB file on a phone): the file's own loader - the very
 * text plenio/player/package.py writes - takes each song's page and the files' pieces as they are read, and the
 * player asks it: what arrived is there at once, what has not waits for it, and a song plays when it is in. */
import { afterEach, describe, expect, it, vi } from 'vitest'

// the loader as package.py writes it - read with Node's own fs (the page's test world has none of its own)
const fs = (process as unknown as { getBuiltinModule(name: string): typeof import('node:fs') }).getBuiltinModule('node:fs')
const packagePy = fs.readFileSync(`${process.cwd()}/../plenio/player/package.py`, 'utf-8')

const DATA = {
  format: 'plenio.portable/2',
  id: 'big1',
  title: 'Big',
  created: '2026-10-18T10:00:00',
  plenio: '1.0.0',
  bitrate: 128,
  songs: [{ id: 's1', title: 'First' }, { id: 's2', title: 'Second' }],
  details: {},
  peaks: {},
  settings: {},
  presets: [],
  playlists: [],
  tags: { s1: ['party'] },
  files: { audio: 2, cover: 1, pdf: 0 },
}

/** The loader as package.py writes it, for ``total`` files. */
function loaderText(total: number): string {
  const text = /LOADER = """([\s\S]*?)"""/.exec(packagePy)?.[1]
  if (!text) throw new Error('no loader in package.py')
  return text.replace('%(total)d', String(total)).replace('%(piece)d', String(512 * 1024))
}

type Loader = {
  d(id: string, text: string): void
  b(kind: string, id: string, mime: string, last: number, data: string): void
  end(): void
}
const b64 = (text: string): string => btoa(text)

afterEach(() => {
  document.body.innerHTML = ''
  delete (window as unknown as { __plenio?: unknown }).__plenio
  vi.resetModules()
  vi.unstubAllGlobals()
})

async function bigPage(): Promise<{ loader: Loader; api: typeof import('../src/player/api'); portable: typeof import('../src/player/portable') }> {
  let made = 0
  vi.stubGlobal('URL', Object.assign(URL, { createObjectURL: () => `blob:test/${++made}` }))
  document.body.innerHTML = `<div id="app"></div><script type="application/json" id="plenio-portable">${JSON.stringify(DATA)}</script>`
  window.eval(loaderText(3))
  const loader = (window as unknown as { __plenio: Loader }).__plenio
  // pieces read before the player starts
  loader.d('s1', JSON.stringify({ detail: { id: 's1', title: 'First', lines: [] }, peaks: [0.2, 0.9] }))
  loader.b('c', 's1', 'image/jpeg', 1, b64('jpeg'))
  vi.resetModules()
  const api = await import('../src/player/api')
  const portable = await import('../src/player/portable')
  return { loader, api, portable }
}

describe('a large shared player', () => {
  it('is read with the loader the file brings, and starts before the songs have all arrived', async () => {
    const { loader, api, portable } = await bigPage()
    expect(portable.isPortable).toBe(true)
    expect((await api.api.library()).songs.map((s) => s.title)).toEqual(['First', 'Second'])
    // what came before the player started is there at once
    expect((await api.api.song('s1')).title).toBe('First')
    expect((await api.api.peaks('s1')).peaks).toEqual([0.2, 0.9])
    expect(api.media('s1', 'cover')).toMatch(/^blob:/)
    expect(portable.loading).toMatchObject({ got: 1, total: 3, done: false })
    // a song still on its way: its page and its sound wait for it
    expect(portable.mediaArrived('s2')).toBe(false)
    const page = api.api.song('s2')
    const sound = api.mediaReady('s2', 'audio')
    loader.d('s2', JSON.stringify({ detail: { id: 's2', title: 'Second', lines: [] }, peaks: null }))
    loader.b('a', 's2', 'audio/mpeg', 0, b64('ID3 first half'))
    expect(portable.mediaArrived('s2')).toBe(false) // half of it is no song yet
    loader.b('a', 's2', 'audio/mpeg', 1, b64('second half'))
    expect((await page).title).toBe('Second')
    expect(await sound).toMatch(/^blob:/)
    expect(portable.mediaArrived('s2')).toBe(true)
    expect(portable.loading.got).toBe(2)
    // the end: what never came is no song, and the waiting ends
    const missing = api.mediaReady('s1', 'audio')
    loader.end()
    expect(await missing).toBe('')
    expect(portable.loading.done).toBe(true)
  })

  it('takes a piece from the text block before its script, and empties both', async () => {
    const { loader, api } = await bigPage()
    const block = document.createElement('script')
    block.type = 'text/plain'
    block.textContent = b64('a whole song')
    const script = document.createElement('script')
    document.body.append(block, script)
    Object.defineProperty(document, 'currentScript', { configurable: true, get: () => script })
    ;(loader as unknown as { t(kind: string, id: string, mime: string, last: number): void }).t('a', 's1', 'audio/mpeg', 1)
    Object.defineProperty(document, 'currentScript', { configurable: true, get: () => null })
    expect(await api.mediaReady('s1', 'audio')).toMatch(/^blob:/)
    // the text and both scripts are gone from the page
    expect(block.isConnected || script.isConnected).toBe(false)
    expect(block.textContent).toBe('')
  })

  it('gives the listener the tags it was shared with', async () => {
    const { api } = await bigPage()
    expect((await api.api.state()).tags).toEqual({ s1: ['party'] })
  })
})
