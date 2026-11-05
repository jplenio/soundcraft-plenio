<script setup lang="ts">
/**
 * Your songs in the making (owner's request 2026-10-25): in their order, each with what identifies it (its title
 * once made; before, its style, length and voice, and the start of its description) and where it is - ready (when,
 * ▶), being made (for how long, the stage, roughly when it is ready), in line (its place, roughly when) - with ↑ ↓,
 * Edit while it waits, and ✕ (out of the line, stopped, or off the list). A song waiting to be released (owner's request
 * 2026-10-29) plays here on one's own device - its maker hears it first and releases it or not; an admin approves it
 * or not.
 */
import Icon from '../components/Icon.vue'
import { progressOf, stateOf, timeOfDay, titleOf } from './form'
import type { MakeJob } from './form'

const props = defineProps<{
  jobs: MakeJob[]
  now: number
  /** The cover of a song made (``null``: none to show). */
  cover?: (job: MakeJob) => string | null
  /** Whose song it is shows (the admin's view of everybody's). */
  owners?: boolean
  /** ▶ for a song made (the player's page; the guests' phones have no sound). */
  playable?: boolean
  busy?: string
  /** Where a song waiting to be released is heard first. */
  listen?: (job: MakeJob) => string
}>()
const emit = defineEmits<{ edit: [job: MakeJob]; move: [job: MakeJob, by: -1 | 1]; remove: [job: MakeJob]; play: [job: MakeJob]; again: [job: MakeJob]; remake: [job: MakeJob]; release: [job: MakeJob]; discard: [job: MakeJob] }>()

const initials = (text: string): string =>
  text
    .replace(/[^\p{L}\p{N} ]/gu, '')
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((w) => w[0] ?? '')
    .join('')
    .toUpperCase() || '♪'
const removeTitle = (job: MakeJob): string =>
  job.status === 'waiting' ? 'Take it out of the line' : ['sending', 'queued', 'running'].includes(job.status) ? 'Stop making it' : 'Off the list (the song stays in the library)'
</script>

<template>
  <ol class="queue">
    <li v-for="job in props.jobs" :key="job.id" class="row" :class="[stateOf(job, now).tone, { mine: job.mine }]">
      <div class="art" :class="{ eq: job.status === 'running' }">
        <img v-if="job.status === 'done' && cover?.(job)" :src="cover(job) ?? ''" alt="" loading="lazy" />
        <template v-else-if="job.status === 'running'"><i /><i /><i /><i /></template>
        <b v-else-if="job.status === 'waiting' && job.position" class="place">{{ job.position }}</b>
        <span v-else class="letters">{{ initials(titleOf(job)) }}</span>
      </div>
      <div class="text">
        <p class="title" :title="titleOf(job)">
          <span v-if="job.kind === 'cover'" class="tag">cover</span>{{ titleOf(job) }}
        </p>
        <p v-if="job.description && job.status !== 'done'" class="desc">“{{ job.description }}”</p>
        <p class="meta">
          <template v-if="owners">{{ job.owner.name }}{{ job.owner.kind === 'guest' ? '' : ` (${job.owner.kind})` }} · </template>
          ordered {{ timeOfDay(job.created) }}<template v-if="job.result?.title && job.status === 'done'"> · {{ job.label }}</template>
        </p>
        <div v-if="job.status === 'running'" class="bar" :title="`about ${Math.round(job.estimate / 60)} minutes for this song`"><i :style="{ width: `${progressOf(job, now) * 100}%` }" /></div>
      </div>
      <div class="state">
        <b>{{ stateOf(job, now).title }}</b>
        <small>{{ stateOf(job, now).detail }}</small>
      </div>
      <div class="tools">
        <button v-if="playable && job.status === 'done' && job.result?.song" class="icon-btn play" title="Play it now" @click="emit('play', job)"><Icon name="play" :size="16" /></button>
        <button v-if="job.status === 'done' && job.result?.song" class="icon-btn again" title="Again… - a new take of it, a new song like it, or a cover of it" @click="emit('remake', job)"><Icon name="wand" :size="16" /></button>
        <button v-if="job.status === 'failed' && job.can.edit !== undefined && job.fields" class="icon-btn" title="Try it again" :disabled="busy === job.id" @click="emit('again', job)"><Icon name="refresh" :size="16" /></button>
        <template v-if="job.status === 'waiting'">
          <button class="icon-btn" title="Earlier (past your next song)" :disabled="!job.can.up || busy === job.id" @click="emit('move', job, -1)"><Icon name="up" :size="16" /></button>
          <button class="icon-btn" title="Later (past your next song)" :disabled="!job.can.down || busy === job.id" @click="emit('move', job, 1)"><Icon name="down" :size="16" /></button>
          <button class="icon-btn" title="Change it - while it waits" :disabled="!job.can.edit || busy === job.id" @click="emit('edit', job)"><Icon name="edit" :size="16" /></button>
        </template>
        <button v-if="job.can.delete" class="icon-btn" :title="removeTitle(job)" :disabled="busy === job.id" @click="emit('remove', job)"><Icon name="close" :size="16" /></button>
      </div>
      <div v-if="job.can.listen && listen" class="hear">
        <audio controls preload="none" :src="listen(job)" />
        <button v-if="job.can.release" class="primary small" :disabled="busy === job.id" :title="job.release === 'admin' ? 'Everybody hears it: it joins the songs - and the party' : 'It joins the songs - or waits for an admin’s approval where the host asks for it'" @click="emit('release', job)"><Icon name="check" :size="15" /> {{ job.release === 'admin' ? 'Approve' : 'Release it' }}</button>
        <button v-if="job.can.discard" class="ghost small" :disabled="busy === job.id" title="Nobody else hears it: it is kept aside, nothing is deleted" @click="emit('discard', job)">{{ job.release === 'admin' ? 'Reject' : 'Don’t release' }}</button>
      </div>
    </li>
  </ol>
