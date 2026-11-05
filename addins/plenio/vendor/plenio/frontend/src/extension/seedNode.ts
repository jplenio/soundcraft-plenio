/**
 * Plenio · Seed (owner's request 2026-10-15, docs/design/subtitles-tags-seeds.md §4): one switch -
 * 🎲 a new seed for every run, or 🔒 the same seed again.
 *
 * - The new seed is drawn **before** the run (the frontend calls ``beforeQueued`` on every widget once per
 *   queued run, also for each run of a batch), so the number shown is always the one the last run used:
 *   switching to 🔒 keeps exactly the result just heard. ComfyUI's own *control after generate* changes the
 *   number after the run - the number shown there belongs to the next run.
 * - The node's colour says what happens on the next run: amber for 🎲, blue for 🔒.
 * - A line under the switch says what it means for the part this seed decides (the template names the part
 *   in the node's ``plenio_part`` property: *take*, *draft* ...), and a button draws one new seed now.
 *
 * A seed whose number comes in through a link is left alone.
 */
import { type ComfyNode, type ComfyNodeType, type ComfyWidget, chain } from '../shared/comfy'

export const SEED_NODE = 'PlenioSeed'
/** Drawn seeds stay below 2^32: every sampler and model server Plenio feeds takes them. */
export const SEED_LIMIT = 2 ** 32
export const PART_PROPERTY = 'plenio_part'
const HINT_WIDGET = 'plenio_seed_hint'
const HINT_HEIGHT = 56

export const LOOKS = {
  fresh: { color: '#7a5418', bgcolor: '#3b2a10' },
  keep: { color: '#1f4e6e', bgcolor: '#14304a' }
} as const

export function drawSeed(random: () => number = Math.random): number {
  return Math.floor(random() * SEED_LIMIT)
}

/** The line under the switch. */
export function seedHint(keep: boolean, part: string): string {
  const what = part.trim() || 'result'
  return keep
    ? `🔒 Every run uses this seed again: the same ${what}.`
    : `🎲 Every run draws a new seed: a new ${what}. Liked it? Switch to 🔒.`
}

interface SeedWidget extends ComfyWidget {
  beforeQueued?: (options?: { isPartialExecution?: boolean }) => void
}

interface ButtonHost extends ComfyNode {
  addWidget?(type: string, name: string, value: unknown, callback: () => void, options?: Record<string, unknown>): ComfyWidget
  color?: string
  bgcolor?: string
}

function widget(node: ComfyNode, name: string): SeedWidget | undefined {
  return node.widgets?.find((w) => w.name === name) as SeedWidget | undefined
}

/** The seed comes in through a link: its number is not this node's to change. */
export function seedLinked(node: ComfyNode): boolean {
  const input = node.inputs?.find((slot) => slot.name === 'seed')
  return input?.link !== undefined && input?.link !== null
}

/** Colour and line for the node's switch. */
export function restyle(node: ComfyNode): void {
  const keep = Boolean(widget(node, 'keep_seed')?.value)
  const host = node as ButtonHost
  const look = keep ? LOOKS.keep : LOOKS.fresh
  host.color = look.color
  host.bgcolor = look.bgcolor
  const hint = widget(node, HINT_WIDGET)?.element
  if (hint) hint.textContent = seedHint(keep, String(node.properties?.[PART_PROPERTY] ?? ''))
  node.setDirtyCanvas?.(true, true)
}

/** Draw a new seed into the node's number (and tell the frontend it changed). */
export function newSeed(node: ComfyNode, random: () => number = Math.random): void {
  const seed = widget(node, 'seed')
  if (!seed || seedLinked(node)) return
  seed.value = drawSeed(random)
  seed.callback?.(seed.value)
  node.setDirtyCanvas?.(true, true)
}

/** Wire one node: the draw before every run, the switch's colour and line, the 🎲 button. */
export function setUpSeed(node: ComfyNode, random: () => number = Math.random): void {
  const seed = widget(node, 'seed')
  const keep = widget(node, 'keep_seed')
  if (!seed || !keep) return
  seed.beforeQueued = () => {
    if (!keep.value) newSeed(node, random)
  }
  keep.callback = chain(keep.callback, () => restyle(node))
  const host = node as ButtonHost
  const button = host.addWidget?.('button', '🎲 new seed now', null, () => newSeed(node, random), { serialize: false })
  if (button) button.serialize = false
  if (!widget(node, HINT_WIDGET)) {
    const element = document.createElement('div')
    element.className = 'plenio-seed-hint'
    const hint = node.addDOMWidget(HINT_WIDGET, HINT_WIDGET, element, {
      serialize: false,
      getValue: () => '',
      setValue: () => {},
      // two lines of text and the frontend's margin of 10 px above and below a DOM widget
      getMinHeight: () => HINT_HEIGHT,
      getMaxHeight: () => HINT_HEIGHT
    })
    hint.serialize = false
  }
  restyle(node)
}

export function installSeedNode(nodeType: ComfyNodeType): void {
  const proto = nodeType.prototype as ComfyNode & { onNodeCreated?: () => void }
  const created = proto.onNodeCreated
  proto.onNodeCreated = function (this: ComfyNode) {
    created?.call(this)
    setUpSeed(this)
  }
  // a loaded workflow: the switch's saved state decides the colour and the line
  nodeType.prototype.onConfigure = chain(nodeType.prototype.onConfigure, function (this: ComfyNode) {
    restyle(this)
  })
}
