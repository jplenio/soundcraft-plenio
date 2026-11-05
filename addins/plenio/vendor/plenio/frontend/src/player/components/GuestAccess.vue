<script setup lang="ts">
/**
 * Guests in your network (owner's request 2026-10-17), in Live Play: the access switched on or off, what the
 * guests may do (only look, or change the live playlist), what the screen shows of the way in (QR code,
 * address, both or nothing - in Live Play and Now playing), the address with a new one at any time, and how
 * many guests are looking.
 */
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

import { guestBig, guestError, guestStatus, loadGuests, setGuests } from '../guests'
import { say, settings } from '../store'
import Icon from './Icon.vue'
import QrCode from './QrCode.vue'

const status = guestStatus
const busy = ref(false)
const on = computed(() => !!status.value?.on)
const others = computed(() => status.value?.urls.slice(1) ?? [])
let timer: number | undefined

async function change(changes: Parameters<typeof setGuests>[0], done = ''): Promise<void> {
  busy.value = true
  await setGuests(changes)
  busy.value = false
  if (done && !guestError.value) say(done, 3000)
}
async function copy(): Promise<void> {
  if (!status.value?.url) return
  try {
    await navigator.clipboard.writeText(status.value.url)
    say('Address copied', 2000)
  } catch {
    say('Could not copy - select the address and copy it', 3000)
  }
}
function renew(): void {
  if (window.confirm('Make a new address? The old one stops working - guests need the new QR code or address.'))
    void change({ regenerate: true }, 'A new address - the old one leads nowhere now')
}
onMounted(() => {
  void loadGuests()
  // how many guests are looking: now and then
  timer = window.setInterval(() => void loadGuests(), 5000)
})
onBeforeUnmount(() => window.clearInterval(timer))
</script>

