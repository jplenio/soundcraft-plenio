<script setup lang="ts">
/**
 * Which lyrics to follow (lyricsVersion.ts). For a song: as written or as sung - kept for that song, like the
 * player bar's switch (W); *As sung* needs a song exported with what its take sings, and is never chosen by itself.
 * In Settings: the rule for every song - as written (the default) or as sung. On a song's page
 * (``full``) a third choice shows the lyrics as their full text, with their sections, to copy (GitHub issue
 * 2026-10-28) - a view only: the song keeps following the version chosen.
 */
import { computed } from 'vue'

import type { SongDetail } from '../api'
import { chooseFor, LYRICS_CHOICES, LYRICS_VERSIONS, sectionsNotSung, sungNote, sungOf, versionFor } from '../lyricsVersion'
import { settings } from '../store'

/** ``detail``: the song the switch is for; none (Settings, or nothing plays): the rule for every song. */
const props = defineProps<{ detail?: SongDetail | null; details?: boolean; full?: boolean }>()

const sung = computed(() => sungOf(props.detail))
const note = computed(() => (sung.value ? sungNote(sung.value) : ''))
const notSung = computed(() => (sung.value ? sectionsNotSung(sung.value) : []))
const shown = computed(() => versionFor(props.detail, settings))
const chosen = computed(() => Object.keys(settings.lyricsFor).length)
const asText = computed(() => !!props.full && settings.lyricsView === 'text')
function follow(version: 'written' | 'sung'): void {
  if (props.full) settings.lyricsView = 'timed'
  if (props.detail) chooseFor(props.detail, version, settings)
}
</script>

<template>
  <div class="version">
    <div v-if="detail" class="switch" role="radiogroup" aria-label="Which lyrics">
      <button
        v-for="v in LYRICS_VERSIONS"
        :key="v.id"
        type="button"
        role="radio"
        :aria-checked="!asText && shown === v.id"
        :class="{ on: !asText && shown === v.id }"
        :disabled="v.id === 'sung' && !sung"
        :title="v.id === 'sung' && !sung ? 'This song was exported before Plenio kept what its take sings' : `${v.title} - kept for this song (W)`"
        @click="follow(v.id)"
      >
        {{ v.label }}
      </button>
      <button
        v-if="full"
        type="button"
        role="radio"
        :aria-checked="asText"
        :class="{ on: asText }"
        title="The whole lyrics as text, with their sections - to read and copy"
        @click="settings.lyricsView = 'text'"
      >
        Full lyrics
      </button>
    </div>
    <div v-else class="switch" role="radiogroup" aria-label="Which lyrics, for every song">
      <button
        v-for="v in LYRICS_CHOICES"
        :key="v.id"
        type="button"
        role="radio"
        :aria-checked="settings.lyricsChoice === v.id"
        :class="{ on: settings.lyricsChoice === v.id }"
        :title="v.title"
        @click="settings.lyricsChoice = v.id"
      >
        {{ v.label }}
      </button>
    </div>
    <p v-if="!detail && chosen" class="note">
      {{ chosen }} song{{ chosen === 1 ? '' : 's' }} with a choice of their own.
      <button type="button" class="link" @click="settings.lyricsFor = {}">Follow the rule again</button>
    </p>
    <p v-if="details && !asText && note" class="note">
      {{ note }}<template v-if="notSung.length"> Not sung as written: {{ notSung.map((t) => `[${t}]`).join(', ') }}.</template>
    </p>
    <details v-if="details && !asText && sung && sung.not_sung.length" class="missing">
      <summary>Lines of the lyrics not heard</summary>
      <p v-for="(line, i) in sung.not_sung" :key="i">{{ line }}</p>
    </details>
  </div>
</template>

<style scoped>
.version {
  display: grid;
  gap: 6px;
  margin-bottom: 10px;
}
.switch {
  display: inline-flex;
  width: max-content;
  border: 1px solid rgba(255, 255, 255, 0.18);
  border-radius: 999px;
  overflow: hidden;
}
.switch button {
  padding: 5px 14px;
  font-size: 13px;
  background: transparent;
  color: rgba(255, 255, 255, 0.75);
  border: 0;
  cursor: pointer;
}
.switch button.on {
  background: var(--accent);
  color: #fff;
}
.switch button:disabled {
  opacity: 0.45;
  cursor: default;
}
.note {
  margin: 0;
  font-size: 13px;
  color: rgba(255, 255, 255, 0.65);
}
.link {
  padding: 0;
  border: 0;
  background: none;
  color: var(--accent);
  cursor: pointer;
  font-size: 13px;
}
.missing {
  font-size: 13px;
  color: rgba(255, 255, 255, 0.65);
}
.missing p {
  margin: 2px 0 0 12px;
}
</style>
