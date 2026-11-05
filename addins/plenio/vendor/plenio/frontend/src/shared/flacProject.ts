/**
 * The Plenio project inside a song's FLAC (GitHub issue #9): Export Release writes the release record into an
 * APPLICATION metadata block - the id ``PLNO``, ``plenio.project/1``, a NUL, then the record as gzip-compressed
 * JSON (``plenio/core/release.py``). Read here in the browser from the file's metadata blocks only, so a FLAC
 * that is chosen or dropped is not uploaded to continue its song.
 */

const RECORD_SCHEMA = 'plenio.record/1'
const APPLICATION = 2
const PROJECT_ID = 'PLNO'
const PREFIX = new TextEncoder().encode(`${PROJECT_ID}plenio.project/1\0`)
/** The largest record a project may unpack to (as large as a release record file may be). */
export const MAX_PROJECT_BYTES = 32 * 2 ** 20

/** A FLAC whose project cannot be read: no FLAC at all, or a damaged or unknown project. */
export class FlacProjectError extends Error {}

async function read(file: Blob, start: number, length: number): Promise<Uint8Array> {
  return new Uint8Array(await file.slice(start, start + length).arrayBuffer())
}

function startsWith(data: Uint8Array, prefix: Uint8Array): boolean {
  return data.length >= prefix.length && prefix.every((byte, i) => data[i] === byte)
}

async function unpack(packed: Blob): Promise<string> {
  const reader = packed.stream().pipeThrough(new DecompressionStream('gzip')).getReader()
  const chunks: Uint8Array[] = []
  let total = 0
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    total += value.length
    if (total > MAX_PROJECT_BYTES) {
      await reader.cancel()
      throw new FlacProjectError(`its Plenio project is larger than ${MAX_PROJECT_BYTES / 2 ** 20} MB`)
    }
    chunks.push(value)
  }
  const all = new Uint8Array(total)
  let offset = 0
  for (const chunk of chunks) {
    all.set(chunk, offset)
    offset += chunk.length
  }
  return new TextDecoder().decode(all)
}

/** The release record a FLAC carries (``null``: none - exported before Plenio 0.8.0, or with *project in FLAC*
 * off). Throws a ``FlacProjectError`` for a file that is no FLAC or whose project is damaged or unknown. */
export async function projectOfFlac(file: Blob): Promise<Record<string, unknown> | null> {
  if (!startsWith(await read(file, 0, 4), new TextEncoder().encode('fLaC'))) throw new FlacProjectError('it is not a FLAC file')
  let at = 4
  for (;;) {
    const header = await read(file, at, 4)
    if (header.length < 4) throw new FlacProjectError('the file ends inside its metadata')
    const length = (header[1] << 16) | (header[2] << 8) | header[3]
    if ((header[0] & 0x7f) === APPLICATION && length >= 4) {
      const head = await read(file, at + 4, Math.min(length, PREFIX.length))
      if (startsWith(head, PREFIX.subarray(0, 4))) {
        if (!startsWith(head, PREFIX)) throw new FlacProjectError('it holds a Plenio project of an unknown layout (made by a newer Plenio)')
        let text: string
        try {
          text = await unpack(file.slice(at + 4 + PREFIX.length, at + 4 + length))
        } catch (error) {
          if (error instanceof FlacProjectError) throw error
          throw new FlacProjectError(`its Plenio project is damaged (${error instanceof Error ? error.message : String(error)})`)
        }
        let record: unknown
        try {
          record = JSON.parse(text)
        } catch {
          throw new FlacProjectError('its Plenio project is damaged (no JSON)')
        }
        if ((record as { schema?: unknown } | null)?.schema !== RECORD_SCHEMA) {
          throw new FlacProjectError(`its Plenio project is no release record (${RECORD_SCHEMA})`)
        }
        return record as Record<string, unknown>
      }
    }
    if (header[0] & 0x80) return null
    at += 4 + length
  }
}

/** Whether a file is a FLAC by its name or type. */
export function isFlac(file: File): boolean {
  return /\.flac$/i.test(file.name ?? '') || file.type === 'audio/flac' || file.type === 'audio/x-flac'
}
