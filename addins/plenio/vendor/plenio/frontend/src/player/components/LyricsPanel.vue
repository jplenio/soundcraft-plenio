<script setup lang="ts">
/**
 * How the lyrics look (owner's request 2026-10-16): the font (each shown in itself; or any installed font by
 * its name), the size, the colour of what is sung, and the effect - with a line that sings itself as a
 * preview. Used in Settings and in Now playing; the choice is kept with the other settings.
 */
import { onBeforeUnmount, onMounted, ref } from 'vue'

import type { TimedLine } from '../api'
import { COLORS, EFFECTS, FONTS } from '../lyricsStyle'
import { palette } from '../now'
import { settings } from '../store'
import LyricLine from './LyricLine.vue'

defineProps<{ compact?: boolean }>()

const style = settings.lyrics
const WORDS = ['Every ', 'word ', 'lights ', 'up ', 'as ', 'it ', 'is ', 'sung']
const DEMO: TimedLine = (() => {
  const text = WORDS.join('')
  let cut = 0
  const units = WORDS.map((word, k) => {
    cut += word.length
    return [0.4 + k * 0.38, cut]
  })
  return { text, start: 0.4, end: 0.4 + WORDS.length * 0.38, units }
})()

const t = ref(0)
const pulse = ref(0)
let raf = 0
let began = performance.now()
function loop(): void {
  raf = requestAnimationFrame(loop)
  const now = (performance.now() - began) / 1000
  t.value = now % 4.6
  // a beat every half second, for *On the beat*
  pulse.value = Math.max(0, 1 - ((now % 0.5) / 0.5) * 1.6)
}
onMounted(() => {
  began = performance.now()
  loop()
})
onBeforeUnmount(() => cancelAnimationFrame(raf))

const swatch = (value: string): string => value || palette.value.accent
</script>

<template>
  <div class="lyrics-style" :class="{ compact }">
    <div class="preview"><LyricLine :line="DEMO" :time="t" :effect="style.effect" :pulse="pulse" /></div>

    <h4>Font</h4>
    <div class="fonts">
      <button v-for="f in FONTS" :key="f.id" type="button" class="font" :class="{ on: style.font === f.id }" :style="{ fontFamily: f.stack, fontWeight: f.weight }" :title="f.stack" @click="style.font = f.id">
        {{ f.label }}
      </button>
      <button type="button" class="font" :class="{ on: style.font === 'own' }" @click="style.font = 'own'">Your own font…</button>
    </div>
    <label v-if="style.font === 'own'" class="row own">
      Name <input v-model.lazy="style.own" placeholder="a font installed on this computer, e.g. Bauhaus 93" spellcheck="false" />
    </label>

    <h4>Effect</h4>
    <div class="effects">
      <button v-for="e in EFFECTS" :key="e.id" type="button" class="effect" :class="{ on: style.effect === e.id }" :title="e.blurb" @click="style.effect = e.id">
        <b>{{ e.label }}</b><small>{{ e.blurb }}</small>
      </button>
    </div>

    <h4>Colour of what is sung</h4>
    <div class="colors">
      <button v-for="c in COLORS" :key="c.id" type="button" class="color" :class="{ on: style.color === c.id }" :title="c.label" @click="style.color = c.id">
        <i :style="{ background: swatch(c.value) }" /> {{ c.label }}
      </button>
    </div>

    <label class="row">Size <input v-model.number="style.size" type="range" min="0.7" max="1.6" step="0.05" /> <span>{{ Math.round(style.size * 100) }} %</span></label>
    <p class="hint">For the lyrics, Now playing and the subtitles over the visual - and the default of a song’s video.</p>
  </div>
</template>

<style scoped>
.lyrics-style {
  display: grid;
  gap: 8px;
}
.preview {
  display: grid;
  place-items: center;
  min-height: 96px;
  padding: 14px;
  border-radius: 12px;
  background: radial-gradient(circle at 30% 20%, color-mix(in srgb, var(--accent) 22%, transparent), rgba(0, 0, 0, 0.5));
  border: 1px solid rgba(255, 255, 255, 0.08);
  text-align: center;
  font-family: var(--lyrics-font, var(--font));
  font-weight: var(--lyrics-weight, 700);
  font-size: calc(28px * var(--lyrics-scale, 1));
  line-height: 1.25;
  overflow: hidden;
}
.compact .preview {
  font-size: calc(22px * var(--lyrics-scale, 1));
}
h4 {
  margin: 10px 0 2px;
  font: 600 11px var(--font);
  text-transform: uppercase;
  letter-spacing: 0.7px;
  color: var(--muted);
}
.fonts {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(118px, 1fr));
  gap: 6px;
}
.compact .fonts {
  grid-template-columns: 1fr 1fr;
}
.font,
.effect,
.color {
  border: 1px solid rgba(255, 255, 255, 0.1);
  background: rgba(255, 255, 255, 0.03);
  color: #eee;
  border-radius: 10px;
  cursor: pointer;
  text-align: left;
}
.font {
  padding: 8px 10px;
  font-size: 16px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.font.on,
.effect.on,
.color.on {
  border-color: var(--accent);
  background: color-mix(in srgb, var(--accent) 18%, transparent);
}
.effects {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
  gap: 6px;
}
.compact .effects {
  grid-template-columns: 1fr 1fr;
}
.effect {
  display: grid;
  gap: 2px;
  padding: 7px 10px;
  font: 12px var(--font);
}
.effect b {
  font-size: 13px;
}
.effect small {
  color: var(--muted);
  font-size: 11px;
}
.colors {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.color {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 5px 10px;
  font: 12px var(--font);
}
.color i {
  width: 14px;
  height: 14px;
  border-radius: 50%;
  border: 1px solid rgba(255, 255, 255, 0.3);
}
.row {
  display: flex;
  align-items: center;
  gap: 10px;
  color: var(--muted);
  font-size: 13px;
}
.row input[type='range'] {
  flex: 1;
  accent-color: var(--accent);
}
.own input {
  flex: 1;
  background: rgba(255, 255, 255, 0.06);
  color: #fff;
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 8px;
  padding: 6px 8px;
  font: 13px var(--font);
}
.hint {
  color: var(--muted);
  font-size: 11px;
  margin: 4px 0 0;
}
</style>
