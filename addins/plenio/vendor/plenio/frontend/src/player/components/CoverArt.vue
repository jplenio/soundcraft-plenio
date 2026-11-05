<script setup lang="ts">
/**
 * A song's cover: its own image when Export saved one, otherwise art drawn from the song itself - its
 * colour from the genre, waves from its title, always the same for the same song. ``live`` turns it slowly.
 * ``size``: about how many CSS pixels wide it shows - the player sends a small picture of the cover, sharp at that
 * size (a card 12 KB instead of 200).
 */
import { computed } from 'vue'

import { coverUrl, type SongSummary } from '../api'
import { hashOf, songHue } from '../colors'

const props = defineProps<{ song: SongSummary; live?: boolean; rounded?: boolean; size?: number }>()

const hue = computed(() => songHue(props.song.id, props.song.genre))
const seed = computed(() => hashOf(props.song.id + props.song.title))
const waves = computed(() => {
  const s = seed.value
  return Array.from({ length: 7 }, (_, k) => {
    const amp = 6 + ((s >> (k * 3)) % 14)
    const phase = ((s >> k) % 100) / 16
    const y = 22 + k * 9
    let d = `M0 ${y}`
    for (let x = 0; x <= 100; x += 5) d += ` L${x} ${(y + Math.sin(x / 13 + phase + k) * amp * 0.35).toFixed(2)}`
    return { d, opacity: 0.18 + k * 0.08, width: 0.6 + (k % 3) * 0.35 }
  })
})
const initials = computed(() =>
  props.song.title
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase() ?? '')
    .join('')
)
</script>

<template>
  <div class="cover" :class="{ live, rounded }">
    <img v-if="song.has.cover" :src="coverUrl(song.id, size)" :alt="song.title" loading="lazy" decoding="async" />
    <svg v-else viewBox="0 0 100 100" preserveAspectRatio="xMidYMid slice">
      <defs>
        <linearGradient :id="`g${song.id}`" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" :stop-color="`hsl(${hue} 70% 32%)`" />
          <stop offset="1" :stop-color="`hsl(${(hue + 55) % 360} 75% 14%)`" />
        </linearGradient>
        <radialGradient :id="`r${song.id}`" cx="0.7" cy="0.25" r="0.7">
          <stop offset="0" :stop-color="`hsl(${(hue + 25) % 360} 95% 70%)`" stop-opacity="0.7" />
          <stop offset="1" stop-color="#000" stop-opacity="0" />
        </radialGradient>
      </defs>
      <rect width="100" height="100" :fill="`url(#g${song.id})`" />
      <rect width="100" height="100" :fill="`url(#r${song.id})`" />
      <g class="waves">
        <path v-for="(w, k) in waves" :key="k" :d="w.d" fill="none" :stroke="`hsl(${(hue + k * 9) % 360} 90% 78%)`" :stroke-width="w.width" :opacity="w.opacity" />
      </g>
      <text x="8" y="92" class="initials">{{ initials }}</text>
    </svg>
  </div>
</template>

<style scoped>
.cover {
  position: relative;
  overflow: hidden;
  aspect-ratio: 1;
  background: #111;
}
.cover.rounded {
  border-radius: 14px;
}
.cover img,
.cover svg {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}
.initials {
  font: 700 18px/1 var(--font);
  fill: rgba(255, 255, 255, 0.55);
  letter-spacing: 1px;
}
.live .waves {
  animation: drift 9s ease-in-out infinite alternate;
  transform-origin: 50% 50%;
}
.live img {
  animation: breathe 12s ease-in-out infinite alternate;
}
@keyframes drift {
  from {
    transform: translateX(-4%) scale(1.04);
  }
  to {
    transform: translateX(4%) scale(1.1);
  }
}
@keyframes breathe {
  from {
    transform: scale(1);
  }
  to {
    transform: scale(1.06);
  }
}
</style>
