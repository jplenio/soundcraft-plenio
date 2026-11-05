<script setup lang="ts">
/**
 * Help and the video tutorials (owner's request 2026-10-26): short guides by topic - searchable, each opened with a
 * click (``#/help/<topic>`` opens one) - and the narrated tutorials, played in a window over the page after a click
 * (nothing is loaded from YouTube before), with the keys at the end.
 */
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import { embedUrl, type HelpTopic, PLAYLIST, searchHelp, searchTutorials, type Tutorial, watchUrl } from '../help'
import { go, settings } from '../store'
import Icon from './Icon.vue'

const props = defineProps<{ topic?: string }>()

const query = ref('')
const open = ref<Set<string>>(new Set(props.topic ? [props.topic] : ['start']))
const watching = ref<Tutorial | null>(null)
const topics = computed(() => searchHelp(query.value))
const tutorials = computed(() => searchTutorials(query.value))
const groups = computed(() => [
  { title: 'The Plenio Player', items: tutorials.value.filter((t) => t.where !== 'comfyui') },
  { title: 'Making songs in ComfyUI', items: tutorials.value.filter((t) => t.where === 'comfyui') },
])
watch(query, (q) => {
  // a search opens every topic it finds
  if (q.trim()) open.value = new Set(topics.value.map((t) => t.id))
})

