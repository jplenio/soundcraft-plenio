<script setup lang="ts">
/**
 * One lyrics line as it is sung, with the effect chosen (lyricsStyle.ts): each syllable is sung, being
 * sung or still to come, and the effect shows it - a colour running through it, a glow, a hop, a swell, a
 * wave through the letters, letters typed one by one, syllables rising in, a blur sharpening, neon flicking
 * on, a rainbow, the line pulsing with the beat. The font, size and colours come from CSS variables set
 * where the lyrics are shown (``--lyrics-font``, ``--lit``).
 */
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import type { TimedLine } from '../api'
import { engine } from '../engine'
import { chunksAt } from '../timing'

const props = defineProps<{ line: TimedLine; time: number; effect: string; pulse?: number }>()

const LETTERS = new Set(['wave', 'typewriter'])
const chunks = computed(() => chunksAt(props.line, props.time))
// the line as a whole keeps its usual wrapping: the words below are the units
const state = (fill: number): string => (fill >= 1 ? 'sung' : fill > 0 ? 'singing' : 'unsung')

interface Letter {
  c: string
  lit: boolean
  index: number
  last: boolean
}
interface Part {
  text: string
  fill: number
  state: string
  letters: Letter[] | null
}

/** The line's words, each its syllables (a word never breaks across lines; the spaces between words do),
 * and for the effects that work letter by letter, each letter - lit when the voice has reached it. */
const words = computed(() => {
  const byLetter = LETTERS.has(props.effect)
  const out: { parts: Part[]; space: string }[] = []
  let word: Part[] = []
  let index = 0
  let lastLit: Letter | null = null
  const close = (space: string) => {
    if (word.length) out.push({ parts: word, space })
    else if (out.length) out[out.length - 1].space += space
    word = []
  }
  for (const chunk of chunks.value) {
    const [, lead, body, trail] = /^(\s*)([\s\S]*?)(\s*)$/.exec(chunk.text) ?? ['', '', chunk.text, '']
    if (lead) close(lead)
    if (body) {
      const reached = Math.round(chunk.fill * body.length)
      const letters = byLetter
        ? [...body].map((c, j) => {
            const letter = { c, lit: j < reached, index: index++, last: false }
            if (letter.lit) lastLit = letter
            return letter
          })
        : null
      word.push({ text: body, fill: chunk.fill, state: state(chunk.fill), letters })
    }
    if (trail) close(trail)
  }
  close('')
  if (lastLit) (lastLit as Letter).last = true
  return out
})

// On the beat: the line breathes with the music's pulse
const beat = ref(0)
let raf = 0
function follow(): void {
  raf = requestAnimationFrame(follow)
  beat.value = props.pulse ?? engine.frame().pulse
}
function start(): void {
  cancelAnimationFrame(raf)
  if (props.effect === 'beat' && props.pulse === undefined) follow()
}
watch(() => props.effect, start)
onMounted(start)
onBeforeUnmount(() => cancelAnimationFrame(raf))
const lineStyle = computed(() => (props.effect === 'beat' ? { transform: `scale(${1 + 0.07 * (props.pulse ?? beat.value)})` } : {}))
</script>

<template>
  <span class="lyric" :class="`fx-${effect}`" :style="lineStyle">
    <template v-for="(word, w) in words" :key="w">
      <span class="word"><span v-for="(part, k) in word.parts" :key="k" class="chunk" :class="part.state" :style="{ '--fill': `${part.fill * 100}%` }"><template v-if="part.letters"><span v-for="l in part.letters" :key="l.index" class="letter" :class="{ lit: l.lit, last: l.last }" :style="{ '--i': l.index }">{{ l.c }}</span></template><template v-else>{{ part.text }}</template></span></span>{{ word.space }}
    </template>
  </span>
</template>

