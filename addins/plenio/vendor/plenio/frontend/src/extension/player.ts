/**
 * The Plenio Player from ComfyUI (owner's request 2026-10-16): one click on *Plenio Player* - the action bar,
 * the Plenio menu, Export Release's button - opens it. ComfyUI does not serve the player: its route starts
 * the player as a program of its own when none runs (``plenio.player.launch``) and says where it is.
 *
 * The way back: the player's *Open in ComfyUI* opens ComfyUI with ``?plenio=continue``; this page tells
 * its opener it is ready and takes the song's record from it - from its own origin or a loopback one only -
 * and continues the song as a dropped record does.
 */
import { type Fetcher, PlenioApiError } from '../api/client'
import type { ComfyApp, ComfyNode, ComfyNodeType } from '../shared/comfy'
import { chain } from '../shared/comfy'
import { type ContinueHost, continueSong } from './continueSong'

export const PLAYER_COMMAND = 'Plenio.OpenPlayer'
/** The browser tab the player opens in: the next click finds it again. */
export const PLAYER_TAB = 'plenio-player'
const BUTTON = '▶ Open in the Plenio Player'

export interface PlayerAnswer {
  url: string
  started: boolean
  version: string
}

export interface PlayerHost {
  app: ComfyApp
  fetcher: Fetcher
}

function toast(app: ComfyApp, severity: string, summary: string, detail: string, life = 12000): void {
  app.extensionManager?.toast?.add({ severity, summary, detail, life })
}

/** Ask ComfyUI's server for the player: the one running, or one started now. */
export async function startPlayer(fetcher: Fetcher): Promise<PlayerAnswer> {
  const response = await fetcher.fetchApi('/plenio/player/open', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: '{}'
  })
  const data = await response.json().catch(() => ({}))
  if (!response.ok) {
    const error = data?.error ?? {}
    throw new PlenioApiError(error.message ?? `The Plenio Player did not start (${response.status})`, error.hint ?? null)
  }
  return data as PlayerAnswer
}

/** Where to send the player's tab: the library, or the song of a record. Always with a fragment, so a tab
 * that shows the player already moves without reloading (the music keeps playing). */
export function playerAddress(url: string, record?: string | null): string {
  const base = url.endsWith('/') ? url : `${url}/`
  return record ? `${base}#/record/${encodeURIComponent(record)}` : `${base}#/`
}

/** Open the player (at the song of ``record``). The tab opens inside the click - one opened after the
 * server's answer would be a pop-up to block - and goes to the player when the answer comes. */
export async function openPlayer(host: PlayerHost, record: string | null = null, opener: Pick<Window, 'open'> = window): Promise<void> {
  const tab = opener.open('', PLAYER_TAB)
  let fresh = true
  try {
    fresh = !tab || tab.location.href === 'about:blank'
  } catch {
    fresh = false // the tab shows the player already (another origin)
  }
  if (tab && fresh) {
    try {
      // dark like the player, so the tab does not flash white while the player starts
      tab.document.title = 'Plenio Player'
      tab.document.body.style.cssText = 'margin:0;height:100vh;display:grid;place-items:center;background:#0a0910;color:#a99fc0;font:600 18px system-ui,sans-serif'
      tab.document.body.textContent = 'Starting the Plenio Player …'
    } catch {
      /* nothing to show then */
    }
  }
  try {
    const answer = await startPlayer(host.fetcher)
    if (tab) {
      if (fresh || record) tab.location.href = playerAddress(answer.url, record)
      tab.focus()
    } else {
      opener.open(playerAddress(answer.url, record), PLAYER_TAB)
    }
    if (answer.started) {
      toast(host.app, 'success', 'Plenio Player started', `${answer.url} - it keeps running when ComfyUI stops; stop it on its Settings page.`)
    }
  } catch (error) {
    if (tab && fresh) tab.close()
    const hint = error instanceof PlenioApiError && error.hint ? ` ${error.hint}` : ''
    toast(host.app, 'error', 'Plenio Player', `${error instanceof Error ? error.message : String(error)}${hint}`, 20000)
  }
}

/** Export Release: a button that opens the player at the song the node exported last. */
export function installPlayerButton(nodeType: ComfyNodeType, host: PlayerHost): void {
  const records = new WeakMap<ComfyNode, string>()
  const proto = nodeType.prototype as ComfyNode & { onNodeCreated?: () => void }
  const created = proto.onNodeCreated
  proto.onNodeCreated = function (this: ComfyNode) {
    created?.call(this)
    const node = this as ComfyNode & {
      addWidget?(type: string, name: string, value: unknown, callback: () => void, options?: Record<string, unknown>): { serialize?: boolean } | undefined
    }
    const button = node.addWidget?.('button', BUTTON, null, () => void openPlayer(host, records.get(this) ?? null), { serialize: false })
    if (button) button.serialize = false
  }
  nodeType.prototype.onExecuted = chain(nodeType.prototype.onExecuted, function (this: ComfyNode, output) {
    const items = output?.plenio_player as { record?: string }[] | undefined
    const record = items?.[items.length - 1]?.record
    if (record) records.set(this, record)
  })
}

const LOOPBACK = new Set(['127.0.0.1', 'localhost', '[::1]'])

/** A record may come from this page's own origin, from a player on this computer, or - this ComfyUI opened
 * from the network by the player's gateway - from the player's gateway on the same computer (the same host,
 * another port); nothing else. */
export function trustedOrigin(origin: string, own: string): boolean {
  if (origin === own) return true
  try {
    const url = new URL(origin)
    if (url.protocol !== 'http:' && url.protocol !== 'https:') return false
    return LOOPBACK.has(url.hostname) || url.hostname === new URL(own).hostname
  } catch {
    return false
  }
}

interface ContinueMessage {
  type: 'plenio-continue'
  record: unknown
  name?: string
}

/** Opened by the player's *Open in ComfyUI* (``?plenio=continue``): say so to the player and continue the
 * song it sends. ``false``: this page was not opened that way. */
export function installContinueFromPlayer(host: ContinueHost, win: Window = window, settle = 1500): boolean {
  const params = new URLSearchParams(win.location.search)
  if (params.get('plenio') !== 'continue') return false
  // the address without the request, so that reloading the page does not ask again
  params.delete('plenio')
  const rest = params.toString()
  win.history.replaceState(win.history.state, '', `${win.location.pathname}${rest ? `?${rest}` : ''}${win.location.hash}`)
  const opener = win.opener as Window | null
  if (!opener) return true
  const onMessage = (event: MessageEvent) => {
    const data = event.data as ContinueMessage | null
    if (data?.type !== 'plenio-continue' || event.source !== opener || !trustedOrigin(event.origin, win.location.origin)) return
    win.removeEventListener('message', onMessage)
    continueSong(host, { record: data.record, name: String(data.name || 'the Plenio Player') }).catch((error: unknown) => {
      const hint = error instanceof PlenioApiError && error.hint ? ` ${error.hint}` : ''
      toast(host.app as ComfyApp, 'error', 'Continue a song', `${error instanceof Error ? error.message : String(error)}${hint}`, 20000)
    })
  }
  win.addEventListener('message', onMessage)
  // ComfyUI restores its last workflow while it starts: the song's workflow comes after that
  win.setTimeout(() => opener.postMessage({ type: 'plenio-ready' }, '*'), settle)
  return true
}