</template>

<style scoped>
.queue {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: 8px;
  container-type: inline-size;
}
.row {
  display: grid;
  grid-template-columns: 52px minmax(0, 1fr) minmax(110px, auto) auto;
  gap: 12px;
  align-items: center;
  padding: 10px 12px;
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.07);
}
.hear {
  grid-column: 1 / -1;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}
.hear audio {
  flex: 1 1 220px;
  min-width: 0;
  height: 36px;
}
.row.busy {
  border-color: color-mix(in srgb, var(--accent) 55%, transparent);
  background: linear-gradient(110deg, color-mix(in srgb, var(--accent) 16%, transparent), rgba(255, 255, 255, 0.03));
}
.row.done {
  border-color: rgba(79, 191, 127, 0.35);
}
.row.bad {
  border-color: rgba(255, 120, 120, 0.35);
}
.row.off {
  opacity: 0.6;
}
.art {
  width: 52px;
  height: 52px;
  border-radius: 12px;
  overflow: hidden;
  display: grid;
  place-items: center;
  background: linear-gradient(135deg, color-mix(in srgb, var(--accent) 55%, #1a1528), color-mix(in srgb, var(--accent2) 45%, #1a1528));
}
.art img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.art .place {
  font: 800 20px var(--font);
}
.art .letters {
  font: 800 15px var(--font);
  opacity: 0.85;
}
.art.eq {
  display: flex;
  align-items: flex-end;
  justify-content: center;
  gap: 3px;
  padding-bottom: 12px;
}
.art.eq i {
  width: 5px;
  height: 26px;
  border-radius: 3px;
  background: #fff;
  transform-origin: bottom;
  animation: eq 0.9s ease-in-out infinite;
}
.art.eq i:nth-child(2) {
  animation-delay: -0.25s;
}
.art.eq i:nth-child(3) {
  animation-delay: -0.5s;
}
.art.eq i:nth-child(4) {
  animation-delay: -0.7s;
}
@keyframes eq {
  0%,
  100% {
    transform: scaleY(0.25);
  }
  50% {
    transform: scaleY(1);
  }
}
.text {
  min-width: 0;
}
.text p {
  margin: 0;
}
.title {
  font-weight: 650;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.tag {
  display: inline-block;
  margin-right: 6px;
  padding: 0 6px;
  border-radius: 99px;
  background: rgba(255, 255, 255, 0.1);
  font-size: 10.5px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  vertical-align: 1px;
}
.desc {
  color: rgba(255, 255, 255, 0.62);
  font-size: 12.5px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.meta {
  color: var(--muted);
  font-size: 11.5px;
}
.bar {
  margin-top: 6px;
  height: 5px;
  border-radius: 99px;
  background: rgba(255, 255, 255, 0.1);
  overflow: hidden;
}
.bar i {
  display: block;
  height: 100%;
  background: linear-gradient(90deg, var(--accent), var(--accent2));
  transition: width 1s linear;
}
.state {
  display: grid;
  text-align: right;
}
.state b {
  font-size: 13px;
}
.state small {
  color: var(--muted);
  font-size: 11.5px;
}
.row.done .state b {
  color: #7fe0a6;
}
.row.bad .state b {
  color: #ff9a9a;
}
.tools {
  display: flex;
  gap: 2px;
}
.play {
  background: var(--accent);
  color: #0b0a12;
}
.again {
  color: var(--accent);
}
/* a narrow list (beside the form, or a phone): the state under the song */
@container (max-width: 620px) {
  .row {
    grid-template-columns: 44px minmax(0, 1fr) auto;
    grid-template-areas: 'art text tools' 'art state state';
  }
  .art {
    grid-area: art;
    width: 44px;
    height: 44px;
  }
  .text {
    grid-area: text;
  }
  .tools {
    grid-area: tools;
  }
  .state {
    grid-area: state;
    text-align: left;
    display: flex;
    gap: 8px;
    align-items: baseline;
    flex-wrap: wrap;
  }
}
</style>
