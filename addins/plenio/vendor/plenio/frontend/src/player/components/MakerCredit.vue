<script setup lang="ts">
/**
 * Who made a party song, while it plays (Settings > Party songs > *Who made it*): the name large as the song
 * begins, with every new section and as it ends - between, a badge in a corner (*spotlight*) or the name
 * floating slowly across the picture (*drift*), glowing with the beat. Over the visual all of it; in the other
 * views of Now playing the moments and a quiet badge.
 */
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

import { engine } from '../engine'
import { creditMoment, driftAt, type Credit } from '../make/form'
import { sectionName } from '../timing'

const props = defineProps<{
  name: string
  /** When its party was: ``on 27 October 2026`` (``''``: not known). */
  when?: string
  mode: Exclude<Credit, 'off'>
  time: number
  duration: number
  sections: { at: number; label: string }[]
  /** Only the visual on the screen: the name may move over the whole picture. */
  overVisual: boolean
  /** The corner the guests' way in takes (the badge takes another). */
  avoid: string
}>()

const pulse = ref(0)
let frame = 0
function step(): void {
  const now = engine.frame().pulse
  pulse.value = pulse.value * 0.82 + now * 0.18
  frame = requestAnimationFrame(step)
}
onMounted(() => (frame = requestAnimationFrame(step)))
onBeforeUnmount(() => cancelAnimationFrame(frame))

const moment = computed(() => creditMoment(props.time, props.duration, props.sections))
const letters = computed(() => [...props.name])
const drifting = computed(() => props.mode === 'drift' && props.overVisual && !moment.value)
const corner = computed(() => (props.avoid === 'top-left' ? 'top-right' : 'top-left'))
const driftStyle = computed(() => {
  const at = driftAt(props.time)
  return { left: `${at.x}%`, top: `${at.y}%`, transform: `translate(-50%, -50%) rotate(${at.tilt}deg) scale(${1 + pulse.value * 0.12})` }
})
const glow = computed(() => ({ '--glow': String(0.35 + pulse.value * 0.65) }))
</script>

<template>
  <div class="credit" :style="glow" aria-live="off">
    <Transition name="moment" mode="out-in">
      <div v-if="moment?.kind === 'intro'" key="intro" class="moment intro">
        <small>a party song{{ when ? ` ${when}` : '' }} by</small>
        <b class="letters"><span v-for="(c, i) in letters" :key="i" class="name" :style="{ animationDelay: `${0.25 + i * 0.06}s, 0s` }">{{ c === ' ' ? ' ' : c }}</span></b>
      </div>
      <div v-else-if="moment?.kind === 'section'" :key="`section-${moment.label}-${Math.floor(time)}`" class="moment section">
        <i>✨</i> <span>{{ sectionName(moment.label) }}</span> <small>by</small> <b class="name">{{ name }}</b>
      </div>
      <div v-else-if="moment?.kind === 'outro'" key="outro" class="moment outro">
        <small>made at the party {{ when || '' }} by</small>
        <b class="name">{{ name }}</b>
        <em>thank you ♥</em>
      </div>
      <div v-else-if="drifting" key="drift" class="drift" :style="driftStyle">
        <small>a song by</small>
        <b class="name">{{ name }}</b>
      </div>
      <div v-else key="badge" class="badge" :class="overVisual ? corner : 'top'">
        <i>✨</i> <small>by</small> <b class="name">{{ name }}</b>
      </div>
    </Transition>
  </div>
</template>

