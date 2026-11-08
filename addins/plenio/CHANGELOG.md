# Changelog of the Plenio add-in

The add-in's versions are its own (`addins/plenio/crates/*/Cargo.toml`); the SoundCraft version it
was released on is named with each one. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and versions follow [Semantic Versioning](https://semver.org/). Releases are tagged `plenio-v<version>`.

## [0.1.1-alpha] - 2026-11-08

On SoundCraft 0.18.0 (its release tag `v0.18.0`, `5ff012a`) with Plenio 1.5.1 (its release tag `v1.5.1`,
`2e745f5`): the add-in on both releases. Its own code is unchanged.

### Changed

- **SoundCraft 0.18.0.** 0.1.0-alpha was built on SoundCraft's `main` at `bb0e070`, which SoundCraft then
  released as 0.18.0 with no change but its version. The program now names itself 0.18.0.
- **Plenio 1.5.1** in `vendor/`. The copy in 0.1.0-alpha was taken from the commit just before that release
  (`f269728`), so 1.5.1's changes were already in it: notes fitted to their lyrics, locked tracks, your own
  lyrics sung exactly as written, Gemma 4 12B as the default writer. New are its version, its changelog and
  its rebuilt player page. The studio installs the new copy by itself at its next start.
- **The videos on YouTube:** the teaser, the tutorial and a playlist for the videos to come, linked from both
  READMEs, the tutorial and the release's text. The launch texts fit each channel's limits.
- `tools/update_soundcraft.ps1 -Version 0.18.0` merges a SoundCraft release (its tag) instead of `main`.
- The tests that named Plenio's version compare it with the version the copy declares, so a sync of a newer
  Plenio needs no change to them.

## [0.1.0-alpha] - 2026-11-07

The first release, on SoundCraft 0.17.0 (upstream `bb0e070`) with Plenio 1.5.0. **Alpha:** it works
end to end and is checked by its tests and by real songs made through the UI, but its data and
commands may still change, and it has been used on Windows only.

### Added

- **Plenio menu** in SoundCraft: activate the add-in (the models' licences once), make songs and
  covers, bring in Plenio songs, the song inspector, the Plenio Player, the studio and its models,
  Getting Started, About.
- **The studio:** a ComfyUI instance of the add-in's own with Plenio inside, started and stopped by
  SoundCraft, on the ComfyUI and the models already on the computer. A crashed ComfyUI is noticed
  within seconds. **Studio and Models** lists every model the YuE2 templates need and downloads the
  missing ones, one by one or all at once.
- **New Song:** 250 searchable styles with their sound and shape, an idea or your own lyrics, vocals,
  length, language, title, and every other field of Plenio's Song API under **More options**
  (genre, mood, tempo, key, meter, voice, theme, arrangement, creativity, lyrics fidelity, HQ
  mastering, cover art, writer model …). A text field left empty takes the style's value, shown as
  its hint.
- **New Cover from Selected Track:** a cover of any recording on an audio track, in another style,
  with the original lyrics, new lyrics or as an instrumental; a selection on the track becomes the
  excerpt.
- **The song on tracks:** a folder track per song with the **Lyrics** (one clip per sung line),
  the **Song** (each take on a playlist of its own) and the score as MIDI (**Melody**, **Instrument
  Line**, **Chords**); the song's sections drawn on its lane, its take and state on its header.
- **The audio is the master:** every measure of the score is found in the take's audio and becomes a
  tempo change on its bar line, so metronome, grid and any MIDI you add stay on the music. The first
  bars are reckoned back from the first stretch of the song that is sure.
- **Make again:** change the lyrics, the notes on the score tracks or the brief, and **Generate**
  makes what the changes call for (new words get new notes, your notes are sung as written, a new
  brief writes the song anew, nothing changed is a new take). Seeds can be locked.
- **Stems:** vocals, drums, bass, other and the rest on tracks of their own, per take; optionally
  **right away** for every new take.
- **Import Plenio Song:** a song Plenio made, from its FLAC (which carries the whole song) or its
  `.plenio.json`, to edit and make again.
- **Send the mix to the Plenio Player**, with your effects, the take's lyrics and notes.
- Every change is a command (`plenio.*`): one undo step, reachable from the control channel and MCP.
- Documentation: README, tutorial (also as a video), developer guide, the plan and the fork's guide; a tour
  through the UI that renders every screenshot (`examples/plenio_tour.rs`), `plenio_shot` for every dialog
  without a studio, and the media tools (`tools/media/`).
- A portable Windows package with the add-in's Python files beside the program (`tools/package_windows.ps1`)
  and its smoke test (`tools/smoke_package.ps1`).

### Fixed during the alpha

- Text fields of the brief and the ComfyUI folder kept no typed character (the edit buffer was made
  anew every frame).
- Number fields of the brief ignored their ranges (the API names them `minimum` and `maximum`).
- Leaving a field without a change marked the brief as changed.
- "What it is about" replaced the style's description of the sound; it now is the idea of the lyrics.
- A second take of a song came back as "Title (2)": every take now has a release folder of its own.
- The New Song dialog hid Make the Song below its fold; its buttons are always in view.
- A take or stems that arrived after their session was closed landed in the session open then, even on
  another song with the same id; late work now lands only on the song that asked for it.
- A second song with a tempo of its own (a cover in the same session) made the first song's notes count as
  edited; notes are now read in their own take's bars.
- The studio's window grew as wide as the screen with the catalogue's long model descriptions.

[0.1.1-alpha]: https://github.com/jplenio/soundcraft-plenio/releases/tag/plenio-v0.1.1-alpha
[0.1.0-alpha]: https://github.com/jplenio/soundcraft-plenio/releases/tag/plenio-v0.1.0-alpha
