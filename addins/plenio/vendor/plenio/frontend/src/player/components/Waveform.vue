<script setup lang="ts">
/**
 * The seek bar as the song's waveform: played in the song's colours, its sections marked, and on hover the
 * time and the lyrics line sung there. Click or drag to jump.
 */
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import { api, type TimedLine } from '../api'
import { engine } from '../engine'
import { formatTime, lineAt, sectionName, type TimedSection } from '../timing'

const props = defineProps<{ songId: string | null; time: number; duration: number; sections: TimedSection[]; lines: TimedLine[]; tall?: boolean }>()

const canvas = ref<HTMLCanvasElement | null>(null)
const peaks = ref<number[]>([])
const hover = ref<{ x: number; t: number } | null>(null)
const width = ref(0)
let dragging = false
const cache = new Map<string, number[]>()

async function loadPeaks(id: string | null): Promise<void> {
  peaks.value = []
  if (!id) return
  if (cache.has(id)) {
    peaks.value = cache.get(id) ?? []
    return
  }
  try {
    const answer = await api.peaks(id)
    cache.set(id, answer.peaks)
    if (props.songId === id) peaks.value = answer.peaks
  } catch {
    peaks.value = []
  }
}

function draw(): void {
  const el = canvas.value
  if (!el) return
  const ratio = Math.min(2, window.devicePixelRatio || 1)
  width.value = el.clientWidth
  const w = Math.floor(el.clientWidth * ratio)
  const h = Math.floor(el.clientHeight * ratio)
  if (el.width !== w || el.height !== h) {
    el.width = w
    el.height = h
  }
  const ctx = el.getContext('2d')
  if (!ctx) return
  ctx.clearRect(0, 0, w, h)
  const style = getComputedStyle(el)
  const accent = style.getPropertyValue('--accent').trim() || '#8f7cff'
  const accent2 = style.getPropertyValue('--accent2').trim() || '#ff7cc8'
  const done = props.duration > 0 ? props.time / props.duration : 0
  const bars = Math.max(40, Math.floor(w / (3 * ratio)))
  const gradient = ctx.createLinearGradient(0, 0, w, 0)
  gradient.addColorStop(0, accent)
  gradient.addColorStop(1, accent2)
  for (let i = 0; i < bars; i++) {
    const p = peaks.value.length ? peaks.value[Math.floor((i / bars) * peaks.value.length)] : 0.35 + 0.15 * Math.sin(i * 0.7)
    const bh = Math.max(2 * ratio, p * h * 0.92)
    const x = (i / bars) * w
    ctx.fillStyle = i / bars <= done ? gradient : 'rgba(255,255,255,0.22)'
    ctx.fillRect(x, (h - bh) / 2, Math.max(1, w / bars - ratio), bh)
  }
  // the sections
  if (props.duration > 0) {
    ctx.fillStyle = 'rgba(255,255,255,0.55)'
    for (const section of props.sections) {
      if (section.at <= 0.5) continue
      const x = (section.at / props.duration) * w
      ctx.fillRect(x, 0, ratio, h)
    }
  }
}

/** The section names under the tall waveform that fit (a name too close to the one before is left out). */
const labels = computed(() => {
  if (!props.tall || !props.duration || !width.value) return []
  const shown: { at: number; x: number; name: string }[] = []
  let free = 0
  for (const s of props.sections) {
    if (s.at <= 0.5) continue
    const x = (s.at / props.duration) * width.value
    const name = sectionName(s.label)
    if (x < free) continue
    shown.push({ at: s.at, x, name })
    free = x + name.length * 6.2 + 14
  }
  return shown
})

const hoverLine = computed(() => {
  if (!hover.value) return ''
  const i = lineAt(props.lines, hover.value.t)
  return i >= 0 && hover.value.t <= props.lines[i].end + 1 ? props.lines[i].text : ''
})
const hoverSection = computed(() => {
  if (!hover.value) return ''
  let found = ''
  for (const s of props.sections) if (s.at <= hover.value.t) found = sectionName(s.label)
  return found
})

function at(event: PointerEvent): number {
  const rect = (event.currentTarget as HTMLElement).getBoundingClientRect()
  return Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width)) * props.duration
}

function down(event: PointerEvent): void {
  if (!props.duration) return
  dragging = true
  ;(event.currentTarget as HTMLElement).setPointerCapture(event.pointerId)
  engine.seek(at(event))
}
function move(event: PointerEvent): void {
  const rect = (event.currentTarget as HTMLElement).getBoundingClientRect()
  hover.value = { x: event.clientX - rect.left, t: at(event) }
  if (dragging) engine.seek(at(event))
}

watch(() => props.songId, loadPeaks, { immediate: true })
watch(() => [props.time, props.duration, peaks.value, props.sections], draw)
let observer: ResizeObserver | null = null
onMounted(() => {
  draw()
  observer = new ResizeObserver(draw)
  if (canvas.value) observer.observe(canvas.value)
})
onBeforeUnmount(() => observer?.disconnect())
</script>

<template>
  <div class="wave" :class="{ tall }" @pointerdown="down" @pointermove="move" @pointerup="dragging = false" @pointerleave="hover = null">
    <canvas ref="canvas" />
    <div v-if="hover && duration" class="tip" :style="{ left: `${hover.x}px` }">
      <b>{{ formatTime(hover.t) }}</b>
      <span v-if="hoverSection" class="sec">{{ hoverSection }}</span>
      <span v-if="hoverLine" class="lyric">“{{ hoverLine }}”</span>
    </div>
    <div v-if="labels.length" class="labels">
      <span v-for="s in labels" :key="s.at" :style="{ left: `${s.x}px` }">{{ s.name }}</span>
    </div>
  </div>
</template>

<style scoped>
.wave {
  position: relative;
  height: 34px;
  cursor: pointer;
  touch-action: none;
}
.wave.tall {
  height: 64px;
}
canvas {
  width: 100%;
  height: 100%;
  display: block;
}
.tip {
  position: absolute;
  bottom: calc(100% + 8px);
  transform: translateX(-50%);
  background: rgba(15, 14, 24, 0.95);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 10px;
  padding: 6px 10px;
  font: 12px/1.4 var(--font);
  color: #fff;
  white-space: nowrap;
  max-width: 340px;
  overflow: hidden;
  text-overflow: ellipsis;
  pointer-events: none;
  display: flex;
  gap: 8px;
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.5);
  z-index: 5;
}
.sec {
  color: var(--accent);
  font-weight: 600;
}
.lyric {
  color: rgba(255, 255, 255, 0.75);
  overflow: hidden;
  text-overflow: ellipsis;
}
.labels {
  position: absolute;
  inset: auto 0 -14px 0;
  height: 12px;
  pointer-events: none;
}
.labels span {
  position: absolute;
  font: 9px/12px var(--font);
  color: var(--muted);
  transform: translateX(3px);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  white-space: nowrap;
}
</style>
