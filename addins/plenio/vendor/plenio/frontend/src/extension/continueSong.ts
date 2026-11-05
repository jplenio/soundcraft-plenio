/**
 * Continue a song from its release record (owner's request 2026-10-11): the menu entry *File > Continue
 * a Plenio song…* lists the records of the output folder (and opens a record file or a song's FLAC from
 * elsewhere), and a ``<name>.plenio.json`` dropped onto ComfyUI continues that song - the frontend would
 * otherwise take the record for a workflow and load nothing. Since 0.8.0 the song's FLAC carries its record
 * too (GitHub issue #9): a FLAC dropped onto the empty canvas continues its song.
 * The backend decides what is restored (``core.continuation``); ``shared/continuation.ts`` applies it.
 */
import { type Fetcher, PlenioApiError, continueRecord } from '../api/client'
import type { ComfyApp } from '../shared/comfy'
import { FlacProjectError, isFlac, projectOfFlac } from '../shared/flacProject'
import { type GraphLike, applyContinuation, describe, documentsIntoSheets, workflowName } from '../shared/continuation'
import { codeIsStale, importOrReload, loadFresh } from './staleCode'

export const CONTINUE_COMMAND = 'Plenio.ContinueSong'
const RECORD_SCHEMA = 'plenio.record/1'

type Request = { path: string } | { record: unknown; name: string }

/** The graph canvas as far as a drop needs it: its element and the graph position of a pointer event. */
interface DropCanvas {
  canvas?: unknown
  convertEventToCanvasOffset?(event: MouseEvent): [number, number] | number[]
}

/** The part of the ComfyUI app this uses besides the toast: loading a workflow (``app.loadGraphData``) and,
 * for a dropped FLAC without a Plenio project, what the frontend does with a dropped file (``app.handleFile``). */
export interface ContinueApp extends Omit<ComfyApp, 'canvas'> {
  canvas?: DropCanvas & { ds?: { scale?: number } }
  loadGraphData?(graph: unknown, clean?: boolean, restoreView?: boolean, workflow?: string | null): Promise<void>
  handleFile?(file: File): Promise<void>
}

export interface ContinueHost {
  app: ContinueApp
  fetcher: Fetcher
}

function toast(host: ContinueHost, severity: string, summary: string, detail: string, life = 20000): void {
  host.app.extensionManager?.toast?.add({ severity, summary, detail, life })
}

/** Continue the song of a record: open its workflow with its documents kept, or - when none can be rebuilt -
 * put its documents into the open workflow's Song Sheets. Throws when neither is possible. */
export async function continueSong(host: ContinueHost, request: Request): Promise<void> {
  const plan = await continueRecord(host.fetcher, request)
  if (plan.workflow) {
    if (!host.app.loadGraphData) throw new Error('This ComfyUI frontend cannot load a workflow for Plenio.')
    await host.app.loadGraphData(plan.workflow, true, true, workflowName('path' in request ? request.path : request.name, plan.title))
    const graph = host.app.graph as (GraphLike & { setDirtyCanvas?(a: boolean, b: boolean): void }) | undefined
    if (!graph) throw new Error('The workflow did not load.')
    const applied = applyContinuation(graph, plan)
    graph.setDirtyCanvas?.(true, true)
    if (applied.missing.length) console.warn('Plenio: settings of the song without a field in this workflow', applied.missing)
    toast(host, 'success', 'Song opened', describe(plan, applied))
    return
  }
  const graph = host.app.graph as GraphLike | undefined
  const sheets = graph ? documentsIntoSheets(graph, plan.documents) : 0
  if (!sheets) {
    throw new PlenioApiError(
      describe(plan, null),
      "Open a workflow with a Song Sheet (a Plenio template) and continue again: the song's texts and score then go into its Song Sheets."
    )
  }
  toast(host, 'success', 'Song texts taken', `${describe(plan, null)} Its texts and score went into this workflow's Song Sheets (${sheets}, manual).`)
}

/** The record in ``file``: a release record, or the one a song's FLAC carries (``null``: none). A FLAC whose
 * project is damaged throws (``FlacProjectError``). */
