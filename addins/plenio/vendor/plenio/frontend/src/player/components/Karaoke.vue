<script setup lang="ts">
/**
 * The lyrics as they are sung: the current line large, painted syllable by syllable as the voice reaches
 * it, the lines before it fading upwards, the next ones waiting below; a click on a line jumps there. A
 * song without measured times shows its lyrics still.
 */
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import type { TimedLine } from '../api'
import { engine } from '../engine'
import { settings } from '../store'
import { lineAt, lineOn } from '../timing'
import LyricLine from './LyricLine.vue'

const props = defineProps<{ lines: TimedLine[]; time: number; plain?: string; compact?: boolean }>()

const box = ref<HTMLElement | null>(null)
const active = computed(() => lineAt(props.lines, props.time))
const on = computed(() => lineOn(props.lines, active.value, props.time))

/** Scroll the line sung now to its place in the box (40 % down, 35 % when compact). Measured against the
 * box itself: offsetTop counts from the nearest positioned ancestor - on the song's page that is the whole
 * page, header included, and the line slid out of view. */
function center(smooth = true): void {
  const host = box.value
  const el = host?.querySelector<HTMLElement>(`[data-line="${Math.max(0, active.value)}"]`)
  if (!host || !el) return
  const top = el.getBoundingClientRect().top - host.getBoundingClientRect().top + host.scrollTop
  const target = top - host.clientHeight * (props.compact ? 0.35 : 0.4) + el.offsetHeight / 2
  host.scrollTo({ top: Math.max(0, target), behavior: smooth ? 'smooth' : 'auto' })
}

watch(active, async () => {
  await nextTick()
  center()
})
// a new song, or the box shown again (a tab, a view): straight to the line sung now
watch(() => props.lines, async () => {
  await nextTick()
  center(false)
})
let observer: ResizeObserver | null = null
onMounted(async () => {
  await nextTick()
  center(false)
  observer = new ResizeObserver(() => center(false))
  if (box.value) observer.observe(box.value)
})
onBeforeUnmount(() => observer?.disconnect())

const stanzas = computed(() => (props.plain ?? '').split(/\n\s*\n/).map((s) => s.split('\n')))
</script>

<template>
  <div ref="box" class="karaoke" :class="{ compact }">
    <template v-if="lines.length">
      <div class="pad" />
      <p
        v-for="(line, i) in lines"
        :key="i"
        :data-line="i"
        class="line"
        :class="{ now: i === active && on, past: i < active || (i === active && !on), soon: i === active + 1 }"
        @click="engine.seek(Math.max(0, line.start - 0.15))"
      >
        <LyricLine v-if="i === active" :line="line" :time="time" :effect="settings.lyrics.effect" />
        <template v-else>{{ line.text }}</template>
      </p>
      <div class="pad" />
    </template>
    <div v-else-if="plain" class="plain">
      <p class="hint">No times for this song - its lyrics as written.</p>
      <div v-for="(stanza, s) in stanzas" :key="s" class="stanza">
        <p v-for="(line, k) in stanza" :key="k">{{ line }}</p>
      </div>
    </div>
    <p v-else class="hint">An instrumental - no lyrics.</p>
  </div>
</template>

<style scoped>
.karaoke {
  height: 100%;
  overflow-y: auto;
  scrollbar-width: none;
  mask-image: linear-gradient(transparent, #000 18%, #000 75%, transparent);
  padding: 0 8px;
}
.karaoke::-webkit-scrollbar {
  display: none;
}
.pad {
  height: 40%;
}
.line {
  font-family: var(--lyrics-font, var(--font));
  font-weight: var(--lyrics-weight, 700);
  font-size: calc(clamp(20px, 2.4vw, 34px) * var(--lyrics-scale, 1));
  line-height: 1.3;
  color: rgba(255, 255, 255, 0.28);
  margin: 0 0 0.55em;
  cursor: pointer;
  transition: color 0.4s, transform 0.5s cubic-bezier(0.2, 0.8, 0.2, 1), opacity 0.4s, filter 0.4s;
  transform-origin: left center;
  filter: blur(0.3px);
}
.compact .line {
  font-size: calc(clamp(16px, 1.6vw, 22px) * var(--lyrics-scale, 1));
}
.line:hover {
  color: rgba(255, 255, 255, 0.6);
}
.line.past {
  color: rgba(255, 255, 255, 0.4);
  opacity: 0.6;
}
.line.soon {
  color: rgba(255, 255, 255, 0.55);
}
.line.now {
  transform: scale(1.06);
  filter: none;
  color: rgba(255, 255, 255, 0.35);
}
.plain {
  padding: 8% 0;
  font: 500 17px/1.6 var(--font);
  color: rgba(255, 255, 255, 0.75);
}
.stanza {
  margin-bottom: 1.2em;
}
.stanza p {
  margin: 0;
}
.hint {
  color: var(--muted);
  font: 13px var(--font);
}
</style>
