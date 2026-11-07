# Attribution

Every asset bundled with or committed to SoundCraft is listed here with its author, source and
license. `cargo xtask assets` fails CI when a tracked asset file has no row.

**Rule:** no Avid, Pro Tools, Adobe or other proprietary icons, images, sounds or presets — ever.
Assets must be original, public domain (CC0) or permissively licensed. See `AGENTS.md`.

## Icons

All UI icons (tools, transport, track buttons) are drawn procedurally in
`crates/ui-egui/src/icons.rs` by the SoundCraft contributors (MIT OR Apache-2.0). No UI icon image
files are used. The app icon (`assets/app-icon/`, a singing nightingale drawn as original SVG by
the SoundCraft contributors) is listed under Files below.

## Audio

The demo session's audio (drums, bass, pad) and its MIDI parts are synthesised in code in
`crates/engine/src/demo.rs` by the SoundCraft contributors (MIT OR Apache-2.0). No sample files
are bundled.

## Fonts

SoundCraft bundles no font files. It uses the default fonts shipped inside the `egui` crate
(Ubuntu-Light: Ubuntu Font Licence 1.0; Hack: MIT; Noto Emoji: OFL-1.1; emoji-icon-font: MIT)
and, at runtime, the operating system's own UI fonts when available (never redistributed).

## Bundled egui font icons

These dependency fonts are embedded by the pinned egui font definitions; no font file is added
here. The subset uses default_fonts; the parent face uses monochrome_emoji_fonts.

| Asset | Author | Source | Licence |
|---|---|---|---|
| `epaint_default_fonts/fonts/egui-icons.ttf` | John Slegers (emoji-icon-font) | https://github.com/storytold/egui/blob/6d518fc799681571963842f95b55a6b68431b15a/crates/epaint_default_fonts/fonts/egui-icons.txt; original https://github.com/jslegers/emoji-icon-font | MIT (complete copyright and permission text in NOTICE) |
| `epaint_default_fonts/fonts/emoji-icon-font.ttf` | John Slegers | https://github.com/storytold/egui/blob/6d518fc799681571963842f95b55a6b68431b15a/crates/epaint_default_fonts/fonts/emoji-icon-font-mit-license.txt; original https://github.com/jslegers/emoji-icon-font | MIT (complete copyright and permission text in NOTICE) |

## Files

| Path | Author | Source | License |
|---|---|---|---|
| `assets/app-icon/icon.svg` | SoundCraft contributors | original (hand-placed SVG paths; placeholder app icon) | MIT OR Apache-2.0 |
| `packaging/macos/dmg/` (all files) | @XusBadia | original (macOS DMG window background and layout, from the app icon; see `packaging/macos/dmg/README.md`) | MIT OR Apache-2.0 |
| `assets/app-icon/soundcraft-1024.png` | SoundCraft contributors | original, rendered from `icon.svg` | MIT OR Apache-2.0 |
| `assets/app-icon/soundcraft-macos-512.png` | SoundCraft contributors | original, rendered from `icon.svg` | MIT OR Apache-2.0 |
| `assets/app-icon/soundcraft.icns` | SoundCraft contributors | original, rendered from `icon.svg` | MIT OR Apache-2.0 |
| `assets/app-icon/soundcraft.ico` | SoundCraft contributors | original, rendered from `icon.svg` | MIT OR Apache-2.0 |
| `assets/app-icon/hicolor/` | SoundCraft contributors | original, rendered from `icon.svg` (16–512 px PNGs and the scalable SVG) | MIT OR Apache-2.0 |
| `docs/images/` | SoundCraft contributors | screenshots of SoundCraft rendered from the synthesised demo session | MIT OR Apache-2.0 |
| `crates/audio-io/tests/fixtures/` | SoundCraft contributors | original test tones and silence generated with ffmpeg (sine) or by hand; commands in `crates/audio-io/tests/fixtures/README.md` | MIT OR Apache-2.0 |
| `addins/plenio/docs/media/logo.svg` | Johannes Plenio (Plenio add-in) | original: Plenio's mark (a P of three lines) with a waveform, drawn as SVG | Apache-2.0 (no rights to the name or mark as a trademark, Apache-2.0 section 6) |
| `addins/plenio/docs/media/logo-512.png` | Johannes Plenio (Plenio add-in) | original, rendered from `logo.svg` by `addins/plenio/tools/media/render_brand.py` | Apache-2.0 (as `logo.svg`) |
| `addins/plenio/docs/media/banner.png` | Johannes Plenio (Plenio add-in) | original, rendered from `addins/plenio/docs/media/src/banner.html` (text in Montserrat, OFL-1.1, not shipped) | Apache-2.0 (as `logo.svg`) |
| `addins/plenio/docs/media/social-preview.png` | Johannes Plenio (Plenio add-in) | original, rendered from `addins/plenio/docs/media/src/social.html` (text in Montserrat, OFL-1.1, not shipped) | Apache-2.0 (as `logo.svg`) |
| `addins/plenio/docs/media/` | Johannes Plenio and the add-in's contributors | every other file: screenshots and animations of SoundCraft with the add-in, rendered offscreen by `addins/plenio/crates/ui/examples/plenio_tour.rs` and `plenio_shot.rs` from a demo session the add-in made (`addins/plenio/tools/media/make_media.py`) | MIT OR Apache-2.0 |
| `addins/plenio/vendor/` | Johannes Plenio (Plenio Music Production System) | copied unchanged from github.com/jplenio/Plenio-Music-Production-System by `addins/plenio/tools/sync_plenio.py` (commit in `VENDOR.toml`): template thumbnails, the Plenio Player's app icons | Apache-2.0 (`addins/plenio/vendor/plenio/LICENSE`, `NOTICE.md`; bundled libraries in `THIRD_PARTY.md`) |
