<script setup lang="ts">
/** The queue, from the right: what plays and what comes next (drag to reorder), save it as a playlist,
 * clear what is left - and the sleep timer. */
import { computed, ref } from 'vue'

import type { SongSummary } from '../api'
import { byId, current, index, newPlaylist, playAt, playing, queue, setSleep, settings, sleep, sleepLeft } from '../store'
import { formatTime } from '../timing'
import CoverArt from './CoverArt.vue'
import Icon from './Icon.vue'

const emit = defineEmits<{ close: [] }>()
const dragging = ref(-1)
const over = ref(-1)
const saved = ref('')

const items = computed(() =>
  queue.value.map((id, i) => ({ i, song: byId.value.get(id) })).filter((x): x is { i: number; song: SongSummary } => !!x.song)
)
const upcoming = computed(() => items.value.filter((x) => x.i > index.value))
const earlier = computed(() => items.value.filter((x) => x.i < index.value).slice(-5))
const left = computed(() => upcoming.value.reduce((t, x) => t + x.song.seconds, 0))

function remove(i: number): void {
  queue.value.splice(i, 1)
  if (i < index.value) index.value -= 1
}
function clearUpcoming(): void {
  queue.value.splice(index.value + 1)
}
function drop(to: number): void {
  const from = dragging.value
  dragging.value = over.value = -1
  if (from < 0 || from === to) return
  const nowId = queue.value[index.value]
  const [moved] = queue.value.splice(from, 1)
  queue.value.splice(from < to ? to - 1 : to, 0, moved)
  index.value = queue.value.indexOf(nowId)
}
function save(): void {
  const playlist = newPlaylist(`Queue ${new Date().toLocaleDateString()}`, queue.value)
  saved.value = playlist.name
  window.setTimeout(() => (saved.value = ''), 2200)
}
const SLEEP = [15, 30, 45, 60, 90]
</script>

<template>
  <aside class="queue">
    <header>
      <h3><Icon name="queue" /> Queue</h3>
      <button class="icon-btn" title="Close (Q)" @click="emit('close')"><Icon name="close" /></button>
    </header>

    <div class="sleep">
      <Icon name="timer" :size="16" />
      <span>Sleep</span>
      <button class="chip" :class="{ on: !sleep }" @click="setSleep(null)">off</button>
      <button v-for="m in SLEEP" :key="m" class="chip" :class="{ on: sleep && sleep !== 'song' && sleep.minutes === m }" @click="setSleep(m)">{{ m }}′</button>
      <button class="chip" :class="{ on: sleep === 'song' }" @click="setSleep('song')">after this song</button>
      <small v-if="sleep && sleep !== 'song'">stops in {{ formatTime(sleepLeft) }}, fading out</small>
    </div>

    <div class="opts">
      <label><input v-model.number="settings.crossfade" type="range" min="0" max="12" step="1" /> Crossfade {{ settings.crossfade ? `${settings.crossfade} s` : 'off' }}</label>
    </div>

    <template v-if="earlier.length">
      <h4>Played</h4>
      <button v-for="{ i, song } in earlier" :key="`e${i}`" class="row past" @click="playAt(i)">
        <CoverArt :song="song" rounded :size="48" /><span class="t">{{ song.title }}<small>{{ song.genre }}</small></span><span class="len">{{ formatTime(song.seconds) }}</span>
      </button>
    </template>

    <h4>Now</h4>
    <div v-if="current" class="row now">
      <CoverArt :song="current" :live="playing" rounded :size="56" /><span class="t">{{ current.title }}<small>{{ current.genre }}</small></span>
      <span class="eq" :class="{ on: playing }"><i /><i /><i /></span>
    </div>
    <p v-else class="hint">Nothing plays.</p>

    <h4>
      Next <small v-if="upcoming.length">{{ upcoming.length }} · {{ formatTime(left) }}</small>
      <span class="grow" />
      <button v-if="queue.length" class="link" @click="save">{{ saved ? `saved as “${saved}”` : 'Save as playlist' }}</button>
      <button v-if="upcoming.length" class="link" @click="clearUpcoming">Clear</button>
    </h4>
    <div class="list">
      <div
        v-for="{ i, song } in upcoming"
        :key="`u${i}-${song.id}`"
        class="row"
        draggable="true"
        :class="{ over: over === i, dragging: dragging === i }"
        @dragstart="dragging = i"
        @dragover.prevent="over = i"
        @drop.prevent="drop(i)"
        @dragend="dragging = over = -1"
        @dblclick="playAt(i)"
      >
        <CoverArt :song="song" rounded :size="48" />
        <span class="t">{{ song.title }}<small>{{ song.genre }}</small></span>
        <span class="len">{{ formatTime(song.seconds) }}</span>
        <button class="icon-btn rm" title="Remove" @click="remove(i)"><Icon name="close" :size="14" /></button>
      </div>
      <p v-if="!upcoming.length" class="hint">The queue ends here{{ settings.repeat === 'all' ? ' - and starts again' : '' }}.</p>
    </div>
  </aside>
