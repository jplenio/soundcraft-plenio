// The Song Sheet's editor button says what one edits there (owner's request 2026-10-24): the words, the score,
// or the score composed in the DAW template's piano roll.
import { describe, expect, it } from 'vitest'

import { SHEET_LOOKS, sheetKind } from '../src/extension/sheetKind'
import type { ComfyNode } from '../src/shared/comfy'

function sheet(linked: string[], properties: Record<string, unknown> = {}): ComfyNode {
  const names = ['title', 'style', 'lyrics', 'score', 'artwork_prompt', 'context_score']
  return {
    id: 7,
    type: 'PlenioSongSheet',
    properties,
    inputs: names.map((name, index) => ({ name, link: linked.includes(name) ? index + 1 : null }))
  } as unknown as ComfyNode
}

describe('sheetKind', () => {
  it('tells the words, the score and the DAW apart', () => {
    expect(sheetKind(sheet(['title', 'style', 'lyrics', 'artwork_prompt']))).toBe('text')
    // a cover's text sheet shows the score as context: it still edits the words
    expect(sheetKind(sheet(['lyrics', 'context_score']))).toBe('text')
    expect(sheetKind(sheet(['score']))).toBe('score')
    expect(sheetKind(sheet(['score'], { plenio_editor_layout: 'daw' }))).toBe('daw')
    // a sheet without links (just added) edits the words
    expect(sheetKind(sheet([]))).toBe('text')
  })

  it('has a name, a line and an icon for each kind', () => {
    for (const look of Object.values(SHEET_LOOKS)) {
      expect(look.name).toMatch(/^(Edit|Compose) /)
      expect(look.what.length).toBeGreaterThan(10)
      expect(look.icon).toMatch(/^<svg viewBox="0 0 24 24"/)
    }
  })
})
