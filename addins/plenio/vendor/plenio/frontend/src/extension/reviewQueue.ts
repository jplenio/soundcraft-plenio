/**
 * A run that stops for review, queued in a series (the owner's batch of 2026-10-23: 68 covers in *one cover,
 * stop to review* each waited at Song Sheet · Score, and nothing was rendered): when such a run joins a queue
 * that already has runs, or comes as several runs of one batch, a warning says that it waits for the Approve
 * and how to let the runs go through. Nothing is changed - the brief's mode stays the user's choice.
 *
 * The queue's size comes from ComfyUI's ``status`` events; the frontend calls ``beforeQueued`` on every widget
 * once per queued run, so the brief's *mode* widget hears of every run (also each one of a batch).
 */
import { type ComfyNode, type ComfyWidget } from '../shared/comfy'

/** The brief modes whose Song Sheets stop for review (``core.brief``: *careful*). */
export const REVIEW_MODES: Record<string, string> = {
  'one song, stop to review': 'new song every run',
  'one cover, stop to review': 'new cover every run'
}
/** Runs queued within this many milliseconds of each other count as one batch. */
export const BATCH_MS = 2000
/** One warning in this many milliseconds is enough. */
export const QUIET_MS = 30000

export interface ReviewNotice {
  summary: string
  detail: string
}

interface ModeWidget extends ComfyWidget {
  beforeQueued?: (options?: { isPartialExecution?: boolean }) => void
}

/** What a queued run in ``mode`` should be told: ``null`` when it runs through or stands alone. */
export function reviewNotice(brief: string, mode: string, queued: number, batch: number): ReviewNotice | null {
  const through = REVIEW_MODES[mode]
  if (!through || (queued <= 0 && batch <= 1)) return null
  return {
    summary: 'These runs stop for your review',
    detail:
      `${brief}: "${mode}" - each run waits at the Song Sheets until you press Approve, so queued runs render ` +
      `nothing by themselves. For runs that go through, choose "${through}" in the brief's mode.`
  }
}

/** The queue as this page hears of it, and the warnings it gave. */
export class ReviewQueue {
  /** Runs the server has (running and waiting), from its ``status`` events. */
  queued = 0
  private recent: number[] = []
  private lastNotice = -Infinity

  constructor(
    private readonly notify: (notice: ReviewNotice) => void,
    private readonly now: () => number = Date.now
  ) {}

  status(remaining: unknown): void {
    if (typeof remaining === 'number' && Number.isFinite(remaining)) this.queued = Math.max(0, remaining)
  }

  /** A run of a brief in ``mode`` is being queued. */
  queuing(brief: string, mode: string): void {
    const now = this.now()
    this.recent = [...this.recent.filter((t) => now - t < BATCH_MS), now]
    const notice = reviewNotice(brief, mode, this.queued, this.recent.length)
    if (!notice || now - this.lastNotice < QUIET_MS) return
    this.lastNotice = now
    this.notify(notice)
  }

  /** Hear of every run queued with this brief node (its *mode* widget's ``beforeQueued``). */
  watch(node: ComfyNode): void {
    const mode = node.widgets?.find((w) => w.name === 'mode') as ModeWidget | undefined
    if (!mode) return
    const before = mode.beforeQueued
    mode.beforeQueued = (options) => {
      before?.(options)
      if (!options?.isPartialExecution) this.queuing(String(node.title || node.type), String(mode.value ?? ''))
    }
  }
}
