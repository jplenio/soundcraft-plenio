/**
 * The seeds follow the brief's mode (owner's request 2026-10-23): runs that go through without a stop - *a new
 * song (cover) every run* - draw every seed anew (🎲), so nobody has to switch each seed node by hand; one song
 * with review stops keeps the song's seeds (🔒: the draft, the plan, the arrangement, the cover stay while it is
 * reviewed) and draws the take's anew. Only when the mode is changed by hand: a saved workflow keeps its
 * switches, and a seed switched afterwards stays as it was switched.
 */
import { type ComfyNode, chain } from '../shared/comfy'
import { PART_PROPERTY, SEED_NODE, restyle, seedLinked } from './seedNode'

/** The brief modes whose runs go through, and those that stop for review (``core.brief``). */
export const THROUGH_MODES = new Set(['new song every run', 'new cover every run'])
export const REVIEW_MODES = new Set(['one song, stop to review', 'one cover, stop to review'])

interface GraphLike {
  nodes?: ComfyNode[]
  _nodes?: ComfyNode[]
}

/** Whether a seed for ``part`` keeps its number in ``mode`` (``null``: the mode says nothing about it). */
export function keepIn(mode: string, part: string): boolean | null {
  if (THROUGH_MODES.has(mode)) return false
  if (REVIEW_MODES.has(mode)) return part.trim() !== 'take'
  return null
}

/** Switch the seeds among ``nodes`` for ``mode``; how many changed. */
export function followMode(nodes: ComfyNode[], mode: string): number {
  let changed = 0
  for (const node of nodes) {
    if (node.type !== SEED_NODE || seedLinked(node)) continue
    const keep = keepIn(mode, String(node.properties?.[PART_PROPERTY] ?? ''))
    const widget = node.widgets?.find((w) => w.name === 'keep_seed')
    if (keep === null || !widget || Boolean(widget.value) === keep) continue
    widget.value = keep
    restyle(node)
    changed++
  }
  return changed
}

/** What the toast says after ``changed`` seeds followed ``mode``. */
export function followNote(mode: string, changed: number): { summary: string; detail: string } {
  const seeds = `${changed} seed${changed === 1 ? '' : 's'}`
  return THROUGH_MODES.has(mode)
    ? { summary: `${seeds} now 🎲 new seed`, detail: `"${mode}": every run draws all its seeds anew - a new song each time. Switch a seed to 🔒 to keep that part.` }
    : { summary: `${seeds} now 🔒 same seed`, detail: `"${mode}": the song's draft, plan, arrangement and cover stay while you review it; the take seed still draws anew.` }
}

/** Hear of the brief's mode being changed by hand. */
export function installSeedsFollowMode(node: ComfyNode, notify: (summary: string, detail: string) => void): void {
  const mode = node.widgets?.find((w) => w.name === 'mode')
  if (!mode) return
  mode.callback = chain(mode.callback, (value: unknown) => {
    const graph = (node as ComfyNode & { graph?: GraphLike | null }).graph
    const chosen = String(value ?? mode.value ?? '')
    const changed = followMode(graph?.nodes ?? graph?._nodes ?? [], chosen)
    if (changed) {
      const note = followNote(chosen, changed)
      notify(note.summary, note.detail)
    }
  })
}
