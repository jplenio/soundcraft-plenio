/**
 * Plenio nodes' tooltips beside the node: right of it at the hovered row, on the left when the right has
 * no room, inside the window; other nodes keep ComfyUI's placement.
 */
import { describe, expect, it } from 'vitest'

import { besideNode, isPlenioNode, nodeBox } from '../src/extension/tooltipPlacement'

const view = { width: 1600, height: 1000 }
const tip = { width: 400, height: 90 }

describe('tooltip placement', () => {
  it('puts the tooltip right of the node at the hovered row', () => {
    const spot = besideNode({ left: 300, top: 50, right: 820, bottom: 900 }, 600, tip, view)
    expect(spot).toEqual({ x: 832, y: 586 })
  })

  it('uses the left side when the right has no room, and nothing when neither has', () => {
    expect(besideNode({ left: 700, top: 0, right: 1300, bottom: 500 }, 300, tip, view)?.x).toBe(700 - 12 - 400)
    expect(besideNode({ left: 100, top: 0, right: 1300, bottom: 500 }, 300, tip, view)).toBeNull()
  })

  it('keeps a tall tooltip inside the window', () => {
    const spot = besideNode({ left: 0, top: 0, right: 500, bottom: 900 }, 980, { width: 300, height: 400 }, view)
    expect(spot?.y).toBe(1000 - 8 - 400)
  })

  it('places only the tooltips of Plenio nodes and blocks', () => {
    expect(isPlenioNode({ type: 'PlenioSongBrief' })).toBe(true)
    expect(isPlenioNode({ type: '0b7f2e2c-uuid', title: 'Plenio · Write Song' })).toBe(true)
    expect(isPlenioNode({ type: 'KSampler', title: 'KSampler' })).toBe(false)
    expect(isPlenioNode(null)).toBe(false)
  })

  it('finds the node on screen from the canvas offset and scale', () => {
    const canvas = document.createElement('canvas')
    canvas.getBoundingClientRect = () => ({ left: 10, top: 20, right: 1610, bottom: 1020, width: 1600, height: 1000, x: 10, y: 20, toJSON: () => ({}) })
    const box = nodeBox({ canvas, ds: { offset: [100, 50], scale: 0.5 }, node_over: { pos: [200, 300], size: [520, 800] } })
    expect(box).toEqual({ left: 10 + 150, top: 20 + (300 - 30 + 50) * 0.5, right: 10 + 410, bottom: 20 + 575 })
  })
})
