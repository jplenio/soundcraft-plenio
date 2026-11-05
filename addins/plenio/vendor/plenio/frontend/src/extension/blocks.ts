/**
 * Plenio blocks saved in a workflow before they followed the brief's creativity, brought up to date as the
 * workflow opens (owner's report 2026-10-20: a tab the browser restored on another device had the slider at
 * 100 on its Song Brief, and the song's plan and take sampling were still 50's).
 *
 * ComfyUI keeps each block's inner graph in the workflow. Before the workflow is configured
 * (``beforeConfigureGraph``), a workflow with a Plenio block that samples (the writer's first draft, YuE2's plan
 * or take) but has no Creativity node goes to the backend (``plenio/core/blocks.py``): those blocks become the
 * current ones and the YuE2 blocks' *creativity* is linked from the brief. The graph is changed in place - the
 * frontend configures what it was given - and a toast says what changed and what was kept as it was.
 */
import { type BlocksUpgrade, type Fetcher, upgradeBlocks } from '../api/client'

const BLOCK_PREFIX = 'Plenio · '
/** The nodes of a block the creativity steers: its sampling or the prompt of a first draft. */
const STEERED = new Set(['YuE2GenerateABC', 'YuE2GenerateMusic', 'PlenioComposePrompt', 'PlenioComposeArrangement'])
const CREATIVITY_NODE = 'PlenioCreativity'

interface Definition {
  name?: unknown
  nodes?: { type?: unknown }[]
}

function definitions(graph: unknown): Definition[] {
  const subgraphs = (graph as { definitions?: { subgraphs?: unknown } } | null)?.definitions?.subgraphs
  return Array.isArray(subgraphs) ? (subgraphs as Definition[]) : []
}

/** ``true`` when ``graph`` has a Plenio block that samples without a Creativity node (saved before 1.0.2). */
export function mayBeOutdated(graph: unknown): boolean {
  return definitions(graph).some((definition) => {
    if (typeof definition?.name !== 'string' || !definition.name.startsWith(BLOCK_PREFIX)) return false
    const types = new Set((definition.nodes ?? []).map((node) => node?.type))
    return !types.has(CREATIVITY_NODE) && [...types].some((type) => STEERED.has(String(type)))
  })
}

/** Brings ``graph``'s blocks up to date in place; what the backend answered (``null``: nothing to ask). */
export async function bringBlocksUpToDate(graph: unknown, fetcher: Fetcher): Promise<BlocksUpgrade | null> {
  if (!graph || typeof graph !== 'object' || !mayBeOutdated(graph)) return null
  const answer = await upgradeBlocks(fetcher, graph)
  if (answer.workflow) {
    const target = graph as Record<string, unknown>
    for (const key of Object.keys(target)) delete target[key]
    Object.assign(target, answer.workflow)
  }
  return answer
}

const short = (name: string): string => (name.startsWith(BLOCK_PREFIX) ? name.slice(BLOCK_PREFIX.length) : name)
const list = (names: string[]): string => names.map(short).join(', ')

export interface BlocksMessage {
  severity: 'info' | 'warn'
  summary: string
  detail: string
}

/** The toasts for an answer: what was brought up to date, and what the creativity does not reach. */
export function blocksMessages(answer: BlocksUpgrade | null): BlocksMessage[] {
  if (!answer) return []
  const out: BlocksMessage[] = []
  if (answer.updated.length) {
    const linked = answer.linked.length ? ` The creativity of ${list(answer.linked)} now comes from the brief.` : ''
    out.push({
      severity: 'info',
      summary: 'Plenio blocks brought up to date',
      detail:
        `This workflow was saved before its blocks followed the brief's creativity: ${list(answer.updated)} are the ` +
        `current blocks now.${linked} At creativity 50 they work exactly as before. Save the workflow to keep it.`
    })
  }
  const missed = [
    ...answer.kept.map(([name, why]) => `${short(name)} was kept as it was (${why}) - its sampling stays fixed`),
    ...answer.unlinked.map(([name, why]) => `${short(name)} has its own creativity slider (${why})`)
  ]
  if (missed.length) {
    out.push({
      severity: 'warn',
      summary: "The brief's creativity does not reach every block",
      detail: `${missed.join('; ')}. The template, opened again from the template browser, has the current blocks.`
    })
  }
  return out
}
