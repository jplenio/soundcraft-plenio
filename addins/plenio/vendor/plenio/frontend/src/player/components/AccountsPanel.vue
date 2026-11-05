<script setup lang="ts">
/**
 * Settings · Accounts (owner's request 2026-10-23): your picture and password; for the admin also the users -
 * set one up, give a new password, rename, remove - and each one's group (owner's request 2026-10-29): listens,
 * makes songs, or admin (a helper with the admin's rights). A guest is told where their things stay.
 */
import { onMounted, ref } from 'vue'

import { type Account, type Group, GROUPS, addUser, avatarUrl, canAdmin, changeUser, guest, initials, listUsers, me, removeUser, setAvatar, switchUser } from '../account'
import { say } from '../store'
import Icon from './Icon.vue'

const users = ref<Account[]>([])
const name = ref('')
const password = ref('')
const group = ref<Group>('maker')
const mine = ref('')
const busy = ref(false)
const error = ref('')

async function refresh(): Promise<void> {
  if (canAdmin.value) users.value = await listUsers().catch(() => [])
}
onMounted(refresh)

async function act(step: () => Promise<unknown>, done = ''): Promise<void> {
  busy.value = true
  error.value = ''
  try {
    await step()
    await refresh()
    if (done) say(done)
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    busy.value = false
  }
}

function picked(account: Account, event: Event): void {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (file) void act(() => setAvatar(account.id, file), 'Picture saved')
}

function create(): void {
  void act(async () => {
    await addUser(name.value, password.value, group.value)
    name.value = ''
    password.value = ''
  }, 'User set up')
}

function setGroup(account: Account, next: Group): void {
  const label = GROUPS.find(([id]) => id === next)?.[1] ?? next
  void act(() => changeUser(account.id, { group: next }), `${account.name}: ${label.toLowerCase()}`)
}

/** What a user may, said under their name. */
const groupOf = (account: Account): string => (account.admin ? 'admin · this computer' : account.helper ? 'admin · a helper' : GROUPS.find(([id]) => id === (account.group ?? 'maker'))?.[1].toLowerCase() ?? '')

function newPassword(account: Account): void {
  const next = window.prompt(`A new password for ${account.name} (at least 4 characters):`)
  if (next) void act(() => changeUser(account.id, { password: next }), `${account.name} has a new password`)
}

function rename(account: Account): void {
  const next = window.prompt('The new name:', account.name)
  if (next && next.trim() !== account.name) void act(() => changeUser(account.id, { name: next.trim() }))
}

function remove(account: Account): void {
  if (window.confirm(`Remove ${account.name}? Their playlists, likes, plays and settings are deleted with them.`)) {
    void act(() => removeUser(account.id), `${account.name} removed`)
  }
}

function changeMine(): void {
  if (!me.value) return
  const account = me.value
  void act(async () => {
    await changeUser(account.id, { password: mine.value })
    mine.value = ''
  }, 'Your password is changed')
}
</script>