export async function recordOf(file: File): Promise<unknown | null> {
  if (isFlac(file)) return projectOfFlac(file)
  if (!/\.json$/i.test(file.name ?? '')) return null
  try {
    const data = JSON.parse(await file.text()) as { schema?: unknown } | null
    return data?.schema === RECORD_SCHEMA ? data : null
  } catch {
    return null
  }
}

/** A drop that carries a release record (``<name>.plenio.json``) - only then is the drop Plenio's. */
export function droppedRecord(event: DragEvent): File | null {
  const files = [...(event.dataTransfer?.files ?? [])]
  return files.length === 1 && /\.plenio\.json$/i.test(files[0].name) ? files[0] : null
}

/** A single FLAC dropped onto the empty canvas without Shift: it may carry its song's record. A drop onto a
 * node (its upload), onto the rest of the page or with Shift held stays the frontend's - decided at once,
 * since only a drop handled at once can be kept from the frontend. */
export function droppedFlac(event: DragEvent, app: ContinueApp): File | null {
  const files = [...(event.dataTransfer?.files ?? [])]
  if (files.length !== 1 || !isFlac(files[0]) || event.shiftKey) return null
  const canvas = app.canvas
  const graph = app.graph as { getNodeOnPos?(x: number, y: number): unknown } | undefined
  if (!canvas?.canvas || event.target !== canvas.canvas || !canvas.convertEventToCanvasOffset || !graph?.getNodeOnPos) return null
  const [x, y] = canvas.convertEventToCanvasOffset(event)
  return graph.getNodeOnPos(x, y) ? null : files[0]
}

/**
 * Let a release record dropped onto ComfyUI continue its song. A DOM listener in the capture phase takes
 * the drop of a ``<name>.plenio.json`` before the frontend does (it would take the record for a workflow and
 * load nothing), and that of a FLAC onto the empty canvas (``droppedFlac``): one that carries its song's
 * record continues the song, any other goes to ``app.handleFile`` - what the frontend does with a drop (a Load
 * Audio node, or the workflow ComfyUI saved in it). Every other drop reaches the frontend unchanged (R11: no
 * frontend internals are patched).
 * Returns the listener's removal.
 */
export function installRecordDrop(host: ContinueHost, target: Pick<Window, 'addEventListener' | 'removeEventListener'> = window): () => void {
  const onDrop = (event: Event) => {
    const flac = droppedRecord(event as DragEvent) ? null : droppedFlac(event as DragEvent, host.app)
    const file = flac ?? droppedRecord(event as DragEvent)
    if (!file) return
    event.preventDefault()
    event.stopImmediatePropagation()
    void (async () => {
      if (flac) {
        const carried = await projectOfFlac(flac)
        if (carried) return continueSong(host, { record: carried, name: flac.name })
        if (!host.app.handleFile) throw new PlenioApiError(`${flac.name} carries no Plenio project.`, 'Drop it with Shift held to give it to ComfyUI.')
        return host.app.handleFile(flac)
      }
      const record = await recordOf(file)
      if (!record) throw new PlenioApiError(`${file.name} is no Plenio release record.`, 'Drop the <name>.plenio.json that Export Release wrote next to the song.')
      await continueSong(host, { record, name: file.name })
    })().catch((error: unknown) => {
      const detail =
        error instanceof FlacProjectError
          ? `${file.name}: ${error.message}.`
          : error instanceof PlenioApiError && error.hint
            ? `${error.message} ${error.hint}`
            : String(error instanceof Error ? error.message : error)
      toast(host, 'error', 'Song not opened', detail, 30000)
    })
  }
  target.addEventListener('drop', onDrop, true)
  return () => target.removeEventListener('drop', onDrop, true)
}

/** The *Continue a song* dialog (its code is loaded when it opens). */
export async function openContinueSong(host: ContinueHost): Promise<void> {
  const stale = () => codeIsStale(import.meta.url, loadFresh)
  const { openContinueDialog } = await importOrReload(() => import('../continue/openContinue'), stale)
  openContinueDialog(host.fetcher, (request) => continueSong(host, request))
}
