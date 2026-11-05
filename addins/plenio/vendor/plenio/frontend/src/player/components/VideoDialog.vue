<script setup lang="ts">
/**
 * Save a song as a video (owner's request 2026-10-16): the size (also square and upright), the frame rate,
 * the part of the song, the visual (or a new one at every section), the colours, the lyrics (subtitles or
 * karaoke), the notation following the music, a title card, the song in a corner, a progress bar, the credit,
 * the take - a preview frame to see it. *Make the video* puts it in the queue (owner's request 2026-10-18: in
 * the background): the dialog shows how far it is with a live picture, and may be closed - it goes on, under
 * *In the making*. Another video with other settings can follow at once.
 *
 * The visuals over the video's time (owner's request 2026-10-25): one all the way, a new one at every section or
 * every so many seconds, each chosen in a gallery of little windows playing to the song, or at random
 * (VisualTimeline.vue) - kept per song; and more looks (video/looks.ts).
 */
import { computed, onBeforeUnmount, onMounted, reactive, ref, shallowRef, watch } from 'vue'

import { api, type SongDetail, type SongSummary } from '../api'
import { frameWatchers, jobs, progressOf, progressText, queueVideo, stopJob } from '../jobs'
import { COLORS, EFFECTS, FONTS, lyricsWithDefaults } from '../lyricsStyle'
import { LYRICS_VERSIONS, sungOf, versionFor } from '../lyricsVersion'
import { go, settings } from '../store'
import { formatTime, sectionName, sectionsInSong, songAnchors } from '../timing'
import type { Scheme } from '../visuals/presets'
import { FADE_STYLES } from '../visuals/mixer'
import { AUDIO_RATES, BITRATE_LIMITS, COVER_PLACES, KEYFRAMES, QUALITIES, SIZES, preview, soundOf, videoBitrate, videoSize, videoWithDefaults, type VideoOptions } from '../video/make'
import { ENTRANCES } from '../video/overlay'
import { PreviewMaker } from '../video/previews'
import { media } from '../api'
import Icon from './Icon.vue'
import VisualTimeline from './VisualTimeline.vue'

const props = defineProps<{ song: SongSummary }>()
const emit = defineEmits<{ close: [] }>()

const options = reactive<VideoOptions>(videoWithDefaults(settings.video, settings.lyrics))
/** The plans of the songs made into videos before (song id -> when the visual changes, and the visuals chosen). */
type Plan = Pick<VideoOptions, 'change' | 'interval' | 'picks' | 'seed'>
const plans = (): Record<string, Plan> => {
  const raw = settings.video.plans
  return raw && typeof raw === 'object' ? (raw as Record<string, Plan>) : {}
}
{
  const kept = plans()[props.song.id]
  if (kept) Object.assign(options, videoWithDefaults({ ...options, ...kept }, options.lyricsStyle, options.lyricsVersion), { start: 0, length: 0 })
  else options.seed = Math.floor(Math.random() * 2 ** 31)
}
/** The little moving previews of the visuals with this song (made when its sound is read). */
const maker = shallowRef<PreviewMaker | null>(null)
const detail = ref<SongDetail | null>(null)
const shot = ref<HTMLDivElement | null>(null)
const error = ref('')
const previewing = ref(false)
/** The videos this dialog put in the queue; the last one's progress shows here. */
const mine = ref<string[]>([])
const job = computed(() => jobs.value.find((j) => j.id === mine.value[mine.value.length - 1]) ?? null)
const waiting = computed(() => mine.value.filter((id) => jobs.value.find((j) => j.id === id)?.state === 'waiting').length)

