<script setup lang="ts">
/**
 * A sheet that slides up from the bottom of a phone (the filters, a song's actions, the sort): a handle to pull it
 * down by, its title, what it holds - scrolling inside, never the page behind it - and a foot that stays (a button
 * such as *Show 120 songs*). A pull down, a tap beside it or Esc closes it.
 */
import { onBeforeUnmount, onMounted, ref } from 'vue'

import { paletteStyle } from '../now'
import Icon from './Icon.vue'

defineOptions({ inheritAttrs: false })
defineProps<{ title?: string }>()
const emit = defineEmits<{ close: [] }>()

const pull = ref(0)
let start: number | null = null
function down(event: PointerEvent): void {
  start = event.clientY
  ;(event.currentTarget as HTMLElement).setPointerCapture?.(event.pointerId)
}
function move(event: PointerEvent): void {
  if (start !== null) pull.value = Math.max(0, event.clientY - start)
}
function up(): void {
  if (start === null) return
  start = null
  if (pull.value > 90) emit('close')
  pull.value = 0
}
function onKey(event: KeyboardEvent): void {
  if (event.key !== 'Escape') return
  event.stopImmediatePropagation()
  emit('close')
}
onMounted(() => window.addEventListener('keydown', onKey, true))
onBeforeUnmount(() => window.removeEventListener('keydown', onKey, true))
</script>

<template>
  <Teleport to="body">
    <div class="veil" @click="emit('close')" />
    <section v-bind="$attrs" class="sheet" role="dialog" aria-modal="true" :aria-label="title" :style="[paletteStyle, { transform: pull ? `translateY(${pull}px)` : '' }]">
      <header @pointerdown="down" @pointermove="move" @pointerup="up" @pointercancel="up">
        <i class="handle" />
        <h3 v-if="title">{{ title }}</h3>
        <button class="icon-btn" title="Close" @click="emit('close')"><Icon name="close" /></button>
      </header>
      <div class="content"><slot /></div>
      <footer v-if="$slots.foot"><slot name="foot" /></footer>
    </section>
  </Teleport>
</template>

<style scoped>
.veil {
  position: fixed;
  inset: 0;
  z-index: 80;
  background: rgba(0, 0, 0, 0.55);
  backdrop-filter: blur(3px);
  animation: fade 0.25s ease-out;
}
.sheet {
  position: fixed;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: 81;
  display: flex;
  flex-direction: column;
  max-height: min(86vh, 86dvh);
  padding-bottom: env(safe-area-inset-bottom, 0px);
  border-radius: 22px 22px 0 0;
  background: #15121f;
  border-top: 1px solid rgba(255, 255, 255, 0.1);
  box-shadow: 0 -20px 60px rgba(0, 0, 0, 0.6);
  color: #f2f0f8;
  animation: rise 0.32s cubic-bezier(0.2, 0.8, 0.2, 1);
  transition: transform 0.12s;
}
header {
  position: relative;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 18px 10px 8px 18px;
  touch-action: none;
  cursor: grab;
}
.handle {
  position: absolute;
  top: 7px;
  left: 50%;
  width: 40px;
  height: 4px;
  margin-left: -20px;
  border-radius: 4px;
  background: rgba(255, 255, 255, 0.25);
}
h3 {
  flex: 1;
  margin: 0;
  font: 700 17px var(--font);
}
.content {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  overscroll-behavior: contain;
  padding: 4px 18px 16px;
}
footer {
  padding: 10px 18px 12px;
  border-top: 1px solid rgba(255, 255, 255, 0.07);
}
@keyframes rise {
  from {
    transform: translateY(100%);
  }
}
@keyframes fade {
  from {
    opacity: 0;
  }
}
</style>
