<script setup lang="ts">
/**
 * The video's visuals over its time (owner's request 2026-10-25): one visual all the way, a new one at every section,
 * or one every so many seconds - and for every section or span the visual chosen in a gallery of moving previews
 * (VisualGallery.vue), or one at random. The strip shows the part of the song with its slots as wide as they last,
 * each with a still of its visual; the random ones come from a seed (🎲 draws others) and from the visuals ticked in
 * the visuals' settings, every visual, or the ones that suit the song. Sections of one name can share their visual;
 * a change can wait for the beat.
 */
import { computed, onBeforeUnmount, ref, watch } from 'vue'

import type { SongSummary } from '../api'
import { settings } from '../store'
import { sectionName, type TimedSection } from '../timing'
import { chooseVisual, songMoods } from '../visuals/chooser'
import { offeredForVideo } from '../visuals/gpu'
import { allPresets, presetById } from '../visuals/presets'
import type { VideoOptions } from '../video/make'
import { resolvePlan, setPick, slotsOf, type Slot } from '../video/plan'
import { type PreviewMaker, showFrame } from '../video/previews'
import Icon from './Icon.vue'
import VisualGallery from './VisualGallery.vue'

const props = defineProps<{
  song: SongSummary
  options: VideoOptions
  sections: TimedSection[]
  /** The part's length in seconds. */
  length: number
  maker: PreviewMaker | null
}>()

const gallery = ref<Slot | null>(null)
const stills = new Map<number, HTMLCanvasElement>()

const slots = computed(() => slotsOf(props.options.change, props.options.interval, props.sections, props.options.start, props.length, sectionName))
/** A visual this browser can draw (no WebGL visual where there is none). */
const exists = (id: string): boolean => {
  const preset = presetById(id)
  return !!preset && offeredForVideo(preset)
}
/** Where the random visuals come from. */
const pool = computed(() => randomPool(props.options.randomFrom))
function randomPool(from: VideoOptions['randomFrom']): string[] {
  const all = allPresets().filter(offeredForVideo)
  if (from === 'all') return all.map((p) => p.id)
  if (from === 'match') {
    const moods = songMoods(props.song)
    const fitting = all.filter((p) => !moods.length || p.suits.some((s) => moods.includes(s)))
    return (fitting.length ? fitting : all).map((p) => p.id)
  }
  const ticked = settings.visuals.pool.filter(exists)
  return ticked.length ? ticked : all.map((p) => p.id)
}
/** The visual of each slot: as chosen, else by the dice; one visual for the whole video: as chosen, else as the
 * visuals' settings choose for this song. */
const resolved = computed<string[]>(() => {
  if (props.options.change === 'never') return [props.options.visual || chooseVisual({ settings: settings.visuals, song: props.song, previous: null, turn: 0 })]
  return resolvePlan(slots.value, props.options.picks, pool.value, props.options.seed, props.options.repeats, exists)
})
const picked = (slot: Slot): string => (props.options.change === 'never' ? props.options.visual : props.options.picks[slot.index] ?? '')
const sameKind = (slot: Slot): number => slots.value.filter((s) => s.kind === slot.kind).length

function choose(id: string): void {
  const slot = gallery.value
  gallery.value = null
  if (!slot) return
  if (props.options.change === 'never') props.options.visual = id
  else props.options.picks = setPick(slots.value, props.options.picks, slot.index, id, props.options.repeats)
}
function shuffle(): void {
  props.options.seed = Math.floor(Math.random() * 2 ** 31)
}
function allRandom(): void {
  props.options.picks = []
}

/** The stills of the strip: each slot's visual at the slot's middle. */
function still(index: number, el: unknown): void {
  if (el instanceof HTMLCanvasElement) stills.set(index, el)
  else stills.delete(index)
}
let drawing = 0
async function drawStills(): Promise<void> {
  const maker = props.maker
  const run = ++drawing
  if (!maker) return
  for (const slot of slots.value) {
    const id = resolved.value[slot.index]
    if (!id) continue
    const mid = (slot.start + slot.end) / 2
    const preview = await maker.get(id, mid, 1, -1)
    if (run !== drawing) return
    const canvas = stills.get(slot.index)
    if (preview && canvas) showFrame(canvas, preview, 0)
  }
}
watch([resolved, slots, () => props.maker], () => void drawStills(), { immediate: true })
onBeforeUnmount(() => (drawing += 1))

const MODES: [VideoOptions['change'], string, string][] = [
  ['never', 'One visual', 'The same visual all the way'],
  ['section', 'Every section', 'A new visual at every section - verse, chorus …'],
  ['interval', 'Every few seconds', 'A new visual every so many seconds'],
]
const name = (id: string): string => presetById(id)?.name ?? '?'
</script>

