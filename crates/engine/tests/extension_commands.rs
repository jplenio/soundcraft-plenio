//! Extension commands, end to end: registered before the registry is built, they run, undo and
//! list like SoundCraft's own.
//!
//! A test binary of its own, not a module of `it`: the registry is built once per process, so the
//! registration must come before any other test reads it.

use serde_json::{Value, json};
use soundcraft_engine::cmd::{always, refused_extension_commands, register_extension_commands};
use soundcraft_engine::{Engine, EngineError, command_specs, find_command};

fn remember(e: &mut Engine, p: &Value) -> soundcraft_engine::Result<Value> {
    let text = p.get("text").and_then(Value::as_str).unwrap_or_default().to_string();
    e.session_mut().set_extension("test-addin", text).map_err(|err| EngineError::BadParams("test-addin.remember".into(), err.to_string()))?;
    Ok(json!({"kept": e.session().extension("test-addin").is_some()}))
}

fn not_yet(_: &Engine) -> std::result::Result<(), String> {
    Err("the add-in is not activated".into())
}

fn nothing(_: &mut Engine, _: &Value) -> soundcraft_engine::Result<Value> {
    Ok(Value::Null)
}

#[test]
fn extension_commands_register_once_and_run_like_builtin_ones() {
    // Bad ids and repeats are refused and leave nothing behind.
    assert!(register_extension_commands(vec![soundcraft_engine::cmd!("Bad Id", "Bad", [], None, "{}", always, nothing)]).is_err());
    assert!(
        register_extension_commands(vec![
            soundcraft_engine::cmd!("test-addin.twice", "Twice", [], None, "{}", always, nothing),
            soundcraft_engine::cmd!("test-addin.twice", "Twice", [], None, "{}", always, nothing),
        ])
        .is_err()
    );
    register_extension_commands(vec![
        soundcraft_engine::cmd!("test-addin.remember", "Remember", [], None, "{\"text\": string}", always, remember),
        soundcraft_engine::cmd!("test-addin.inactive", "Inactive", [], None, "{}", not_yet, nothing),
        // SoundCraft's own id: left out of the registry and reported.
        soundcraft_engine::cmd!("edit.undo", "Not Undo", [], None, "{}", always, nothing),
    ])
    .unwrap();
    // The first read builds the registry and closes registration.
    let ids: Vec<&str> = command_specs().iter().map(|c| c.id).collect();
    assert!(ids.contains(&"test-addin.remember") && ids.contains(&"test-addin.inactive"));
    assert!(!ids.contains(&"test-addin.twice"));
    assert_eq!(ids.iter().filter(|id| **id == "edit.undo").count(), 1);
    assert_eq!(find_command("edit.undo").map(|c| c.label), Some("Undo"));
    assert_eq!(refused_extension_commands().len(), 1);
    assert!(register_extension_commands(vec![soundcraft_engine::cmd!("test-addin.late", "Late", [], None, "{}", always, nothing)]).is_err());

    // It runs through the engine: one undo step, and the document is dirty.
    let mut e = Engine::default();
    assert_eq!(e.execute("test-addin.remember", &json!({"text": "{\"v\":1}"})).unwrap(), json!({"kept": true}));
    assert_eq!(e.session().extension("test-addin"), Some("{\"v\":1}"));
    assert!(e.can_undo());
    assert!(e.undo());
    assert_eq!(e.session().extension("test-addin"), None);
    // Its own `enabled` decides, as for any command.
    assert!(matches!(e.execute("test-addin.inactive", &json!({})), Err(EngineError::Disabled(..))));
}
