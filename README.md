# SoundCraft with Plenio

A fork of [SoundCraft](https://github.com/storytold/soundcraft), the open-source digital audio
workstation written in Rust, with the
[Plenio Music Production System](https://github.com/jplenio/Plenio-Music-Production-System) built in
as an add-in: songs and covers made with YuE2, their lyrics, notes, takes and stems as ordinary tracks
of the session, and the Plenio Player.

This fork is based on SoundCraft by the ArtCraft team. It is not made, sponsored, endorsed or
supported by them: problems with this fork belong in this repository, not in SoundCraft's.

## What the add-in adds

- **Plenio › New Song…** and **New Cover from Selected Track…**: a folder track with the song's tracks.
- **Lyrics** on a track of their own, one clip per line where it is sung.
- **Notes** on MIDI tracks (melody, instrument line, chords), lying on the audio and the bars of the
  session, to read, edit and have sung as written.
- **Takes** as playlists: change the lyrics, the notes or the brief at any time and generate again.
- **Stems** on tracks of their own, with effects and edits like any other track.
- **Send the mix to the Plenio Player**, with your effects, its lyrics and its notes.

Everything else is SoundCraft: audio and MIDI tracks, plug-ins, automation and the mixer work next to
the song's tracks as usual. Its manual, feature tour and shortcuts are in
[SoundCraft's README](https://github.com/storytold/soundcraft#readme) and in [`docs/`](docs/).

How to use the add-in: [`addins/plenio/README.md`](addins/plenio/README.md).

## Getting started

```sh
git clone https://github.com/jplenio/soundcraft-plenio
cd soundcraft-plenio
cargo run --release -p soundcraft -- --demo
```

You need Rust 1.95 or later (on Linux also the ALSA headers). Making songs needs
[ComfyUI](https://github.com/comfyanonymous/ComfyUI) 0.37 or later and a graphics card; the add-in
finds an installed ComfyUI, runs an instance of its own and downloads the models it needs.

`cargo build -p soundcraft --no-default-features` builds SoundCraft without the add-in.

## How this fork stays up to date

The add-in lives in [`addins/plenio/`](addins/plenio/); SoundCraft's own code has only a few small
entry points for it. So SoundCraft's changes can be merged at any time:

```sh
pwsh addins/plenio/tools/update_soundcraft.ps1 -Preview   # what would come, and does it conflict?
pwsh addins/plenio/tools/update_soundcraft.ps1 -Push      # merge, check everything, push
```

The branches, what differs from SoundCraft and what to do on a conflict:
[`addins/plenio/docs/FORK.md`](addins/plenio/docs/FORK.md).

## License and credits

SoundCraft is Copyright (c) 2026 ArtCraft Team and the SoundCraft contributors, under the
[MIT License](LICENSE-MIT) or the [Apache License 2.0](LICENSE-APACHE), at your option. Required
notices are in [NOTICE](NOTICE), third-party material in [ATTRIBUTION.md](ATTRIBUTION.md). The add-in's
code is under the same licenses.

Plenio is by Johannes Plenio, under the Apache License 2.0: its copy in
[`addins/plenio/vendor/plenio`](addins/plenio/vendor/plenio) keeps its own license and notices.

The models the add-in downloads have licenses of their own: YuE2 and SheetSage2 are CC BY-NC 4.0, for
non-commercial use only. You accept them when you activate the add-in.

The ArtCraft name, wordmark and logos are trademarks of the ArtCraft Team and are not part of this
fork; their terms are in [`docs/brand/LICENSE-brand.txt`](docs/brand/LICENSE-brand.txt).