<template>
  <div class="accounts">
    <template v-if="guest || !me">
      <p class="lead">You listen as a <b>guest</b>: your playlists, likes and plays stay in this browser only. With an account (the admin sets it up on the player’s computer) they are the same on every device.</p>
      <button class="ghost small" @click="switchUser"><Icon name="user" :size="14" /> Log in…</button>
    </template>

    <template v-else>
      <div class="me">
        <label class="face big" :style="{ background: me.color }" title="Choose a picture">
          <img v-if="me.avatar" :src="avatarUrl(me)" alt="" />
          <template v-else>{{ initials(me.name) }}</template>
          <input type="file" accept="image/*" :disabled="busy" @change="picked(me, $event)" />
          <span class="edit"><Icon name="edit" :size="13" /></span>
        </label>
        <div>
          <p class="who">{{ me.name }} <small>{{ groupOf(me) }}</small></p>
          <p class="hint">{{ me.admin ? 'The player’s own playlists, likes and settings - and the users below.' : me.helper ? 'Your playlists, likes and plays, the same on every device - and the admin’s rights: the users below, approvals, the party’s settings.' : 'Your playlists, likes and plays: the same on every device you log in on.' }}</p>
          <div class="row">
            <button v-if="me.avatar" class="ghost small" :disabled="busy" @click="act(() => setAvatar(me!.id, null))">Remove the picture</button>
            <button class="ghost small" :disabled="busy" @click="rename(me)">Rename</button>
            <button class="ghost small" :disabled="busy" @click="switchUser"><Icon name="logout" :size="14" /> Log out</button>
          </div>
          <form v-if="!me.admin" class="row" @submit.prevent="changeMine">
            <input v-model="mine" type="password" autocomplete="new-password" placeholder="New password" />
            <button class="ghost small" :disabled="busy || mine.length < 4">Change the password</button>
          </form>
        </div>
      </div>

      <template v-if="canAdmin">
        <h4>Users</h4>
        <p class="hint">Each user <b>listens</b>, also <b>makes songs</b> (when the party’s settings let users make them), or is an <b>admin</b> - a helper with your rights, from any device, to step in when needed: approve songs, set up users, change the party’s settings.</p>
        <ul class="users">
          <li v-for="u in users" :key="u.id">
            <label class="face" :style="{ background: u.color }" title="Choose a picture">
              <img v-if="u.avatar" :src="avatarUrl(u)" alt="" />
              <template v-else>{{ initials(u.name) }}</template>
              <input type="file" accept="image/*" :disabled="busy" @change="picked(u, $event)" />
            </label>
            <span class="name">{{ u.name }} <small v-if="u.last_login">last in {{ new Date(u.last_login * 1000).toLocaleDateString() }}</small></span>
            <select class="group" :value="u.group ?? 'maker'" :disabled="busy || u.id === me.id" :title="u.id === me.id ? 'Your own group: another admin changes it' : GROUPS.find(([id]) => id === (u.group ?? 'maker'))?.[2]" @change="setGroup(u, ($event.target as HTMLSelectElement).value as Group)">
              <option v-for="[id, label, hint] in GROUPS" :key="id" :value="id" :title="hint">{{ label }}</option>
            </select>
            <button class="icon-btn" title="Rename" :disabled="busy" @click="rename(u)"><Icon name="edit" :size="15" /></button>
            <button class="ghost small" :disabled="busy" @click="newPassword(u)">New password</button>
            <button class="icon-btn" title="Remove the user and their things" :disabled="busy" @click="remove(u)"><Icon name="trash" :size="15" /></button>
          </li>
          <li v-if="!users.length" class="hint">No users yet. A user logs in from any device that opens the player (the network link) and keeps their own playlists, likes and plays.</li>
        </ul>
        <form class="row add" @submit.prevent="create">
          <input v-model="name" placeholder="Name" maxlength="40" autocomplete="off" />
          <input v-model="password" type="password" placeholder="Password (4 or more)" autocomplete="new-password" />
          <select v-model="group" class="group" title="What the new user may">
            <option v-for="[id, label, hint] in GROUPS" :key="id" :value="id" :title="hint">{{ label }}</option>
          </select>
          <button class="ghost small" :disabled="busy || !name.trim() || password.length < 4"><Icon name="plus" :size="14" /> Set up a user</button>
        </form>
      </template>
    </template>
    <p v-if="error" class="error">{{ error }}</p>
  </div>
</template>

<style scoped>
.accounts {
  display: grid;
  gap: 10px;
}
.me {
  display: flex;
  gap: 16px;
  align-items: flex-start;
}
.face {
  position: relative;
  flex: none;
  display: grid;
  place-items: center;
  width: 38px;
  height: 38px;
  border-radius: 50%;
  overflow: hidden;
  font: 700 14px var(--font);
  color: #fff;
  cursor: pointer;
}
.face.big {
  width: 72px;
  height: 72px;
  font-size: 24px;
}
.face img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.face input {
  display: none;
}
.face .edit {
  position: absolute;
  right: 6px;
  bottom: 6px;
  display: grid;
  place-items: center;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: rgba(0, 0, 0, 0.6);
}
.who {
  margin: 0;
  font-weight: 700;
  font-size: 16px;
}
.who small {
  font-weight: 400;
  opacity: 0.6;
}
.row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  margin-top: 8px;
}
.row input {
  padding: 6px 10px;
  border-radius: 8px;
  border: 1px solid rgba(255, 255, 255, 0.15);
  background: rgba(0, 0, 0, 0.3);
  color: #fff;
}
.users {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: 6px;
}
.users li {
  display: flex;
  align-items: center;
  gap: 10px;
}
.users .name {
  flex: 1;
  min-width: 0;
}
select.group {
  padding: 5px 8px;
  border-radius: 8px;
  border: 1px solid rgba(255, 255, 255, 0.12);
  background: rgba(255, 255, 255, 0.05);
  color: #fff;
  font: 12px var(--font);
}
.users .name small {
  opacity: 0.55;
  margin-left: 6px;
}
h4 {
  margin: 10px 0 0;
}
.error {
  color: #ff8c7a;
  margin: 0;
}
</style>
