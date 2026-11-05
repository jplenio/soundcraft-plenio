/** A song's colours: from its cover when it has one, otherwise from its genre and title (always the same). */

export interface Palette {
  hue: number
  accent: string
  accent2: string
  deep: string
  glow: string
}

export function hashOf(text: string): number {
  let h = 2166136261
  for (let i = 0; i < text.length; i++) {
    h ^= text.charCodeAt(i)
    h = Math.imul(h, 16777619)
  }
  return h >>> 0
}

/** Genre words that suggest a colour (warm for rock and soul, cold for ambient and techno ...). */
const GENRE_HUES: [RegExp, number][] = [
  [/metal|punk|rock|hard/i, 8],
  [/soul|funk|disco|r&b|rnb/i, 28],
  [/country|folk|blues|americana/i, 38],
  [/reggae|latin|afro|samba|salsa/i, 95],
  [/jazz|lounge|bossa/i, 45],
  [/ambient|chill|meditation|sleep/i, 190],
  [/techno|trance|house|edm|electro|synth/i, 265],
  [/classical|orchestra|cinematic|piano/i, 215],
  [/hip ?hop|rap|trap|drill/i, 300],
  [/pop|dance/i, 330],
]

export function paletteFrom(hue: number): Palette {
  const h = ((hue % 360) + 360) % 360
  return {
    hue: h,
    accent: `hsl(${h} 85% 62%)`,
    accent2: `hsl(${(h + 40) % 360} 80% 58%)`,
    deep: `hsl(${h} 45% 12%)`,
    glow: `hsla(${h} 90% 60% / 0.55)`,
  }
}

export function songHue(id: string, genre = ''): number {
  const hit = GENRE_HUES.find(([pattern]) => pattern.test(genre))
  const jitter = (hashOf(id) % 40) - 20
  return hit ? hit[1] + jitter : hashOf(id + genre) % 360
}

/** The dominant hue of an image (a small canvas, saturated pixels weighted most); ``null`` when grey. */
export async function coverHue(url: string): Promise<number | null> {
  const image = new Image()
  image.src = url
  try {
    await image.decode()
  } catch {
    return null
  }
  const canvas = document.createElement('canvas')
  canvas.width = canvas.height = 32
  const ctx = canvas.getContext('2d', { willReadFrequently: true })
  if (!ctx) return null
  ctx.drawImage(image, 0, 0, 32, 32)
  const data = ctx.getImageData(0, 0, 32, 32).data
  const bins = new Array(36).fill(0)
  for (let i = 0; i < data.length; i += 4) {
    const r = data[i] / 255
    const g = data[i + 1] / 255
    const b = data[i + 2] / 255
    const max = Math.max(r, g, b)
    const min = Math.min(r, g, b)
    const sat = max - min
    if (sat < 0.15 || max < 0.2) continue
    let h = 0
    if (max === r) h = ((g - b) / sat) % 6
    else if (max === g) h = (b - r) / sat + 2
    else h = (r - g) / sat + 4
    bins[Math.floor((((h * 60) % 360) + 360) % 360 / 10)] += sat * max
  }
  const best = bins.indexOf(Math.max(...bins))
  return bins[best] > 0 ? best * 10 + 5 : null
}
