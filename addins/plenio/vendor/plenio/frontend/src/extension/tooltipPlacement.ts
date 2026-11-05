/**
 * The tooltips of Plenio nodes beside the node, never over its fields (owner's report 2026-10-15: the
 * tooltip of *genre closeness* covered the brief's fields).
 *
 * ComfyUI draws a node's tooltip at the mouse, above and to the right of it (``.node-tooltip``,
 * ``translate(5px, -100%)``): over a node's own fields it covers the rows above the hovered one, and a tall
 * tooltip runs off the window. For Plenio nodes the tooltip moves to the side of the node - 12 px right of
 * it at the height of the hovered row, on the left when the right has no room, kept inside the window. It
 * does so with a class on ``<body>`` and two CSS custom properties, so ComfyUI's own positioning is left
 * untouched for every other node; without a ``.node-tooltip`` element nothing happens.
 */

export const TIP_CLASS = 'plenio-tip'
const GAP = 12
const MARGIN = 8

export interface Box {
  left: number
  top: number
  right: number
  bottom: number
}

/** Where the tooltip goes (window pixels): beside ``node`` at ``pointerY``; ``null`` when neither side has room. */
export function besideNode(
  node: Box,
  pointerY: number,
  tip: { width: number; height: number },
  view: { width: number; height: number }
): { x: number; y: number } | null {
  let x = node.right + GAP
  if (x + tip.width > view.width - MARGIN) x = node.left - GAP - tip.width
  if (x < MARGIN) return null
  const y = Math.max(MARGIN, Math.min(pointerY - 14, view.height - MARGIN - tip.height))
  return { x, y }
}

export interface CanvasLike {
  node_over?: { type?: string; title?: string; pos: [number, number]; size: [number, number]; flags?: { collapsed?: boolean } } | null
  ds?: { offset: [number, number]; scale: number }
  canvas?: HTMLCanvasElement
}

/** A node whose tooltips Plenio places: a Plenio node, or a Plenio block (its title starts with "Plenio"). */
export function isPlenioNode(node: { type?: string; title?: string } | null | undefined): boolean {
  return !!node && (String(node.type ?? '').startsWith('Plenio') || String(node.title ?? '').startsWith('Plenio'))
}

const TITLE_HEIGHT = 30

/** The node's box in window pixels (title bar included). */
export function nodeBox(canvas: CanvasLike): Box | null {
  const node = canvas.node_over
  const ds = canvas.ds
  const element = canvas.canvas
  if (!node || !ds || !element) return null
  const rect = element.getBoundingClientRect()
  const height = node.flags?.collapsed ? 0 : node.size[1]
  return {
    left: rect.left + (node.pos[0] + ds.offset[0]) * ds.scale,
    top: rect.top + (node.pos[1] - TITLE_HEIGHT + ds.offset[1]) * ds.scale,
    right: rect.left + (node.pos[0] + node.size[0] + ds.offset[0]) * ds.scale,
    bottom: rect.top + (node.pos[1] + height + ds.offset[1]) * ds.scale
  }
}

export function installTooltipPlacement(canvas: () => CanvasLike | undefined): void {
  const body = document.body
  const off = () => body.classList.remove(TIP_CLASS)
  let pointerY = 0
  let watched: HTMLElement | null = null

  const place = (tip: HTMLElement) => {
    const current = canvas()
    if (tip.style.display === 'none' || !tip.textContent?.trim() || !current || !isPlenioNode(current.node_over)) return off()
    const box = nodeBox(current)
    const size = tip.getBoundingClientRect()
    const spot = box && besideNode(box, pointerY, size, { width: window.innerWidth, height: window.innerHeight })
    if (!spot) return off()
    const parent = (tip.offsetParent as HTMLElement | null)?.getBoundingClientRect() ?? { left: 0, top: 0 }
    body.style.setProperty('--plenio-tip-x', `${Math.round(spot.x - parent.left)}px`)
    body.style.setProperty('--plenio-tip-y', `${Math.round(spot.y - parent.top)}px`)
    body.classList.add(TIP_CLASS)
  }

  // the tooltip element comes with the graph view (and again after a view change): looked for while the
  // pointer moves and none is watched
  const watch = () => {
    const tip = document.querySelector<HTMLElement>('.node-tooltip')
    if (!tip) return
    watched = tip
    new MutationObserver(() => place(tip)).observe(tip, {
      attributes: true,
      attributeFilter: ['style'],
      childList: true,
      characterData: true,
      subtree: true
    })
  }
  window.addEventListener('mousemove', (event) => {
    pointerY = event.clientY
    if (!watched?.isConnected) watch()
  })
}

export const TOOLTIP_CSS = `
body.${TIP_CLASS} .node-tooltip { left: var(--plenio-tip-x) !important; top: var(--plenio-tip-y) !important;
  transform: none !important; }
`
