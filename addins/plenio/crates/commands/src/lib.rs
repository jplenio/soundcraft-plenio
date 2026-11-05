//! The Plenio add-in's engine commands (`plenio.*`). They register with SoundCraft's command
//! registry as the app starts ([`register`]), so the add-in's menus, the CLI, the control channel
//! and MCP all run the same ids, with undo like any other command.
//!
//! A command that makes or changes songs needs the add-in to be activated (its setup done); the
//! UI reports that with [`set_activated`].
#![deny(clippy::unwrap_used, clippy::expect_used, clippy::panic, clippy::unimplemented, clippy::todo, clippy::unreachable)]

use serde_json::{Value, json};
use soundcraft_engine::cmd::{CommandSpec, always};
use soundcraft_engine::{Engine, EngineError, Result};
use soundcraft_plenio_project::Project;
use std::sync::atomic::{AtomicBool, Ordering};

/// The add-in's version, as its commands report it.
pub const VERSION: &str = env!("CARGO_PKG_VERSION");

static ACTIVATED: AtomicBool = AtomicBool::new(false);

/// Whether the add-in is activated: its setup is done and its commands may make songs.
pub fn activated() -> bool {
    ACTIVATED.load(Ordering::Relaxed)
}

/// Set by the UI when the add-in is activated or deactivated.
pub fn set_activated(on: bool) {
    ACTIVATED.store(on, Ordering::Relaxed);
}

/// Enabled only while the add-in is activated.
pub fn when_activated(_: &Engine) -> std::result::Result<(), String> {
    if activated() { Ok(()) } else { Err("activate the Plenio add-in first (Plenio › Activate Plenio Add-in…)".into()) }
}

/// The add-in's commands.
pub fn specs() -> Vec<CommandSpec> {
    vec![soundcraft_engine::cmd!(query "plenio.status", "Plenio Status", [], None, "{}", always, status)]
}

/// Add the commands to SoundCraft's registry. Call it once as the app starts, before the first
/// command runs; a failure is logged and the app goes on without them.
pub fn register() {
    if let Err(e) = soundcraft_engine::cmd::register_extension_commands(specs()) {
        log::error!("Plenio commands not registered: {e}");
    }
}

/// `plenio.status`: whether the add-in is activated, and the songs the session holds.
fn status(e: &mut Engine, _: &Value) -> Result<Value> {
    let project = Project::load(e.session()).map_err(|err| EngineError::Unsupported(err.to_string()))?;
    let songs: Vec<Value> = project.songs.iter().map(|s| json!({"id": s.id, "kind": s.kind, "title": s.title, "tracks": s.tracks.len()})).collect();
    Ok(json!({"addin": "plenio", "version": VERSION, "activated": activated(), "songs": songs}))
}

#[cfg(test)]
mod tests {
    use super::*;
    use soundcraft_plenio_project::{Song, SongKind};

    #[test]
    fn status_names_the_songs_of_the_session() {
        let mut e = Engine::default();
        let mut p = Project::default();
        p.songs.push(Song { id: 1, kind: SongKind::Song, title: "Night Drive".into(), tracks: Vec::new() });
        p.store(e.session_mut()).unwrap();
        // Called directly: the registry of this test binary is SoundCraft's own.
        let v = status(&mut e, &json!({})).unwrap();
        assert_eq!(v["songs"][0]["title"], "Night Drive");
        assert_eq!(v["songs"][0]["kind"], "song");
        assert!(v["activated"].is_boolean());
    }

    #[test]
    fn unreadable_data_is_an_error_not_a_panic() {
        let mut e = Engine::default();
        e.session_mut().set_extension(soundcraft_plenio_project::KEY, "{").unwrap();
        assert!(status(&mut e, &json!({})).is_err());
    }

    #[test]
    fn the_command_ids_are_valid_extension_ids() {
        for spec in specs() {
            assert!(soundcraft_engine::cmd::extension_command_id_ok(spec.id), "{}", spec.id);
            assert!(spec.id.starts_with("plenio."), "{}", spec.id);
        }
    }

    #[test]
    fn commands_that_make_songs_wait_for_activation() {
        let e = Engine::default();
        set_activated(false);
        assert!(when_activated(&e).is_err());
        set_activated(true);
        assert!(when_activated(&e).is_ok());
        set_activated(false);
    }
}