const sizeId = computed({
  get: () => SIZES.find((s) => s.width === options.width && s.height === options.height)?.id ?? '1080p',
  set: (id: string) => {
    const size = SIZES.find((s) => s.id === id) ?? SIZES[0]
    options.width = size.width
    options.height = size.height
  },
})
const SCHEMES: [Scheme, string][] = [
  ['song', 'The song’s colours'],
  ['winamp', 'Winamp classic'],
  ['neon', 'Neon'],
  ['sunset', 'Sunset'],
  ['mono', 'Monochrome'],
]
const hasLines = computed(() => (detail.value?.lines.length ?? 0) > 0)
const hasSung = computed(() => !!sungOf(detail.value))
const PLACE_NAMES: Record<string, string> = { 'top-left': 'top left', top: 'top', 'top-right': 'top right', left: 'left', center: 'in the middle', right: 'right', 'bottom-left': 'bottom left', bottom: 'bottom', 'bottom-right': 'bottom right', drift: 'drifting slowly' }
const usesDrop = computed(() => !options.visual || options.visual.startsWith('drop-') || options.visual.startsWith('my-'))
/** The song's sections on its time line (the plan's slots). */
const timed = computed(() => {
  const d = detail.value
  return d ? sectionsInSong(d.notation.sections, songAnchors(d.lines, d.notation), d.notation.warp, duration.value || Infinity) : []
})
const wide = computed(() => options.width >= options.height * 1.3)
const hasNotation = computed(() => !!detail.value?.notation.abc)
const sections = computed(() => {
  const d = detail.value
  if (!d?.notation.sections?.length) return []
  return d.notation.sections
})
const duration = computed(() => props.song.seconds || detail.value?.seconds || 0)
const end = computed({
  get: () => (options.length > 0 ? options.start + options.length : duration.value),
  set: (value: number) => (options.length = Math.max(0, Math.min(duration.value, value) - options.start)),
})
const partLength = computed(() => (options.length > 0 ? options.length : Math.max(0, duration.value - options.start)))
const estimate = computed(() => videoSize(options, partLength.value) / 2 ** 20)
/** What the quality chosen means: the video's rate, and how large a minute of it gets. */
const rateText = computed(() => {
  const mbit = videoBitrate(options) / 1e6
  const constant = options.quality === 'custom' && options.constant
  const minute = videoSize(options, 60) / 2 ** 20
  return `${mbit >= 10 ? Math.round(mbit) : mbit.toFixed(1)} Mbit/s ${constant ? 'all the way' : 'aimed at, less where little moves'} · about ${Math.max(1, Math.round(minute))} MB a minute`
})
const FPS_CHOICES: [number, string][] = [
  [24, '24 a second - like a film'],
  [25, '25 a second'],
  [30, '30 a second'],
  [50, '50 a second - smoother'],
  [60, '60 a second - the smoothest, larger'],
]

function remember(): void {
  // which lyrics belongs to the song (its page, the player bar), not to every video; the visuals chosen belong to
  // the song too (its sections): kept per song, the last 40
  const { start: _s, length: _l, lyricsVersion: _v, picks, seed, ...kept } = options
  const others = Object.entries(plans()).filter(([id]) => id !== props.song.id).slice(-39)
  settings.video = { ...kept, plans: Object.fromEntries([...others, [props.song.id, { change: options.change, interval: options.interval, picks: [...picks], seed }]]) }
}
watch(options, remember, { deep: true })

async function look(): Promise<void> {
  if (!detail.value || previewing.value) return
  previewing.value = true
  error.value = ''
  try {
    const at = Math.min(duration.value - 0.1, options.start + Math.min(partLength.value * 0.4, 40))
    const canvas = await preview(props.song, detail.value, { ...options }, at, 720)
    show(canvas)
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    previewing.value = false
  }
}
function show(canvas: HTMLCanvasElement): void {
  if (!shot.value) return
  // a still copy (the canvas goes on drawing the next frames)
  const copy = document.createElement('canvas')
  copy.width = Math.min(720, canvas.width)
  copy.height = Math.round((copy.width / canvas.width) * canvas.height)
  copy.getContext('2d')?.drawImage(canvas, 0, 0, copy.width, copy.height)
  shot.value.replaceChildren(copy)
}

