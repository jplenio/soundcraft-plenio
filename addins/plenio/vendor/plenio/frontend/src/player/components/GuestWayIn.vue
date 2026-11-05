<script setup lang="ts">
/**
 * The way in for guests, on the screen (owner's request 2026-10-17): while the guests' access is on and Live
 * Play runs, a card with the QR code and/or the address - as the access's *On the screen* says - in Live Play
 * and Now playing; ``big`` shows it over everything, for a screen the whole room sees.
 */
import { computed } from 'vue'

import { guestBig, guestStatus } from '../guests'
import { settings } from '../store'
import Icon from './Icon.vue'
import QrCode from './QrCode.vue'

/** ``side``: the QR code's side in the card (over the visual it can be larger, for a room to scan). */
const props = defineProps<{ big?: boolean; side?: number }>()
const status = guestStatus
const shown = computed(() => {
  const s = status.value
  if (!s?.on || !s.url) return false
  return props.big || (s.show !== 'none' && !!settings.live?.on)
})
const qr = computed(() => props.big || status.value?.show === 'both' || status.value?.show === 'qr')
const address = computed(() => props.big || status.value?.show === 'both' || status.value?.show === 'address')
const short = computed(() => status.value?.url.replace(/^https?:\/\//, '') ?? '')
</script>

<template>
  <div v-if="shown && big" class="veil" role="dialog" aria-label="The way in for guests" @click.self="guestBig = false">
    <div class="poster">
      <button class="icon-btn close" title="Close (Esc)" @click="guestBig = false"><Icon name="close" /></button>
      <h2><Icon name="live" :size="30" /> Join the live playlist</h2>
      <p>Scan it with your phone - same Wi-Fi. {{ status?.mode === 'change' ? 'Move songs, take them out, add your favourites.' : 'See what plays and what comes next.' }}</p>
      <QrCode :text="status?.url ?? ''" :size="420" />
      <code>{{ short }}</code>
    </div>
  </div>
  <button v-else-if="shown" class="card" :class="{ wide: address && !qr }" title="Show it big" @click="guestBig = true">
    <QrCode v-if="qr" :text="status?.url ?? ''" :size="side ?? 104" />
    <span class="text">
      <b><Icon name="guests" :size="14" /> Join the live playlist</b>
      <small v-if="address">{{ short }}</small>
      <small v-else>scan with your phone - same Wi-Fi</small>
    </span>
  </button>
</template>

<style scoped>
.card {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 14px 10px 10px;
  border-radius: 16px;
  border: 1px solid rgba(255, 255, 255, 0.14);
  background: rgba(12, 10, 24, 0.82);
  backdrop-filter: blur(10px);
  color: #fff;
  font: 13px var(--font);
  text-align: left;
  cursor: zoom-in;
  box-shadow: 0 10px 40px rgba(0, 0, 0, 0.45);
}
.text {
  display: grid;
  gap: 4px;
  max-width: 250px;
}
.text b {
  display: flex;
  align-items: center;
  gap: 6px;
}
.text small {
  color: rgba(255, 255, 255, 0.75);
  font-family: var(--mono);
  font-size: 11px;
  overflow-wrap: anywhere;
}
.card.wide .text {
  max-width: 340px;
}
.card.wide .text small {
  font-size: 15px;
  color: #fff;
}
.veil {
  position: fixed;
  inset: 0;
  z-index: 120;
  display: grid;
  place-items: center;
  background: rgba(5, 4, 12, 0.88);
  backdrop-filter: blur(6px);
}
.poster {
  position: relative;
  display: grid;
  justify-items: center;
  gap: 16px;
  padding: 34px 44px;
  border-radius: 26px;
  background: #15111f;
  border: 1px solid rgba(255, 255, 255, 0.1);
  max-width: 92vw;
  text-align: center;
}
.poster h2 {
  display: flex;
  align-items: center;
  gap: 12px;
  margin: 0;
  font: 800 34px var(--font);
}
.poster p {
  margin: 0;
  color: var(--muted);
  font-size: 17px;
}
.poster :deep(.qr) {
  width: min(420px, 62vh, 80vw);
  height: auto;
}
.poster code {
  font: 700 clamp(16px, 2.4vw, 28px) var(--mono);
  color: #fff;
  word-break: break-all;
}
.close {
  position: absolute;
  top: 12px;
  right: 12px;
}
</style>
