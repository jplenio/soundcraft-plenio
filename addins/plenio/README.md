# Plenio add-in for SoundCraft

YuE2 · Song, YuE2 · Cover and the Plenio Player from the
[Plenio Music Production System](https://github.com/jplenio/Plenio-Music-Production-System) by
Johannes Plenio, built into SoundCraft. MiniMax is not part of it.

The plan, the decisions and the progress are in [docs/PLAN.md](docs/PLAN.md); how this fork is kept
up to date with SoundCraft is in [docs/FORK.md](docs/FORK.md).

## Using it

1. **Plenio › Activate Plenio Add-in…** - accept the models' licences (YuE2 and SheetSage2 are
   CC BY-NC 4.0, non-commercial). The add-in starts its **studio**: a ComfyUI instance of its own with
   Plenio inside, using the ComfyUI and the models already on this computer (found the way Plenio last
   started ComfyUI). Your own ComfyUI and Plenio stay as they are. **Plenio › Studio and Models…**
   shows the studio, every model the YuE2 templates need, and downloads missing ones.
2. **Plenio › New Song…** - a template (250), an idea or your own lyrics, vocals, length, language.
   SoundCraft gets a folder track named after the song with its tracks:
   - the **song lane** (the folder) shows the song's sections; its header the take and what changed,
   - **Lyrics**: one clip per line, where it is sung,
   - **Song**: the take's audio - every take on a playlist of its own,
   - **Melody**, **Instrument Line**, **Chords**: the score as MIDI (muted; unmute to hear the notes),
     over the whole length of the score.

   **The audio is the master, and the session's tempo follows it.** A YuE2 render keeps no steady tempo:
   against the best single tempo its beats wander by a quarter of a second in the median song and by a
   second in the worst, so no BPM value, however exact, keeps a metronome on it. Every measure of the
   score is found in the audio (its onsets, the score's pitch classes, the sung words), and each becomes
   a tempo change on its bar line. The session's bars are then the take's: metronome, grid and any MIDI
   you add stay on the audio, the audio is not changed, and the notes stay on the grid as written. Meter
   changes in the score become meter changes in the session. Each take brings its own tempo map when
   you choose it; your own MIDI clips keep their bar and beat. Takes and stems keep their own place on
   their own playlists. A take whose bars cannot be measured (the status line says so) lies on the
   straight line Plenio measured, with its notes stretched to match.
3. The **Plenio Song** inspector: choose a take, change the lyrics (YuE2's section tags as buttons;
   *Check* runs Plenio's own rules), the brief (every field of the Song API's template), lock seeds.
   **Generate** does what the changes call for: new words get new notes, notes you changed on the score
   tracks are sung as written, a changed brief writes the song anew, nothing changed is a new take.
4. **Split this take into stems** - vocals, drums, bass, other and the rest (together exactly the
   take), on tracks of their own; the song track is muted while a take with stems plays.
5. **Plenio › New Cover from Selected Track…** - a cover of the recording on an audio track; an edit
   selection on it becomes the excerpt.
6. **Send the mix to the Plenio Player** - the session's mix with your effects, with the take's lyrics
   and notes, in the Plenio Player; **Plenio › Open Plenio Player** shows every song the studio made.
7. **Plenio › Import Plenio Song…** - a song Plenio made, to edit and make again: its FLAC (which
   carries the whole song) or its `.plenio.json`. The song comes in when the studio is ready, and
   nothing is written into the folder it came from. Plain audio comes in with **File › Import Audio**.

Every change goes through the add-in's commands (`plenio.*`), one undo step each; the control channel
reaches them too (`plenio.status`, `plenio.song.new`, `plenio.take.select` …).

## How it fits into SoundCraft

Everything of the add-in lives in this folder. SoundCraft itself only has three general entry points
for add-ins (see [docs/architecture.md › Extensions](../../docs/architecture.md#extensions)):

| Entry point | Where | The add-in uses it for |
|---|---|---|
| `Session::extensions` | `crates/model` | its songs, takes and their tracks, under the key `plenio` |
| `register_extension_commands` | `crates/engine` | its commands `plenio.*` |
| `UiExtension` | `crates/ui-egui` | the Plenio menu, its windows, its drawing on tracks |

The app turns the add-in on with the Cargo feature `plenio` of `apps/soundcraft` (on by default in
this fork): `cargo build -p soundcraft --no-default-features` builds SoundCraft without it.

Songs are made by Plenio's **Song API** (`/plenio/api/v1`) in the add-in's own ComfyUI instance;
the editor's routes (`/plenio/score/midi/*`, `/plenio/lyrics/analyze`) and `/plenio/api/v1/from-record`
serve the notes, the lyrics check and imports. The add-in's wrapper adds only `/scp/v1` (who it is,
the models without MiniMax, stems, and where every bar of a score lies in its take).

## Folders

| Folder | What it holds |
|---|---|
| `crates/project` (`soundcraft-plenio-project`, L2) | songs, takes, the roles of their tracks, and what the next take is made from |
| `crates/backend` (`soundcraft-plenio-backend`, L4) | settings, finding ComfyUI, the instance, the Song API client, the player, model downloads |
| `crates/commands` (`soundcraft-plenio-commands`, L4) | the engine commands `plenio.*`, the score on MIDI tracks and back |
| `crates/ui` (`soundcraft-plenio-ui`, L6) | the menu, the windows, the track drawing; `examples/plenio_e2e.rs` makes a whole song through the UI |
| `backend/soundcraft_plenio` | the ComfyUI package: Plenio's extension unchanged, plus `/scp/v1` and a watch on SoundCraft's process |
| `vendor/plenio` | Plenio, copied unchanged (`tools/sync_plenio.py`; `VENDOR.toml` says from which commit) |
| `tools` | `sync_plenio.py` (copy Plenio again, `--check`), `update_soundcraft.ps1` (upstream updates), `test_all.ps1` (every check) |

Every crate follows SoundCraft's rules: `[lints] workspace = true`, the crate-level `deny` of
`unwrap`/`expect`/`panic`, no `unsafe`, everything read from files or the studio treated as hostile,
nothing that waits on the UI or audio thread.

## Licences

The Rust and Python code here is under SoundCraft's licence (MIT OR Apache-2.0). Plenio's code in
`vendor/` stays under its own Apache-2.0 licence with its NOTICE. The models have licences of their
own: YuE2 and SheetSage2 are CC BY-NC 4.0 (non-commercial).