</template>

<style scoped>
.queue {
  width: 360px;
  height: 100%;
  overflow-y: auto;
  padding: 16px 16px 24px;
  background: rgba(12, 11, 20, 0.96);
  border-left: 1px solid rgba(255, 255, 255, 0.08);
  backdrop-filter: blur(20px);
  box-shadow: -20px 0 60px rgba(0, 0, 0, 0.45);
  font: 13px var(--font);
}
header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
h3 {
  display: flex;
  gap: 8px;
  align-items: center;
  margin: 0;
  font: 600 16px var(--font);
}
h4 {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 16px 0 6px;
  font: 600 11px var(--font);
  text-transform: uppercase;
  letter-spacing: 0.7px;
  color: var(--muted);
}
h4 small {
  text-transform: none;
  letter-spacing: 0;
  font-weight: 400;
}
.grow {
  flex: 1;
}
.link {
  border: 0;
  background: none;
  color: var(--accent);
  font: 12px var(--font);
  cursor: pointer;
  text-transform: none;
  letter-spacing: 0;
}
.sleep {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
  align-items: center;
  margin: 14px 0 4px;
  color: var(--muted);
}
.sleep small {
  width: 100%;
  color: var(--accent);
}
.opts label {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--muted);
  margin-top: 8px;
}
.opts input {
  accent-color: var(--accent);
  width: 120px;
}
.row {
  display: grid;
  grid-template-columns: 40px 1fr auto auto;
  gap: 10px;
  align-items: center;
  width: 100%;
  padding: 5px 6px;
  border: 0;
  border-top: 1px solid transparent;
  border-radius: 10px;
  background: none;
  color: #fff;
  text-align: left;
  cursor: default;
}
.row:hover {
  background: rgba(255, 255, 255, 0.05);
}
.row.past {
  opacity: 0.5;
  cursor: pointer;
  grid-template-columns: 40px 1fr auto;
}
.row.now {
  background: color-mix(in srgb, var(--accent) 20%, transparent);
  grid-template-columns: 40px 1fr auto;
}
.row.over {
  border-top-color: var(--accent);
}
.row.dragging {
  opacity: 0.35;
}
.t {
  min-width: 0;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}
.t small {
  display: block;
  color: var(--muted);
  font-size: 11px;
  overflow: hidden;
  text-overflow: ellipsis;
}
.len {
  font: 11px var(--mono);
  color: var(--muted);
}
.rm {
  opacity: 0;
}
.row:hover .rm {
  opacity: 1;
}
.hint {
  color: var(--muted);
  font-size: 12px;
}
.eq {
  display: inline-flex;
  gap: 2px;
  align-items: flex-end;
  height: 14px;
}
.eq i {
  width: 3px;
  height: 3px;
  background: var(--accent);
}
.eq.on i {
  animation: eq 0.9s ease-in-out infinite;
}
.eq i:nth-child(2) {
  animation-delay: -0.3s;
}
.eq i:nth-child(3) {
  animation-delay: -0.6s;
}
@keyframes eq {
  0%,
  100% {
    height: 3px;
  }
  50% {
    height: 14px;
  }
}
</style>