<template>
  <section v-if="status" class="guests" :class="{ on }">
    <div class="top">
      <h3><Icon name="guests" :size="16" /> Guests in your network</h3>
      <label class="switch big">
        <input type="checkbox" :checked="on" :disabled="busy" @change="change({ on: !on }, on ? 'Guests can no longer see the live playlist' : 'Guests in your network can see the live playlist')" />
        Let guests see the live playlist
      </label>
    </div>
    <p class="lead">Anyone on the same network (the party’s Wi-Fi) opens a page of their own on the phone: the song that plays and what comes next - and, if you like, they move songs, take them out and add songs from your library. The music plays here.</p>
    <div v-if="on" class="grid">
      <button class="qr-box" title="Show it big, for everyone to scan" @click="guestBig = true">
        <QrCode v-if="status.url" :text="status.url" :size="150" />
        <span v-else class="no-net">No network address found - is this computer in a network?</span>
      </button>
      <div class="info">
        <div v-if="status.url" class="url">
          <code>{{ status.url }}</code>
          <button class="icon-btn" title="Copy the address" @click="copy"><Icon name="copy" :size="16" /></button>
        </div>
        <div class="choice">
          <span>Guests may</span>
          <label><input type="radio" :checked="status.mode === 'view'" @change="change({ mode: 'view' })" /> only look</label>
          <label><input type="radio" :checked="status.mode === 'change'" @change="change({ mode: 'change' })" /> change it: move, take out, add songs</label>
        </div>
        <div class="choice">
          <span>Reactions</span>
          <label><input type="checkbox" :checked="status.reactions" @change="change({ reactions: !status.reactions })" /> guests may send 🔥 ❤️ 🎉 👏 💃 😂</label>
          <select v-if="status.reactions" :value="status.reactions_per_song ?? 'any'" @change="change({ reactions_per_song: ($event.target as HTMLSelectElement).value as 'any' | 'one' })">
            <option value="any">as many per song as they like</option>
            <option value="one">one per song and guest - a tap on another changes it</option>
          </select>
          <small>they float up the edges of this screen and are counted for each song (the song's page shows them - apart from your hearts)</small>
        </div>
        <div class="choice">
          <span>Hear again</span>
          <label><input type="checkbox" :checked="status.replay !== false" @change="change({ replay: status.replay === false })" /> guests hear this party’s songs again on their phones, once they played</label>
          <small>
            only the songs made at the party - by guests, users and you - and only this party’s:
            since {{ status.party_since ? new Date(status.party_since * 1000).toLocaleString(undefined, { weekday: 'short', hour: '2-digit', minute: '2-digit' }) : 'the access is switched on' }}<template v-if="status.party_songs"> · {{ status.party_songs }} {{ status.party_songs === 1 ? 'song' : 'songs' }} so far</template>
            · <a @click="change({ new_party: true }, 'A new party - its songs start anew')">start a new party</a>
          </small>
        </div>
        <div class="choice">
          <span>On the screen</span>
          <select :value="status.show" @change="change({ show: ($event.target as HTMLSelectElement).value as 'both' })">
            <option value="both">the QR code and the address</option>
            <option value="qr">the QR code</option>
            <option value="address">the address</option>
            <option value="none">nothing</option>
          </select>
          <small>in Live Play and Now playing</small>
        </div>
        <div class="choice">
          <span>Over the visual</span>
          <label><input v-model="settings.live.overVisual" type="checkbox" /> show it too</label>
          <template v-if="settings.live.overVisual">
            <select v-model="settings.live.wayInCorner" title="Where on the visual">
              <option value="top-right">top right</option>
              <option value="top-left">top left</option>
              <option value="bottom-right">bottom right</option>
              <option value="bottom-left">bottom left</option>
            </select>
            <select v-model="settings.live.wayInSize" title="How large - large for a room to scan">
              <option value="s">small</option>
              <option value="m">medium</option>
              <option value="l">large</option>
            </select>
          </template>
          <small>the visual on the whole screen (<b>Show the visual</b> above)</small>
        </div>
        <div class="buttons">
          <button class="ghost small" @click="guestBig = true"><Icon name="qr" :size="14" /> Show it big</button>
          <button class="ghost small" :disabled="busy" @click="renew"><Icon name="refresh" :size="14" /> New address</button>
        </div>
        <p class="hint">
          <b>{{ status.guests }}</b> {{ status.guests === 1 ? 'guest is' : 'guests are' }} looking now.
          The first time, Windows may ask whether Python may accept connections - allow it for private networks, or the phones cannot reach the player.
        </p>
        <p v-if="others.length" class="hint">This computer’s other addresses: <code v-for="u in others" :key="u">{{ u }}</code></p>
      </div>
    </div>
    <p v-if="guestError" class="error">{{ guestError }}</p>
  </section>
</template>

<style scoped>
.guests {
  display: grid;
  gap: 10px;
  padding: 14px 16px;
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.06);
}
.guests.on {
  border-color: color-mix(in srgb, var(--accent) 45%, transparent);
  background: color-mix(in srgb, var(--accent) 7%, transparent);
}
.top {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  align-items: center;
  gap: 10px;
}
h3 {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0;
  font: 600 13px var(--font);
  text-transform: uppercase;
  letter-spacing: 0.7px;
  color: var(--muted);
}
.lead {
  margin: 0;
  color: var(--muted);
  font-size: 13px;
  max-width: 760px;
}
.switch {
  display: flex;
  gap: 8px;
  align-items: center;
  cursor: pointer;
  font-weight: 600;
}
.grid {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  gap: 18px;
  align-items: start;
}
.qr-box {
  padding: 0;
  border: 0;
  background: none;
  cursor: zoom-in;
}
.no-net {
  display: block;
  width: 150px;
  color: var(--muted);
  font-size: 12px;
}
.info {
  display: grid;
  gap: 10px;
  min-width: 0;
}
.url {
  display: flex;
  align-items: center;
  gap: 6px;
}
.url code {
  font: 600 15px var(--mono);
  color: #fff;
  word-break: break-all;
  user-select: all;
}
.choice {
  display: flex;
  flex-wrap: wrap;
  gap: 14px;
  align-items: center;
  font-size: 13px;
}
.choice > span {
  min-width: 110px;
  color: var(--muted);
}
.choice label {
  display: flex;
  gap: 6px;
  align-items: center;
  cursor: pointer;
}
.choice small {
  color: var(--muted);
}
select {
  background: rgba(255, 255, 255, 0.06);
  color: #fff;
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 8px;
  padding: 6px 9px;
  font: 13px var(--font);
}
input[type='radio'],
input[type='checkbox'] {
  accent-color: var(--accent);
}
.buttons {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.hint {
  margin: 0;
  color: var(--muted);
  font-size: 12px;
}
.hint code {
  margin-right: 8px;
  font-family: var(--mono);
}
.error {
  margin: 0;
  color: #ff9a9a;
}
@media (max-width: 700px) {
  .grid {
    grid-template-columns: 1fr;
  }
}
</style>
