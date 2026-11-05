<script setup lang="ts">
/**
 * The player in your network (owner's request 2026-10-18): one switch opens the whole player - and ComfyUI,
 * when it runs here - to the devices in the home network, by a link with a code of its own (a QR code for a
 * phone). The browser that opened the link once comes in by the address alone from then on; *New link* shuts
 * every other one out. On a page that came from the network: what it is, and ComfyUI by the same way.
 */
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

import { api, type NetworkStatus } from '../api'
import { info, say } from '../store'
import Icon from './Icon.vue'
import QrCode from './QrCode.vue'

const status = ref<NetworkStatus | null>(null)
const busy = ref(false)
const error = ref('')
const remote = computed(() => !!info.value?.remote)
let timer: number | undefined

async function read(): Promise<void> {
  try {
    status.value = await api.network()
  } catch {
    // an older player: nothing to show
  }
}
async function change(changes: { on?: boolean; regenerate?: boolean }, done: string): Promise<void> {
  busy.value = true
  error.value = ''
  try {
    status.value = await api.setNetwork(changes)
    if (status.value.error) error.value = status.value.error
    else say(done, 3000)
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    busy.value = false
  }
}
function renew(): void {
  if (window.confirm('Make a new link? The old one, and every browser that came in by it, is shut out - open the new one on each device.'))
    void change({ regenerate: true }, 'A new link - the old one leads nowhere now')
}
async function copy(text: string): Promise<void> {
  try {
    await navigator.clipboard.writeText(text)
    say('Link copied', 2000)
  } catch {
    say('Could not copy - select the link and copy it', 3000)
  }
}
const short = (url: string): string => url.replace(/^https?:\/\//, '')
onMounted(() => {
  void read()
  // ComfyUI started or stopped meanwhile
  timer = window.setInterval(() => void read(), 8000)
})
onBeforeUnmount(() => window.clearInterval(timer))
</script>

<template>
  <section v-if="status" class="block network" :class="{ on: status.on }">
    <h3><Icon name="external" /> In your network</h3>
    <template v-if="remote">
      <p class="lead">You came to this player from the network - it is the whole player of the computer it runs on: play, search, playlists, tags, videos and shared players. Choosing its folders, stopping it, opening folders on its screen and deleting songs for good are done on that computer.</p>
      <div class="row">
        <a v-if="status.comfyui_running && status.comfyui_here" class="ghost" :href="status.comfyui_here" target="_blank" rel="noopener"><Icon name="external" :size="16" /> Open ComfyUI</a>
        <span v-else class="hint">ComfyUI is not running on that computer.</span>
      </div>
    </template>
    <template v-else>
      <label class="switch">
        <input type="checkbox" :checked="status.on" :disabled="busy" @change="change({ on: !status.on }, status.on ? 'The player is closed to the network again' : 'Open to your network - scan the QR code with a phone')" />
        Open the player from your network
      </label>
      <p class="lead">Every phone, tablet or computer in your home network opens the whole player - your songs, playlists, the visuals - with this link while the player runs here; and ComfyUI, when it runs on this computer. The music plays on the device that opens it. A browser that opened the link once comes in by the address alone from then on; nobody without the link does.</p>
      <div v-if="status.on" class="grid">
        <div class="qr"><QrCode v-if="status.url" :text="status.url" :size="160" /><span v-else class="hint">No network address found - is this computer in a network?</span></div>
        <div class="links">
          <p class="label">The player</p>
          <div v-if="status.url" class="url">
            <a :href="status.url" target="_blank" rel="noopener"><code>{{ short(status.url) }}</code></a>
            <button class="icon-btn" title="Copy the link" @click="copy(status.url)"><Icon name="copy" :size="16" /></button>
          </div>
          <p class="label">ComfyUI <small :class="{ ok: status.comfyui_running }">{{ status.comfyui_running ? 'running' : 'not running now - the link works once it does' }}</small></p>
          <div v-if="status.comfyui_url" class="url">
            <a :href="status.comfyui_url" target="_blank" rel="noopener"><code>{{ short(status.comfyui_url) }}</code></a>
            <button class="icon-btn" title="Copy the link" @click="copy(status.comfyui_url)"><Icon name="copy" :size="16" /></button>
          </div>
          <div class="row">
            <button class="ghost small" :disabled="busy" @click="renew"><Icon name="refresh" :size="14" /> New link</button>
          </div>
          <p class="hint">
            From the network the player does everything but choose its folders, stop, open folders on this screen and delete songs for good (it retires them). The first time, Windows may ask whether Python may accept connections - allow it for private networks.
            <template v-if="status.urls.length > 1"> This computer's other addresses: <code v-for="u in status.urls.slice(1)" :key="u">{{ short(u) }}</code></template>
          </p>
        </div>
      </div>
    </template>
    <p v-if="error" class="error">{{ error }}</p>
  </section>
</template>

<style scoped>
.network.on {
  border-color: color-mix(in srgb, var(--accent) 45%, transparent);
}
.switch {
  display: flex;
  gap: 8px;
  align-items: center;
  font-weight: 600;
  cursor: pointer;
  margin-bottom: 8px;
}
input[type='checkbox'] {
  accent-color: var(--accent);
}
.grid {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  gap: 18px;
  align-items: start;
}
.links {
  display: grid;
  gap: 6px;
  min-width: 0;
}
.label {
  margin: 4px 0 0;
  font: 600 12px var(--font);
  text-transform: uppercase;
  letter-spacing: 0.6px;
  color: var(--muted);
}
.label small {
  text-transform: none;
  letter-spacing: 0;
  font-weight: 500;
  color: #ffb36b;
}
.label small.ok {
  color: #7fe0a0;
}
.url {
  display: flex;
  align-items: center;
  gap: 6px;
}
.url a {
  color: #fff;
  text-decoration: none;
  min-width: 0;
}
.url code {
  font: 600 14px var(--mono);
  word-break: break-all;
}
.row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 6px;
}
.small {
  height: 32px;
  font-size: 12px;
}
.hint {
  color: var(--muted);
  font-size: 12px;
}
.hint code {
  margin-right: 8px;
}
.error {
  color: #ff9a9a;
}
@media (max-width: 700px) {
  .grid {
    grid-template-columns: 1fr;
  }
}
</style>
