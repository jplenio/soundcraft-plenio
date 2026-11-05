<script setup lang="ts">
/**
 * The login page (owner's request 2026-10-23): who listens - a user (their picture, then the password), the
 * admin on the player's own computer, or a guest whose things stay in this browser. Shown once per device: a
 * login is kept, and so is a guest's choice.
 */
import { computed, nextTick, ref } from 'vue'

import { type Account, avatarUrl, continueAsGuest, initials, logIn, logInAdmin, session } from '../account'

const emit = defineEmits<{ done: [] }>()

const chosen = ref<Account | null>(null)
const password = ref('')
const busy = ref(false)
const error = ref('')
const field = ref<HTMLInputElement | null>(null)

const users = computed(() => session.value?.users ?? [])
const admin = computed(() => (session.value?.local ? session.value.admin ?? null : null))

async function pick(account: Account): Promise<void> {
  error.value = ''
  if (account.admin) {
    await act(() => logInAdmin())
    return
  }
  chosen.value = account
  password.value = ''
  await nextTick()
  field.value?.focus()
}

async function act(step: () => Promise<void> | void): Promise<void> {
  busy.value = true
  error.value = ''
  try {
    await step()
    emit('done')
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    busy.value = false
  }
}

const submit = (): Promise<void> => act(() => logIn(chosen.value!.id, password.value))
</script>

<template>
  <div class="login" role="dialog" aria-modal="true" aria-label="Who is listening?">
    <div class="glow" />
    <div class="card">
      <div class="brand"><span class="logo"><i /><i /><i /><i /></span> Plenio <b>Player</b></div>
      <h1>Who is listening?</h1>

      <div v-if="!chosen" class="people">
        <button v-for="u in users" :key="u.id" type="button" class="person" :disabled="busy" @click="pick(u)">
          <span class="face" :style="{ background: u.color }">
            <img v-if="u.avatar" :src="avatarUrl(u)" alt="" />
            <template v-else>{{ initials(u.name) }}</template>
          </span>
          <span class="name">{{ u.name }}</span>
        </button>
        <button v-if="admin" type="button" class="person admin" :disabled="busy" title="The admin: the player's own playlists and settings, and the users - only on this computer" @click="pick(admin)">
          <span class="face" :style="{ background: admin.color }">
            <img v-if="admin.avatar" :src="avatarUrl(admin)" alt="" />
            <template v-else>{{ initials(admin.name) }}</template>
            <span class="key">🔑</span>
          </span>
          <span class="name">{{ admin.name }}</span>
          <small>this computer</small>
        </button>
      </div>

      <form v-else class="password" @submit.prevent="submit">
        <span class="face big" :style="{ background: chosen.color }">
          <img v-if="chosen.avatar" :src="avatarUrl(chosen)" alt="" />
          <template v-else>{{ initials(chosen.name) }}</template>
        </span>
        <p class="who">{{ chosen.name }}</p>
        <input ref="field" v-model="password" type="password" autocomplete="current-password" placeholder="Password" :disabled="busy" />
        <div class="row">
          <button type="button" class="ghost" :disabled="busy" @click="chosen = null">Back</button>
          <button type="submit" class="primary" :disabled="busy || !password">Log in</button>
        </div>
      </form>

      <p v-if="error" class="error">{{ error }}</p>

      <div class="guest">
        <button type="button" class="ghost wide" :disabled="busy" @click="act(continueAsGuest)">Continue as a guest</button>
        <p class="hint">
          A guest’s playlists, likes and plays stay in this browser only.
          <template v-if="!users.length && !admin">Ask the player’s admin for an account to keep them on every device.</template>
          <template v-else>Logged in, they are the same on every device.</template>
        </p>
      </div>
    </div>
  </div>
</template>

