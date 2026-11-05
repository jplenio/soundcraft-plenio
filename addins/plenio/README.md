# Plenio add-in for SoundCraft

YuE2 · Song, YuE2 · Cover and the Plenio Player from the
[Plenio Music Production System](https://github.com/jplenio/Plenio-Music-Production-System) by
Johannes Plenio, built into SoundCraft. MiniMax is not part of it.

The plan, the decisions and the progress are in [docs/PLAN.md](docs/PLAN.md).

## How it fits into SoundCraft

Everything of the add-in lives in this folder. SoundCraft itself only has three general entry points
for add-ins (see [docs/architecture.md › Extensions](../../docs/architecture.md#extensions)):

| Entry point | Where | The add-in uses it for |
|---|---|---|
| `Session::extensions` | `crates/model` | its songs and their tracks, under the key `plenio` |
| `register_extension_commands` | `crates/engine` | its commands `plenio.*` |
| `UiExtension` | `crates/ui-egui` | the Plenio menu, its windows, its drawing on tracks |

The app turns the add-in on with the Cargo feature `plenio` of `apps/soundcraft` (on by default in
this branch): `cargo build -p soundcraft --no-default-features` builds SoundCraft without it.

## Crates

| Crate | Layer | What it holds |
|---|---|---|
| `crates/project` (`soundcraft-plenio-project`) | 2 | the songs and the roles of their tracks, read from and written to the session |
| `crates/backend` (`soundcraft-plenio-backend`) | 4 | the add-in's settings; to come: the ComfyUI instance, the stage API client, model downloads |
| `crates/commands` (`soundcraft-plenio-commands`) | 4 | the engine commands `plenio.*` |
| `crates/ui` (`soundcraft-plenio-ui`) | 6 | the menu, the windows, the track drawing |

Every crate follows SoundCraft's rules: `[lints] workspace = true`, the crate-level `deny` of
`unwrap`/`expect`/`panic`, no `unsafe`, everything read from files or the backend treated as hostile.

## Licences

The Rust code here is under SoundCraft's licence (MIT OR Apache-2.0). Plenio's code, copied into
`vendor/` in the next milestone, stays under its own Apache-2.0 licence with its NOTICE. The models
have licences of their own: YuE2 and SheetSage2 are CC BY-NC 4.0 (non-commercial).
