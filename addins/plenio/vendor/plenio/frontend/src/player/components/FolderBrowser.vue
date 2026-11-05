<script setup lang="ts">
/**
 * Choose a folder of this computer (Settings > Songs): the places to start (home, music, the drives), the
 * folder's subfolders to go into, up to its parent - or a path typed or pasted. Only folders are listed.
 */
import { onMounted, ref } from 'vue'

import { api, type DirsAnswer } from '../api'
import Icon from './Icon.vue'

const emit = defineEmits<{ choose: [path: string]; close: [] }>()

const at = ref<DirsAnswer | null>(null)
const typed = ref('')
const busy = ref(false)

async function open(path: string | null): Promise<void> {
  busy.value = true
  try {
    at.value = await api.dirs(path)
    if (at.value.path) typed.value = at.value.path
  } finally {
    busy.value = false
  }
}

onMounted(() => void open(null))
</script>

<template>
  <div class="veil" @click.self="emit('close')">
    <div class="browser" role="dialog" aria-label="Choose a folder">
      <header>
        <h3><Icon name="folder" /> Choose a folder</h3>
        <button class="icon-btn" title="Close" @click="emit('close')"><Icon name="close" /></button>
      </header>
      <div class="places">
        <button v-for="p in at?.places ?? []" :key="p.path" class="chip" @click="open(p.path)">{{ p.name }}</button>
      </div>
      <form class="typed" @submit.prevent="open(typed)">
        <input v-model="typed" placeholder="Type or paste a folder's path" spellcheck="false" />
        <button class="ghost small" type="submit">Go</button>
      </form>
      <p v-if="at?.error" class="error">{{ at.error }}</p>
      <ul class="dirs" :class="{ busy }">
        <li v-if="at?.parent"><button @click="open(at.parent)"><Icon name="back" :size="14" /> ..</button></li>
        <li v-for="d in at?.dirs ?? []" :key="d.path"><button @click="open(d.path)"><Icon name="folder" :size="14" /> {{ d.name }}</button></li>
        <li v-if="at?.path && !at.dirs.length" class="empty">No folders inside.</li>
        <li v-if="!at?.path" class="empty">Start from a place above, or type a path.</li>
      </ul>
      <footer>
        <code>{{ at?.path ?? '' }}</code>
        <button class="primary" :disabled="!at?.path" @click="at?.path && emit('choose', at.path)">Choose this folder</button>
      </footer>
    </div>
  </div>
</template>

<style scoped>
.veil {
  position: fixed;
  inset: 0;
  z-index: 80;
  display: grid;
  place-items: center;
  background: rgba(0, 0, 0, 0.55);
}
.browser {
  width: min(640px, 92vw);
  max-height: 80vh;
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 18px 20px;
  border-radius: 16px;
  background: #15121f;
  border: 1px solid rgba(255, 255, 255, 0.1);
  box-shadow: 0 30px 80px rgba(0, 0, 0, 0.6);
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
}
.places {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.typed {
  display: flex;
  gap: 8px;
}
.typed input {
  flex: 1;
  background: rgba(255, 255, 255, 0.06);
  color: #fff;
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 8px;
  padding: 7px 10px;
  font: 13px var(--mono, monospace);
}
.dirs {
  list-style: none;
  margin: 0;
  padding: 0;
  overflow-y: auto;
  min-height: 200px;
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: 10px;
}
.dirs.busy {
  opacity: 0.6;
}
.dirs button {
  display: flex;
  gap: 8px;
  align-items: center;
  width: 100%;
  padding: 7px 12px;
  background: none;
  border: 0;
  color: #eee;
  text-align: left;
  cursor: pointer;
  font: 13px var(--font);
}
.dirs button:hover {
  background: rgba(255, 255, 255, 0.05);
}
.empty {
  padding: 12px;
  color: var(--muted);
}
.error {
  color: #ff9a9a;
  margin: 0;
}
footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
}
footer .primary {
  flex-shrink: 0;
  white-space: nowrap;
}
footer code {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--muted);
}
</style>
