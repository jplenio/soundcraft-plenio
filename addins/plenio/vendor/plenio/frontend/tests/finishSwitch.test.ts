/**
 * HQ Mastering & Cover Art (owner's request 2026-10-23): two cards - HQ mastering is the node's value, Cover Art
 * bypasses the template's cover nodes; the seeds follow the brief's mode when it is changed by hand.
 */
import { describe, expect, it } from 'vitest'

import { asBoolean, coverOn, finishSwitchWidget, setCover } from '../src/extension/finishSwitch'
import { followMode, followNote, keepIn } from '../src/extension/seedsFollowMode'
import type { ComfyNode, ComfyWidget } from '../src/shared/comfy'

const cover = (mode: number) => ({ id: 1, type: 'x', mode, properties: { plenio_switch: 'cover' } }) as unknown as ComfyNode & { mode: number }

function switchNode(graph: { nodes: ComfyNode[] }) {
  const widgets: ComfyWidget[] = []
  const node = {
    id: 9,
    type: 'PlenioHQMastering',
    title: 'HQ Mastering & Cover Art',
    properties: {},
    widgets,
    graph,
    addDOMWidget(name: string, type: string, element: HTMLElement, options: { getValue: () => unknown; setValue: (v: unknown) => void }) {
      const widget = {
        name,
        type,
        element,
        options: {},
        get value() {
          return options.getValue()
        },
        set value(v: unknown) {
          options.setValue(v)
        }
      } as ComfyWidget
      widgets.push(widget)
      return widget
    }
  } as unknown as ComfyNode
  return node
}

describe('HQ Mastering & Cover Art', () => {
  it('reads and switches the cover from its nodes', () => {
    const graph = { nodes: [cover(0), cover(0)] }
    expect(coverOn(graph)).toBe(true)
    setCover(graph, false)
    expect(graph.nodes.map((n) => (n as { mode?: number }).mode)).toEqual([4, 4])
    expect(coverOn(graph)).toBe(false)
    expect(coverOn({ nodes: [] })).toBeNull() // no cover in this template: no card
  })

  it('draws two cards and switches HQ mastering as the node value', () => {
    const graph = { nodes: [cover(4)] }
    const node = switchNode(graph)
    const { widget } = finishSwitchWidget(node, 'hq_mastering', ['PLENIO_FINISH_SWITCH', { default: false }], {} as never)
    const [hq, art] = Array.from(widget.element!.querySelectorAll('button'))
    expect(hq.textContent).toContain('HQ Mastering')
    expect(hq.classList.contains('on')).toBe(false)
    expect(art.querySelector('.pill')?.textContent).toBe('OFF')
    hq.click()
    expect(widget.value).toBe(true)
    expect(hq.querySelector('.pill')?.textContent).toBe('ON')
    art.click()
    expect((graph.nodes[0] as { mode?: number }).mode).toBe(0)
    expect(art.classList.contains('on')).toBe(true)
    widget.value = 'false' // a saved value from elsewhere
    expect(widget.value).toBe(false)
    expect(asBoolean('on')).toBe(true)
  })
})

describe('seeds follow the brief mode', () => {
  const seed = (part: string, keep: boolean, linked = false) =>
    ({
      id: part,
      type: 'PlenioSeed',
      properties: { plenio_part: part },
      inputs: [{ name: 'seed', link: linked ? 3 : null }],
      widgets: [
        { name: 'seed', type: 'number', value: 1, options: {} },
        { name: 'keep_seed', type: 'toggle', value: keep, options: {} }
      ],
      setDirtyCanvas() {}
    }) as unknown as ComfyNode

  it('draws every seed anew for runs that go through, keeps the song’s for review', () => {
    const nodes = [seed('draft (title, style, lyrics)', true), seed('take', false), seed('cover art', true), seed('plan', true, true)]
    expect(followMode(nodes, 'new song every run')).toBe(2)
    expect(nodes.map((n) => n.widgets?.[1].value)).toEqual([false, false, false, true]) // a linked seed is left alone
    expect(followMode(nodes, 'one cover, stop to review')).toBe(2)
    expect(nodes.map((n) => n.widgets?.[1].value)).toEqual([true, false, true, true]) // the take still draws anew
    expect(keepIn('something else', 'take')).toBeNull()
    expect(followNote('new cover every run', 3).summary).toBe('3 seeds now 🎲 new seed')
  })
})