<style scoped>
.credit {
  position: absolute;
  inset: 0;
  z-index: 4;
  pointer-events: none;
  --glow: 0.4;
}
.name {
  background: linear-gradient(90deg, #f472b6, #fbbf24, #a78bfa, #f472b6);
  background-size: 300% 100%;
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
  animation: shimmer 6s linear infinite;
  filter: drop-shadow(0 0 calc(2px + 9px * var(--glow)) rgba(244, 114, 182, calc(0.2 + 0.4 * var(--glow))));
}
@keyframes shimmer {
  to {
    background-position: 300% 0;
  }
}
.moment {
  position: absolute;
  left: 50%;
  transform: translateX(-50%);
  text-align: center;
  white-space: nowrap;
  text-shadow: 0 2px 18px rgba(0, 0, 0, 0.6);
}
.moment small {
  display: block;
  font: 600 clamp(13px, 1.6vw, 20px) var(--font);
  letter-spacing: 0.32em;
  text-transform: uppercase;
  color: rgba(255, 255, 255, 0.78);
}
.moment .name {
  display: inline-block;
  font: 800 clamp(34px, 6.4vw, 92px) / 1.1 var(--font);
  letter-spacing: -0.01em;
}
/* above the controls at the bottom */
.intro {
  bottom: 236px;
}
.intro .letters {
  display: inline-block;
  font: 800 clamp(34px, 6.4vw, 92px) / 1.1 var(--font);
}
.intro .letters .name {
  display: inline-block;
  opacity: 0;
  transform: translateY(0.4em) scale(0.6) rotate(-8deg);
  animation:
    letter 0.7s cubic-bezier(0.2, 1.4, 0.4, 1) forwards,
    shimmer 6s linear infinite;
}
@keyframes letter {
  to {
    opacity: 1;
    transform: none;
  }
}
.section {
  bottom: 236px;
  display: flex;
  align-items: baseline;
  gap: 10px;
  padding: 10px 24px;
  border-radius: 999px;
  background: rgba(10, 8, 22, 0.42);
  backdrop-filter: blur(8px);
  font: 700 clamp(15px, 1.8vw, 24px) var(--font);
}
.section small {
  display: inline;
  letter-spacing: 0.1em;
}
.section .name {
  font-size: clamp(22px, 2.8vw, 38px);
}
.outro {
  top: 50%;
  transform: translate(-50%, -50%);
}
.outro .name {
  font-size: clamp(44px, 8vw, 120px);
}
.outro em {
  display: block;
  margin-top: 6px;
  font: italic 600 clamp(15px, 1.8vw, 24px) var(--font);
  color: rgba(255, 255, 255, 0.82);
}
.drift {
  position: absolute;
  text-align: center;
  white-space: nowrap;
  transition: transform 0.12s linear;
}
.drift small {
  display: block;
  font: 600 clamp(11px, 1.2vw, 15px) var(--font);
  letter-spacing: 0.3em;
  text-transform: uppercase;
  color: rgba(255, 255, 255, 0.7);
}
.drift .name {
  font: 800 clamp(30px, 4.2vw, 62px) / 1.1 var(--font);
}
/* a soft dark halo: the name stays readable over a bright visual */
.intro::before,
.outro::before,
.drift::before {
  content: '';
  position: absolute;
  inset: -40% -25%;
  z-index: -1;
  background: radial-gradient(closest-side, rgba(5, 4, 12, 0.55), transparent);
}
.badge {
  position: absolute;
  display: flex;
  align-items: baseline;
  gap: 7px;
  padding: 7px 16px;
  border-radius: 999px;
  background: rgba(10, 8, 22, 0.45);
  backdrop-filter: blur(6px);
  border: 1px solid rgba(255, 255, 255, calc(0.08 + 0.25 * var(--glow)));
  font: 600 14px var(--font);
  color: rgba(255, 255, 255, 0.8);
}
.badge .name {
  font: 800 19px var(--font);
}
.badge.top-left {
  top: 22px;
  left: 22px;
}
.badge.top-right {
  top: 22px;
  right: 22px;
}
.badge.top {
  top: 70px;
  left: 50%;
  transform: translateX(-50%);
}
.moment-enter-active,
.moment-leave-active {
  transition: opacity 0.6s ease, filter 0.6s ease;
}
.moment-enter-from,
.moment-leave-to {
  opacity: 0;
  filter: blur(6px);
}
@media (prefers-reduced-motion: reduce) {
  .name,
  .intro .letters .name {
    animation: none;
    opacity: 1;
    transform: none;
  }
}
</style>
