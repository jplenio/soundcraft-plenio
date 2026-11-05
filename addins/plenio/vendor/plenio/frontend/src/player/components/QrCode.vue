<script setup lang="ts">
/** A QR code of ``text`` as SVG (``qr.ts``): dark on white with the quiet zone round it, as phones read best. */
import { computed } from 'vue'

import { qrModules, qrPath } from '../qr'

const props = withDefaults(defineProps<{ text: string; size?: number }>(), { size: 160 })
const BORDER = 4
const modules = computed(() => qrModules(props.text))
const side = computed(() => (modules.value?.length ?? 21) + BORDER * 2)
const path = computed(() => (modules.value ? qrPath(modules.value, BORDER) : ''))
</script>

<template>
  <svg v-if="modules" class="qr" :width="size" :height="size" :viewBox="`0 0 ${side} ${side}`" shape-rendering="crispEdges" role="img" :aria-label="`QR code: ${text}`">
    <rect width="100%" height="100%" fill="#fff" />
    <path :d="path" fill="#111" />
  </svg>
  <p v-else class="qr-too-long">The address is too long for a QR code.</p>
</template>

<style scoped>
.qr {
  display: block;
  border-radius: 8px;
}
</style>
