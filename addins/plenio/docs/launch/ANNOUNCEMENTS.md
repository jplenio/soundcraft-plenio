# Announcing Plenio for SoundCraft 0.1.0-alpha

Ready-to-post texts for each channel, written in the owner's voice. Replace `<VIDEO>` with the teaser's
link once it is uploaded (YouTube, or the release asset), and post in the order of
[the launch plan](README.md). Images: `../media/social-preview.png` (1280 x 640) for link cards,
`../media/banner.png` for headers, the teaser for video posts.

Every text fits its channel: X 280 characters and Mastodon 500 (on both a link counts as 23), Bluesky 300,
Hacker News titles 80, YouTube titles 100, Product Hunt's tagline 60 and description 260. Where a post's
line breaks matter, it is in a code block: copy it as it is (GitHub's copy button keeps every line). The
other texts are paragraphs wrapped for reading.

Links used below:

- Repository: https://github.com/jplenio/soundcraft-plenio
- Release: https://github.com/jplenio/soundcraft-plenio/releases/tag/plenio-v0.1.0-alpha
- Tutorial: https://github.com/jplenio/soundcraft-plenio/blob/plenio-addin/addins/plenio/docs/TUTORIAL.md
- Plenio: https://github.com/jplenio/Plenio-Music-Production-System

Keep in every longer post: it is an **alpha**, it runs **locally** (ComfyUI and a 16 GB GPU), songs made
with YuE2 are **non-commercial** (CC BY-NC 4.0), and the fork is **independent** of the SoundCraft team.

---

## X / Twitter (a thread)

Post 1, then reply to it with 2 to 5. Better than the link in post 1: attach the teaser and leave the link
out, so X plays it in the timeline.

**1/5**

```text
Plenio comes to SoundCraft. 🎛️

Write your lyrics, pick a style, press Generate: a full song with vocals lands in an open-source DAW, with its lyrics, MIDI score, takes and stems on real tracks.

Alpha 0.1.0, free, runs on your own GPU.
<VIDEO>
```

**2/5**

```text
Every part of the song is something you can edit:
🎤 Lyrics: a clip per sung line
🎹 Melody, instrument line, chords as MIDI
🎚️ Each take on its own playlist
🥁 Stems: vocals, drums, bass, other, rest

Change a word or a note and Generate makes just that again.
```

**3/5**

```text
The hard part: AI renders don't keep a steady tempo. So the add-in finds every bar in the audio and gives the session a tempo change on each bar line.

The metronome stays on the music. Your own MIDI stays on the beat. The audio is never stretched.
```

**4/5**

```text
Covers too: select any recording, pick a style (late-night jazz, synthwave, folk …) and keep the original lyrics or write new ones.

And every song Plenio made in ComfyUI comes in from its FLAC, ready to edit.
```

**5/5**

```text
YuE2 + Plenio in my fork of SoundCraft (Rust). Windows tested, needs ComfyUI and a 16 GB GPU. Songs are non-commercial (CC BY-NC 4.0 models).

Code, tutorial, download 👇
https://github.com/jplenio/soundcraft-plenio

#AImusic #ComfyUI #RustLang #opensource
```

---

## Bluesky

```text
Plenio comes to SoundCraft 🎛️

Lyrics in, song out: YuE2 songs inside an open-source Rust DAW, with lyrics, MIDI score, takes and stems on real tracks. Bars measured from the audio, so the metronome stays in sync.

Alpha 0.1.0, local, free:
https://github.com/jplenio/soundcraft-plenio
```

---

## Mastodon

```text
Plenio comes to SoundCraft (alpha 0.1.0) 🎛️

My Plenio Music Production System now lives in SoundCraft, the open-source Rust DAW:

• pick a style, write lyrics, Generate
• the song lands as tracks: lyrics, takes, MIDI score, stems
• every bar is measured in the audio, so the metronome stays in time
• change a word or a note and make just that again

Runs locally (ComfyUI, 16 GB GPU). YuE2 songs are non-commercial (CC BY-NC 4.0).

https://github.com/jplenio/soundcraft-plenio

#AIMusic #ComfyUI #Rust #OpenSource
```

**Alt text for the teaser** (Mastodon, Bluesky, X):

A 72-second teaser set to the song "Plenio Comes to SoundCraft", made with the add-in, its lyrics shown as
they are sung. Screens of SoundCraft show the steps: write your words, pick one of 250 styles, the score as
MIDI, every take on its own playlist, press Generate, the song's lyrics, takes, score and stems on tracks,
stems in one click, the tempo following the audio bar by bar, and a cover of a recording in another style.

---

## LinkedIn

**Plenio comes to SoundCraft: AI songwriting inside an open-source DAW (alpha)**

Generative music tools usually hand you a finished audio file. Musicians need the parts.

Today I'm releasing the first alpha of the Plenio add-in for SoundCraft, the open-source digital audio
workstation written in Rust. You write lyrics (or a sentence about the song), pick one of 250 styles, and
press Generate. YuE2 composes and sings the song on your own computer, and SoundCraft receives it as a project
you can work with:

- the lyrics on a track, one clip per sung line
- the score as MIDI: melody, instrument line and chords
- every take on its own playlist
- the stems (vocals, drums, bass, other) on request or right away

The detail I'm proudest of: AI renders don't keep a steady tempo, so a fixed BPM drifts off within a few bars.
The add-in measures every bar in the audio and turns it into the session's tempo map. The metronome and any
MIDI you add stay on the music, and the audio itself is never stretched.

You can change a line of the lyrics, a note of the melody or the brief, and Generate makes exactly what the
change calls for. Covers of a recording in another style, and imports of songs made with Plenio in ComfyUI,
work the same way.

It's free and open source (MIT/Apache-2.0), runs locally with ComfyUI on a 16 GB GPU, and is an independent
fork. Songs made with the YuE2 models are for non-commercial use (CC BY-NC 4.0).

Teaser, tutorial and download: https://github.com/jplenio/soundcraft-plenio

#MusicTechnology #GenerativeAI #OpenSource #Rust #MusicProduction

---

## Reddit

Read each subreddit's rules before posting (self-promotion, AI content, flair). Post as a text post with
the video or a screenshot, and answer questions in the comments.

### r/comfyui

**Title:** Plenio (YuE2 songs) now runs inside a DAW: lyrics, MIDI score, takes and stems as tracks [alpha, open source]

Hi all, I'm the author of the Plenio Music Production System for ComfyUI. I've now built its YuE2 Song, YuE2
Cover and the Plenio Player into SoundCraft, an open-source DAW written in Rust.

How it works: the add-in starts its own ComfyUI instance with Plenio inside (it uses your installed ComfyUI
and models and leaves your setup alone) and talks to Plenio's Song API. The finished song lands in the DAW as
a folder track: lyrics clips where they're sung, each take on its own playlist, the score as MIDI, and the
stems from BS-RoFormer. Every bar is measured in the audio, so the session's tempo follows the render.

You can change the lyrics or the notes on the MIDI tracks and generate again; it sings your notes as written.
Covers and imports of Plenio FLACs work too.

Alpha 0.1.0, Windows tested, 16 GB GPU. YuE2 is CC BY-NC 4.0, so songs are non-commercial.

Repo, tutorial, teaser: https://github.com/jplenio/soundcraft-plenio

Happy to answer questions about the integration or the bar tracking.

### r/rust

**Title:** An AI songwriting add-in for SoundCraft, a pure-Rust DAW: egui UI extension, engine commands, a ComfyUI sidecar

I've been building an add-in for SoundCraft (the open-source DAW in Rust) that brings generated songs into the
session as ordinary tracks. Some things that might interest Rust folks:

- It lives entirely in its own crates (`addins/plenio/`) with three small seams in the host: extension data in
  the session, extension commands in the engine's registry, and a `UiExtension` trait for the egui UI.
  Upstream changes merge without touching the add-in.
- Everything the UI changes is a command with undo; the same ids work from the control channel and MCP.
- No panics in production code (`deny(clippy::unwrap_used, …)` on every crate root), hostile input bounded.
- The UI never blocks: a studio worker thread runs ComfyUI as a child process and talks HTTP to it; the UI
  polls events once a frame.
- The UI is tested offscreen with egui_kittest, and a "tour" example clicks through the real dialogs against a
  real studio and renders every screenshot of the docs.

Alpha, MIT/Apache-2.0: https://github.com/jplenio/soundcraft-plenio

### r/LocalLLaMA (or r/aimusic)

**Title:** Local AI songwriting in a DAW: YuE2 + Plenio inside SoundCraft, with lyrics, MIDI and stems on tracks

Everything runs on your own machine: a local writer model drafts the lyrics if you want, YuE2 (3B) composes
and sings, BS-RoFormer splits stems, and the result lands as editable tracks in an open-source DAW. 16 GB VRAM
is enough; a two-minute song takes three to six minutes on an RTX 5060 Ti.

Alpha, free, non-commercial models: https://github.com/jplenio/soundcraft-plenio

---

## Hacker News

**Title** (at most 80 characters): Show HN: Plenio – AI songs with editable lyrics, MIDI and stems in a Rust DAW

**URL:** https://github.com/jplenio/soundcraft-plenio

**Text:**

Plenio is a music production system for ComfyUI that I've been working on; this release builds it into
SoundCraft, an open-source DAW written in Rust (as an independent fork).

You write lyrics or an idea and pick a style. YuE2 renders the song locally, and the DAW gets the parts:
lyrics as clips where they're sung, the score as MIDI, each take on a playlist, stems on request. If you
change a line or a note, generating again makes only what changed (your notes are sung as written).

The part that took the most work: YuE2 renders don't keep a fixed tempo. So the add-in finds every bar in the
audio (onsets, the score's pitch classes, the sung words) and writes a tempo change per bar. On three test
songs, the best constant BPM put 37–58 % of the metronome's clicks within 15 ms of an onset and was up to
160–850 ms off; with the measured tempo map it is 75–93 %, median 2.6–7.2 ms. The metronome and added MIDI
stay in sync without stretching the audio.

It's an alpha (Windows tested, 16 GB GPU, ComfyUI required). The YuE2 models are CC BY-NC 4.0.

---

## Discord (ComfyUI, YuE and SoundCraft communities, #showcase or #projects)

```text
🎛️ **Plenio comes to SoundCraft** (alpha 0.1.0)
YuE2 songs and covers straight into an open-source DAW: lyrics clips, MIDI score, takes and stems on real tracks, tempo map measured from the audio. Local, free, MIT/Apache-2.0 (models CC BY-NC).
Teaser: <VIDEO> · Repo: https://github.com/jplenio/soundcraft-plenio
```

---

## YouTube

**Title:** Plenio comes to SoundCraft – AI songs with editable lyrics, MIDI and stems (alpha)

**Description:**

Write the words, generate the song: the Plenio Music Production System inside SoundCraft, the open-source DAW.
Every song lands as tracks you can edit: lyrics, takes, the score as MIDI, and stems.

The music of this video was made with the add-in itself: "Plenio Comes to SoundCraft", composed and sung by
YuE2 (CC BY-NC 4.0) in Plenio.

▶ Download, code and tutorial: https://github.com/jplenio/soundcraft-plenio

▶ Plenio for ComfyUI: https://github.com/jplenio/Plenio-Music-Production-System

Alpha 0.1.0 · runs locally (ComfyUI, 16 GB GPU) · songs are non-commercial · an independent fork of
SoundCraft.

**Tags:** AI music, YuE, YuE2, ComfyUI, DAW, SoundCraft, Plenio, AI songwriting, stems, MIDI, open source, Rust

---

**The tutorial video** (`plenio-tutorial.mp4`)

**Title:** Plenio for SoundCraft tutorial – make, change, cover and import a song (alpha)

**Description:**

In under two minutes: activate the add-in, make a song from a style and your own lyrics, get its take with
lyrics, score and stems on real tracks, make a second take, cover the song as late-night jazz, and bring in a
song Plenio made in ComfyUI. Every frame is the real app.

Written tutorial with every step:
https://github.com/jplenio/soundcraft-plenio/blob/plenio-addin/addins/plenio/docs/TUTORIAL.md

Music: the tutorial's cover, made with Plenio in SoundCraft (YuE2, CC BY-NC 4.0).

## Instagram, TikTok, YouTube Shorts (the vertical teaser)

```text
Lyrics in. Song out. Every take, lyric, note and stem on its own track. 🎛️✨
Plenio comes to SoundCraft – free, open source, on your own GPU. Link in bio.
#aimusic #musicproduction #daw #songwriting #comfyui #opensource
```

On YouTube Shorts the first line is the title.

---

## Product Hunt

**Name:** Plenio for SoundCraft

**Tagline (60 characters):** AI songs with editable lyrics, MIDI and stems in a DAW

**Description (260 characters):** Write lyrics, pick a style, press Generate: YuE2 makes the song on your GPU and an open-source DAW gets the parts – lyrics, takes, score as MIDI, stems – synced bar by bar. Change a word or a note and make it again. Free, alpha.

**First comment:**

Hi Product Hunt! I built Plenio to make songs with AI in ComfyUI; this is the step into a real DAW. What
mattered most to me: nothing is a black box. Every part of the song is a track you can edit, and the tempo map
follows the audio, so you can keep producing on top. It's an alpha, so I'd love your feedback.

---

## KVR Audio forum (Software › DAW or Instruments)

**Subject:** Plenio for SoundCraft 0.1.0-alpha: generated songs with lyrics, MIDI and stems on tracks

Plenio for SoundCraft is a free, open-source add-in (in a fork of the SoundCraft DAW) that generates songs
with vocals locally and hands them over as a production: the lyrics as clips, the score as MIDI, each take on
its own playlist, the stems on their own tracks, and a tempo map measured bar by bar from the audio. Alpha,
Windows, needs ComfyUI and a 16 GB NVIDIA GPU; songs made with the YuE2 models are non-commercial.

https://github.com/jplenio/soundcraft-plenio

---

## Newsletter or blog post

**Introducing Plenio for SoundCraft (alpha)**

When I started Plenio, the goal was a song from a single idea: the lyrics written, the music composed, sung
and mastered, the cover painted. It works, in ComfyUI. But a finished WAV is where producing begins, not where
it ends.

So Plenio now lives inside a DAW. SoundCraft is an open-source digital audio workstation written in Rust, and
the Plenio add-in puts a generated song into a session as what a producer needs: the lyrics on a track, a clip
per sung line; the score as MIDI for melody, instrument line and chords; every take on its own playlist; the
stems on their own tracks.

The audio stays the master. AI renders breathe, their tempo is never quite constant, so the add-in measures
every bar in the audio and writes it into the session's tempo map. Press play with the metronome on and it
stays with the song from the first bar to the last; any MIDI you record stays on the beat.

From there it's a conversation: change a line, Generate composes new notes for it; change a note, Generate
sings it as written; keep the seed of the arrangement and try another take. Covers of any recording work the
same way, and songs made with Plenio in ComfyUI come in from their FLAC.

It's an alpha: tested on Windows, it needs ComfyUI and a 16 GB graphics card, and songs made with YuE2 are for
non-commercial use. The teaser's song, "Plenio Comes to SoundCraft", was made with it.

Try it, break it, tell me what you'd make with it: https://github.com/jplenio/soundcraft-plenio

---

## GitHub

**Repository description (About):** SoundCraft, the open-source Rust DAW, with the Plenio add-in: AI songs and covers (YuE2) with lyrics, MIDI score, takes and stems on tracks.

**Website:** https://github.com/jplenio/soundcraft-plenio/blob/plenio-addin/addins/plenio/docs/TUTORIAL.md

**Topics:** `daw`, `music-production`, `ai-music`, `yue`, `comfyui`, `rust`, `egui`, `text-to-music`, `stems`, `midi`, `songwriting`

**Social preview:** upload `addins/plenio/docs/media/social-preview.png` (Settings › General › Social preview).
