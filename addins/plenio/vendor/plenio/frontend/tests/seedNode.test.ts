/**
 * Plenio · Seed: 🎲 draws a new seed before every run (so the number shown is the last run's), 🔒 keeps it;
 * the colour and the line follow the switch; a linked seed is left alone; the 🎲 button draws one now.
 */
import { describe, expect, it } from 'vitest'

import { LOOKS, SEED_LIMIT, drawSeed, seedHint, setUpSeed } from '../src/extension/seedNode'
import type { ComfyNode, ComfyWidget } from '../src/shared/comfy'

interface QueuedWidget extends ComfyWidget {
  beforeQueued?: () => void
}

function seedNode(keep: boolean, part = 'take', linked = false) {
  const widgets: QueuedWidget[] = [
    { name: 'seed', type: 'number', value: 7, options: {} },
    { name: 'keep_seed', type: 'toggle', value: keep, options: {} }
  ]
  const node = {
    id: 3,
    type: 'PlenioSeed',
    title: 'Take seed',
    properties: { plenio_part: part },
    widgets,
    inputs: [{ name: 'seed', link: linked ? 12 : null }],
    color: '',
    bgcolor: '',
    addWidget(type: string, name: string, value: unknown, callback: () => void) {
      const widget = { name, type, value, options: {}, callback } as ComfyWidget
      widgets.push(widget)
      return widget
    },
    addDOMWidget(name: string, type: string, element: HTMLElement) {
      const widget = { name, type, value: '', options: {}, element }
      widgets.push(widget)
      return widget
    },
    setDirtyCanvas() {}
  } as unknown as ComfyNode & { color: string; bgcolor: string }
  return { node, widgets }
}

const queue = (widgets: QueuedWidget[]) => {
  for (const widget of widgets) widget.beforeQueued?.()
}

describe('Plenio · Seed', () => {
  it('draws a new seed before every run when set to new seed', () => {
    const { node, widgets } = seedNode(false)
    const draws = [0.25, 0.5]
    setUpSeed(node, () => draws.shift() ?? 0)
    queue(widgets)
    expect(widgets[0].value).toBe(Math.floor(0.25 * SEED_LIMIT))
    queue(widgets) // the next run of a batch gets its own
    expect(widgets[0].value).toBe(Math.floor(0.5 * SEED_LIMIT))
  })

  it('keeps the seed with same seed - the number shown is the one the last run used', () => {
    const { node, widgets } = seedNode(true)
    setUpSeed(node, () => 0.9)
    queue(widgets)
    queue(widgets)
    expect(widgets[0].value).toBe(7)
  })

  it('leaves a seed that comes in through a link alone', () => {
    const { node, widgets } = seedNode(false, 'take', true)
    setUpSeed(node, () => 0.9)
    queue(widgets)
    expect(widgets[0].value).toBe(7)
  })

  it('colours the node and explains the switch for its part', () => {
    const { node, widgets } = seedNode(false, 'draft (title, style, lyrics)')
    setUpSeed(node, () => 0.1)
    const hint = widgets.find((w) => w.name === 'plenio_seed_hint')?.element
    expect((node as unknown as { color: string }).color).toBe(LOOKS.fresh.color)
    expect(hint?.textContent).toContain('a new draft (title, style, lyrics)')
    widgets[1].value = true
    widgets[1].callback?.(true)
    expect((node as unknown as { color: string }).color).toBe(LOOKS.keep.color)
    expect(hint?.textContent).toContain('the same draft (title, style, lyrics)')
  })

  it('draws one new seed with the button, also while it keeps the seed', () => {
    const { node, widgets } = seedNode(true)
    setUpSeed(node, () => 0.75)
    const button = widgets.find((w) => w.type === 'button')
    expect(button?.serialize).toBe(false)
    button?.callback?.(null)
    expect(widgets[0].value).toBe(Math.floor(0.75 * SEED_LIMIT))
  })

  it('draws seeds below 2^32 and says what the switch does', () => {
    expect(drawSeed(() => 0.999999999)).toBeLessThan(2 ** 32)
    expect(seedHint(true, '')).toContain('the same result')
    expect(seedHint(false, 'take')).toContain('a new take. Liked it? Switch to 🔒.')
  })
})