/** Put the video, as set now, in the queue; its frames show here while the dialog is open. */
function make(): void {
  error.value = ''
  const queued = queueVideo(props.song, { ...options, length: partLength.value })
  for (const id of mine.value) frameWatchers.delete(id)
  frameWatchers.set(queued.id, show)
  mine.value = [...mine.value, queued.id]
}
/** The videos folder in the file manager, the video chosen; a failure is said, not swallowed. */
async function showFolder(file: string): Promise<void> {
  try {
    await api.openVideos(file)
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  }
}
function cancel(): void {
  if (job.value) void stopJob(job.value)
}
/** Closing does not stop the video: it goes on in the background. */
function close(): void {
  emit('close')
}
function part(at: number, until: number): void {
  options.start = Math.max(0, at)
  options.length = Math.max(1, until - at)
}
const sizeText = (bytes: number): string => (bytes > 2 ** 30 ? `${(bytes / 2 ** 30).toFixed(1)} GB` : `${Math.max(1, Math.round(bytes / 2 ** 20))} MB`)

/** The previews' maker for the song as set (its sound, the video's shape, the colours). */
async function makePreviews(): Promise<void> {
  const d = detail.value
  if (!d) return
  try {
    const sound = await soundOf(props.song, options.take)
    const cover = props.song.has.cover ? await loadCover() : null
    maker.value?.stop()
    maker.value = new PreviewMaker(props.song, d, sound, options.width / options.height, options.scheme, cover, settings.visuals.sensitivity * options.look.reactivity)
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  }
}
let coverImage: Promise<HTMLImageElement | null> | null = null
function loadCover(): Promise<HTMLImageElement | null> {
  coverImage ??= new Promise((resolve) => {
    const img = new Image()
    img.onload = () => resolve(img)
    img.onerror = () => resolve(null)
    img.src = media(props.song.id, 'cover')
  })
  return coverImage
}
watch(
  () => [options.take, options.scheme, options.width / options.height, options.look.reactivity],
  () => void makePreviews()
)

onMounted(async () => {
  try {
    detail.value = await api.song(props.song.id)
    options.lyricsVersion = versionFor(detail.value, settings)
    if (!detail.value.lines.length && options.lyrics !== 'off') options.lyrics = 'off'
    if (!detail.value.notation.abc) options.notation = false
    if (options.take === 'original' && !props.song.has.original) options.take = 'master'
    if (options.change === 'section' && !detail.value.notation.sections?.length) options.change = 'never'
    void look()
    void makePreviews()
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  }
})
onBeforeUnmount(() => {
  for (const id of mine.value) frameWatchers.delete(id)
  maker.value?.stop()
})
</script>

