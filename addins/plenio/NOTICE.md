# NOTICE

Plenio add-in for SoundCraft
Copyright 2026 Johannes Plenio

## What is licensed how

| Part | Licence |
|---|---|
| The add-in's code and documentation: everything in `addins/plenio/` except `vendor/` | MIT OR Apache-2.0, at your option, like SoundCraft (`LICENSE-MIT` and `LICENSE-APACHE` at the root of this repository) |
| `vendor/plenio/`: the Plenio Music Production System, copied unchanged | Apache-2.0 (`vendor/plenio/LICENSE`, `vendor/plenio/NOTICE.md`, its bundled libraries in `vendor/plenio/THIRD_PARTY.md`) |
| The logo, banner and social preview in `docs/media/` | Apache-2.0 |
| The screenshots and animations in `docs/media/` | MIT OR Apache-2.0 |

The Apache License grants no rights to the name "Plenio" or its logo as marks (section 6): use them to
refer to this project, not to name or brand another one.

## What the add-in uses but does not ship

- **SoundCraft** by the ArtCraft Team and the SoundCraft contributors (MIT OR Apache-2.0): this
  repository is a fork of it. This fork is not made, sponsored or endorsed by the ArtCraft Team.
- **ComfyUI** (GPL-3.0): the add-in starts the ComfyUI installed on the computer as a program of its
  own and installs Plenio into an instance of it; no ComfyUI code is part of this repository.
- **The models** are downloaded from their official sources, never shipped, and have licences of their
  own. YuE2-3B, the YuE2 VAE and SheetSage2 are **CC BY-NC 4.0**: songs made with them are for
  non-commercial use only, with attribution. The add-in asks to accept this once, when it is activated.
  Every song's release record (`<song>.plenio.json`) names the licences of the models it was made with.

## Covers

A cover uses somebody else's composition. The models' licences do not cover those rights: publishing a
cover generally needs the permission of the rights holders, even when the recording was made legally.
Only cover recordings you are allowed to use.