<template>
  <div class="timeline">
    <div class="modes" role="radiogroup" aria-label="When the visual changes">
      <button v-for="[id, label, hint] in MODES" :key="id" type="button" class="mode" :class="{ on: options.change === id }" :title="hint" :disabled="id === 'section' && !sections.length" role="radio" :aria-checked="options.change === id" @click="options.change = id">{{ label }}</button>
      <label v-if="options.change === 'interval'" class="inline">every <input v-model.number="options.interval" type="number" min="3" max="600" /> s</label>
    </div>
    <div class="strip" :class="{ one: options.change === 'never' }">
      <button
        v-for="slot in slots"
        :key="`${options.change}-${slot.index}`"
        type="button"
        class="slot"
        :class="{ random: !picked(slot) }"
        :style="{ flexGrow: Math.max(0.6, slot.end - slot.start) }"
        :title="`${slot.label}: ${picked(slot) ? name(picked(slot)) : options.change === 'never' ? 'as the visuals’ settings choose' : `at random - ${name(resolved[slot.index])}`} - click to choose`"
        @click="gallery = slot"
      >
        <canvas :ref="(el) => still(slot.index, el)" class="still" />
        <span class="label">{{ slot.label }}</span>
        <span class="what">
          <template v-if="picked(slot)">{{ name(picked(slot)) }}</template>
          <template v-else><Icon name="dice" :size="11" /> {{ name(resolved[slot.index]) }}</template>
        </span>
      </button>
    </div>
    <div v-if="options.change !== 'never'" class="row">
      <button type="button" class="ghost small" title="Other visuals for the slots at random" @click="shuffle"><Icon name="dice" :size="14" /> Shuffle the random ones</button>
      <button type="button" class="ghost small" :disabled="!options.picks.some(Boolean)" @click="allRandom">All at random</button>
      <label class="inline">random from
        <select v-model="options.randomFrom">
          <option value="pool">the visuals ticked in the visuals’ settings</option>
          <option value="match">the ones that suit this song</option>
          <option value="all">every visual</option>
        </select>
      </label>
    </div>
    <div v-if="options.change !== 'never'" class="row">
      <label v-if="options.change === 'section'" class="check" title="Every chorus shows the visual of the first chorus, every verse the one of the first verse - a choice for one is a choice for all"><input v-model="options.repeats" type="checkbox" /> the same visual for every chorus, every verse …</label>
      <label class="check" title="A change waits for the next beat after its time (at most a second and a half)"><input v-model="options.changeOnBeat" type="checkbox" /> change on the beat</label>
    </div>
    <p class="hint">{{ options.change === 'never' ? 'Click the strip to choose the visual - every visual plays in a little window to this song.' : 'Click a part to choose its visual - every visual plays in a little window to the music of that part.' }}</p>
    <VisualGallery
      v-if="gallery"
      :maker="maker"
      :at="(gallery.start + gallery.end) / 2"
      :title="gallery.label"
      :chosen="picked(gallery)"
      :first="options.change === 'never' ? 'auto' : 'random'"
      :random-now="resolved[gallery.index]"
      :repeats="options.repeats && options.change === 'section' ? sameKind(gallery) : 1"
      @pick="choose"
      @close="gallery = null"
    />
  </div>
</template>

<style scoped>
.timeline {
  display: grid;
  gap: 8px;
}
.modes {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
}
.mode {
  height: 30px;
  padding: 0 12px;
  border-radius: 99px;
  border: 1px solid rgba(255, 255, 255, 0.12);
  background: rgba(255, 255, 255, 0.04);
  color: rgba(255, 255, 255, 0.85);
  font: 600 12px var(--font);
  cursor: pointer;
}
.mode.on {
  border-color: var(--accent);
  background: color-mix(in srgb, var(--accent) 24%, transparent);
  color: #fff;
}
.strip {
  display: flex;
  gap: 3px;
  overflow-x: auto;
  padding-bottom: 4px;
}
.slot {
  position: relative;
  flex: 1 1 0;
  min-width: 64px;
  display: grid;
  gap: 2px;
  padding: 3px;
  border-radius: 9px;
  border: 1px solid rgba(255, 255, 255, 0.1);
  background: rgba(255, 255, 255, 0.04);
  color: #fff;
  text-align: left;
  cursor: pointer;
  overflow: hidden;
}
.strip.one .slot {
  max-width: 260px;
}
.slot:hover {
  border-color: var(--accent);
}
.still {
  width: 100%;
  height: 44px;
  border-radius: 6px;
  background: #07060c;
  object-fit: cover;
}
.slot.random .still {
  opacity: 0.75;
}
.label {
  font: 600 11px var(--font);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.what {
  display: flex;
  align-items: center;
  gap: 3px;
  color: var(--muted);
  font-size: 10.5px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.row {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
}
.inline,
.check {
  display: flex;
  align-items: center;
  gap: 6px;
  color: #ddd;
}
select,
input[type='number'] {
  background: rgba(255, 255, 255, 0.06);
  color: #fff;
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 8px;
  padding: 5px 8px;
  font: 12px var(--font);
}
input[type='number'] {
  width: 64px;
}
.small {
  height: 30px;
  font-size: 12px;
  padding: 0 12px;
}
.hint {
  color: var(--muted);
  font-size: 12px;
  margin: 0;
}
</style>
