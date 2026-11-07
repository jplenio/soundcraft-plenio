# The Plenio add-in for SoundCraft: plan and progress

| | |
|---|---|
| **Goal** | Plenio (YuE2 · Song, YuE2 · Cover, Plenio Player, **without MiniMax**) as an add-in in SoundCraft, seamlessly integrated |
| **Branch** | `plenio-addin` (remote `upstream` = `storytold/soundcraft`) |
| **Plenio source** | `D:\Daten2\Deepseek\ComfyUI-MiniMax\Plenio-Music-Production-System` (version 1.5.0): **never changed**, code is copied |
| **Plan made** | 2026-11-05 |
| **Last updated** | 2026-11-07 |
| **State** | **Version 0.1.0-alpha ready to publish** (phase 7): phases 0–6 done and checked live through the UI (song, notes, stems, cover, player, import); the fork is on GitHub (`jplenio/soundcraft-plenio`); open points in "State on the evening of 2026-11-05" and phase 7 |

Legend: `[x]` done · `[ ]` open · `[~]` started or partly done · 💡 note

---

## Progress at a glance

| Phase | Content | Status |
|---|---|---|
| A | Analysis, concept, decisions | ✅ done |
| 0 | Foundation: Git, seams S1–S6, crate skeleton, Plenio menu, activation switch | ✅ done |
| 1 | Backend: copy of Plenio, wrapper, ComfyUI supervisor, models (Song API instead of an own stage API) | ✅ done |
| 2 | MVP "YuE2 Song" | ✅ done |
| 3 | Notes and stems | ✅ done (browser score editor open) |
| 4 | YuE2 Cover | ✅ done (checked live) |
| 5 | Player and release | ✅ done ("Open in SoundCraft" open) |
| 6 | Hardening, update rehearsal, docs | ✅ done |
| 7 | Release 0.1.0-alpha: review, more of the Song API, docs, media, teaser, announcements | ✅ ready (publishing is the owner's) |

---

## Checklist

### Phase A: analysis, concept, decisions

- [x] Read `CLAUDE.md` and `AGENTS.md`, analysed SoundCraft's architecture
  💡 `plan/STATUS.md` and `plan/execution-plan.md` do not exist locally (`plan/` is gitignored and missing on this computer).
- [x] Analysed Plenio (Song API, routes, subgraphs, player, model catalogue, standalone concept)
- [x] Plan made and approved by the owner (2026-11-05)
- [x] Decision 9.1: **an own ComfyUI instance run by the add-in** (own base folder, existing models are shared)
- [x] Decision 9.2: ~~seams may go upstream~~ → **no upstream, an own fork** (changed 2026-11-06, see [FORK.md](FORK.md))
- [x] Decision 9.3: **`origin` renamed to `upstream`, work on branch `plenio-addin`**
- [x] Added requirement: **do not change the Plenio project**, copy the useful code to SoundCraft
- [x] Plan saved as Markdown (this file)

### Phase 0: foundation

- [x] Git: renamed `origin` to `upstream`, created branch `plenio-addin` from `73eeb69`
  💡 The owner still has to create the GitHub fork `jplenio/soundcraft-plenio` as `origin` (steps in [FORK.md](FORK.md)); until then everything is local only.
- [x] Rust toolchain installed: rustup with stable 1.99.1 (`x86_64-pc-windows-msvc` + `wasm32-unknown-unknown`, clippy, rustfmt) under `D:\Rust`
  💡 `CARGO_HOME=D:\Rust\cargo`, `RUSTUP_HOME=D:\Rust\rustup` as user variables; `D:\Rust\cargo\bin` is on the user's PATH (new shells). rustup-init checked by SHA-256. MSVC comes from Visual Studio 2022.
- [x] Baseline on the unchanged state `73eeb69` (own worktree, own target directory)
  💡 fmt, clippy, doctests, assets, layers and wasm green. **3 tests already fail before any change** on this computer: `soundcraft-cli` `it::behaviour::app_port_comes_from_the_flag_then_the_environment`, `it::behaviour::app_takes_an_empty_port_variable_as_unset`, `it::run::app_reports_a_refused_connection_and_checks_arguments_first`. Cause: on Windows, connecting to a closed port runs into a timeout instead of being refused at once ("connection timed out" instead of "refused"). Not caused by the add-in. `cargo xtask ci` therefore stops at the step `test` here; the other steps were run one by one.
- [x] **S1** `crates/model/src/session.rs`: `extensions: BTreeMap<String, Arc<str>>` with `extension()`, `set_extension()`, a key rule and caps (64 entries, 16 MiB per entry, 64 MiB in all), limited in `sanitize` on load; `crates/engine/src/dirty.rs` counts the field for the saved state. 3 tests.
  💡 `Arc<str>` instead of `String`, so that undo snapshots do not copy the text.
- [x] **S2** `crates/engine/src/cmd/extensions.rs` (new): `register_extension_commands`, `refused_extension_commands`, `extension_command_id_ok`; only 3 lines in `cmd.rs` (module, `pub use`, `close_into` at the end of `command_specs()`). A test binary of its own, `crates/engine/tests/extension_commands.rs` (registration, undo, `enabled`, collision with SoundCraft's ids, late registration refused), plus 1 unit test.
  💡 A deliberately small diff: the list of SoundCraft's modules in `command_specs()` stayed unchanged, which makes later merges easier. An id SoundCraft already has is left out when the registry is built and reported.
- [x] **S3** `crates/ui-egui/src/extension.rs` (new): trait `UiExtension` with `logic`, `menu_bar`, `windows`, `track_header`, `lane` (with `Lane::x_of`/`sample_at`), `track_context_menu`; `SoundApp::add_extension`/`extensions()`. Call sites: 1 line each in `app.rs` (2×), `menus.rs`, `edit_window/tracks.rs` (3×), a field in `lib.rs`. A hook that panics stops only that add-in (`catch_unwind`, log and status message). 2 tests.
  💡 The dock panel (`Panel::Extension`), settings and file drop are not in yet: they come additively when needed (default methods break nothing).
- [x] **S4** `apps/soundcraft`: feature `plenio` (default on this branch), `register_commands()` right after the logger, `add_extension(...)` after the prefs (the settings folder only when prefs are active).
  💡 `cargo clippy -p soundcraft --no-default-features` is green: SoundCraft still builds without the add-in.
- [x] **S5** `Cargo.toml`: members `addins/*/crates/*`; for crates outside its table, `xtask layers` reads `[package.metadata.soundcraft] layer = N` from the manifest.
  💡 General instead of Plenio-specific `LAYERS` entries. Documented in `docs/architecture.md › Extensions` (with a revision entry).
- [x] **S6** `ATTRIBUTION.md`: a directory row for `addins/plenio/vendor/` (template preview images, the player's app icons; Apache-2.0)
- [x] Crate skeleton `addins/plenio/crates/{project,backend,commands,ui}` with `[lints] workspace = true`, crate-wide `#![deny(...)]` attributes and the layer in the manifest (2/4/4/6)
  💡 `project`: songs and track roles in `Session.extensions["plenio"]` (limited, orphaned roles fall away, newer versions are refused). `backend`: settings in `<settings folder>/Plenio/settings.json`, written atomically. `commands`: `plenio.status` and the activation check `when_activated`. `ui`: menu and windows. 12 tests.
- [x] Menu "Plenio" visible, "Activate Plenio Add-in…" with a window (names the own ComfyUI instance, the models and the CC-BY-NC licence); activated: "New Song…", "New Cover from Selection…", "Open Plenio Player" (still greyed out), "Deactivate", "About"
  💡 Checked offscreen with `cargo run -p soundcraft-plenio-ui --example plenio_shot -- <folder>` (three PNGs: menu, activation, menu activated). The UI is in English like SoundCraft and Plenio.
- [x] Gates: fmt, clippy `--workspace --all-targets -D warnings`, tests, doctests, assets, layers, wasm green, apart from the 3 baseline failures above. Commits by topic on `plenio-addin` (local, not pushed).
- [ ] Open for later: `soundcraft-cli` (headless/MCP) does not register the `plenio.*` commands yet. In the running desktop app the control channel and `soundcraft-cli mcp --connect` go through its registry and should therefore reach them; this has not been checked yet (the GUI app has so far only been rendered offscreen, not started).

### Phase 1: backend

- [x] `tools/sync_plenio.py`: a fixed copy list, `vendor/VENDOR.toml` (source, commit, version, date, count), `vendor/VENDOR.sha256`, a change report (`--dry-run`), a hash check against changes by hand (`--check`)
  💡 Reads only Git blobs of the commit (`ls-tree` + `cat-file`): uncommitted changes in Plenio are never copied, every sync of a commit gives the same files, and the Plenio repository is not changed. `vendor/.gitattributes` keeps LF line endings like Plenio (its tests compare byte by byte; SoundCraft works with `core.autocrlf=true` here).
- [x] First copy to `addins/plenio/vendor/plenio/`: Plenio 1.5.0 @ `f26972890377`, 1027 files, about 18 MB
  💡 Copied: `plenio/`, `resources/`, `frontend/`, `tests/`, `tools/` (without `tools/tutorials/`), `subgraphs/` and `example_workflows/` without MiniMax, `locales/`, licence and readme files, `pyproject.toml`, `requirements.txt`, player starters. Not copied: `web/` (the built ComfyUI frontend extension), `docs/`, `assets/` (branding), `tools/tutorials/` (a speaker recording and showcase images of unclear origin, not needed for tests). MiniMax models are still in the copied `models.toml`; the wrapper filters them at runtime.
- [x] Python wrapper `backend/soundcraft_plenio/`: an own `comfy_entrypoint` = Plenio's extension unchanged + `/scp/v1`
  💡 Plenio has no MiniMax nodes of its own (MiniMax is an engine choice in templates); leaving out MiniMax templates, subgraphs and models is enough. A watchdog ends the instance when SoundCraft is gone (`SCP_PARENT_PID`).
- [x] ~~Stage API~~ → **Plenio's Song API directly** (`/plenio/api/v1/jobs`, `?wait`, `DELETE`, `templates`, `briefs`, `uploads`, `from-record`); `/scp/v1` only for info, models (without MiniMax), stems and bars
  💡 Stopping after lyrics or notes ("stop at lyrics/notes") therefore does not exist as an intermediate stop; lyrics and notes can be changed after every take and made again.
- [x] ComfyUI supervisor: finds ComfyUI through Plenio's `comfyui-start.json`, an own instance with `--base-directory`, the owner's `--models-directory`, a free port, a log; stops on closing
  💡 ComfyUI 0.43.0 under `D:\Daten2\ComfyUI`, models under `F:\ComfyUI\models`. Live: ready after about 10 s. No idle stop yet (a stop button in the studio window).
- [x] Model manager (`/scp/v1/models` + downloads in Rust with progress, resume and a size check; CC-BY-NC models only after the licence is confirmed)
  💡 A system check through `/plenio/system` (Plenio's route) is possible, not shown in the UI yet.
- [x] ~~Golden test against a stage chain~~ dropped: songs are made with Plenio's own template through the Song API, so identically to using Plenio
  💡 Real runs: a 61 s instrumental (133 s), a sung song "Heavy in My Pocket" (93.7 s, through SoundCraft's UI, 238 s).
- [x] Copied Plenio test suite against the copy: `tools/test_all.ps1 -Plenio <checkout>` (pytest from Plenio's `.devdeps`, read only)

### Phase 2: MVP "YuE2 Song"

- [x] Dialog "Plenio › New Song…" (250 genre templates with search, idea or own lyrics, length, vocals)
- [x] Song folder (routing folder) with lyrics, note and mix tracks; roles in `Session.extensions`
- [x] Lyrics track: one clip per sung line (from Plenio's `(lines).srt`), otherwise per section; checked with Plenio's rules (`/plenio/lyrics/analyze`)
  💡 Plenio's check shows the token budget and syllables as hints; there is no budget display of its own. The take is chosen in the inspector (not in the track header).
- [x] Lyrics editor panel (section tags as buttons, syllables, budget, status auto/edited/manual, diff against the last take)
- [x] Inspector with a dynamic form from `/templates/{id}`
- [x] Generate → a take as a playlist; choosing a take switches all tracks at once
- [x] Staleness display ("lyrics changed → notes + take"), lock or re-roll seeds
- [x] Jobs in the background with progress and cancel; every take taken in is one undo step
- [ ] ~~Switch "stop at lyrics/notes"~~ (Song API v1 does not stop; see phase 1)

### Phase 3: notes and stems

- [x] Score ↔ MIDI (melody, chords, accompaniment line) through `/plenio/score/midi/export|import`; muted instrument tracks with a synth to preview
- [x] DAW path: edited notes → back to Plenio (conductor track with layout and unchanged tracks byte for byte) → YuE2 sings exactly these notes
- [x] Tempo, meter and key from the score (first take of an otherwise empty session); sections as coloured blocks in the song lane
  💡 No memory locations are created (several songs in one session would mix).
- [x] Stems (vocals, drums, bass, other, rest) with Plenio's BS-RoFormer through `/scp/v1/stems`, as tracks with take playlists; the mix track is muted while a take with stems plays
  💡 Live: a 61 s take in 21.7 s. Stems as MIDI not yet.
- [ ] Browser score editor (copied Vue frontend with a SoundCraft adapter in an overlay), changes flow back into the session

### Phase 4: YuE2 Cover

- [x] "New Cover from Selected Track…" and in the context menu; the edit selection = the excerpt (`excerpt.start_index/duration`); upload through `/plenio/api/v1/uploads`
- [x] Plenio's cover template does the analysis (SheetSage2, Qwen3-ASR); the take brings the cover's tempo, notes and lyrics along
  💡 The add-in does not show the original's heard lyrics and sung pitch separately (the Song API does not deliver them as a result of their own).
- [x] All cover fields of the Song API in the inspector form (modes, harmony, closeness, original notes); Plenio does Fit Lyrics in the template
- [x] A/B against the original: the recording lies in the cover's folder and is muted on the first cover take (unmute to compare)
- [x] Cover live through the UI (`examples/plenio_cover_e2e.rs`): recording imported → New Cover from Selected Track → uploaded after 23 s → cover take after 309 s (54.6 s, with lyrics and notes)

### Phase 5: player and release

- [x] Player sidecar: the copied player, its own state folder and port, library = the instance's output; party songs go to the instance (`studio.json`)
- [x] "Send the mix to the Plenio Player": `file.bounce_mix` (FLAC 24 bit) + a record from the take's (documents, lyrics timing as `(lines).srt`)
  💡 Without Plenio's mastering and without a PDF; the mix is SoundCraft's.
- [ ] The way back, "Open in SoundCraft" (an overlay instead of "Open in ComfyUI", through the control channel)
- [x] "Import Plenio Song…": the FLAC alone (Plenio puts the record in it as a `PLNO` block) or `.plenio.json` + audio beside it → a song with fields and seeds from `/from-record`, a take with lyrics and notes (also party songs from the player's library); after that a new take and stems like any song
  💡 The import waits for a studio that is still starting (notes and fields come from it). Derived files (`score.mid`, stems) lie in the add-in's folder, never in the song's. FLACs without a record (before Plenio 0.8.0) need the `.plenio.json` beside them.

### Phase 6: hardening

- [x] Parity: songs are made with Plenio's own templates through the Song API, so with everything the templates do (best take, check vocals, LoRAs, creativity, creative modes, master, cover art, export); the form has all fields of the Song API. Plenio's unit tests against the copy: **1980 passed, 1 skipped, 0 failed**.
  💡 Not reachable through the API and therefore open: intermediate stops to review (review mode), LoRA choice (no field in Song API v1).
- [x] Property tests with hostile input: job, record, score, SRT (`backend/tests/hostile.rs`), MIDI splicing (`commands/tests/hostile_midi.rs`); the stems route's path guard checked live
- [x] SoundCraft update rehearsal: first real merge on 2026-11-06 (5 commits from `upstream/main`, 1 conflict in `crates/engine/src/dirty.rs`), script rehearsed in throw-away clones with a made-up upstream (README, logos, `Cargo.lock`, a second merge without manual work)
- [x] Plenio update rehearsal: Plenio sync several times without manual work (copy extended by `docs/api`, `docs/design/data`, `docs/user/models.md`, `web/docs`).
- [x] ~~Submit the seams upstream~~: dropped, the owner keeps an own fork (2026-11-06). Branch `extension-api` deleted; its commits are in `plenio-addin`.
- [x] Fork prepared: its own `README.md`, ArtCraft marks removed (their licence requires it), the app's update source pointed at the fork, `tools/update_soundcraft.ps1` rewritten (merges instead of rebasing), [FORK.md](FORK.md)
  💡 Open with the owner: create the repository on GitHub and upload. Open before own installers: `packaging/` still names the folder `ArtCraft`.
- [x] User and developer docs: `addins/plenio/README.md`, `docs/architecture.md › Extensions`

### Phase 7: release 0.1.0-alpha (the owner's request of 2026-11-07)

- [x] Everything in English: a scan of every file the fork adds or changes finds German only in data (song titles, test fixtures of Plenio's linguistics)
- [x] SoundCraft taken in again: `bb0e070` (a Preferences window, the house rules in `AGENTS.md`), no conflict, all checks green
- [x] Review of the app through a tour of the real UI (`examples/plenio_tour.rs`), with a real studio: activate, a song with typed lyrics, a second take, a cover, an import. It found, and the alpha fixes:
  - [x] the New Song dialog hid **Make the Song** below its fold (now its buttons are always in view, the lyrics scroll on their own, windows open centred)
  - [x] the second take of a song came back as "Title (2)", and renamed the song (each take has a release folder of its own now)
  - [x] a take or stems that arrived after their session was closed landed in the session open then, even on another song with the same id (a uid per song, checked for every piece of work that arrives late)
  - [x] a second song with its own tempo (a cover in the same session) made the first song's notes count as edited (notes are read in their own take's bars now)
  - [x] the studio's window was as wide as the screen (the catalogue's long descriptions are shortened, with a tooltip)
- [x] Code review: the brief's text fields and the ComfyUI folder kept no typed character (a buffer made anew every frame); number fields ignored their ranges (`minimum`/`maximum`); leaving a field unchanged marked the brief as changed; "What it is about" replaced the style's sound instead of being the lyrics' idea; failed commands were dropped silently (`run_or_say`); a crashed ComfyUI was noticed only at the next request (now within 2 s)
- [x] More of the Song API in the New Song and New Cover dialogs: 250 styles with name, group and sound (`/briefs`), every other field under **More options** with the style's values as hints, `when` conditions honoured, the answers cached for the next start (`Plenio/api-cache.json`)
- [x] Stems right away: per song (dialog and inspector), remembered for the next song, also for imports
- [x] Studio and Models: opens after activation, **Download All Missing**, **Browse…** for the ComfyUI folder; **Getting Started** in the menu
- [x] Maintainability: `windows.rs` split into `windows/{mod, song_dialog, inspector}.rs`, the fields in `fields.rs`; [DEVELOPMENT.md](DEVELOPMENT.md) (parts, rules, a take's journey, tests, releases)
- [x] Version `0.1.0-alpha` in the add-in's crates, [CHANGELOG.md](../CHANGELOG.md), [NOTICE.md](../NOTICE.md); the licence: MIT OR Apache-2.0 like SoundCraft, Plenio's copy Apache-2.0, logo and banner Apache-2.0, screenshots MIT OR Apache-2.0, songs CC BY-NC 4.0 by the models
  💡 Why not one licence for all: the add-in lives in SoundCraft's workspace (MIT OR Apache-2.0) and may give seams back; Plenio's code keeps its own licence and NOTICE (Apache-2.0 §4); the logo under Apache-2.0 keeps the name out of the grant (§6); YuE2's licence binds every song it makes, so also the teaser.
- [x] README of the fork and of the add-in, [TUTORIAL.md](TUTORIAL.md), logo, banner, social preview, screenshots and the animation `tour.gif` (`tools/media/`), all made from the tour's real session
- [x] Teaser 16:9 and 9:16 (`tools/media/make_teaser.py`): the tour's song, its scenes on its measured bars and sung lines; outside the repository (its music is CC BY-NC 4.0)
- [x] The tutorial also as a video (`tools/media/make_tutorial.py`, 1:52): six chapters of the tour's real frames with captions, the tour's cover as quiet music
- [x] Release text ([release/plenio-v0.1.0-alpha.md](release/plenio-v0.1.0-alpha.md)), announcements for every channel ([launch/ANNOUNCEMENTS.md](launch/ANNOUNCEMENTS.md)), the launch plan ([launch/README.md](launch/README.md))
- [x] Windows package: `tools/package_windows.ps1` (portable zip with `plenio-addin/` beside the program, checksums)
- [ ] Publishing: push, the tag `plenio-v0.1.0-alpha`, the GitHub release (pre-release), the video, the posts: the owner's ([launch/README.md](launch/README.md))

---

## 1. Core decisions

1. **Generation stays where it works today:** ComfyUI with the copied Plenio code runs as a background process of its own. YuE2, SheetSage2, ASR and stems need PyTorch and ComfyUI's kernel. Plenio's own concept (`docs/design/standalone-app-concept.md`) estimates 30–46 weeks until a Rust inference sounds as it does today.
2. **SoundCraft gets a native Rust add-in** for UI, tracks, takes and control. A crash in Python or CUDA cannot take SoundCraft down ("never crash").
3. **All of the add-in's code lies in `addins/plenio/`.** SoundCraft gets only 6 small, general extension points ("seams"), because it has no add-in system today:
   - The command registry is a static `OnceLock` (`crates/engine/src/cmd.rs`).
   - The menu is built from the catalogue (`crates/ui-egui/src/menus.rs`, `tree()`).
   - The docking panels are a fixed enum (`crates/ui-egui/src/docking.rs`, `Panel`).
   - `Session` has no extension field; foreign data would be lost on the next save.
4. **Plenio is copied, not changed.** A sync script copies it 1:1 to `addins/plenio/vendor/`; all adaptations lie outside the copy (wrapper, overlays).

## 2. Architecture

```
┌──────────────────── SoundCraft (Rust, one process) ─────────────────────┐
│ Upstream crates (unchanged)    ◄─ 6 seams ─►  addins/plenio/crates/*    │
│ model · engine · mix · ui-egui               project · backend ·        │
│                                              commands · ui              │
└──────────────────────────────┬──────────────────────────────────────────┘
          HTTP 127.0.0.1 (JSON, long poll); processes started and watched by the add-in
        ┌──────────────────────┴─────────────────────┐
        ▼                                            ▼
ComfyUI (own instance, headless)            Plenio Player (copy, Python stdlib)
 └ custom_nodes/soundcraft-plenio            127.0.0.1:8765…
    ├ soundcraft_plenio/  wrapper: /scp/v1, model manager
    └ vendor/plenio/      1:1 copy (core, comfy, player, workers, third_party …)
```

## 3. Separation and updates

### 3.1 Folders

```
addins/plenio/
├─ docs/PLAN.md                 this file
├─ crates/
│  ├─ project/   data model: songs, track roles, documents, seeds, takes (plain data)
│  ├─ backend/   HTTP client (ureq), jobs, process supervisor, models
│  ├─ commands/  engine commands plenio.* (run through Engine::execute → undo for free)
│  └─ ui/        egui: inspector, lyrics editor, lanes, take choice, activation assistant
├─ backend/soundcraft_plenio/   own ComfyUI entry point + /scp/v1 (Python, new)
├─ vendor/plenio/               1:1 copy + VENDOR.toml (commit, version, file hashes)
├─ frontend/overlay/            replaces e.g. shared/comfy.ts with a SoundCraft adapter at build time
└─ tools/  sync_plenio.py · update_soundcraft.ps1 · test_all.ps1
```

### 3.2 The only changes to SoundCraft (general, nothing specific to Plenio)

| # | Where | What | Size |
|---|---|---|---|
| S1 | `crates/model/src/session.rs` | `extensions: BTreeMap<String, String>` (serde default, not saved when empty, size capped in `sanitize`). So the add-in's data is part of the session: undo, autosave, crash recovery and bundles work with no extra work. | ~30 lines |
| S2 | `crates/engine/src/cmd.rs` | `register_extension_commands(Vec<CommandSpec>)`, included in `command_specs()`/`find_command`. `plenio.*` automatically lands in CLI, MCP and control channel too. | ~30 lines |
| S3 | `crates/ui-egui/src/extension.rs` (new) + 5–6 call sites | Trait `UiExtension`: menu, track header, lane drawing, dock panel (`Panel::Extension`), frame update, context menu, settings, file drop | ~200–250 lines |
| S4 | `apps/soundcraft` | Cargo feature `plenio` plus 3 lines of registration in `main.rs` | ~10 lines |
| S5 | `Cargo.toml` + `xtask` | Workspace members `addins/*/crates/*` and entries in `LAYERS` (otherwise `cargo xtask layers` fails) | ~10 lines |
| S6 | `ATTRIBUTION.md` | a directory row for `addins/plenio/vendor/` (`xtask assets` accepts directory rows) | 1–3 lines |

**Rule for the add-in's code:** it changes SoundCraft only through its own command ids (e.g. `track.new`, `track.playlist_new`, `track.playlist_select`, `track.move_to_folder`, `event.tempo`, `event.add_key_change`, `file.import_midi`). It uses `session_mut()` only for its own extension data and for what no command does (a take's tempo map with the owner's clips kept on their bars). If the API changes, a compile error in `addins/` shows it.

### 3.3 Taking in SoundCraft updates

- Remote `upstream` = `storytold/soundcraft`; branch `plenio-addin` = `upstream/main` + the seams + `addins/`.
- `tools/update_soundcraft.ps1`: fetch, **merge** (the fork is published, so no rebase), `README.md` stays, `Cargo.lock` is resolved anew, ArtCraft marks out, then `tools/test_all.ps1`. Conflicts are only possible at the places listed in [FORK.md](FORK.md); `git rerere` remembers solutions.

### 3.4 Taking in Plenio updates

- `tools/sync_plenio.py --from D:\…\Plenio-Music-Production-System` copies a fixed list 1:1: `plenio/`, `resources/`, the YuE2 subgraphs, templates 0/1/2/4/5, `frontend/src`, `tests/` and LICENSE/NOTICE/THIRD_PARTY.
- It writes `VENDOR.toml`, reports changed files and runs Plenio's tests and the wrapper tests. A hash check prevents changes by hand in `vendor/`.
- **MiniMax:** no templates, subgraphs or models of MiniMax, nothing in the UI; the wrapper does not register MiniMax nodes. MiniMax is woven into `plenio/core` (`engines/__init__.py`, `brief.py`, `writing.py`); these files are copied along as inactive code, because removing it would change the copy.

## 4. How it is used

### 4.1 A Plenio song in the edit window

```
▼ Night Drive (Plenio song)   Take ◀ 3/5 ▶ 4 stars   lyrics changed   [Generate]
  │Intro│ Verse 1 │Pre│ Chorus │ Verse 2 │ Chorus │Bridge│ Chorus │Outro│  ← song form
  ├ Lyrics       [verse] Rain on the asphalt … │ [chorus] We ride …
  ├ Melody       MIDI, to preview with a SoundCraft instrument
  ├ Chords       MIDI
  ├ Accompaniment MIDI
  ├ Song (mix)   audio, takes as playlists
  └ (optional) Vocals · Drums · Bass · Other · Rest   ← stems, their sum = the take
 Audio 1 · MIDI 1 · Instrument …   ← your own tracks, anywhere, also in the folder
```

| Track | Technically | What the add-in adds |
|---|---|---|
| **Song** | routing folder: sums all its children (effects on the whole song) | header with status, take choice, generate; a lane with the sections; inspector with all YuE2 parameters |
| **Lyrics** | muted MIDI track, one clip per section | the lane shows text instead of notes; YuE2's rules live (section tags, own tags, syllables, token budget 24 576 through Plenio's tokenizer); after rendering, words where they are sung |
| **Notes** | MIDI tracks with a built-in instrument | a projection of Plenio's score (ABC stays the main source); editing → "edited" → YuE2 sings exactly these notes (path "YuE2 · DAW") |
| **Result** | normal audio tracks | effects, cuts, fades, automation as always; takes = playlists; comping with the existing playlist lanes |
| **Cover source** | normal audio track with the original | analysis source; A/B through solo/mute |

The tempo map follows the take's audio ([section 10a](#10a-the-audio-is-the-master-the-owners-decision-2026-11-06)), meter and key come from the score, so that your own MIDI tracks lie on the grid at once. Sections are shown in the song lane.

### 4.2 Takes

- Every generation is a **take** over all the song's tracks: playlists of the same name on lyrics, note and audio tracks ("Take 4 · 4 stars").
- A take freezes lyrics, notes, parameters and seeds. If you choose take 2 you see its lyrics and notes and can go on working from there.
- Old takes stay with your edits; clean up with `track.playlist_delete_unused`.
- Every generation taken in is **one undo step**.

### 4.3 Change and generate again

| You change … | Plenio makes anew … | Result |
|---|---|---|
| Seed, number of takes, LoRA, lyrics fidelity | only the render | a new take |
| Notes (MIDI or score editor) | a render with your score | a new take, sings exactly your notes |
| Lyrics | composing, then rendering (new words need new notes); on a cover alternatively fitting them to the melody (Fit Lyrics) | new notes and a new take |
| Style, tempo, key, length | planning, then rendering | the same |
| Brief or idea | writing, planning, rendering | the same |

- Documents edited by hand stay untouched (auto, edited, manual).
- Seeds (draft, plan, arrangement, take) can be locked or re-rolled.
- The song header shows what is stale ("lyrics changed → notes + take").
- Generate menu: "New take", "Compose again", "Rewrite lyrics", "×4 takes, choose best take".
- Jobs run in the background; the transport keeps playing; progress and cancel in the header and in the jobs panel.

### 4.4 New song

- **Plenio › New Song…**: genre from 250 templates (search), idea or own lyrics, length, vocals, "Create".
- The tracks appear at once and fill one after the other: lyrics, notes, take.
- A switch **"stop at lyrics/notes"** would match Plenio's mode "one song, stop to review" (not in Song API v1, see phase 1).

### 4.5 Cover

- Right-click on an audio track or selection → **"Plenio cover from this…"**; the edit selection becomes the excerpt (`excerpt`).
- The analysis fills tempo and beat grid (SheetSage2), the note tracks with the original, the lyrics track with the heard words (uncertain ones marked), optionally the sung pitch.
- To choose: instrumental, original lyrics, new lyrics, harmony, song flow closeness, lyrics closeness, original notes. After that as with a song.

### 4.6 Notation

1. **Native:** note tracks in SoundCraft's MIDI and score editor (notation, MusicXML, print score). Later lyrics under the melody notes.
2. **Full parity from day one:** **"Open in Plenio's score editor"** starts the copied Vue editor in the browser (overlay adapter instead of ComfyUI): chord lane, bar inspector, arranging, MIDI keyboard, PDF. Changes flow back into the session.

### 4.7 Stems

- "Split into stems" creates vocals, drums, bass, other, rest; optionally automatically for every take.
- Optionally stems as MIDI (e.g. to replace the bass line with an own instrument).
- The default stays one mix track (Plenio rates stems as experimental).

### 4.8 Player

- **Plenio › Send to Player:** a bounce of the song's folder (with your effects), then the copied export release step (FLAC/MP3, tags, lyrics timing on the vocal stem, PDF, `.plenio.json`) into the player's library; Plenio's mastering (-14 LUFS) optional.
- **Open Player** starts the copied player with its own state folder. An overlay turns "Open in ComfyUI" into "Open in SoundCraft" (control channel).
- Party songs keep working; "Take into SoundCraft" makes a Plenio song from them that can be made again, as does a Plenio FLAC dragged in.

### 4.9 Activation and loading models automatically

**Plenio › Activate Add-in…** opens an assistant:

1. **System check** (copied `system.py`): GPU, VRAM → recommends int8 (4 GB) or bf16 (7.8 GB, from 24 GB of VRAM).
2. **Find ComfyUI:** through Plenio's `comfyui-start.json` and `extra_model_paths.yaml`, otherwise offer to download ComfyUI portable. An own headless instance with its own base folder; existing ComfyUI and Plenio installations stay untouched, existing models are shared.
3. **Models** through the copied catalogue (`models.toml` without MiniMax) and downloader (resumable, SHA-256), with progress in SoundCraft:
   - Profile "Song": YuE2, instrumental LoRA, writer, UniverSR.
   - Profile "Cover" on the first cover: SheetSage2 (1.4 GB), Qwen3-ASR + aligner (3.8 + 1.7 GB), BS-RoFormer (0.5 GB).
   - FLUX.2 Klein (cover art) optional.
   - **The CC BY-NC 4.0 licence (non-commercial) of YuE2 and SheetSage2 is shown before the download and must be confirmed.**
4. **Test run:** a short instrumental take.

Deactivating hides the UI and ends the processes; the session stays fully usable (everything made is normal audio and MIDI).

## 5. Backend: copied code plus a wrapper

Song API v1 always runs to the end (no review stops), and its result roles hold no stems. The first plan therefore had the wrapper offer a **stage API under `/scp/v1`**, each stage a ComfyUI run from the copied subgraphs. That was dropped (see phase 1): generation goes straight through the Song API, and `/scp/v1` holds only what the Song API does not offer.

| Endpoint planned at first | Basis (copied) |
|---|---|
| `draft`: brief → title, style, lyrics | subgraph *Write Song*, `core.writing` |
| `lyrics/check`: check live | routes `lyrics/analyze`, `sheet/resolve` |
| `plan`: score, sections, BPM, key, MIDI | *YuE2 Plan*, Song Form, `score/midi` |
| `score/from-midi`, `to-midi`, `musicxml` | `score/midi/*`, `musicxml/*` |
| `render`: takes, best take, quality, sung timing | *YuE2 Render/Takes*, Subtitles |
| `stems` | *Stems* |
| `cover/analyze`, `cover/fit` | *Transcribe Score*, Lyrics ASR, Sung Pitch, Fit Lyrics |
| `release` | Export Release, *Master* |
| `system`, `models` | `system.py`, `assets/fetch.py` |
| `jobs/{id}?wait`, `DELETE` | the Song API's job mechanism |

The Rust UI builds the parameter forms **dynamically from `/templates/{id}`**; new Plenio fields appear with no change in Rust.

## 6. Quality at least as good as today

- The same code, the same ComfyUI nodes, the same subgraphs.
- Plenio's test suite runs against the copy after every sync.
- A parity checklist from Plenio's inventory of functions (see phase 6).

## 7. SoundCraft's rules

- Every add-in crate: `[lints] workspace = true` and `#![deny(clippy::unwrap_used, clippy::expect_used, clippy::panic, clippy::unimplemented, clippy::todo, clippy::unreachable)]`; no `unsafe`.
- Backend answers are hostile input: cap sizes, `get()` instead of indexing, checked arithmetic.
- HTTP never on the UI or audio thread; results through a channel, applied by `execute` in the frame hook.
- The add-in is native only; the web/WASM build stays untouched.
- CI stays unchanged; Python tests locally through `tools/test_all.ps1`.
- `addins/plenio` under Apache-2.0 with a NOTICE (fits MIT OR Apache-2.0). ComfyUI (GPL) is never copied or bundled, only started as an external process.
- Every bundled asset (also in `vendor/`) needs a row in `ATTRIBUTION.md` (S6).
- Everything in the project is in English: comments, docs, scripts, UI text, commit messages (the owner's rule, 2026-11-06).

## 8. Phases and effort (rough estimate in agent hours)

| Phase | Content | Acceptance | h |
|---|---|---|---|
| 0 Foundation | Git, seams S1–S6 with tests, empty crates, Plenio menu, activation switch | `cargo xtask ci` green | 10–15 |
| 1 Backend | sync script, wrapper, ComfyUI supervisor, system check, model downloads | a song identical to Plenio's | 25–40 |
| 2 MVP song | dialog, folder and tracks, lyrics track and editor, inspector, takes as playlists, staleness display, jobs, undo | a first song entirely in SoundCraft | 35–55 |
| 3 Notes and stems | score↔MIDI, DAW path, tempo/key, stems, browser editor adapter | edit notes, YuE2 sings them | 30–45 |
| 4 Cover | cover from a track or selection, analysis, three vocal modes, Fit Lyrics, A/B | a cover like Plenio's | 20–30 |
| 5 Player | player sidecar, "Send to Player", the way back, taking in a FLAC | a song in the player with lyrics and notes | 12–20 |
| 6 Hardening | parity checklist, fuzzing, update rehearsal, docs | both updates without manual work | 15–25 |

Up to the MVP roughly 70–110 h, in all about 150–230 h.

## 9. Risks

- **The score round trip ABC ↔ MIDI** can lose details; the browser editor would catch that.
- **An own ComfyUI instance:** if your ComfyUI and the add-in's instance run at once, they compete for the GPU; the add-in's instance should unload its models or stop when idle.
- **Comping across takes** works well with the same score (same form), less well with a new score. Takes have tempo maps of their own, so a comp across takes plays against one of them.

## 10. Decisions (all made on 2026-11-05)

| # | Question | Decision |
|---|---|---|
| 9.1 | An own ComfyUI instance or the existing one? | **Own instance** |
| 9.2 | Submit the seams upstream? | ~~Yes, allowed~~ → **No: an own fork with regular merges** (2026-11-06) |
| 9.3 | `origin` → `upstream`, branch `plenio-addin`? | **Yes, allowed**: done |
| – | Change the Plenio project? | **No**: code is copied to SoundCraft |

## 10a. The audio is the master (the owner's decision, 2026-11-06)

Feedback: "one of the two has to be the master", and it should be the audio file, so that it is not changed; bar starts must be exact, so that further MIDI tracks fit later. The ways checked, measured on the owner's real songs:

| Way | Result |
|---|---|
| One exact constant BPM | **Impossible.** The tempo of a YuE2 render wanders smoothly over the song: against the best straight line 150–250 ms in the median song, up to 1 s in the worst. Hits on strong onsets (±15 ms): 26 % |
| Stretching the audio to a constant tempo (MIDI as the master) | Not wanted by the owner: changes the audio file and its length |
| Forcing the render to a fixed tempo | Not possible: Plenio itself only measures the deviation afterwards |
| **A tempo map from the audio** (chosen) | One tempo event per bar, bar lines on the sample. Hits on strong onsets: 44.5 % (median over 173 songs); control half a beat off: 18 %; the earlier warp line: 7 % |
| Tempo events per beat instead of per bar | No gain (82 % against 82 % hits), only more events |

How: `backend/soundcraft_plenio/beats.py` (`POST /scp/v1/beats`) looks for every pulse of the score in the audio: dynamic programming over the onsets, near the warp's line, with even intervals. Onsets alone find the pulse but not which pulse it is (often whole beats off): the score's pitches (weight 16) and the sung words say that. `Take.bars` holds the times per bar, `score::tempo_map` makes the session's tempo map from them, and `songs::conduct` sets it on `take.add` and `take.select` and keeps the owner's MIDI clips on their bars.

💡 On known audio (synthetic clicks with a wandering tempo, mixed meters, 6/8): ±2 ms. The first prototype lay 39 ms early there (window length 1024, time from the window's start); against real songs this did not show, because grid and onsets had the same offset. Now 256 samples and a measured correction of 6.5 ms.

💡 Meters: over 10 % of the 3174 stored songs change meter (4/4 with 9/8, 7/8 …). The map carries every bar's meter; before, one meter held for the whole session.

💡 Limits: only one tempo per session, so it follows the take chosen last. The next take change overwrites tempos changed by hand. Takes from older sessions have no map and stay as they are (import or generate again). Without a warp and an estimate, or when the notes fit clearly worse on the map than on the straight line (by more than 0.05), it stays with the straight line, and the status line says so.

### The start of a song (the owner's feedback, 2026-11-06)

Feedback: the beginning is sometimes bumpy, above all in songs that begin slowly: the "1" is not found at once, and the sync comes only later or not at all. The owner's idea: first find a place in the song that is unambiguous, then reckon back to the start. That is what was built.

Two causes, measured on the owner's songs and with a stress test (71 songs with a sure map, whose first 8 bars were made hard in known ways, so that the true bars are known):

| Cause | Fix | Result |
|---|---|---|
| The search window hung on the warp's line, and the true place can lie outside it. "Das Zentrum": bar 0 searched down to −1.75 s, the true place −2.69 s, so the first 6 bars lay a beat off, with a tempo of 83 to 88 BPM | Window of ±5 s instead of ±2.5 s | The first bars of that song in sync, at 83.2 to 84.0 BPM. Over 108 songs bars off 504 → 458, none loses more than 5 points of its hits on strong onsets |
| Onsets at another tempo in a free intro pull the search away | The measures before the first sure stretch are reckoned back from it | See below; on 108 normal songs only 8 move by more than a quarter of a beat, all at their start. By construction only what lies before the sure stretch changes |

The stress test, first 8 bars with strong onsets 8 % off the song's tempo. "Wrong 1" = the first bar line more than 150 ms off:

| | Songs with a wrong 1 | Median error | Worst | Tempo bump |
|---|---|---|---|---|
| Before | 61 of 71 | 160 ms | 571 ms | 7.4 % |
| Now | 17 of 71 | 52 ms | 106 ms | 2.1 % |
| Before, without usable pitches | 71 of 71 | 544 ms | 1159 ms | 7.5 % |
| Now, without usable pitches | 20 of 71 | 25 ms | 64 ms | 0.7 % |

What makes a stretch sure: four measures in a row whose tempo lies within 2.5 % of the song around them, which the score's pitches do not contradict, and whose pulse shows in the onsets or is confirmed by the pitches. **The tempo condition is the decisive one:** without it a free intro counts as sure, because its onsets are clear.

Tried and rejected, each with numbers on the same songs: a coarse search over the pitches alone, trusting the sung words (their times lie over a second off in some older records: one song went from 1 to 67 bars off, at 116 to 136 BPM); comparing pitches over 4 or 8 pulses instead of one (bars off 458 → 959 and more, because the chord changes at the pulse carry the information); deriving unsure stretches in the middle and at the end of a song as well (it overwrites a real ritardando, and one song went off the beat in its last bars); a weaker pull to the warp's line (better in made-up cases, but it moved paths that were right in the middle of songs); a rule to keep the first search when it lies on the pulse (rescues one normal song and costs the free intro: 20 → 29 songs).

💡 Is the "1" right? Measured from the audio alone, independent of the score: on 149 of 179 songs (83 %) the harmony changes most on the map's 1, clearly so on 102; clearly elsewhere on only 7 (4 %), mostly by small margins, which also fits chords that come a beat early. No systematic error. A song with hardly any change of harmony gives no evidence either way ("Peaceful Electric Current").

💡 Limits: where a start gives no hint at all (no onsets, no pitches), its first bars can only be reckoned at the tempo that follows: 15 of 71 songs more than 150 ms off at the first bar line, 36 ms in the median, a little worse than the first search there (12 of 71, 29 ms). A real change of tempo at a stroke is smoothed by about 50 ms at its bar line.

## 11. Where things are, for the implementation (checked 2026-11-05)

**SoundCraft**

- Command registry: `crates/engine/src/cmd.rs`: `command_specs()` (static `OnceLock`), `find_command`, macro `cmd!`; `CommandSpec` fields are `pub` (`&'static str`, function pointers).
- Engine API: `crates/engine/src/lib.rs`: `session()`, `session_mut()` (pub), `execute()`, `execute_merged()`.
- Session: `crates/model/src/session.rs`: `Session`, `from_json` parses without a `Value` tree, unknown keys are ignored; `EditState.flags`/`values` (used by Score Setup).
- Track/playlist/clip: `crates/model/src/track.rs`, `crates/model/src/clip.rs` (`ClipContent::Audio|Midi|Video`).
- Playlist lanes with comping: `crates/ui-egui/src/edit_window/tracks.rs` (`playlist_lanes`).
- Menu: `crates/ui-egui/src/menus.rs` (`tree()`, `UI_COMMANDS`, `menu_bar`).
- Docking: `crates/ui-egui/src/docking.rs` (`Panel` enum).
- App entry: `apps/soundcraft/src/main.rs` (`SoundApp::new(engine, player, services())`).
- Notation: `crates/engine/src/score.rs`, `crates/ui-egui/src/panels/score_editor.rs`.
- Tempo: `crates/time/src/tempo.rs` (`TempoMap`), metronome: `crates/mix/src/click.rs` (every click through the tempo map).
- Reusable commands: `track.playlist_new`, `track.playlist_select`, `track.playlist_duplicate`, `track.playlist_delete_unused`, `track.move_to_folder`, `track.rename`, `track.color`, `track.comments`, `event.tempo`, `event.add_key_change`, `file.import_midi`, `clip.rename`, `clip.color`.
- Layer check: `xtask/src/main.rs` (`LAYERS`); asset check: `assets()` (directory rows cover whole trees).
- Already in `Cargo.lock`: `ureq 3.5.0`, `sha2 0.10.9`, `zip 9.1.3`, `flate2 1.1.10`.

**Plenio**

- Song API: `plenio/comfy/song_api.py`, `plenio/core/song_api.py`, docs `docs/api/README.md` (v1.3; no review stops).
- Routes for editor and tools: `plenio/comfy/routes.py` (`ROUTES`: score analyze/transform, midi import/export, musicxml, lyrics analyze, sheet resolve, templates, brief fields, presets, eq, export sheet-music, records, player open).
- Entry: `plenio/comfy/extension.py` (`PlenioExtension.on_load`), node list `plenio/comfy/nodes/__init__.py` (`NODES`).
- Subgraphs: `subgraphs/` (Write Song, YuE2 Plan, YuE2 Render, YuE2 Takes, Stems, Transcribe Score, Fix Misheard Words, Master, Arrange, Cover Art, Refine).
- Models: `resources/models.toml`, downloader `plenio/core/assets/fetch.py`.
- Starting ComfyUI: `plenio/player/studio.py` (finding Python, arguments, log, idle stop, `comfyui-start.json`), player start: `plenio/player/launch.py`.
- Stems: `plenio/comfy/nodes/stems.py` (Separate Stems, Stem Mixer, Stems as MIDI).
- Release record: `resources/schemas/record-1.schema.json`; the record inside a FLAC: `plenio/core/release.py` (`read_project`).

## State on the evening of 2026-11-05 (point to continue from)

- [x] **Decision:** generation runs straight through Plenio's **Song API** (`/plenio/api/v1`: jobs, templates, briefs, uploads), not through an own stage API. The wrapper `addins/plenio/backend/soundcraft_plenio` loads Plenio unchanged and only adds `/scp/v1` (info, models without MiniMax) and a parent watchdog (`SCP_PARENT_PID`).
- [x] Phase 1: studio (`crates/backend`: discover, instance, client, song, studio). An own instance with `--base-directory`, models from `F:\ComfyUI\models`, `PLENIO_PLAYER_STATE` in the add-in's folder. Checked live: start and stop in 10 s, a real job (a 61 s instrumental in 133 s).
- [x] Phase 2: `plenio.song.new/set/forget`, `plenio.take.add/select`; plan rules (new words → new notes); UI with menu, New Song dialog (250 templates), inspector (takes, Generate/More, lyrics editor with YuE2's tags and a check through `/plenio/lyrics/analyze`, brief form dynamically from `/templates`, seeds), a badge in the track header, sections in the song lane, studio and model window with downloads.
- [x] Phase 3 (part): the score as Plenio's MIDI on muted note tracks (Melody, Instrument Line, Chords); edited notes are sent back with Plenio's conductor track byte for byte (`/plenio/score/midi/import`) and sung. Stems still open.
- [x] End to end through SoundCraft's UI (`cargo run -p soundcraft-plenio-ui --example plenio_e2e -- <folder>`): activate → New Song → take after 241 s ("The Heavy Air", 94.8 s, 8 sung lines, 4 sections, 74 BPM) → notes on Melody/Instrument Line/Chords → stems through the inspector in 21 s (vocals, drums, bass, other, rest; song track muted) → mix sent to the player, player started
- [ ] Open: browser score editor (Plenio's Vue editor with a SoundCraft adapter), "Open in SoundCraft" from the player, intermediate stops (review) and LoRAs (not in Song API v1), the studio's idle stop, the inspector as a dock panel, `soundcraft-cli` (headless/MCP) with `plenio.*`
- 💡 egui_kittest aborts on missing glyphs, and the app then only shows replacement boxes: no symbols like ✦ ★ ● ▾ ✓ in UI texts.

## Change log

| Date | Change |
|---|---|
| 2026-11-05 | Plan made, decisions 9.1–9.3 entered; Git set up (`upstream`, branch `plenio-addin`); missing Rust toolchain noted |
| 2026-11-05 | Rust 1.99.1 installed; baseline measured (3 Windows failures in `soundcraft-cli`, already before the add-in); phase 0 done: seams S1–S6, four add-in crates, Plenio menu and activation, offscreen screenshots checked; phase 1 started: sync script and first copy of Plenio 1.5.0 |
| 2026-11-05 | Phases 1–3 and 5: studio, Song API connection, songs/takes/notes/stems, player, import; Plenio's unit tests against the copy: 1980 passed, 1 skipped; end to end through the UI; branch `extension-api` with the seams |
| 2026-11-06 | Phase 4 live: cover through the UI (309 s), original muted on the first cover take |
| 2026-11-07 | Phase 7, release 0.1.0-alpha, see [phase 7](#phase-7-release-010-alpha-the-owners-request-of-2026-11-07): SoundCraft `bb0e070` merged; the tour through the real UI found five faults, the code review seven more (one of them by the test harness's accessibility check), all fixed; the UI has 27 tests now, the commands 16 + 10, with tests for the faults (late work, another song's tempo and a word typed into the brief shown to fail without their fix; the hidden button and the wide window checked in renders); more of the Song API in the dialogs; stems right away; docs, media, teaser, announcements, the Windows package |
| 2026-11-06 | The owner's feedback "the start of a song is bumpy, the 1 is not found at once": a wider search, and the bars before the first sure stretch reckoned back from it, see [The start of a song](#the-start-of-a-song-the-owners-feedback-2026-11-06). Checked through the app on the owner's four songs, and with a stress test with a known truth |
| 2026-11-06 | The owner's request: everything in the project in English. This plan and [FORK.md](FORK.md) translated; no German left outside the byte-exact copy in `vendor/` |
| 2026-11-06 | The owner's feedback "the metronome runs apart": the audio is the master and the session's tempo map follows it, see [section 10a](#10a-the-audio-is-the-master-the-owners-decision-2026-11-06). Live through the app, measured from outside on the audio files: A Winter Shroud 93 % of clicks within 15 ms of an onset, median 2.6 ms (best constant BPM 37 %, up to 308 ms off); Das Herz kommt an 90 %, 3.2 ms (58 %, 164 ms); Wo das Schweigen hält 75 %, 7.2 ms (43 %, 854 ms) |
| 2026-11-06 | The owner's feedback "importing a FLAC: nothing arrives", three causes: the file dialog ignored the extensions its caller named and offered only audio (`.plenio.json` could not be chosen); `import_record` read the file as text; `engine.message` reaches no UI, so all of the add-in's messages ended up only in the log. Now: a FLAC with an embedded record is read (`backend/src/release.rs`), the dialog honours the extensions (`open_filter`), messages also go to the status line through `say`. Live with "Das Herz kommt an" (`examples/plenio_import_e2e.rs`): the FLAC alone and in its own folder in 10–12 s after the studio's start, 153 s of audio, 25 lines, 7 sections, 243 + 194 notes, 22 fields; a new take in 193 s; stems in 47 s; the folder `151 songs` unchanged |
| 2026-11-06 | The owner's feedback: (1) inspector height resizable, lyrics grow with it. (2) Audio, lyrics and notes lie together: Plenio's measured warp from the release record (`timing[0].warp`, without words an estimate through `POST /scp/v1/align`, since replaced by `/scp/v1/beats`); the score's first bar on a bar line, the audio placed against it; stems and player follow. Measured on "A Winter Shroud": sung lines against notes median 0.05 s instead of 1.3 s; live on "Sentences in the Shower" (warp 1.009/−1.71): median 0.07 s, worst line 0.38 s. Plenio's `follow()` path was worse than the straight line against what is heard (median 0.12 s), hence the straight line. (3) The first take's MIDI clips were measured with the old session tempo (120 instead of 84 BPM: ending at 70 %) and only to the last note of their own track: tempo first, every clip to the score's end. Data checked: score, MIDI and SoundCraft's reader have the same 143/240/280 notes. (4) An own fork instead of an upstream PR, see [FORK.md](FORK.md); first real merge of `upstream/main` (5 commits, 1 conflict in `dirty.rs`), script also rehearsed in throw-away clones |
