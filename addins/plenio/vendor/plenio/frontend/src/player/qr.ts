/**
 * QR codes for the guests' address (owner's request 2026-10-17: the way in on the screen, as a QR code or as
 * text). A small encoder of our own - no package to download: byte mode, error correction level M (15 % of
 * the code may be covered or blurred), versions 1 to 10 (up to 213 bytes, plenty for an address), the mask
 * chosen by the standard's penalty rules. Follows ISO/IEC 18004 as Project Nayuki's reference encoder does.
 */

/** Error correction codewords per block and blocks, level M, versions 1-10. */
const ECC_PER_BLOCK = [0, 10, 16, 26, 18, 24, 16, 18, 22, 22, 26]
const BLOCKS = [0, 1, 1, 1, 2, 2, 4, 4, 4, 5, 5]
const MAX_VERSION = 10
const FORMAT_M = 0 // level M's two format bits

/** The modules (true: dark), row by row; ``null`` when the text is too long for version 10. */
export function qrModules(text: string): boolean[][] | null {
  const data = Array.from(new TextEncoder().encode(text))
  let version = 1
  for (; version <= MAX_VERSION; version++) {
    const bits = 4 + (version < 10 ? 8 : 16) + data.length * 8
    if (bits <= dataCodewords(version) * 8) break
  }
  if (version > MAX_VERSION) return null
  const qr = new Matrix(version)
  qr.drawFunctionPatterns()
  qr.drawCodewords(addEccAndInterleave(encode(data, version), version))
  let best = 0
  let lowest = Infinity
  for (let mask = 0; mask < 8; mask++) {
    qr.applyMask(mask)
    qr.drawFormatBits(mask)
    const penalty = qr.penalty()
    if (penalty < lowest) {
      lowest = penalty
      best = mask
    }
    qr.applyMask(mask) // undo
  }
  qr.applyMask(best)
  qr.drawFormatBits(best)
  return qr.modules
}

/** The modules as one SVG path (one unit per module, with ``border`` light modules round it). */
export function qrPath(modules: boolean[][], border = 4): string {
  const parts: string[] = []
  modules.forEach((row, y) => row.forEach((dark, x) => dark && parts.push(`M${x + border},${y + border}h1v1h-1z`)))
  return parts.join('')
}

// --- the data --------------------------------------------------------------------------------------------

function rawModules(version: number): number {
  let result = (16 * version + 128) * version + 64
  if (version >= 2) {
    const align = Math.floor(version / 7) + 2
    result -= (25 * align - 10) * align - 55
    if (version >= 7) result -= 36
  }
  return result
}

function dataCodewords(version: number): number {
  return Math.floor(rawModules(version) / 8) - ECC_PER_BLOCK[version] * BLOCKS[version]
}

/** Mode, length, the bytes, the terminator and the padding, as codewords. */
function encode(data: number[], version: number): number[] {
  const bits: number[] = []
  const put = (value: number, length: number): void => {
    for (let i = length - 1; i >= 0; i--) bits.push((value >>> i) & 1)
  }
  put(0b0100, 4)
  put(data.length, version < 10 ? 8 : 16)
  for (const byte of data) put(byte, 8)
  const capacity = dataCodewords(version) * 8
  put(0, Math.min(4, capacity - bits.length))
  put(0, (8 - (bits.length % 8)) % 8)
  for (let pad = 0xec; bits.length < capacity; pad ^= 0xec ^ 0x11) put(pad, 8)
  const out: number[] = []
  for (let i = 0; i < bits.length; i += 8) out.push(bits.slice(i, i + 8).reduce((v, b) => (v << 1) | b, 0))
  return out
}

function multiply(x: number, y: number): number {
  let z = 0
  for (let i = 7; i >= 0; i--) {
    z = (z << 1) ^ ((z >>> 7) * 0x11d)
    z ^= ((y >>> i) & 1) * x
  }
  return z
}

