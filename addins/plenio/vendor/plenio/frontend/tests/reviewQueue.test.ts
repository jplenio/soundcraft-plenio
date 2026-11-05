/**
 * Runs that stop for review, queued in a series (the owner's batch of 2026-10-23: 68 covers waited at Song
 * Sheet · Score): a warning when such a run joins a queue or comes as a batch - and none for runs that go
 * through or stand alone.
 */
import { describe, expect, it } from 'vitest'

import type { ComfyNode } from '../src/shared/comfy'
import { BATCH_MS, QUIET_MS, type ReviewNotice, ReviewQueue, reviewNotice } from '../src/extension/reviewQueue'

function brief(mode: string): ComfyNode {
  return { id: 1, type: 'PlenioCoverBrief', title: 'Cover Brief', widgets: [{ name: 'mode', type: 'combo', value: mode, options: {} }] } as unknown as ComfyNode
}

function queue(): { queue: ReviewQueue; notices: ReviewNotice[]; clock: { t: number } } {
  const notices: ReviewNotice[] = []
  const clock = { t: 1_000_000 }
  return { queue: new ReviewQueue((n) => notices.push(n), () => clock.t), notices, clock }
}

function run(node: ComfyNode): void {
  const mode = node.widgets?.find((w) => w.name === 'mode') as { beforeQueued?: (o?: { isPartialExecution?: boolean }) => void }
  mode.beforeQueued?.()
}

describe('reviewQueue', () => {
  it('says what a review stop means for a queue, and how to run through', () => {
    expect(reviewNotice('Cover Brief', 'new cover every run', 5, 3)).toBeNull()
    expect(reviewNotice('Cover Brief', 'one cover, stop to review', 0, 1)).toBeNull() // alone: the stop is wanted
    const notice = reviewNotice('Cover Brief', 'one cover, stop to review', 2, 1)
    expect(notice?.detail).toContain('"new cover every run"')
    expect(reviewNotice('Song Brief', 'one song, stop to review', 0, 2)?.detail).toContain('"new song every run"')
  })

  it('warns once when runs in review mode join a queue, also as a batch', () => {
    const { queue: q, notices, clock } = queue()
    const node = brief('one cover, stop to review')
    q.watch(node)
    run(node) // alone, the queue empty
    expect(notices).toHaveLength(0)
    q.status(1) // one run waiting
    clock.t += BATCH_MS + 1
    run(node)
    run(node)
    expect(notices).toHaveLength(1) // once, not for every run
    clock.t += QUIET_MS + 1
    q.status(0)
    run(node)
    expect(notices).toHaveLength(1)
    run(node) // the second run of a batch, a moment later
    expect(notices).toHaveLength(2)
  })

  it('keeps quiet for runs that go through, and keeps what the widget did before', () => {
    const { queue: q, notices } = queue()
    const node = brief('new cover every run')
    let before = 0
    const mode = node.widgets![0] as { beforeQueued?: () => void }
    mode.beforeQueued = () => {
      before += 1
    }
    q.watch(node)
    q.status(4)
    run(node)
    run(node)
    expect(notices).toHaveLength(0)
    expect(before).toBe(2)
  })
})
