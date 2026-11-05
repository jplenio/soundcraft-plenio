/**
 * *HQ Mastering & Cover Art* (owner's request 2026-10-23): two switches at the start of a template, drawn as
 * cards with an icon so that one sees at once what is on - in the graph and in App mode.
 *
 * - **HQ mastering** is the node's value (the ``PLENIO_FINISH_SWITCH`` input, a boolean): on, UniverSR runs
 *   in Plenio · Master.
 * - **Cover Art** has no value of its own: it switches the template's cover nodes (marked with the property
 *   ``plenio_switch: "cover"``) between running and bypassed, so a graph with the cover off loads no image
 *   model. What it shows is read from those nodes, so a cover bypassed by hand (Ctrl+B) shows as off too.
 */
import type { ComfyNode, InputSpec, WidgetConstructor } from '../shared/comfy'

export const FINISH_SWITCH_TYPE = 'PLENIO_FINISH_SWITCH'
export const SWITCH_PROPERTY = 'plenio_switch'
/** Two cards and the frontend's margins (10 px above and below a DOM widget). */
export const FINISH_SWITCH_HEIGHT = 148
const ALWAYS = 0
const BYPASS = 4

interface GraphLike {
  nodes?: ComfyNode[]
  _nodes?: ComfyNode[]
  setDirtyCanvas?(fg: boolean, bg: boolean): void
}

interface NodeWithGraph extends ComfyNode {
  graph?: GraphLike | null
  mode?: number
}

export interface Card {
  id: 'hq' | 'cover'
  name: string
  on: string
  off: string
  icon: string
}

export const CARDS: Card[] = [
  {
    id: 'hq',
    name: 'HQ Mastering',
    on: 'UniverSR regenerates the highs: less AI shimmer · about 2× the time',
    off: 'Faster, without UniverSR · switch on for the best sound',
    // sparkles
    icon: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 2.5l1.9 5.1 5.1 1.9-5.1 1.9L12 16.5l-1.9-5.1L5 9.5l5.1-1.9z"/><path d="M19 14.5l.9 2.4 2.4.9-2.4.9-.9 2.4-.9-2.4-2.4-.9 2.4-.9zM5 15.5l.7 1.8 1.8.7-1.8.7L5 20.5l-.7-1.8-1.8-.7 1.8-.7z"/></svg>'
  },
  {
    id: 'cover',
    name: 'Cover Art',
    on: 'Paints the cover from the artwork prompt · embedded in the files',
    off: 'No cover · no image model needed',
    // a picture: frame, sun and hills
    icon: '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="4" width="18" height="16" rx="2.5" fill="none" stroke="currentColor" stroke-width="2"/><circle cx="9" cy="9.5" r="1.8"/><path d="M4.5 18l5-5.5 3.5 3.5 2.5-2.5 4 4.5z"/></svg>'
  }
]

function nodesOf(graph: GraphLike | null | undefined): NodeWithGraph[] {
  return (graph?.nodes ?? graph?._nodes ?? []) as NodeWithGraph[]
}

/** The template's cover nodes (Cover Art, its seed, its preview). */
export function coverNodes(graph: GraphLike | null | undefined): NodeWithGraph[] {
  return nodesOf(graph).filter((n) => n.properties?.[SWITCH_PROPERTY] === 'cover')
}

/** Whether the cover is painted: any of its nodes runs. ``null``: the graph has no cover nodes. */
export function coverOn(graph: GraphLike | null | undefined): boolean | null {
  const nodes = coverNodes(graph)
  return nodes.length ? nodes.some((n) => (n.mode ?? ALWAYS) === ALWAYS) : null
}

/** Switch the cover on (its nodes run) or off (bypassed). */
export function setCover(graph: GraphLike | null | undefined, on: boolean): void {
  for (const node of coverNodes(graph)) node.mode = on ? ALWAYS : BYPASS
  graph?.setDirtyCanvas?.(true, true)
}

export function asBoolean(value: unknown): boolean {
  return value === true || (typeof value === 'string' && ['true', '1', 'on'].includes(value.trim().toLowerCase()))
}

const cards = new Set<() => void>()

/** Read the cards again (a workflow loaded, a node bypassed by hand). */
export function refreshFinishSwitches(): void {
  for (const render of cards) render()
}

export const finishSwitchWidget: WidgetConstructor = (node: ComfyNode, inputName: string, inputData: InputSpec) => {
  let value = asBoolean(inputData?.[1]?.default)
  const host = node as NodeWithGraph
  const element = document.createElement('div')
  element.className = 'plenio-switches'
  const buttons = new Map<Card['id'], HTMLButtonElement>()
  for (const card of CARDS) {
    const button = document.createElement('button')
    button.type = 'button'
    button.className = 'plenio-switch'
    button.dataset.switch = card.id
    button.innerHTML = `<span class="icon">${card.icon}</span><span class="text"><span class="name"></span><span class="what"></span></span><span class="pill"></span>`
    button.addEventListener('click', (event) => {
      event.stopPropagation()
      if (card.id === 'hq') {
        value = !value
        widget.value = value
        widget.callback?.(value)
      } else setCover(host.graph, !coverOn(host.graph))
      render()
    })
    buttons.set(card.id, button)
    element.append(button)
  }

  function paint(card: Card, on: boolean | null): void {
    const button = buttons.get(card.id)
    if (!button) return
    button.hidden = on === null
    button.classList.toggle('on', !!on)
    button.setAttribute('aria-pressed', String(!!on))
    button.title = `${card.name}: ${on ? 'on' : 'off'} - click to switch it ${on ? 'off' : 'on'}`
    ;(button.querySelector('.name') as HTMLElement).textContent = card.name
    ;(button.querySelector('.what') as HTMLElement).textContent = on ? card.on : card.off
    ;(button.querySelector('.pill') as HTMLElement).textContent = on ? 'ON' : 'OFF'
  }

  function render(): void {
    paint(CARDS[0], value)
    paint(CARDS[1], coverOn(host.graph))
  }

  const widget = node.addDOMWidget(inputName, FINISH_SWITCH_TYPE, element, {
    getValue: () => value,
    setValue: (next: unknown) => {
      value = asBoolean(next)
      render()
    },
    getMinHeight: () => FINISH_SWITCH_HEIGHT,
    getMaxHeight: () => FINISH_SWITCH_HEIGHT
  })
  cards.add(render)
  // a cover bypassed by hand (Ctrl+B) shows at the next frame
  let shown = coverOn(host.graph)
  const draw = node.onDrawForeground
  node.onDrawForeground = function (this: ComfyNode, ctx: CanvasRenderingContext2D) {
    draw?.call(this, ctx)
    const now = coverOn(host.graph)
    if (now !== shown) {
      shown = now
      render()
    }
  }
  const removed = node.onRemoved
  node.onRemoved = function (this: ComfyNode) {
    cards.delete(render)
    removed?.call(this)
  }
  render()
  return { widget }
}