function divisor(degree: number): number[] {
  const result = new Array<number>(degree).fill(0)
  result[degree - 1] = 1
  let root = 1
  for (let i = 0; i < degree; i++) {
    for (let j = 0; j < result.length; j++) {
      result[j] = multiply(result[j], root)
      if (j + 1 < result.length) result[j] ^= result[j + 1]
    }
    root = multiply(root, 0x02)
  }
  return result
}

function remainder(data: number[], by: number[]): number[] {
  const result = by.map(() => 0)
  for (const byte of data) {
    const factor = byte ^ (result.shift() as number)
    result.push(0)
    by.forEach((coefficient, i) => (result[i] ^= multiply(coefficient, factor)))
  }
  return result
}

function addEccAndInterleave(data: number[], version: number): number[] {
  const blocks = BLOCKS[version]
  const eccLength = ECC_PER_BLOCK[version]
  const raw = Math.floor(rawModules(version) / 8)
  const shortBlocks = blocks - (raw % blocks)
  const shortLength = Math.floor(raw / blocks)
  const by = divisor(eccLength)
  const all: number[][] = []
  for (let i = 0, k = 0; i < blocks; i++) {
    const part = data.slice(k, k + shortLength - eccLength + (i < shortBlocks ? 0 : 1))
    k += part.length
    const ecc = remainder(part, by)
    if (i < shortBlocks) part.push(0)
    all.push(part.concat(ecc))
  }
  const result: number[] = []
  for (let i = 0; i < all[0].length; i++) {
    all.forEach((block, j) => {
      if (i !== shortLength - eccLength || j >= shortBlocks) result.push(block[i])
    })
  }
  return result
}

// --- the matrix ------------------------------------------------------------------------------------------

class Matrix {
  readonly size: number
  readonly modules: boolean[][]
  private readonly fixed: boolean[][]

  constructor(readonly version: number) {
    this.size = version * 4 + 17
    this.modules = Array.from({ length: this.size }, () => new Array<boolean>(this.size).fill(false))
    this.fixed = Array.from({ length: this.size }, () => new Array<boolean>(this.size).fill(false))
  }

  private set(x: number, y: number, dark: boolean): void {
    this.modules[y][x] = dark
    this.fixed[y][x] = true
  }

  drawFunctionPatterns(): void {
    const size = this.size
    for (let i = 0; i < size; i++) {
      this.set(6, i, i % 2 === 0)
      this.set(i, 6, i % 2 === 0)
    }
    for (const [x, y] of [[3, 3], [size - 4, 3], [3, size - 4]]) {
      for (let dy = -4; dy <= 4; dy++) {
        for (let dx = -4; dx <= 4; dx++) {
          const distance = Math.max(Math.abs(dx), Math.abs(dy))
          if (x + dx >= 0 && x + dx < size && y + dy >= 0 && y + dy < size) this.set(x + dx, y + dy, distance !== 2 && distance !== 4)
        }
      }
    }
    const positions = this.alignmentPositions()
    const last = positions.length - 1
    positions.forEach((px, i) =>
      positions.forEach((py, j) => {
        if ((i === 0 && j === 0) || (i === 0 && j === last) || (i === last && j === 0)) return
        for (let dy = -2; dy <= 2; dy++) for (let dx = -2; dx <= 2; dx++) this.set(px + dx, py + dy, Math.max(Math.abs(dx), Math.abs(dy)) !== 1)
      })
    )
    this.drawFormatBits(0) // reserves the format areas; drawn again with the mask chosen
    if (this.version >= 7) {
      let rem = this.version
      for (let i = 0; i < 12; i++) rem = (rem << 1) ^ ((rem >>> 11) * 0x1f25)
      const bits = (this.version << 12) | rem
      for (let i = 0; i < 18; i++) {
        const dark = ((bits >>> i) & 1) !== 0
        const a = size - 11 + (i % 3)
        const b = Math.floor(i / 3)
        this.set(a, b, dark)
        this.set(b, a, dark)
      }
    }
  }

