/**
 * What a Song Sheet's editor button edits, said with an icon (owner's request 2026-10-24: the sheets that stop
 * a run for review should stand out, and their button should show at once what one edits there). The kind is
 * read from the node: a sheet that gets a score edits the score (the DAW template's sheet composes it in the
 * piano roll), any other the words - title, style, lyrics and the cover prompt.
 */
import type { ComfyNode } from '../shared/comfy'

export type SheetKind = 'text' | 'score' | 'daw'

export interface SheetLook {
  /** The button's first line: what one does there. */
  name: string
  /** The second line: what the editor holds. */
  what: string
  icon: string
}

export const SHEET_LOOKS: Record<SheetKind, SheetLook> = {
  text: {
    name: 'Edit lyrics & text',
    what: 'Title · style · lyrics · cover prompt',
    // a written page and a pen
    icon:
      '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 2.5h8.2L18.5 7v4.6l-2 2V8h-4V4.5H6v15h5.4l-.5 2H6a2 2 0 0 1-2-2v-15a2 2 0 0 1 2-2z"/>' +
      '<path d="M7.6 10h7v1.7h-7zM7.6 13.4h5.6v1.7H7.6zM7.6 16.8h3.2v1.7H7.6z"/><path d="M20.3 12.6l1.6 1.6-6.7 6.7-2.6.9.9-2.6z"/></svg>'
  },
  score: {
    name: 'Edit the score',
    what: 'Melody · chords · sections · listen and compare',
    // notes on a staff
    icon:
      '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M2 6h20M2 9.5h20M2 13h20M2 16.5h20" fill="none" stroke="currentColor" stroke-width="1" opacity=".45"/>' +
      '<path d="M8.6 5.2l11-2.6v12.6a2.9 2.3 0 1 1-1.8-2.1V6.2l-7.4 1.8v9.4a2.9 2.3 0 1 1-1.8-2.1z"/></svg>'
  },
  daw: {
    name: 'Compose the score',
    what: 'Piano roll · chords · sections · MIDI',
    // the piano roll: keys and notes
    icon:
      '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M2 3.5h5v17H2z" opacity=".5"/><path d="M2 7.6h3.2v1.4H2zM2 12h3.2v1.4H2zM2 16.4h3.2v1.4H2z"/>' +
      '<rect x="9" y="4.5" width="6.5" height="2.8" rx="1.1"/><rect x="12.5" y="9" width="9" height="2.8" rx="1.1"/>' +
      '<rect x="9" y="13.5" width="4.5" height="2.8" rx="1.1"/><rect x="15" y="18" width="6.5" height="2.8" rx="1.1"/></svg>'
  }
}

interface InputSlot {
  name?: string
  link?: number | null
}

/** The sheet's kind: the template's editor layout, else whether a score comes in. */
export function sheetKind(node: ComfyNode): SheetKind {
  if (node.properties?.plenio_editor_layout === 'daw') return 'daw'
  const inputs = ((node as unknown as { inputs?: InputSlot[] }).inputs ?? []) as InputSlot[]
  return inputs.some((slot) => slot.name === 'score' && slot.link != null) ? 'score' : 'text'
}
