/**
 * A song continued from its FLAC (GitHub issue #9): Export Release writes the release record into an APPLICATION
 * block of the FLAC; the browser reads it from the metadata only, a FLAC dropped onto the empty canvas continues
 * its song, and a FLAC without one goes to the frontend as before.
 */
import { describe, expect, it, vi } from 'vitest'

import type { Fetcher } from '../src/api/client'
import { type ContinueApp, droppedFlac, installRecordDrop, recordOf } from '../src/extension/continueSong'
import { FlacProjectError, projectOfFlac } from '../src/shared/flacProject'
import { workflowName } from '../src/shared/continuation'

const RECORD = { schema: 'plenio.record/1', title: 'Harbour Lights', documents: { lyrics: { text: 'Über den Dächern' } } }

async function gzip(text: string): Promise<Uint8Array> {
  const stream = new Blob([new TextEncoder().encode(text)]).stream().pipeThrough(new CompressionStream('gzip'))
  return new Uint8Array(await new Response(stream).arrayBuffer())
}

function block(kind: number, body: Uint8Array, last = false): Uint8Array<ArrayBuffer> {
  const header = new Uint8Array([(last ? 0x80 : 0) | kind, (body.length >> 16) & 0xff, (body.length >> 8) & 0xff, body.length & 0xff])
  return concat(header, body)
}

function concat(...parts: Uint8Array[]): Uint8Array<ArrayBuffer> {
  const all = new Uint8Array(parts.reduce((n, p) => n + p.length, 0))
  let at = 0
  for (const part of parts) {
    all.set(part, at)
    at += part.length
  }
  return all
}

const text = (s: string) => new TextEncoder().encode(s)

/** A FLAC as Export Release writes it: STREAMINFO, another application's block, the project, padding, frames. */
async function flac(project: Uint8Array | null, name = 'Harbour Lights.flac'): Promise<File> {
  const parts = [text('fLaC'), block(0, new Uint8Array(34)), block(2, text('riffsomething else'))]
  if (project) parts.push(block(2, project))
  parts.push(block(1, new Uint8Array(16), true), new Uint8Array(1000).fill(7))
  return new File([concat(...parts)], name, { type: 'audio/flac' })
}

async function project(record: unknown = RECORD): Promise<Uint8Array> {
  return concat(text('PLNOplenio.project/1\0'), await gzip(JSON.stringify(record)))
}

describe('the project in a FLAC', () => {
  it('is read from the metadata', async () => {
    expect(await projectOfFlac(await flac(await project()))).toEqual(RECORD)
    expect(await recordOf(await flac(await project()))).toEqual(RECORD)
    expect(await projectOfFlac(await flac(null))).toBeNull() // exported before 0.8.0, or without it
  })

  it('says why it cannot be read', async () => {
    await expect(projectOfFlac(new File([text('ID3 an mp3')], 'x.flac'))).rejects.toBeInstanceOf(FlacProjectError)
    await expect(projectOfFlac(await flac(concat(text('PLNOplenio.project/9\0'), text('...'))))).rejects.toThrow('unknown layout')
    await expect(projectOfFlac(await flac(concat(text('PLNOplenio.project/1\0'), text('not gzip'))))).rejects.toThrow('damaged')
    await expect(projectOfFlac(await flac(await project({ schema: 'other/1' })))).rejects.toThrow('no release record')
  })

  it('names the workflow after the FLAC', () => {
    expect(workflowName('C:\\Music\\Harbour Lights.flac', 'Harbour Lights')).toBe('Harbour Lights')
  })
})

describe('a FLAC dropped onto ComfyUI', () => {
  function setup(nodeAtDrop: unknown = null) {
    const target = new EventTarget() as unknown as Window
    const loaded: unknown[] = []
    const handled: File[] = []
    const app: ContinueApp = {
      registerExtension: () => undefined,
      graph: { getNodeOnPos: () => nodeAtDrop, nodes: [], getNodeById: () => null },
      canvas: { canvas: target, convertEventToCanvasOffset: () => [10, 20] },
      loadGraphData: async (data: unknown) => {
        loaded.push(data)
      },
      handleFile: async (file: File) => {
        handled.push(file)
      },
      extensionManager: { toast: { add: vi.fn() } }
    }
    const fetcher = {
      fetchApi: vi.fn(async () => ({ ok: true, status: 200, json: async () => ({ schema: 'plenio.continuation/1', title: 'Harbour Lights', created: '', plenio: '0.8.0', source: '', documents: {}, files: [], workflow: { nodes: [], marker: 1 }, from: 'record', template: null, sheets: {}, values: {}, activate: [], unplaced: [] }) }) as unknown as Response)
    } satisfies Fetcher
    const remove = installRecordDrop({ app, fetcher }, target)
    const later = vi.fn()
    target.addEventListener('drop', later)
    const drop = (file: File, shiftKey = false) => {
      const event = new Event('drop', { cancelable: true }) as DragEvent
      Object.defineProperty(event, 'dataTransfer', { value: { files: [file] } })
      Object.defineProperty(event, 'shiftKey', { value: shiftKey })
      target.dispatchEvent(event)
      return event
    }
    return { app, target, loaded, handled, fetcher, later, drop, remove }
  }

  it('continues its song when it carries one', async () => {
    const { drop, later, loaded, fetcher, remove } = setup()
    const event = drop(await flac(await project()))
    expect(event.defaultPrevented).toBe(true)
    expect(later).not.toHaveBeenCalled()
    await vi.waitFor(() => expect(loaded).toEqual([{ nodes: [], marker: 1 }]))
    const [route, init] = fetcher.fetchApi.mock.calls[0] as unknown as [string, RequestInit]
    expect(route).toBe('/plenio/records/continue')
    expect(JSON.parse(String(init.body))).toEqual({ record: RECORD, name: 'Harbour Lights.flac' })
    remove()
  })

  it('goes to the frontend without one, onto a node or with Shift', async () => {
    const plain = await flac(null, 'take.flac')
    const free = setup()
    expect(free.drop(plain).defaultPrevented).toBe(true)
    await vi.waitFor(() => expect(free.handled).toEqual([plain])) // what the frontend does: a Load Audio node
    expect(free.fetcher.fetchApi).not.toHaveBeenCalled()
    free.remove()

    const onNode = setup({ id: 3 })
    expect(onNode.drop(plain).defaultPrevented).toBe(false) // a node's own upload
    expect(onNode.later).toHaveBeenCalledTimes(1)
    onNode.remove()

    const shifted = setup()
    expect(shifted.drop(await flac(await project()), true).defaultPrevented).toBe(false)
    shifted.remove()
  })

  it('decides at once by where it lands', async () => {
    const app = { registerExtension: () => undefined, graph: { getNodeOnPos: () => null }, canvas: { canvas: 'the canvas', convertEventToCanvasOffset: () => [0, 0] } } as unknown as ContinueApp
    const event = (target: unknown, files: File[]) => ({ dataTransfer: { files }, target, shiftKey: false }) as unknown as DragEvent
    const file = await flac(null)
    expect(droppedFlac(event('the canvas', [file]), app)).toBe(file)
    expect(droppedFlac(event('a sidebar', [file]), app)).toBeNull()
    expect(droppedFlac(event('the canvas', [file, file]), app)).toBeNull()
    expect(droppedFlac(event('the canvas', [new File(['{}'], 'w.json')]), app)).toBeNull()
  })
})
