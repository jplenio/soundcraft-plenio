//! Commands of extensions: add-ins built into an app add their own commands to the registry, so
//! menus, shortcuts, the CLI, the control channel and MCP reach them like SoundCraft's own.
//!
//! The registry is built once, on its first read ([`super::command_specs`]). An extension registers
//! its commands before that, as the app starts; a registration after it is refused.

use super::CommandSpec;
use std::sync::{Mutex, PoisonError};

/// The most commands all extensions may add.
pub const MAX_EXTENSION_COMMANDS: usize = 4096;
/// The longest extension command id, in bytes.
pub const MAX_EXTENSION_ID: usize = 96;

struct Pending {
    specs: Vec<CommandSpec>,
    /// Set when the registry was built: later registrations are refused.
    closed: bool,
    /// Registered ids the registry did not take, and why.
    refused: Vec<String>,
}

static PENDING: Mutex<Pending> = Mutex::new(Pending { specs: Vec::new(), closed: false, refused: Vec::new() });

/// Whether `id` may name an extension command: `area.name`, at most [`MAX_EXTENSION_ID`] bytes of
/// lowercase ASCII letters, digits, `.`, `-` and `_`, with a `.` that is neither first nor last.
pub fn extension_command_id_ok(id: &str) -> bool {
    id.len() <= MAX_EXTENSION_ID
        && id.starts_with(|c: char| c.is_ascii_lowercase())
        && id.contains('.')
        && !id.ends_with('.')
        && id.bytes().all(|b| b.is_ascii_lowercase() || b.is_ascii_digit() || matches!(b, b'.' | b'-' | b'_'))
}

/// Add an extension's commands to the registry. Call it as the app starts, before anything runs
/// or lists a command: the registry is built once, on its first read, and a registration after
/// that is refused. Every id must pass [`extension_command_id_ok`] and be new among the extensions'
/// commands; an id that SoundCraft itself already uses is left out when the registry is built and
/// reported by [`refused_extension_commands`].
pub fn register_extension_commands(specs: Vec<CommandSpec>) -> Result<(), String> {
    let mut pending = PENDING.lock().unwrap_or_else(PoisonError::into_inner);
    if pending.closed {
        return Err("extension commands must be registered before the first command runs".into());
    }
    if pending.specs.len().saturating_add(specs.len()) > MAX_EXTENSION_COMMANDS {
        return Err(format!("extensions may add at most {MAX_EXTENSION_COMMANDS} commands"));
    }
    let mut ids: std::collections::HashSet<&'static str> = pending.specs.iter().map(|c| c.id).collect();
    for spec in &specs {
        if !extension_command_id_ok(spec.id) {
            return Err(format!("not an extension command id: {:?}", spec.id));
        }
        if !ids.insert(spec.id) {
            return Err(format!("the command {} is registered twice", spec.id));
        }
    }
    pending.specs.extend(specs);
    Ok(())
}

/// The extension commands the registry did not take (their id is one of SoundCraft's own), with
/// the reason. Empty until the registry is built.
pub fn refused_extension_commands() -> Vec<String> {
    PENDING.lock().unwrap_or_else(PoisonError::into_inner).refused.clone()
}

/// Close registration and move the registered commands into the registry being built, after the
/// built-in ones. Called once, from the registry's initialisation.
pub(super) fn close_into(registry: &mut Vec<CommandSpec>) {
    let mut pending = PENDING.lock().unwrap_or_else(PoisonError::into_inner);
    pending.closed = true;
    let builtin: std::collections::HashSet<&'static str> = registry.iter().map(|c| c.id).collect();
    for spec in std::mem::take(&mut pending.specs) {
        if builtin.contains(spec.id) {
            log::warn!("extension command {} left out: SoundCraft has a command with that id", spec.id);
            pending.refused.push(format!("{}: SoundCraft has a command with that id", spec.id));
        } else {
            registry.push(spec);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn extension_ids_are_checked() {
        for ok in ["plenio.generate", "plenio.take.select", "my-addin.do_it2"] {
            assert!(extension_command_id_ok(ok), "{ok}");
        }
        for bad in ["", "plenio", ".generate", "plenio.", "Plenio.generate", "plenio generate", "plénio.x", "1plenio.x"] {
            assert!(!extension_command_id_ok(bad), "{bad:?}");
        }
        assert!(!extension_command_id_ok(&format!("a.{}", "b".repeat(MAX_EXTENSION_ID))));
    }
}
