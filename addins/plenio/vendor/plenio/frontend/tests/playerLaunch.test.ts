import { describe, expect, it, vi } from 'vitest'

import { PLAYER_TAB, installContinueFromPlayer, openPlayer, playerAddress, trustedOrigin } from '../src/extension/player'

function fetcher(answer: unknown, ok = true) {
  return {
    fetchApi: vi.fn(async () => ({ ok, status: ok ? 200 : 400, json: async () => answer }) as unknown as Response),
  }
}

describe('the Plenio Player from ComfyUI', () => {
  it('sends the tab to the library or to a record, always with a fragment', () => {
    expect(playerAddress('http://127.0.0.1:8765/')).toBe('http://127.0.0.1:8765/#/')
    expect(playerAddress('http://127.0.0.1:8765', 'C:\\out\\plenio\\A b.plenio.json')).toBe(
      'http://127.0.0.1:8765/#/record/C%3A%5Cout%5Cplenio%5CA%20b.plenio.json'
    )
  })

  it('opens the named tab inside the click and sends it to the player when the server answers', async () => {
    const tab = { location: { href: 'about:blank' }, document: { title: '', body: { textContent: '', style: { cssText: '' } } }, focus: vi.fn(), close: vi.fn() }
    const opener = { open: vi.fn(() => tab as unknown as Window) }
    const toast = vi.fn()
    const host = { app: { registerExtension() {}, extensionManager: { toast: { add: toast } } }, fetcher: fetcher({ url: 'http://127.0.0.1:8765/', started: true, version: '0.8.1' }) }
    await openPlayer(host, '/out/x.plenio.json', opener)
    expect(opener.open).toHaveBeenCalledWith('', PLAYER_TAB)
    expect(host.fetcher.fetchApi).toHaveBeenCalledWith('/plenio/player/open', expect.objectContaining({ method: 'POST' }))
    expect(tab.document.body.textContent).toContain('Starting the Plenio Player')
    expect(tab.document.body.style.cssText).toContain('background:#0a0910')
    expect(tab.location.href).toBe('http://127.0.0.1:8765/#/record/%2Fout%2Fx.plenio.json')
    expect(toast).toHaveBeenCalledWith(expect.objectContaining({ summary: 'Plenio Player started' }))
  })

  it('leaves a tab that shows the player already where it is, and closes a blank one when the start fails', async () => {
    const shown = {
      get location(): { href: string } {
        throw new Error('another origin')
      },
      focus: vi.fn(),
    }
    const host = { app: { registerExtension() {} }, fetcher: fetcher({ url: 'http://127.0.0.1:8765/', started: false, version: '0.8.1' }) }
    await openPlayer(host, null, { open: () => shown as unknown as Window })
    expect(shown.focus).toHaveBeenCalled()

    const blank = { location: { href: 'about:blank' }, document: { title: '', body: { textContent: '', style: { cssText: '' } } }, focus: vi.fn(), close: vi.fn() }
    const toast = vi.fn()
    const failing = { app: { registerExtension() {}, extensionManager: { toast: { add: toast } } }, fetcher: fetcher({ error: { message: 'did not start', hint: 'look at the log' } }, false) }
    await openPlayer(failing, null, { open: () => blank as unknown as Window })
    expect(blank.close).toHaveBeenCalled()
    expect(toast).toHaveBeenCalledWith(expect.objectContaining({ severity: 'error', detail: expect.stringContaining('look at the log') }))
  })

  it('takes a song only from its own origin or a player on this computer', () => {
    expect(trustedOrigin('http://127.0.0.1:8765', 'http://127.0.0.1:8188')).toBe(true)
    expect(trustedOrigin('http://localhost:8765', 'http://127.0.0.1:8188')).toBe(true)
    expect(trustedOrigin('http://[::1]:8765', 'http://127.0.0.1:8188')).toBe(true)
    expect(trustedOrigin('http://192.168.0.5:8188', 'http://192.168.0.5:8188')).toBe(true)
    expect(trustedOrigin('https://evil.example', 'http://127.0.0.1:8188')).toBe(false)
    expect(trustedOrigin('null', 'http://127.0.0.1:8188')).toBe(false)
    // ComfyUI opened from the network by the player's gateway: the player's gateway on the same computer
    expect(trustedOrigin('http://192.168.0.5:8780', 'http://192.168.0.5:8781')).toBe(true)
    expect(trustedOrigin('http://192.168.0.6:8780', 'http://192.168.0.5:8781')).toBe(false)
  })

  it('opened by the player, says it is ready and continues the song the player sends', async () => {
    vi.useFakeTimers()
    const listeners: ((event: MessageEvent) => void)[] = []
    const opener = { postMessage: vi.fn() }
    const win = {
      location: { search: '?plenio=continue', pathname: '/', hash: '', origin: 'http://127.0.0.1:8188' },
      history: { state: null, replaceState: vi.fn() },
      opener,
      addEventListener: (_: string, f: (event: MessageEvent) => void) => listeners.push(f),
      removeEventListener: vi.fn(),
      setTimeout: (f: () => void, ms: number) => setTimeout(f, ms),
    }
    const record = { schema: 'plenio.record/1', title: 'River' }
    const plan = { workflow: null, documents: {}, title: 'River', sheets: {} }
    const host = {
      app: { registerExtension() {}, graph: { nodes: [] }, extensionManager: { toast: { add: vi.fn() } } },
      fetcher: fetcher(plan),
    }
    expect(installContinueFromPlayer(host as never, win as unknown as Window, 10)).toBe(true)
    expect(win.history.replaceState).toHaveBeenCalledWith(null, '', '/')
    vi.advanceTimersByTime(20)
    expect(opener.postMessage).toHaveBeenCalledWith({ type: 'plenio-ready' }, '*')
    // a message from another site is ignored; the player's is taken
    listeners[0]({ data: { type: 'plenio-continue', record }, origin: 'https://evil.example', source: opener } as unknown as MessageEvent)
    expect(host.fetcher.fetchApi).not.toHaveBeenCalled()
    listeners[0]({ data: { type: 'plenio-continue', record, name: 'River' }, origin: 'http://127.0.0.1:8765', source: opener } as unknown as MessageEvent)
    await vi.runAllTimersAsync()
    expect(host.fetcher.fetchApi).toHaveBeenCalledWith('/plenio/records/continue', expect.objectContaining({ body: JSON.stringify({ record, name: 'River' }) }))
    vi.useRealTimers()
  })

  it('does nothing on a page that was not opened by the player', () => {
    const win = { location: { search: '' } }
    expect(installContinueFromPlayer({} as never, win as unknown as Window)).toBe(false)
  })
})
