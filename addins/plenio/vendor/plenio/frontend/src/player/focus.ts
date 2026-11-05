/**
 * ``v-focus``: focus a field when it appears. The ``autofocus`` attribute works only when a page loads, not
 * for a field shown later - typing went to the page and set off its keys (V opened the visuals).
 */
import type { Directive } from 'vue'

export const vFocus: Directive<HTMLElement> = {
  mounted: (el) => el.focus(),
}
