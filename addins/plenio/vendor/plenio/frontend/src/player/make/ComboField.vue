<script setup lang="ts">
/**
 * One field of the song form (owner's request 2026-10-25): a list of every value the style templates have - or a
 * value of one's own, typed instead, which clears the list's choice. A template's value lights up for a moment.
 */
import { computed, nextTick, ref, watch } from 'vue'

const props = defineProps<{
  label: string
  hint: string
  placeholder: string
  options: string[]
  modelValue: string
  /** A value of one's own may be typed (not for the vocals: one of their choices). */
  own?: boolean
  /** The text an option shows (the value it stands for stays). */
  describe?: (value: string) => string
  limit?: number
  /** Lights up: a style template just filled it. */
  lit?: boolean
  /** No "-" entry: the field always has a value (length, vocals). */
  required?: boolean
  /** Counts the templates applied: a new one shows its value in the list again (a value of one's own typed
   * before is replaced). */
  epoch?: number
}>()
const emit = defineEmits<{ 'update:modelValue': [value: string] }>()

const OWN = '\u0001own'
const typing = ref(false)
const input = ref<HTMLInputElement | null>(null)
const inList = computed(() => !props.modelValue || props.options.includes(props.modelValue))
/** What the list shows: the value, or *Your own* while one is typed. */
const shown = computed(() => (props.own && (typing.value || !inList.value) ? OWN : props.modelValue))

// a value set from outside that the list has (a template chosen): the list shows it again
watch(
  () => props.modelValue,
  (value) => {
    if (value && props.options.includes(value) && document.activeElement !== input.value) typing.value = false
  }
)
watch(
  () => props.epoch,
  () => (typing.value = false)
)

function choose(value: string): void {
  if (value === OWN) {
    typing.value = true
    emit('update:modelValue', '')
    void nextTick(() => input.value?.focus())
    return
  }
  typing.value = false
  emit('update:modelValue', value)
}
function back(): void {
  typing.value = false
  emit('update:modelValue', '')
}
</script>

<template>
  <div class="combo" :class="{ lit }">
    <label class="name">
      <span>{{ label }}</span>
      <select :value="shown" :class="{ empty: !shown }" @change="choose(($event.target as HTMLSelectElement).value)">
        <option v-if="!required" value="">-</option>
        <option v-for="o in options" :key="o" :value="o">{{ describe ? describe(o) : o }}</option>
        <option v-if="own" :value="OWN">✎ Your own …</option>
      </select>
    </label>
    <div v-if="shown === OWN" class="own">
      <input ref="input" :value="modelValue" :placeholder="placeholder" :maxlength="limit" :aria-label="`${label}: your own`" @input="emit('update:modelValue', ($event.target as HTMLInputElement).value)" />
      <button type="button" class="back" :title="`Back to the list of ${label.toLowerCase()}s`" @click="back">List</button>
    </div>
    <small class="hint">{{ hint }}</small>
  </div>
</template>

<style scoped>
.combo {
  display: grid;
  gap: 5px;
  padding: 10px 12px 9px;
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.035);
  border: 1px solid rgba(255, 255, 255, 0.07);
  transition: border-color 0.6s, box-shadow 0.6s, background 0.6s;
  min-width: 0;
}
.combo.lit {
  border-color: color-mix(in srgb, var(--accent) 70%, transparent);
  background: color-mix(in srgb, var(--accent) 10%, rgba(255, 255, 255, 0.035));
  box-shadow: 0 0 22px color-mix(in srgb, var(--accent) 22%, transparent);
  transition: none;
}
.name {
  display: grid;
  gap: 5px;
  font: 600 12px var(--font);
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--muted);
}
select,
input {
  width: 100%;
  min-width: 0;
  height: 38px;
  padding: 0 10px;
  border-radius: 10px;
  border: 1px solid rgba(255, 255, 255, 0.12);
  background: rgba(10, 8, 18, 0.55);
  color: #fff;
  font: 500 14px var(--font);
  text-transform: none;
  letter-spacing: 0;
}
select.empty {
  color: rgba(255, 255, 255, 0.45);
}
select:focus,
input:focus {
  outline: none;
  border-color: var(--accent);
}
.own {
  display: flex;
  gap: 6px;
}
.back {
  flex: none;
  height: 38px;
  padding: 0 12px;
  border-radius: 10px;
  border: 1px solid rgba(255, 255, 255, 0.12);
  background: rgba(255, 255, 255, 0.05);
  color: rgba(255, 255, 255, 0.8);
  font: 500 12px var(--font);
  cursor: pointer;
}
.hint {
  color: rgba(235, 232, 245, 0.42);
  font-size: 11.5px;
  line-height: 1.35;
}
</style>
