/**
 * The guests' reactions (owner's request 2026-10-26, the player as a party machine): a guest taps 🔥 ❤️ 🎉 👏 💃 😂
 * on their page (``plenio/player/guest.py``) and it floats up an edge of this screen - over the library, Live Play,
 * Now playing and the visual on the whole screen. They arrive with the guests' wishes every second and a half and
 * are spread over that time, so a burst rises as a stream; each song's count is kept while the page is open.
 */
import { reactive, ref } from 'vue'

import type { GuestReaction } from './api'

export const REACTION_EMOJI: Record<string, string> = { fire: '🔥', heart: '❤️', party: '🎉', clap: '👏', dance: '💃', laugh: '😂' }

/** One reaction on its way up: which edge, how far from it (%), its sway (px), size (px) and time (s). */
export interface Floating {
  key: number
  emoji: string
  side: 'left' | 'right'
  x: number
  drift: number
  size: number
  duration: number
}

/** At most so many float at once: a crowd's burst stays light for the page (the rest are counted only). */
export const MAX_FLOATING = 40
/** The time a batch is spread over: about the time until the next one arrives. */
export const SPREAD_MS = 1400

export const floating = ref<Floating[]>([])
/** The guests' reactions per song (song id -> kind -> count), as the player keeps them - apart from the hearts. */
export const cheers = reactive<Record<string, Record<string, number>>>({})

let key = 0

/** How one reaction floats: up the left or the right edge (the middle stays free for the lyrics and the
 * cover), with a little sway, a size and a time of its own. ``null`` for a kind this page does not know. */
export function flight(kind: string, random: () => number = Math.random): Floating | null {
  const emoji = REACTION_EMOJI[kind]
  if (!emoji) return null
  return {
    key: ++key,
    emoji,
    side: random() < 0.5 ? 'left' : 'right',
    x: 1 + random() * 11,
    drift: Math.round((random() - 0.5) * 60),
    // large enough to see from across the room on a party's big screen
    size: Math.round(46 + random() * 34),
    duration: 3.6 + random() * 1.6,
  }
}

/** The delays (ms) that spread ``count`` reactions evenly over ``over``. */
export function spread(count: number, over = SPREAD_MS): number[] {
  return Array.from({ length: Math.max(0, count) }, (_, i) => Math.round((i * over) / count))
}

/** A song's reactions as one line: ``🔥 12 · ❤️ 3`` (the most first), ``''`` for none. */
export function cheerLine(tally: Record<string, number> | undefined): string {
  return Object.entries(tally ?? {})
    .filter(([kind, count]) => REACTION_EMOJI[kind] && count > 0)
    .sort((a, b) => b[1] - a[1])
    .map(([kind, count]) => `${REACTION_EMOJI[kind]} ${count}`)
    .join(' · ')
}

function launch(kind: string): void {
  if (floating.value.length >= MAX_FLOATING) return
  const one = flight(kind)
  if (!one) return
  floating.value = [...floating.value, one]
  window.setTimeout(() => (floating.value = floating.value.filter((f) => f.key !== one.key)), one.duration * 1000 + 100)
}

/** Reactions that arrived: counted for their songs - the counts as the player keeps them, when it sends them
 * (``kept``: a guest's changed reaction moves from one kind to another) - then sent floating, spread out. */
export function receive(list: GuestReaction[], kept?: Record<string, Record<string, number>>): void {
  for (const reaction of list) {
    if (kept?.[reaction.id]) continue
    const tally = (cheers[reaction.id] ??= {})
    tally[reaction.kind] = (tally[reaction.kind] ?? 0) + 1
  }
  for (const [id, tally] of Object.entries(kept ?? {})) cheers[id] = { ...tally }
  spread(list.length).forEach((delay, i) => window.setTimeout(() => launch(list[i].kind), delay))
}

/** The counts the player keeps (its reactions.json), at the page's start. */
export async function loadCheers(read: () => Promise<{ songs: Record<string, Record<string, number>> }>): Promise<void> {
  try {
    const { songs } = await read()
    for (const [id, tally] of Object.entries(songs ?? {})) cheers[id] = { ...tally }
  } catch {
    // a player without them (a shared player): the page counts what arrives
  }
}
