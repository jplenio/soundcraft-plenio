<script setup lang="ts">
/**
 * The guests' reactions floating up the edges of the screen (``reactions.ts``): over every page and the visual on
 * the whole screen, never in the way of a click. With less motion wished they only fade in and out at the edge.
 */
import { reducedMotion } from '../layout'
import { floating } from '../reactions'
</script>

<template>
  <div class="reactions" :class="{ still: reducedMotion }" aria-hidden="true">
    <span
      v-for="f in floating"
      :key="f.key"
      class="r"
      :style="{ [f.side]: `${f.x}%`, fontSize: `${f.size}px`, animationDuration: `${f.duration}s`, '--drift': `${f.drift}px` }"
      >{{ f.emoji }}</span
    >
  </div>
</template>

<style scoped>
.reactions {
  position: fixed;
  inset: 0;
  z-index: 70;
  pointer-events: none;
  overflow: hidden;
}
.r {
  position: absolute;
  bottom: -70px;
  line-height: 1;
  filter: drop-shadow(0 6px 14px rgba(0, 0, 0, 0.45));
  animation: rise 4s cubic-bezier(0.25, 0.6, 0.35, 1) forwards;
  will-change: transform, opacity;
}
@keyframes rise {
  0% {
    transform: translate(0, 0) scale(0.5);
    opacity: 0;
  }
  10% {
    transform: translate(calc(var(--drift) * 0.3), -8vh) scale(1.08);
    opacity: 1;
  }
  35% {
    transform: translate(calc(var(--drift) * -0.4), -32vh) scale(1);
  }
  65% {
    transform: translate(var(--drift), -60vh) scale(0.95);
    opacity: 0.95;
  }
  100% {
    transform: translate(calc(var(--drift) * -0.2), -95vh) scale(0.8);
    opacity: 0;
  }
}
.still .r {
  bottom: 14vh;
  animation-name: blink;
}
@keyframes blink {
  0%,
  100% {
    opacity: 0;
  }
  20%,
  70% {
    opacity: 1;
  }
}
</style>
