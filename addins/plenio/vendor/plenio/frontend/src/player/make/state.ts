/**
 * The party songs in the player's page (docs/design/party-songs.md §4): the server's answer - who may, the
 * settings, one's songs - asked every few seconds while *Make a song* is open and now and then otherwise (the
 * sidebar's count, a message when a song of one's own is ready). Nothing of it in a shared player.
 */
import { computed, ref, shallowRef } from 'vue'

import { isPortable } from '../portable'
import { makeClient } from './client'
import type { FormData, MakeJob, MakeStatus } from './form'

export const makeApi = makeClient('/api/make', { 'X-Plenio-Player': '1' })
export const makeStatus = shallowRef<MakeStatus | null>(null)
export const makeForm = shallowRef<FormData | null>(null)
export const makeError = ref('')
/** The admin looks at everybody's songs (else at their own). */
export const everybody = ref(false)

const ON_PAGE_MS = 3000
const ELSEWHERE_MS = 15000
let timer: number | undefined
let onPage = false
const told = new Set<string>()
let first = true

/** Read the party songs again; ``ready`` hears of each song of one's own that became ready since the last time. */
export async function loadMake(ready?: (job: MakeJob) => void): Promise<void> {
  if (isPortable) return
  try {
    const status = await makeApi.status(everybody.value && !!makeStatus.value?.admin)
    makeStatus.value = status
    makeError.value = ''
    for (const job of status.jobs) {
      if (!job.mine || job.status !== 'done' || told.has(job.id)) continue
      told.add(job.id)
      if (!first) ready?.(job)
    }
    first = false
  } catch (e) {
    makeError.value = e instanceof Error ? e.message : String(e)
  }
}

export async function loadForm(force = false): Promise<void> {
  if (isPortable || (makeForm.value && !force)) return
  makeForm.value = await makeApi.form()
}

let onReady: ((job: MakeJob) => void) | undefined

/** Ask now and then (``page``: often, while *Make a song* shows). */
export function pollMake(page: boolean, ready?: (job: MakeJob) => void): void {
  if (isPortable) return
  if (ready) onReady = ready
  onPage = page
  window.clearInterval(timer)
  void loadMake(onReady)
  timer = window.setInterval(() => {
    if (onPage || document.visibilityState === 'visible') void loadMake(onReady)
  }, page ? ON_PAGE_MS : ELSEWHERE_MS)
}

/** *Make a song* in the sidebar: for whoever may make songs (the admin always, to switch it on; the whole studio
 * from the network also while the party's song making is off). */
export const makeShown = computed(() => !isPortable && !!makeStatus.value && (makeStatus.value.admin || !!makeStatus.value.me.full || (makeStatus.value.on && makeStatus.value.may)))
/** Songs waiting for an admin's approval (the admins' sidebar count). */
export const approvalsNow = computed(() => makeStatus.value?.approvals?.length ?? 0)
/** One's songs in the making (the sidebar's count). */
export const makingNow = computed(() => (makeStatus.value?.jobs ?? []).filter((j) => j.mine && !['done', 'failed', 'cancelled'].includes(j.status)).length)