<style scoped>
.login {
  position: fixed;
  inset: 0;
  z-index: 1000;
  display: grid;
  place-items: center;
  overflow: auto;
  padding: 24px 16px;
  background: radial-gradient(1200px 700px at 30% 20%, #2a1d4d 0%, #120d22 55%, #08060f 100%);
  color: #eee;
}
.glow {
  position: fixed;
  inset: -30%;
  background: conic-gradient(from 200deg, rgba(120, 80, 255, 0.18), rgba(255, 110, 180, 0.12), rgba(80, 200, 255, 0.14), rgba(120, 80, 255, 0.18));
  filter: blur(90px);
  animation: turn 40s linear infinite;
  pointer-events: none;
}
@keyframes turn {
  to {
    transform: rotate(360deg);
  }
}
.card {
  position: relative;
  width: min(720px, 100%);
  padding: 32px 28px;
  border-radius: 24px;
  background: rgba(20, 16, 34, 0.72);
  border: 1px solid rgba(255, 255, 255, 0.08);
  box-shadow: 0 30px 80px rgba(0, 0, 0, 0.5);
  backdrop-filter: blur(12px);
  text-align: center;
}
.brand {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  font: 600 18px var(--font);
  opacity: 0.85;
}
.logo {
  display: flex;
  gap: 3px;
  align-items: flex-end;
  height: 22px;
}
.logo i {
  width: 4px;
  border-radius: 2px;
  background: linear-gradient(var(--accent), var(--accent2));
}
.logo i:nth-child(1) {
  height: 40%;
}
.logo i:nth-child(2) {
  height: 90%;
}
.logo i:nth-child(3) {
  height: 65%;
}
.logo i:nth-child(4) {
  height: 30%;
}
h1 {
  margin: 14px 0 26px;
  font-size: 30px;
  font-weight: 700;
}
.people {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 22px;
}
.person {
  display: grid;
  justify-items: center;
  gap: 8px;
  width: 112px;
  padding: 10px 4px;
  border: 0;
  border-radius: 16px;
  background: transparent;
  color: #ddd;
  cursor: pointer;
  transition: transform 0.15s, background 0.15s;
}
.person:hover:not(:disabled) {
  transform: translateY(-3px);
  background: rgba(255, 255, 255, 0.06);
}
.face {
  position: relative;
  display: grid;
  place-items: center;
  width: 84px;
  height: 84px;
  border-radius: 50%;
  overflow: hidden;
  font: 700 28px var(--font);
  color: #fff;
  box-shadow: 0 0 0 3px rgba(255, 255, 255, 0.12), 0 10px 26px rgba(0, 0, 0, 0.4);
}
.face img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.face.big {
  width: 110px;
  height: 110px;
  font-size: 36px;
  margin: 0 auto;
}
.key {
  position: absolute;
  right: 4px;
  bottom: 4px;
  font-size: 18px;
}
.name {
  font-weight: 600;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.person small {
  margin-top: -6px;
  font-size: 11px;
  opacity: 0.6;
}
.password {
  display: grid;
  gap: 12px;
  justify-items: center;
}
.who {
  margin: 0;
  font-weight: 700;
  font-size: 18px;
}
.password input {
  width: min(320px, 100%);
  padding: 10px 14px;
  border-radius: 12px;
  border: 1px solid rgba(255, 255, 255, 0.18);
  background: rgba(0, 0, 0, 0.35);
  color: #fff;
  font-size: 16px;
}
.row {
  display: flex;
  gap: 10px;
}
.primary {
  padding: 9px 22px;
  border: 0;
  border-radius: 999px;
  background: var(--accent, #7a5cff);
  color: #fff;
  font-weight: 700;
  cursor: pointer;
}
.primary:disabled {
  opacity: 0.5;
  cursor: default;
}
.error {
  margin: 16px 0 0;
  color: #ff8c7a;
}
.guest {
  margin-top: 28px;
  padding-top: 20px;
  border-top: 1px solid rgba(255, 255, 255, 0.08);
}
.guest .wide {
  min-width: 240px;
}
.hint {
  margin: 10px auto 0;
  max-width: 460px;
  font-size: 13px;
  opacity: 0.65;
}
</style>