<style scoped>
.lyric {
  --lit-color: var(--lit, #fff);
  --dim: rgba(255, 255, 255, 0.35);
  display: inline-block;
  transform-origin: center;
  transition: transform 0.08s;
}
.word {
  display: inline-block;
  white-space: nowrap;
}
.chunk {
  display: inline-block;
}
/* Sweep: the colour runs through the syllable */
.fx-sweep .chunk,
.fx-beat .chunk {
  background: linear-gradient(90deg, var(--lit-color) var(--fill), var(--dim) var(--fill));
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
}
/* Glow */
.fx-glow .chunk {
  color: var(--dim);
  transition: color 0.25s, text-shadow 0.25s;
}
.fx-glow .sung {
  color: var(--lit-color);
  text-shadow: 0 0 0.3em color-mix(in srgb, var(--lit-color) 60%, transparent);
}
.fx-glow .singing {
  color: #fff;
  text-shadow: 0 0 0.2em var(--lit-color), 0 0 0.6em var(--lit-color), 0 0 1.1em color-mix(in srgb, var(--lit-color) 70%, transparent);
}
/* Bounce: the syllable hops */
.fx-bounce .chunk {
  color: var(--dim);
  transition: transform 0.16s cubic-bezier(0.3, 1.6, 0.5, 1), color 0.15s;
}
.fx-bounce .singing {
  color: var(--lit-color);
  transform: translateY(-0.24em);
}
.fx-bounce .sung {
  color: var(--lit-color);
}
/* Pop: the syllable swells and settles */
.fx-pop .chunk {
  color: var(--dim);
  transform-origin: 50% 80%;
  transition: transform 0.28s cubic-bezier(0.3, 1.8, 0.4, 1), color 0.15s;
}
.fx-pop .singing {
  color: var(--lit-color);
  transform: scale(1.32);
}
.fx-pop .sung {
  color: var(--lit-color);
}
/* Wave: the letters ripple */
.fx-wave .letter {
  display: inline-block;
  color: var(--dim);
  animation: wave 1.8s ease-in-out infinite;
  animation-delay: calc(var(--i) * -0.08s);
  transition: color 0.2s;
}
.fx-wave .letter.lit {
  color: var(--lit-color);
}
@keyframes wave {
  0%,
  100% {
    transform: translateY(0.06em);
  }
  50% {
    transform: translateY(-0.14em);
  }
}
/* Typewriter: letters appear as they are sung */
.fx-typewriter .letter {
  opacity: 0;
  color: var(--lit-color);
}
.fx-typewriter .letter.lit {
  opacity: 1;
}
.fx-typewriter .letter.last::after {
  content: '';
  display: inline-block;
  width: 0.08em;
  height: 0.95em;
  margin-left: 0.02em;
  vertical-align: -0.12em;
  background: var(--lit-color);
  animation: caret 0.9s steps(1) infinite;
}
@keyframes caret {
  50% {
    opacity: 0;
  }
}
/* Rise: syllables float up and in */
.fx-rise .chunk {
  opacity: 0.12;
  color: var(--lit-color);
  transform: translateY(0.4em);
  transition: opacity 0.35s, transform 0.4s cubic-bezier(0.2, 0.9, 0.3, 1.2);
}
.fx-rise .singing,
.fx-rise .sung {
  opacity: 1;
  transform: none;
}
/* Focus: blurred until sung */
.fx-focus .chunk {
  color: var(--dim);
  filter: blur(0.12em);
  transition: filter 0.3s, color 0.3s;
}
.fx-focus .singing {
  color: var(--lit-color);
  filter: blur(0.03em);
}
.fx-focus .sung {
  color: var(--lit-color);
  filter: none;
}
/* Neon: outlines that flick on */
.fx-neon .chunk {
  color: transparent;
  -webkit-text-stroke: 0.025em rgba(255, 255, 255, 0.3);
}
.fx-neon .sung,
.fx-neon .singing {
  color: #fff;
  -webkit-text-stroke: 0.02em var(--lit-color);
  text-shadow: 0 0 0.08em var(--lit-color), 0 0 0.3em var(--lit-color), 0 0 0.7em var(--lit-color);
}
.fx-neon .singing {
  animation: flicker 0.45s steps(2) 1;
}
@keyframes flicker {
  0% {
    opacity: 0.3;
  }
  40% {
    opacity: 1;
  }
  60% {
    opacity: 0.5;
  }
  100% {
    opacity: 1;
  }
}
/* Rainbow */
.fx-rainbow .chunk {
  color: var(--dim);
}
.fx-rainbow .sung,
.fx-rainbow .singing {
  color: transparent;
  background: linear-gradient(90deg, #ff5e5e, #ffb35e, #fff35e, #6bff7a, #5ed4ff, #8a6bff, #ff5ec8, #ff5e5e);
  background-size: 300% 100%;
  -webkit-background-clip: text;
  background-clip: text;
  animation: rainbow 3s linear infinite;
}
@keyframes rainbow {
  to {
    background-position: 300% 0;
  }
}
</style>
