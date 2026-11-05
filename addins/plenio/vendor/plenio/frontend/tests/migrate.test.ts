import { describe, expect, it } from 'vitest'

import { comboOptions, migrateExportTags, migrateWidgetValues, renameWidgetValues } from '../src/extension/migrate'
import type { ComfyNodeDef } from '../src/shared/comfy'

const songBrief: ComfyNodeDef = {
  name: 'PlenioSongBrief',
  input: {
    required: {
      mode: ['COMBO', { options: ['new song every run', 'one song, stop to review'], default: 'new song every run' }],
      template: ['COMBO', { options: ['none', 'pop/singer-songwriter-acoustic-vocal'] }]
    }
  }
}

describe('widget values of older workflows', () => {
  it('reads combo options in both spec forms', () => {
    expect(comboOptions(songBrief, 'mode')).toEqual(['new song every run', 'one song, stop to review'])
    expect(comboOptions({ name: 'X', input: { required: { mode: [['a', 'b'], {}] } } }, 'mode')).toEqual(['a', 'b'])
    expect(comboOptions(songBrief, 'missing')).toEqual([])
  })

  it('puts the careful mode in front of a Song Brief saved before 0.2.2', () => {
    const info = { widgets_values: ['pop/singer-songwriter-acoustic-vocal', 'a song', 'pop'] }
    expect(migrateWidgetValues(songBrief, info).widgets_values).toEqual([
      'one song, stop to review',
      'pop/singer-songwriter-acoustic-vocal',
      'a song',
      'pop'
    ])
    expect(info.widgets_values).toHaveLength(3) // the saved data itself is not changed
  })

  it('renames the pre-release arrangement "simple" to "off"', () => {
    const widgets = [
      { name: 'arrangement', value: 'simple' },
      { name: 'description', value: 'simple' } // a text that happens to be the word stays
    ]
    expect(renameWidgetValues('PlenioCoverBrief', widgets)).toEqual(['arrangement'])
    expect(widgets.map((w) => w.value)).toEqual(['off', 'simple'])
    expect(renameWidgetValues('PlenioSongBrief', [{ name: 'arrangement', value: 'varied' }])).toEqual([])
    expect(renameWidgetValues('PlenioSongSheet', [{ name: 'arrangement', value: 'simple' }])).toEqual([])
  })

  it('keeps current values and other nodes as they are', () => {
    const current = { widgets_values: ['new song every run', 'none', ''] }
    expect(migrateWidgetValues(songBrief, current)).toBe(current)
    const other = { widgets_values: ['none'] }
    expect(migrateWidgetValues({ name: 'PlenioSongSheet' }, other)).toBe(other)
  })

  it('adds the mode to named values', () => {
    const info = { widgets_values_named: { template: 'none' } }
    expect(migrateWidgetValues({ ...songBrief, name: 'PlenioCoverBrief' }, info).widgets_values_named).toEqual({
      mode: 'one cover, stop to review',
      template: 'none'
    })
  })
})

describe('Export Release saved before 1.0.0', () => {
  const old = ['plenio', '{date} {title}', 'number', true, false, false, 'tags', 'A', 'B', '2026', '3', 'pop', 'c', 'AA', 'Comp', 'PDF (A4)', 'standard', true]

  it('gets an empty lyrics tag after the composer, so the values after it stay on their widgets', () => {
    const migrated = migrateExportTags(old)
    expect(migrated.slice(14, 19)).toEqual(['Comp', '', 'PDF (A4)', 'standard', true])
    const info = migrateWidgetValues({ name: 'PlenioExportRelease' } as ComfyNodeDef, { widgets_values: old })
    expect((info.widgets_values as unknown[]).length).toBe(19)
  })

  it('leaves the title-only mode and the current layout alone', () => {
    const titleOnly = ['plenio', '{date} {title}', 'number', true, false, false, 'title only', 'PDF (A4)', 'standard', true]
    expect(migrateExportTags(titleOnly)).toBe(titleOnly)
    const current = [...old.slice(0, 15), '{lyrics}', 'PDF (A4)', 'standard', true, true]
    expect(migrateExportTags(current)).toBe(current)
  })
})
