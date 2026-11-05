/** What the classic scenes draw with: the spectrum on the ear's scale, a fade, an offscreen buffer, a small
 * pixel canvas. */

/** ``n`` magnitudes 0..1 on a logarithmic frequency scale (as the ear hears), from ~40 Hz to ~16 kHz. */
export function logBins(freq: Uint8Array, n: number, low = 2, high = Math.min(700, freq.length - 1)): Float32Array {
  const out = new Float32Array(n)
  for (let i = 0; i < n; i++) {
    const a = Math.floor(low * Math.pow(high / low, i / n))
    const b = Math.max(a + 1, Math.floor(low * Math.pow(high / low, (i + 1) / n)))
    let peak = 0
    for (let k = a; k < b; k++) peak = Math.max(peak, freq[k])
    out[i] = peak / 255
  }
  return out
}

export function fade(ctx: CanvasRenderingContext2D, width: number, height: number, alpha: number, color = '0,0,0'): void {
  ctx.globalCompositeOperation = 'source-over'
  ctx.fillStyle = `rgba(${color},${alpha})`
  ctx.fillRect(0, 0, width, height)
}

/** An offscreen canvas of the same size (for feedback scenes). */
export function buffer(width: number, height: number, old?: HTMLCanvasElement): HTMLCanvasElement {
  if (old && old.width === width && old.height === height) return old
  const canvas = old ?? document.createElement('canvas')
  canvas.width = width
  canvas.height = height
  return canvas
}

/** A small canvas for the pixel scenes (plasma, fire), drawn smoothly scaled up. */
export function pixels(width: number, height: number): { canvas: HTMLCanvasElement; ctx: CanvasRenderingContext2D; image: ImageData } {
  const canvas = document.createElement('canvas')
  canvas.width = width
  canvas.height = height
  const ctx = canvas.getContext('2d') as CanvasRenderingContext2D
  return { canvas, ctx, image: ctx.createImageData(width, height) }
}
