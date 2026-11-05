<script setup lang="ts">
/**
 * A song's stars, 0 to 5 in halves (owner's request 2026-10-29): the listener's own, given by ear - drawn clearly -
 * and, until they gave some, the measured ones as a faded pre-fill: a hint where to listen first, never the verdict.
 * Click a star (its left half: a half star); 0 and ✕ beside them.
 */
import { computed, ref } from 'vue'

const props = defineProps<{
  /** Given by ear (``null``: not yet). */
  rating: number | null
  /** Measured from the sound and the record (``null``: not measured). */
  measured?: number | null
  editable?: boolean
  size?: number
}>()
const emit = defineEmits<{ rate: [value: number | null] }>()

const hover = ref<number | null>(null)
const shown = computed(() => hover.value ?? props.rating ?? props.measured ?? 0)
/** The pre-fill: the measured stars while the listener gave none. */
const faded = computed(() => hover.value === null && props.rating === null && props.measured !== null && props.measured !== undefined)
const fill = (k: number): number => Math.max(0, Math.min(1, shown.value - k)) * 100

function at(event: MouseEvent, k: number): number {
  const box = (event.currentTarget as HTMLElement).getBoundingClientRect()
  return k + (event.clientX - box.left < box.width / 2 ? 0.5 : 1)
}
</script>

<template>
  <span class="stars" :class="{ faded, editable }" :style="{ '--size': `${size ?? 22}px` }" role="group" :aria-label="rating !== null ? `${rating} of 5 stars, rated by ear` : measured != null ? `${measured} of 5 stars, measured` : 'Not rated'" @mouseleave="hover = null">
    <button v-if="editable" class="zero" :class="{ on: rating === 0 }" title="0 stars" @click="emit('rate', 0)">0</button>
    <button
      v-for="k in 5"
      :key="k"
      class="star"
      :disabled="!editable"
      :title="editable ? 'Your stars: click (its left half for a half star)' : undefined"
      @mousemove="editable && (hover = at($event, k - 1))"
      @click="editable && emit('rate', at($event, k - 1))"
    >
      <span class="base">★</span><span class="fill" :style="{ width: `${fill(k - 1)}%` }">★</span>
    </button>
    <button v-if="editable && rating !== null" class="clear" title="Take your stars back" @click="emit('rate', null)">✕</button>
  </span>
</template>

<style scoped>
.stars {
  display: inline-flex;
  align-items: center;
  gap: 1px;
  line-height: 1;
}
.star {
  position: relative;
  display: inline-block;
  padding: 0;
  border: 0;
  background: none;
  font-size: var(--size);
  line-height: 1;
  cursor: default;
  color: inherit;
}
.editable .star {
  cursor: pointer;
}
.star:disabled {
  opacity: 1;
}
.base {
  color: rgba(255, 255, 255, 0.18);
}
.fill {
  position: absolute;
  inset: 0 auto 0 0;
  overflow: hidden;
  white-space: nowrap;
  color: #f5b301;
  text-shadow: 0 0 10px rgba(245, 179, 1, 0.35);
}
.faded .fill {
  opacity: 0.45;
  text-shadow: none;
}
.zero,
.clear {
  border: 1px solid rgba(255, 255, 255, 0.14);
  background: none;
  color: var(--muted);
  border-radius: 999px;
  font: 11px var(--font);
  padding: 1px 6px;
  margin-right: 4px;
  cursor: pointer;
}
.clear {
  margin: 0 0 0 6px;
}
.zero.on {
  border-color: #f5b301;
  color: #f5b301;
}
</style>