function toggle(id: string): void {
  const next = new Set(open.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  open.value = next
}

/** A guide's lines as paragraphs and lists (a run of lines that start with "- " is one list). */
function blocks(topic: HelpTopic): { list: boolean; lines: string[] }[] {
  const out: { list: boolean; lines: string[] }[] = []
  for (const line of topic.body) {
    const list = line.startsWith('- ')
    const last = out[out.length - 1]
    if (list && last?.list) last.lines.push(line.slice(2))
    else out.push({ list, lines: [list ? line.slice(2) : line] })
  }
  return out
}

/** **bold**, *italic* and `code` of a guide's line, as HTML (the texts are the player's own). */
function rich(line: string): string {
  const safe = line.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  return safe.replace(/\*\*([^*]+)\*\*/g, '<b>$1</b>').replace(/`([^`]+)`/g, '<code>$1</code>').replace(/\*([^*]+)\*/g, '<i>$1</i>')
}

const sections = ref<HTMLElement | null>(null)
/** Esc closes the video first (before the page's own keys see it). */
function onKey(event: KeyboardEvent): void {
  if (event.key !== 'Escape' || !watching.value) return
  event.stopImmediatePropagation()
  watching.value = null
}
onMounted(() => {
  window.addEventListener('keydown', onKey, true)
  if (!props.topic) return
  void nextTick(() => sections.value?.querySelector(`[data-topic="${CSS.escape(props.topic ?? '')}"]`)?.scrollIntoView({ block: 'start', behavior: 'smooth' }))
})
onBeforeUnmount(() => window.removeEventListener('keydown', onKey, true))

function dismissWelcome(): void {
  settings.welcomed = true
}
</script>

<template>
  <div class="help-page">
    <header class="hero">
      <div class="title">
        <span class="badge"><Icon name="help" :size="28" /></span>
        <div>
          <h1>Help &amp; tutorials</h1>
          <p>Short guides, and every tutorial as a video - recorded with the real models.</p>
        </div>
      </div>
      <label class="search">
        <Icon name="search" :size="18" />
        <input v-model="query" type="search" placeholder="Search the help - lyrics, party, filters, video …" aria-label="Search the help" />
      </label>
    </header>

    <section class="videos" aria-label="Video tutorials">
      <template v-for="group in groups" :key="group.title">
        <h2 v-if="group.items.length">{{ group.title }}</h2>
        <div v-if="group.items.length" class="shelf">
          <button v-for="t in group.items" :key="t.id" class="video" :class="t.where" :title="`Play “${t.title}” here (from YouTube)`" @click="watching = t">
            <span class="poster">
              <span class="num">{{ t.number }}</span>
              <span class="play"><Icon name="play" :size="22" /></span>
            </span>
            <b>{{ t.title }}</b>
            <small>{{ t.text }}</small>
          </button>
        </div>
      </template>
      <p class="note">
        The videos play from YouTube (youtube-nocookie.com) when you click one; nothing is loaded from there before.
        <a :href="PLAYLIST" target="_blank" rel="noopener">The whole playlist on YouTube ↗</a>
      </p>
    </section>

    <section ref="sections" class="guides" aria-label="Guides">
      <h2>Guides</h2>
      <p v-if="!topics.length" class="empty">Nothing found for “{{ query }}”. Try fewer words.</p>
      <article v-for="topic in topics" :key="topic.id" class="topic" :class="{ open: open.has(topic.id) }" :data-topic="topic.id">
        <button class="head" :aria-expanded="open.has(topic.id)" @click="toggle(topic.id)">
          <span class="ic"><Icon :name="topic.icon" :size="20" /></span>
          <span class="what"><b>{{ topic.title }}</b><small>{{ topic.lead }}</small></span>
          <Icon name="chevron" :size="18" class="chev" />
        </button>
        <div v-if="open.has(topic.id)" class="body">
          <template v-for="(block, k) in blocks(topic)" :key="k">
            <ul v-if="block.list"><li v-for="(item, n) in block.lines" :key="n" v-html="rich(item)" /></ul>
            <p v-else v-html="rich(block.lines[0])" />
          </template>
          <p class="links">
            <a v-if="topic.more" :href="topic.more" target="_blank" rel="noopener">The full guide ↗</a>
            <button v-for="t in searchTutorials('').filter((x) => x.topic === topic.id).slice(0, 2)" :key="t.id" class="link" @click="watching = t"><Icon name="video" :size="15" /> {{ t.title }}</button>
          </p>
        </div>
      </article>
    </section>

    <p class="foot">
      <button class="ghost" @click="go('/')"><Icon name="music" :size="16" /> To the songs</button>
      <button v-if="!settings.welcomed" class="link" @click="dismissWelcome">Hide the welcome in the songs</button>
      <span>Keys on a computer: press <kbd>?</kbd> anywhere.</span>
    </p>

    <Transition name="fade">
      <div v-if="watching" class="theatre" role="dialog" aria-modal="true" :aria-label="watching.title" @click.self="watching = null">
        <div class="frame">
          <header>
            <b>{{ watching.number !== '★' ? `Tutorial ${watching.number} · ` : '' }}{{ watching.title }}</b>
            <a :href="watchUrl(watching.id)" target="_blank" rel="noopener">On YouTube ↗</a>
            <button class="icon-btn" title="Close (Esc)" @click="watching = null"><Icon name="close" /></button>
          </header>
          <iframe :src="embedUrl(watching.id)" :title="watching.title" allow="autoplay; encrypted-media; picture-in-picture; fullscreen" allowfullscreen referrerpolicy="strict-origin-when-cross-origin" />
        </div>
      </div>
    </Transition>
  </div>
</template>

<style scoped>
.help-page {
  padding: 26px 34px 60px;
  max-width: 1280px;
}
.hero {
  display: flex;
  flex-wrap: wrap;
  gap: 18px;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 26px;
}
.title {
  display: flex;
  gap: 16px;
  align-items: center;
}
.badge {
  display: grid;
  place-items: center;
  width: 56px;
  height: 56px;
  border-radius: 18px;
  color: #0b0a12;
  background: linear-gradient(135deg, var(--accent), var(--accent2));
  box-shadow: 0 10px 30px var(--glow);
}
h1 {
  margin: 0;
  font: 800 32px var(--font);
}
.title p {
  margin: 4px 0 0;
  color: var(--muted);
}
.search {
  flex: 1;
  max-width: 420px;
  min-width: 240px;
  display: flex;
  align-items: center;
  gap: 8px;
  height: 44px;
  padding: 0 14px;
  border-radius: 99px;
  background: rgba(255, 255, 255, 0.06);
  border: 1px solid rgba(255, 255, 255, 0.1);
  color: var(--muted);
}
.search:focus-within {
  border-color: var(--accent);
}
.search input {
  flex: 1;
  min-width: 0;
  border: 0;
  background: none;
  color: #fff;
  outline: none;
  font: 15px var(--font);
}
h2 {
  margin: 22px 0 12px;
  font: 700 13px var(--font);
  color: var(--muted);
  text-transform: uppercase;
  letter-spacing: 1px;
}
.shelf {
  display: grid;
  grid-auto-flow: column;
  grid-auto-columns: minmax(220px, 260px);
  gap: 14px;
  overflow-x: auto;
  padding: 4px 2px 14px;
  scroll-snap-type: x mandatory;
  -webkit-overflow-scrolling: touch;
}
.video {
  scroll-snap-align: start;
  display: grid;
  gap: 6px;
  align-content: start;
  padding: 0 0 12px;
  border: 1px solid rgba(255, 255, 255, 0.07);
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.03);
  color: #fff;
  text-align: left;
  cursor: pointer;
  overflow: hidden;
  transition: transform 0.25s cubic-bezier(0.2, 0.8, 0.2, 1), border-color 0.25s, box-shadow 0.25s;
}
.video:hover,
.video:focus-visible {
  transform: translateY(-4px);
  border-color: color-mix(in srgb, var(--accent) 60%, transparent);
  box-shadow: 0 16px 40px rgba(0, 0, 0, 0.4);
}
.poster {
  position: relative;
  display: grid;
  place-items: center;
  aspect-ratio: 16 / 9;
  margin-bottom: 4px;
  background:
    radial-gradient(circle at 25% 30%, color-mix(in srgb, var(--accent) 70%, transparent), transparent 55%),
    radial-gradient(circle at 80% 80%, color-mix(in srgb, var(--accent2) 60%, transparent), transparent 55%),
    linear-gradient(135deg, #1d1630, #0d0b16);
}
.video.comfyui .poster {
  background:
    radial-gradient(circle at 70% 25%, rgba(120, 190, 255, 0.55), transparent 55%),
    radial-gradient(circle at 20% 85%, color-mix(in srgb, var(--accent) 55%, transparent), transparent 55%),
    linear-gradient(135deg, #14202e, #0b0d16);
}
.num {
  font: 900 54px/1 var(--font);
  color: rgba(255, 255, 255, 0.9);
  text-shadow: 0 6px 30px rgba(0, 0, 0, 0.5);
}
.play {
  position: absolute;
  right: 12px;
  bottom: 12px;
  display: grid;
  place-items: center;
  width: 42px;
  height: 42px;
  border-radius: 50%;
  background: #fff;
  color: #0b0a12;
  transition: transform 0.2s;
}
.video:hover .play {
  transform: scale(1.1);
}
.video b,
.video small {
  padding: 0 14px;
}
.video b {
  font: 700 15px/1.3 var(--font);
}
.video small {
  color: var(--muted);
  font-size: 12.5px;
  line-height: 1.45;
}
.note {
  margin: 4px 0 0;
  color: var(--muted);
  font-size: 12px;
}
.note a,
.links a {
  color: var(--accent);
}
.guides {
  display: grid;
  gap: 10px;
  margin-top: 10px;
}
.topic {
  border-radius: 18px;
  border: 1px solid rgba(255, 255, 255, 0.07);
  background: rgba(255, 255, 255, 0.025);
  transition: border-color 0.25s, background 0.25s;
}
.topic.open {
  border-color: color-mix(in srgb, var(--accent) 40%, transparent);
  background: rgba(255, 255, 255, 0.045);
}
.head {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 14px 16px;
  border: 0;
  background: none;
  color: #fff;
  text-align: left;
  cursor: pointer;
}
.ic {
  display: grid;
  place-items: center;
  width: 38px;
  height: 38px;
  border-radius: 12px;
  flex: none;
  background: color-mix(in srgb, var(--accent) 22%, transparent);
  color: #fff;
}
.what {
  flex: 1;
  display: grid;
  min-width: 0;
}
.what b {
  font: 700 16px var(--font);
}
.what small {
  color: var(--muted);
  font-size: 13px;
}
.chev {
  transition: transform 0.25s;
  color: var(--muted);
}
.topic.open .chev {
  transform: rotate(180deg);
}
.body {
  padding: 0 20px 16px 68px;
  color: rgba(255, 255, 255, 0.86);
  line-height: 1.6;
  font-size: 14px;
  animation: open 0.3s ease-out;
}
.body p {
  margin: 0 0 10px;
}
.body ul {
  margin: 0 0 10px;
  padding-left: 18px;
}
.body :deep(code),
kbd {
  font: 12.5px var(--mono);
  background: rgba(255, 255, 255, 0.08);
  border-radius: 5px;
  padding: 1px 6px;
}
.links {
  display: flex;
  flex-wrap: wrap;
  gap: 14px;
  align-items: center;
}
.link {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  border: 0;
  background: none;
  padding: 0;
  color: var(--accent);
  font: 13px var(--font);
  cursor: pointer;
}
.empty {
  color: var(--muted);
}
.foot {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  align-items: center;
  margin-top: 28px;
  color: var(--muted);
  font-size: 13px;
}
.theatre {
  position: fixed;
  inset: 0;
  z-index: 95;
  display: grid;
  place-items: center;
  padding: 16px;
  background: rgba(0, 0, 0, 0.75);
  backdrop-filter: blur(8px);
}
.frame {
  width: min(1100px, 100%);
  border-radius: 18px;
  overflow: hidden;
  background: #000;
  box-shadow: 0 30px 90px rgba(0, 0, 0, 0.7);
  animation: open 0.35s cubic-bezier(0.2, 0.8, 0.2, 1);
}
.frame header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 8px 8px 16px;
  background: #121019;
}
.frame header b {
  flex: 1;
  min-width: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.frame header a {
  color: var(--accent);
  font-size: 13px;
  white-space: nowrap;
}
.frame iframe {
  display: block;
  width: 100%;
  aspect-ratio: 16 / 9;
  border: 0;
}
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.25s;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
@keyframes open {
  from {
    opacity: 0;
    transform: translateY(8px);
  }
}
@media (max-width: 700px) {
  .help-page {
    padding: 18px 16px 40px;
  }
  h1 {
    font-size: 26px;
  }
  .badge {
    width: 46px;
    height: 46px;
  }
  .search {
    max-width: none;
  }
  .shelf {
    grid-auto-columns: 78%;
  }
  .body {
    padding: 0 16px 14px 16px;
  }
}
</style>
