<script setup lang="ts">
/**
 * Remove a song from the library (owner's request 2026-10-16): to the retired songs - its files moved to a
 * folder the library does not read, from where they can be moved back - or deleted for good, which asks
 * once more. The dialog lists the files either way.
 */
import { computed, onMounted, ref } from 'vue'

import type { SongDetail, SongSummary } from '../api'
import { go, remote, removeSong, route, songDetail } from '../store'
import Icon from './Icon.vue'

const props = defineProps<{ song: SongSummary }>()
const emit = defineEmits<{ close: []; done: [message: string] }>()

const detail = ref<SongDetail | null>(null)
const sure = ref(false)
const busy = ref(false)
const error = ref('')
const files = computed(() => detail.value?.owned_files ?? [])

onMounted(async () => {
  try {
    detail.value = await songDetail(props.song.id)
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  }
})

async function remove(action: 'retire' | 'delete'): Promise<void> {
  if (action === 'delete' && !sure.value) {
    sure.value = true
    return
  }
  busy.value = true
  error.value = ''
  try {
    await removeSong(props.song.id, action)
    if (route.value === `/song/${props.song.id}`) go('/', true)
    emit('done', action === 'retire' ? `“${props.song.title}” retired` : `“${props.song.title}” deleted`)
    emit('close')
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="veil" @click="emit('close')">
    <div class="dialog" role="dialog" aria-modal="true" @click.stop>
      <h3><Icon name="thumbdown" /> Remove “{{ song.title }}”?</h3>
      <p class="lead">It leaves the library, the queue, your playlists and favourites.</p>

      <button class="choice" :disabled="busy || !detail" @click="remove('retire')">
        <b><Icon name="folder" :size="18" /> Move to the retired songs</b>
        <span>The files go to a folder of their own, which the player does not read - move them back to have the song again.</span>
        <code v-if="detail">{{ detail.retire_to }}</code>
      </button>

      <p v-if="remote" class="hint">From the network a song is retired; deleting it for good is done on the computer itself.</p>
      <button v-if="!remote" class="choice danger" :class="{ sure }" :disabled="busy || !detail" @click="remove('delete')">
        <b><Icon name="trash" :size="18" /> {{ sure ? `Yes, delete ${files.length} ${files.length === 1 ? 'file' : 'files'} for good` : 'Delete permanently' }}</b>
        <span>{{ sure ? 'This cannot be undone - click again to delete.' : 'The files are deleted, not moved to the recycle bin.' }}</span>
      </button>

      <details v-if="files.length" class="files">
        <summary>{{ files.length }} {{ files.length === 1 ? 'file' : 'files' }}</summary>
        <ul>
          <li v-for="f in files" :key="f">{{ f }}</li>
        </ul>
      </details>
      <p v-if="error" class="error">{{ error }}</p>
      <div class="foot">
        <button class="ghost" :disabled="busy" @click="emit('close')">Keep the song</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.veil {
  position: fixed;
  inset: 0;
  z-index: 92;
  display: grid;
  place-items: center;
  background: rgba(0, 0, 0, 0.55);
  backdrop-filter: blur(6px);
}
.dialog {
  width: min(560px, 92vw);
  max-height: 88vh;
  overflow-y: auto;
  background: rgba(18, 16, 28, 0.98);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 18px;
  padding: 20px 22px;
  box-shadow: 0 30px 80px rgba(0, 0, 0, 0.6);
}
h3 {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 0 0 6px;
  font: 700 18px var(--font);
}
.lead {
  margin: 0 0 16px;
  color: var(--muted);
  font-size: 13px;
}
.choice {
  display: flex;
  flex-direction: column;
  gap: 4px;
  width: 100%;
  text-align: left;
  margin-bottom: 10px;
  padding: 12px 14px;
  border-radius: 12px;
  border: 1px solid rgba(255, 255, 255, 0.12);
  background: rgba(255, 255, 255, 0.04);
  color: #fff;
  cursor: pointer;
  font: 13px var(--font);
  transition: border-color 0.15s, background 0.15s;
}
.choice:hover:not(:disabled) {
  border-color: var(--accent);
  background: color-mix(in srgb, var(--accent) 14%, transparent);
}
.choice b {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
}
.choice span {
  color: var(--muted);
}
.choice code {
  font: 11px var(--mono);
  color: rgba(255, 255, 255, 0.7);
  word-break: break-all;
}
.danger b {
  color: #ff8f8f;
}
.danger:hover:not(:disabled),
.danger.sure {
  border-color: #ff6b6b;
  background: rgba(255, 80, 80, 0.12);
}
.files {
  margin: 4px 0 8px;
  font-size: 12px;
  color: var(--muted);
}
.files ul {
  margin: 6px 0 0;
  padding-left: 18px;
  font: 11px var(--mono);
  word-break: break-all;
}
.error {
  color: #ff8f8f;
  font-size: 13px;
}
.foot {
  display: flex;
  justify-content: flex-end;
  margin-top: 8px;
}
</style>
