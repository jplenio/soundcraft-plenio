<script setup lang="ts">
/**
 * Tags of your own (owner's request 2026-10-18): a song's tags as chips (× takes one off) and a field to give
 * another - typed, or chosen from the tags given before, which the list offers as you type. With several
 * songs (``ids``: the songs a filter shows) it gives a tag to all of them, and lists the tags they have with
 * how many have each, to take one off all.
 */
import { computed, nextTick, ref } from 'vue'

import { fold } from '../search'
import { addTag, allTags, removeTag, say, state } from '../store'
import Icon from './Icon.vue'

const props = defineProps<{ ids: string[]; autofocus?: boolean }>()
const emit = defineEmits<{ filter: [tag: string] }>()

const text = ref('')
const open = ref(false)
const active = ref(-1)
const input = ref<HTMLInputElement | null>(null)
const many = computed(() => props.ids.length > 1)

/** The tags these songs have: each with how many of them have it. */
const present = computed<[string, number][]>(() => {
  const counts = new Map<string, [string, number]>()
  for (const id of props.ids) {
    for (const tag of state.tags[id] ?? []) {
      const key = tag.toLowerCase()
      const known = counts.get(key)
      counts.set(key, known ? [known[0], known[1] + 1] : [tag, 1])
    }
  }
  const list = [...counts.values()]
  return many.value ? list.sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0])) : list
})
/** The tags to choose from: given before, not on every one of these songs, matching what is typed. */
const offered = computed(() => {
  const want = fold(text.value.trim())
  const full = new Set(present.value.filter(([, n]) => n === props.ids.length).map(([t]) => t.toLowerCase()))
  return allTags.value
    .filter(([tag]) => !full.has(tag.toLowerCase()) && (!want || fold(tag).includes(want)))
    .sort((a, b) => Number(fold(b[0]).startsWith(want)) - Number(fold(a[0]).startsWith(want)) || b[1] - a[1])
    .slice(0, 12)
})
const isNewTag = computed(() => {
  const t = text.value.trim().toLowerCase()
  return !!t && !allTags.value.some(([tag]) => tag.toLowerCase() === t)
})

function give(tag: string): void {
  const done = addTag(props.ids, tag)
  if (!done) return
  if (many.value) say(`#${done} - ${props.ids.length} songs`, 2200)
  text.value = ''
  active.value = -1
  void nextTick(() => input.value?.focus())
}
function take(tag: string): void {
  removeTag(props.ids, tag)
  if (many.value) say(`#${tag} taken off ${props.ids.length} songs`, 2200)
}
function onKey(event: KeyboardEvent): void {
  const list = offered.value
  if (event.key === 'ArrowDown' && list.length) {
    event.preventDefault()
    open.value = true
    active.value = (active.value + 1) % list.length
  } else if (event.key === 'ArrowUp' && list.length) {
    event.preventDefault()
    active.value = (active.value - 1 + list.length) % list.length
  } else if (event.key === 'Enter' || event.key === ',') {
    event.preventDefault()
    if (active.value >= 0 && list[active.value]) give(list[active.value][0])
    else if (text.value.trim()) give(text.value)
  } else if (event.key === 'Backspace' && !text.value && !many.value && present.value.length) {
    take(present.value[present.value.length - 1][0])
  } else if (event.key === 'Escape') {
    open.value = false
  }
}
function blur(): void {
  window.setTimeout(() => (open.value = false), 150)
}
</script>

<template>
  <div class="tag-editor" :class="{ many }">
    <div class="have">
      <span v-for="[tag, n] in present" :key="tag" class="tag-chip" :class="{ part: many && n < ids.length }">
        <button class="name" :title="`The songs tagged #${tag}`" @click="emit('filter', tag)">#{{ tag }}<small v-if="many"> {{ n }}/{{ ids.length }}</small></button>
        <button class="x" :title="many ? `Take #${tag} off these ${ids.length} songs` : `Take #${tag} off`" @click="take(tag)"><Icon name="close" :size="12" /></button>
      </span>
      <label class="add">
        <Icon name="plus" :size="14" />
        <input
          ref="input"
          v-model="text"
          :autofocus="autofocus"
          maxlength="40"
          :placeholder="many ? `A tag for these ${ids.length} songs …` : present.length ? 'Another tag …' : 'Add a tag …'"
          @focus="open = true"
          @input="open = true; active = -1"
          @blur="blur"
          @keydown="onKey"
        />
      </label>
    </div>
    <div v-if="open && (offered.length || isNewTag)" class="offer" @mousedown.prevent>
      <button v-for="([tag, n], k) in offered" :key="tag" :class="{ on: k === active }" @click="give(tag)">#{{ tag }} <small>{{ n }}</small></button>
      <button v-if="isNewTag" class="new" @click="give(text)">+ new tag “{{ text.trim() }}”</button>
    </div>
  </div>
</template>

<style scoped>
.tag-editor {
  position: relative;
}
.have {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
}
.tag-chip {
  display: inline-flex;
  align-items: center;
  height: 28px;
  border-radius: 99px;
  border: 1px solid color-mix(in srgb, var(--accent) 55%, transparent);
  background: color-mix(in srgb, var(--accent) 16%, transparent);
  overflow: hidden;
}
.tag-chip.part {
  border-style: dashed;
  background: rgba(255, 255, 255, 0.04);
}
.tag-chip button {
  border: 0;
  background: none;
  color: #fff;
  cursor: pointer;
  font: 600 12px var(--font);
  height: 100%;
}
.tag-chip .name {
  padding: 0 4px 0 11px;
}
.tag-chip .name small {
  color: var(--muted);
  font-weight: 500;
}
.tag-chip .x {
  display: grid;
  place-items: center;
  padding: 0 8px 0 4px;
  color: rgba(255, 255, 255, 0.6);
}
.tag-chip .x:hover {
  color: #ff9a9a;
}
.add {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  height: 28px;
  padding: 0 10px;
  border-radius: 99px;
  border: 1px dashed rgba(255, 255, 255, 0.22);
  color: var(--muted);
}
.add:focus-within {
  border-color: var(--accent);
  color: #fff;
}
.add input {
  width: 150px;
  background: none;
  border: 0;
  outline: none;
  color: #fff;
  font: 13px var(--font);
}
.many .add input {
  width: 210px;
}
.offer {
  position: absolute;
  z-index: 30;
  top: calc(100% + 6px);
  left: 0;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  max-width: min(520px, 90vw);
  padding: 8px;
  border-radius: 12px;
  background: rgba(20, 18, 30, 0.98);
  border: 1px solid rgba(255, 255, 255, 0.12);
  box-shadow: 0 16px 40px rgba(0, 0, 0, 0.55);
}
.offer button {
  height: 26px;
  padding: 0 10px;
  border-radius: 99px;
  border: 1px solid rgba(255, 255, 255, 0.12);
  background: rgba(255, 255, 255, 0.05);
  color: #ddd;
  cursor: pointer;
  font: 500 12px var(--font);
}
.offer button small {
  color: var(--muted);
}
.offer button:hover,
.offer button.on {
  border-color: var(--accent);
  color: #fff;
}
.offer .new {
  color: var(--accent);
}
</style>