  private alignmentPositions(): number[] {
    if (this.version === 1) return []
    const count = Math.floor(this.version / 7) + 2
    const step = Math.ceil((this.version * 4 + 4) / (count * 2 - 2)) * 2
    const result = [6]
    for (let pos = this.size - 7; result.length < count; pos -= step) result.splice(1, 0, pos)
    return result
  }

  drawFormatBits(mask: number): void {
    const data = (FORMAT_M << 3) | mask
    let rem = data
    for (let i = 0; i < 10; i++) rem = (rem << 1) ^ ((rem >>> 9) * 0x537)
    const bits = ((data << 10) | rem) ^ 0x5412
    const bit = (i: number): boolean => ((bits >>> i) & 1) !== 0
    const size = this.size
    for (let i = 0; i <= 5; i++) this.set(8, i, bit(i))
    this.set(8, 7, bit(6))
    this.set(8, 8, bit(7))
    this.set(7, 8, bit(8))
    for (let i = 9; i < 15; i++) this.set(14 - i, 8, bit(i))
    for (let i = 0; i < 8; i++) this.set(size - 1 - i, 8, bit(i))
    for (let i = 8; i < 15; i++) this.set(8, size - 15 + i, bit(i))
    this.set(8, size - 8, true) // the dark module
  }

  drawCodewords(data: number[]): void {
    let i = 0
    for (let right = this.size - 1; right >= 1; right -= 2) {
      if (right === 6) right = 5
      for (let vertical = 0; vertical < this.size; vertical++) {
        for (let j = 0; j < 2; j++) {
          const x = right - j
          const upward = ((right + 1) & 2) === 0
          const y = upward ? this.size - 1 - vertical : vertical
          if (!this.fixed[y][x] && i < data.length * 8) {
            this.modules[y][x] = ((data[i >>> 3] >>> (7 - (i & 7))) & 1) !== 0
            i++
          }
        }
      }
    }
  }

  applyMask(mask: number): void {
    for (let y = 0; y < this.size; y++) {
      for (let x = 0; x < this.size; x++) {
        if (this.fixed[y][x]) continue
        let invert: boolean
        switch (mask) {
          case 0: invert = (x + y) % 2 === 0; break
          case 1: invert = y % 2 === 0; break
          case 2: invert = x % 3 === 0; break
          case 3: invert = (x + y) % 3 === 0; break
          case 4: invert = (Math.floor(x / 3) + Math.floor(y / 2)) % 2 === 0; break
          case 5: invert = ((x * y) % 2) + ((x * y) % 3) === 0; break
          case 6: invert = (((x * y) % 2) + ((x * y) % 3)) % 2 === 0; break
          default: invert = (((x + y) % 2) + ((x * y) % 3)) % 2 === 0
        }
        if (invert) this.modules[y][x] = !this.modules[y][x]
      }
    }
  } // prettier-ignore

  /** The standard's penalty: runs of five or more, 2x2 blocks, finder-like patterns, and the dark share. */
  penalty(): number {
    const size = this.size
    const m = this.modules
    let result = 0
    const lines: boolean[][] = []
    for (let i = 0; i < size; i++) {
      lines.push(m[i])
      lines.push(m.map((row) => row[i]))
    }
    for (const line of lines) {
      let run = 1
      for (let i = 1; i <= size; i++) {
        if (i < size && line[i] === line[i - 1]) run++
        else {
          if (run >= 5) result += run - 2
          run = 1
        }
      }
      const s = line.map((dark) => (dark ? '1' : '0')).join('')
      for (const pattern of ['10111010000', '00001011101']) {
        for (let at = s.indexOf(pattern); at >= 0; at = s.indexOf(pattern, at + 1)) result += 40
      }
    }
    for (let y = 0; y < size - 1; y++) {
      for (let x = 0; x < size - 1; x++) {
        const c = m[y][x]
        if (c === m[y][x + 1] && c === m[y + 1][x] && c === m[y + 1][x + 1]) result += 3
      }
    }
    const dark = m.reduce((n, row) => n + row.filter(Boolean).length, 0)
    const total = size * size
    result += Math.floor(Math.abs(dark * 20 - total * 10) / total) * 10
    return result
  }
}