<template>
  <div class="veil" @click.self="close">
    <div class="dialog" role="dialog" aria-label="Save as a video">
      <header>
        <h3><Icon name="layers" /> Save “{{ song.title }}” as a video</h3>
        <button class="icon-btn" title="Close" @click="close"><Icon name="close" /></button>
      </header>
      <div class="body">
        <div class="left">
          <div ref="shot" class="shot" :style="{ aspectRatio: `${options.width} / ${options.height}` }"><p class="placeholder">The preview shows here.</p></div>
          <button class="ghost small" :disabled="previewing || !detail" @click="look"><Icon name="refresh" :size="14" /> {{ previewing ? 'Drawing …' : 'Preview' }}</button>
          <div v-if="job && (job.state === 'working' || job.state === 'waiting')" class="progress">
            <p><b>{{ progressText(job) }}</b></p>
            <div class="bar"><i :style="{ width: `${Math.max(3, progressOf(job) * 100)}%` }" /></div>
            <p v-if="job.speed" class="hint">{{ job.speed.toFixed(1) }}× as fast as it plays · {{ formatTime(job.left) }} left</p>
            <p class="hint">It goes on in the background when you close this - see <a class="link" @click="close(); go('/jobs')">In the making</a>.<template v-if="waiting"> {{ waiting }} more of this song waiting.</template></p>
          </div>
          <p v-else-if="job?.state === 'stopped'" class="hint">Stopped.</p>
          <p v-else-if="job?.state === 'error'" class="error">{{ job.error }}</p>
          <div v-if="job?.state === 'done' && job.file" class="done">
            <p><Icon name="check" :size="16" /> Saved: <b>{{ job.file }}</b> ({{ sizeText(job.size ?? 0) }})</p>
            <div class="row">
              <a class="ghost small" :href="`/videos/${encodeURIComponent(job.file)}?download=1`" :download="job.file"><Icon name="download" :size="14" /> Download</a>
              <a class="ghost small" :href="`/videos/${encodeURIComponent(job.file)}`" target="_blank" rel="noopener"><Icon name="play" :size="14" /> Watch</a>
              <button class="ghost small" @click="showFolder(job.file)"><Icon name="folder" :size="14" /> Open the folder</button>
            </div>
            <p class="hint path">{{ job.folder }}</p>
          </div>
          <p v-if="error" class="error">{{ error }}</p>
        </div>

        <form class="right" @submit.prevent>
          <label>Size <select v-model="sizeId"><option v-for="s in SIZES" :key="s.id" :value="s.id">{{ s.label }}</option></select></label>
          <div class="row pair">
            <label>Frame rate <select v-model.number="options.fps"><option v-for="[fps, label] in FPS_CHOICES" :key="fps" :value="fps">{{ label }}</option></select></label>
            <label>Quality <select v-model="options.quality"><option v-for="q in QUALITIES" :key="q.id" :value="q.id">{{ q.label }}</option></select></label>
          </div>
          <div v-if="options.quality === 'custom'" class="row">
            <label class="inline">Bitrate <input v-model.number="options.bitrate" type="number" :min="BITRATE_LIMITS.min" :max="BITRATE_LIMITS.max" step="0.5" /> Mbit/s</label>
            <label class="check" title="Every second gets the same number of bits - for a platform that asks for a constant rate; otherwise a variable one gives quiet parts less and busy parts more"><input v-model="options.constant" type="checkbox" /> constant - the same all the way</label>
          </div>
          <p class="hint">{{ rateText }}</p>
          <details class="more">
            <summary>More about the encoding</summary>
            <div class="row pair">
              <label title="Between two full pictures only what changed is stored: closer ones jump better in a player, farther ones make a smaller file">A full picture every
                <select v-model.number="options.keyframes"><option v-for="s in KEYFRAMES" :key="s" :value="s">{{ s }} {{ s === 1 ? 'second' : 'seconds' }}</option></select>
              </label>
              <label title="The browser encodes on the graphics card where it can - usually the fastest; the processor's encoder is slower">Encoder
                <select v-model="options.encoder"><option value="auto">as the browser chooses</option><option value="hardware">the graphics card</option><option value="software">the processor</option></select>
              </label>
            </div>
            <label>Sound <select v-model.number="options.audio"><option v-for="rate in AUDIO_RATES" :key="rate" :value="rate">AAC, {{ rate }} kbit/s{{ rate === 192 ? ' (as before)' : rate === 320 ? ' - the best AAC' : '' }}</option></select></label>
          </details>

          <fieldset>
            <legend>The part</legend>
            <div class="row">
              <label class="inline">from <input v-model.number="options.start" type="number" min="0" :max="duration" step="1" /> s</label>
              <label class="inline">to <input v-model.number="end" type="number" min="1" :max="duration" step="1" /> s</label>
              <button class="link" type="button" @click="options.start = 0; options.length = 0">the whole song</button>
            </div>
            <div v-if="sections.length" class="chips">
              <button v-for="(s, i) in sections" :key="s.start" type="button" class="chip" @click="part(s.start, sections[i + 1]?.start ?? duration)">{{ sectionName(s.label) }}</button>
            </div>
            <p class="hint">{{ formatTime(options.start) }} - {{ formatTime(options.start + partLength) }} ({{ formatTime(partLength) }}){{ options.start > 0 || options.start + partLength < duration - 0.5 ? ', the sound fades in and out' : '' }}. Section times follow the score.</p>
          </fieldset>

          <fieldset>
            <legend>The visuals</legend>
            <VisualTimeline :song="song" :options="options" :sections="timed" :length="partLength" :maker="maker" />
            <div v-if="options.change !== 'never'" class="row">
              <label>Crossfade
                <select v-model="options.fade">
                  <option v-for="[id, label, hint] in FADE_STYLES" :key="id" :value="id" :title="hint">{{ label }}</option>
                </select>
              </label>
              <label v-if="options.fade !== 'cut'" class="inline">over <input v-model.number="options.fadeSeconds" type="range" min="0.5" max="8" step="0.5" /> {{ options.fadeSeconds }} s</label>
            </div>
            <label>Colours <select v-model="options.scheme"><option v-for="[id, label] in SCHEMES" :key="id" :value="id">{{ label }}</option></select></label>
            <label v-if="options.change !== 'never'" class="check"><input v-model="options.look.cycleColors" type="checkbox" /> other colours at every change of the visual</label>
          </fieldset>

          <fieldset>
            <legend>The look</legend>
            <label class="inline" title="The song's cover, blurred and slowly drifting, glows through the visual from behind">The cover behind the visual <input v-model.number="options.look.backdrop" type="range" min="0" max="1" step="0.05" :disabled="!song.has.cover" /> {{ options.look.backdrop ? `${Math.round(options.look.backdrop * 100)} %` : 'off' }}</label>
            <label class="inline" title="The picture grows a little on every beat and settles between them">Breathes with the beat <input v-model.number="options.look.zoom" type="range" min="0" max="1" step="0.05" /> {{ options.look.zoom ? `${Math.round(options.look.zoom * 100)} %` : 'off' }}</label>
            <label class="inline" title="How strongly the visuals react to the music">The visuals react <input v-model.number="options.look.reactivity" type="range" min="0.5" max="2" step="0.1" /> {{ options.look.reactivity.toFixed(1) }}×</label>
            <label class="inline" title="A film's grain over the picture">Film grain <input v-model.number="options.look.grain" type="range" min="0" max="1" step="0.05" /> {{ options.look.grain ? `${Math.round(options.look.grain * 100)} %` : 'off' }}</label>
            <div class="row">
              <label class="check"><input v-model="options.look.vignette" type="checkbox" /> darker corners</label>
              <label class="check" :title="wide ? 'Black bars above and below: a picture of 2.39:1' : 'For a wide video only'"><input v-model="options.look.bars" type="checkbox" :disabled="!wide" /> cinema bars</label>
              <label class="check"><input v-model="options.look.fades" type="checkbox" /> in from black, out to black</label>
            </div>
            <div class="row">
              <label class="check" :title="sections.length ? 'Verse, Chorus … in large letters for a moment as each section begins' : 'This song has no sections'"><input v-model="options.look.sections" type="checkbox" :disabled="!sections.length" /> the section’s name as it begins</label>
              <label class="check" title="The last seconds: the cover, the title, who made it"><input v-model="options.look.endCard" type="checkbox" /> an end card</label>
            </div>
          </fieldset>

          <fieldset>
            <legend>Over the visual</legend>
            <label>Lyrics
              <select v-model="options.lyrics" :disabled="!hasLines">
                <option value="off">none</option>
                <option value="subtitles">subtitles, lit up as they are sung</option>
                <option value="karaoke">karaoke - large, the lines before and after</option>
                <option value="words">word by word - each word large as it is sung</option>
              </select>
            </label>
            <label v-if="options.lyrics !== 'off' && hasSung">Which
              <select v-model="options.lyricsVersion">
                <option v-for="v in LYRICS_VERSIONS" :key="v.id" :value="v.id" :title="v.title">{{ v.label.toLowerCase() }}</option>
              </select>
            </label>
            <div v-if="options.lyrics !== 'off' && hasLines" class="row look">
              <label>Where
                <select v-model="options.lyricsPlace">
                  <option value="bottom">{{ options.lyrics === 'karaoke' ? 'in the middle' : 'at the bottom' }}</option>
                  <option value="middle">in the middle</option>
                  <option value="top">at the top</option>
                  <option value="random">a new place every line</option>
                </select>
              </label>
              <label v-if="options.lyrics !== 'words'">A line comes in
                <select v-model="options.lyricsIn">
                  <option v-for="[id, label] in ENTRANCES" :key="id" :value="id">{{ label }}</option>
                </select>
              </label>
              <label class="check beat" title="A line comes in in one beat of the song, and the lyrics pulse with the beat"><input v-model="options.onBeat" type="checkbox" /> on the beat</label>
            </div>
            <p v-if="detail && !hasLines" class="hint">This song has no timed lyrics.</p>
            <template v-if="options.lyrics !== 'off' && hasLines">
              <div class="row look">
                <label>Font
                  <select v-model="options.lyricsStyle.font">
                    <option v-for="f in FONTS" :key="f.id" :value="f.id" :style="{ fontFamily: f.stack }">{{ f.label }}</option>
                    <option value="own">Your own font…</option>
                  </select>
                </label>
                <label>Effect
                  <select v-model="options.lyricsStyle.effect">
                    <option v-for="e in EFFECTS" :key="e.id" :value="e.id" :title="e.blurb">{{ e.label }}</option>
                  </select>
                </label>
                <label>Colour
                  <select v-model="options.lyricsStyle.color">
                    <option v-for="c in COLORS" :key="c.id" :value="c.id">{{ c.label }}</option>
                  </select>
                </label>
              </div>
              <label v-if="options.lyricsStyle.font === 'own'" class="inline">Font name <input v-model.lazy="options.lyricsStyle.own" class="text" placeholder="an installed font" /></label>
              <label class="inline">Size <input v-model.number="options.lyricsStyle.size" type="range" min="0.7" max="1.6" step="0.05" /> {{ Math.round(options.lyricsStyle.size * 100) }} %</label>
              <button class="link" type="button" @click="options.lyricsStyle = lyricsWithDefaults(settings.lyrics)">as in the player</button>
            </template>
            <label class="check"><input v-model="options.notation" type="checkbox" :disabled="!hasNotation" /> the notation, following the music</label>
            <label class="check"><input v-model="options.title" type="checkbox" /> a title card at the start (with the cover)</label>
            <label class="check"><input v-model="options.cover.show" type="checkbox" :disabled="!song.has.cover" /> the cover, all the way through</label>
            <div v-if="options.cover.show && song.has.cover" class="row look">
              <label>Where
                <select v-model="options.cover.place">
                  <option v-for="place in COVER_PLACES" :key="place" :value="place">{{ PLACE_NAMES[place] }}</option>
                </select>
              </label>
              <label>Shape
                <select v-model="options.cover.shape">
                  <option value="rounded">rounded</option>
                  <option value="square">square</option>
                  <option value="round">round</option>
                  <option value="record">a spinning record</option>
                </select>
              </label>
              <label class="check beat"><input v-model="options.cover.pulse" type="checkbox" /> pulses with the beat</label>
            </div>
            <label v-if="options.cover.show && song.has.cover" class="inline">Size <input v-model.number="options.cover.size" type="range" min="0.08" max="0.6" step="0.01" /> {{ Math.round(options.cover.size * 100) }} %</label>
            <label class="check"><input v-model="options.corner" type="checkbox" /> the song in the corner</label>
            <label class="check"><input v-model="options.progress" type="checkbox" /> a progress bar with the sections</label>
            <label class="check"><input v-model="options.credit" type="checkbox" /> “made with Plenio”</label>
          </fieldset>

          <fieldset>
            <legend>Into the visual</legend>
            <p class="hint">{{ usesDrop ? 'Drawn into the visual’s smoke: they melt and swirl with it.' : 'Over this visual as a soft glow (a Plenio Drop visual melts them into its smoke).' }} Five Drop visuals draw the song by themselves: Cover Galaxy, Title Smoke, Lyric Tunnel, Album Kaleido, Cover Echo.</p>
            <div class="row">
              <label class="check"><input v-model="options.into.title" type="checkbox" /> the title at the start</label>
              <label class="check"><input v-model="options.into.lyrics" type="checkbox" :disabled="!hasLines" /> the line sung</label>
              <label class="check"><input v-model="options.into.cover" type="checkbox" :disabled="!song.has.cover" /> the cover</label>
            </div>
          </fieldset>

          <label v-if="song.has.original">Sound <select v-model="options.take"><option value="master">the master</option><option value="original">the unmastered take</option></select></label>
        </form>
      </div>
      <footer>
        <span class="hint">MP4 (H.264, AAC {{ options.audio }} kbit/s) · about {{ Math.max(1, Math.round(estimate)) }} MB · saved in the player’s videos folder · made in the background</span>
        <button v-if="job && (job.state === 'working' || job.state === 'waiting')" class="ghost" @click="cancel">Stop</button>
        <button class="primary" :disabled="!detail" :title="job && (job.state === 'working' || job.state === 'waiting') ? 'Another video of this song, with the settings as they are now, after the one being made' : ''" @click="make"><Icon name="download" :size="16" /> {{ job && (job.state === 'working' || job.state === 'waiting') ? 'Make another' : 'Make the video' }}</button>
      </footer>
    </div>
  </div>
