/**
 * Live Play (owner's request 2026-10-16): a live playlist for a party. It plays while it is changed - songs
 * added, removed, moved, played next - and the songs ComfyUI makes while it plays join it as soon as Export
 * Release has written them: next, at the end, or somewhere at random. When it runs out it starts again from
 * the top, or waits for the next new song.
 *
 * The live playlist is the queue. Live Play asks the player's server every few seconds for the songs that
 * appeared since it last asked (``/api/new``).
 */
import { reactive, ref, watch } from 'vue'

import { api, type SongSummary } from './api'
import { engine } from './engine'
import { insertAt, type Insert } from './liveSettings'
import { byId, index, library, liveWaiting, playAt, playSongs, queue, queueSource, say, settings } from './store'
import { isPortable } from './portable'

/** When each new song arrived (for its *new* mark), and what arrived lately, newest first. */
export const arrived = reactive(new Map<string, number>())
export const liveLog = ref<{ id: string; title: string; at: number; where: string }[]>([])
export const NEW_FOR_MS = 15 * 60 * 1000

export function isNew(id: string): boolean {
  const at = arrived.get(id)
  return at !== undefined && Date.now() - at < NEW_FOR_MS
}

/** Put songs into the live playlist (new ones from ComfyUI, or chosen by hand) where ``insert`` says. */
export function addLive(ids: string[], insert: Insert = settings.live.insert): void {
  const fresh = ids.filter((id) => byId.value.has(id) && !queue.value.slice(Math.max(0, index.value + 1)).includes(id))
  if (!fresh.length) return
  if (index.value < 0 || !queue.value.length) {
    void playSongs(fresh, 0, 'live')
    return
  }
  const nowId = queue.value[index.value]
  fresh.forEach((id, k) => {
    // a song already played earlier comes again: it moves to its new place
    const before = queue.value.indexOf(id)
    if (before >= 0 && before !== index.value) queue.value.splice(before, 1)
    const nowAt = queue.value.indexOf(nowId)
    queue.value.splice(insertAt(insert, nowAt, queue.value.length, k), 0, id)
  })
  index.value = queue.value.indexOf(nowId)
  if (liveWaiting.value) {
    liveWaiting.value = false
    void playAt(queue.value.indexOf(fresh[0]))
  }
}

let since: number | null = null
let timer: number | undefined

async function poll(): Promise<void> {
  try {
    const answer = await api.newSongs(since)
    const first = since === null
    since = answer.now
    if (first || !answer.songs.length) return
    const known = byId.value
    const added = answer.songs.filter((s) => !known.has(s.id))
    if (added.length) library.value = [...added, ...library.value]
    const ids = answer.songs.map((s) => s.id)
    for (const id of ids) arrived.set(id, Date.now())
    if (settings.live.auto) {
      addLive(ids)
      for (const song of answer.songs) announce(song)
    } else say(answer.songs.length === 1 ? `New song: ${answer.songs[0].title} - add it in Live Play` : `${answer.songs.length} new songs - add them in Live Play`, 5000)
  } catch {
    // the player is restarting, or the network hiccups: ask again next time
  }
}

function announce(song: SongSummary): void {
  const at = queue.value.indexOf(song.id)
  const where = at === index.value ? 'plays now' : at === index.value + 1 ? 'plays next' : at === queue.value.length - 1 ? 'at the end' : `number ${at - index.value} from now`
  liveLog.value = [{ id: song.id, title: song.title, at: Date.now(), where }, ...liveLog.value].slice(0, 30)
  say(`New song: ${song.title} - ${where}`, 6000)
}

function startPolling(): void {
  if (timer !== undefined || isPortable) return
  since = null
  void poll()
  timer = window.setInterval(() => void poll(), 4000)
}
function stopPolling(): void {
  window.clearInterval(timer)
  timer = undefined
  since = null
}

/** Start Live Play with these songs (``[]``: keep the queue as it is - or wait, when it is empty). */
export async function startLive(ids: string[] = []): Promise<void> {
  settings.live.on = true
  queueSource.value = 'live'
  if (ids.length) await playSongs(ids, 0, 'live')
  else if (!queue.value.length) liveWaiting.value = true
  else if (index.value < 0 || engine.paused) await playAt(Math.max(0, index.value))
}

export function stopLive(): void {
  settings.live.on = false
  liveWaiting.value = false
}

// Live Play on (also after the page opened again): ask for new songs; off: stop asking
watch(
  () => settings.live?.on,
  (on) => (on ? startPolling() : stopPolling()),
  { immediate: true }
)