</template>

<style scoped>
.veil {
  position: fixed;
  inset: 0;
  z-index: 80;
  display: grid;
  place-items: center;
  background: rgba(0, 0, 0, 0.6);
}
.dialog {
  width: min(1180px, 96vw);
  max-height: 94vh;
  display: flex;
  flex-direction: column;
  border-radius: 18px;
  background: #13101c;
  border: 1px solid rgba(255, 255, 255, 0.1);
  box-shadow: 0 30px 90px rgba(0, 0, 0, 0.7);
}
header,
footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 14px 20px;
}
header {
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
}
footer {
  border-top: 1px solid rgba(255, 255, 255, 0.06);
}
h3 {
  display: flex;
  gap: 8px;
  align-items: center;
  margin: 0;
}
.body {
  display: grid;
  grid-template-columns: minmax(0, 1.25fr) minmax(320px, 1fr);
  gap: 22px;
  padding: 18px 20px;
  overflow-y: auto;
}
.left {
  display: grid;
  gap: 10px;
  align-content: start;
}
.shot {
  display: grid;
  place-items: center;
  max-height: 52vh;
  margin: 0 auto;
  width: 100%;
  border-radius: 12px;
  overflow: hidden;
  background: #05040a;
  border: 1px solid rgba(255, 255, 255, 0.08);
}
.shot :deep(canvas) {
  width: 100%;
  height: 100%;
  object-fit: contain;
}
.placeholder {
  color: var(--muted);
}
.right {
  display: grid;
  gap: 10px;
  align-content: start;
  font-size: 13px;
}
label {
  display: grid;
  gap: 4px;
  color: var(--muted);
}
label.check,
label.inline {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #ddd;
}
fieldset {
  display: grid;
  gap: 8px;
  margin: 0;
  padding: 10px 12px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 12px;
}
legend {
  padding: 0 6px;
  color: #fff;
  font-weight: 600;
}
select,
input[type='number'] {
  background: rgba(255, 255, 255, 0.06);
  color: #fff;
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 8px;
  padding: 6px 8px;
  font: 13px var(--font);
}
input[type='number'] {
  width: 80px;
}
input.text {
  flex: 1;
  background: rgba(255, 255, 255, 0.06);
  color: #fff;
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 8px;
  padding: 6px 8px;
  font: 13px var(--font);
}
.look {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  gap: 8px;
}
.look .beat {
  align-self: end;
  padding-bottom: 6px;
}
.pair {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
  align-items: end;
}
details.more {
  display: grid;
  gap: 8px;
  padding: 8px 12px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 12px;
}
details.more summary {
  cursor: pointer;
  color: #ddd;
}
details.more[open] summary {
  margin-bottom: 6px;
}
input[type='range'] {
  flex: 1;
  accent-color: var(--accent);
}
input[type='checkbox'] {
  accent-color: var(--accent);
}
.row {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
}
.chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.link {
  background: none;
  border: 0;
  color: var(--accent);
  cursor: pointer;
  padding: 0;
  font: 13px var(--font);
}
.hint {
  color: var(--muted);
  font-size: 12px;
  margin: 0;
}
.hint.path {
  word-break: break-all;
}
.progress p {
  margin: 0 0 6px;
}
.bar {
  height: 8px;
  border-radius: 99px;
  background: rgba(255, 255, 255, 0.08);
  overflow: hidden;
}
.bar i {
  display: block;
  height: 100%;
  background: var(--accent);
  transition: width 0.3s;
}
.done p {
  display: flex;
  gap: 6px;
  align-items: center;
  margin: 0 0 8px;
}
.error {
  color: #ff9a9a;
}
</style>
