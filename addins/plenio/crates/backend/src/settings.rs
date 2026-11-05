//! The add-in's settings for this computer (not for one session): whether it is activated. Kept as
//! `Plenio/settings.json` in SoundCraft's settings folder.

use serde::{Deserialize, Serialize};
use std::path::{Path, PathBuf};

/// The add-in's folder in SoundCraft's settings folder.
pub const FOLDER: &str = "Plenio";
/// The settings file in that folder.
pub const FILE: &str = "settings.json";
/// The largest settings file read; anything bigger is not ours.
pub const MAX_BYTES: u64 = 1024 * 1024;

#[derive(Debug, thiserror::Error)]
pub enum SettingsError {
    #[error("Plenio settings {0}: {1}")]
    Io(PathBuf, String),
    #[error("Plenio settings {0} are not readable: {1}")]
    Format(PathBuf, String),
}

/// The add-in's settings.
#[derive(Debug, Clone, PartialEq, Eq, Default, Serialize, Deserialize)]
#[serde(default)]
pub struct Settings {
    /// The add-in is activated: its menus offer songs, and its setup is done.
    pub activated: bool,
}

impl Settings {
    /// The settings file below SoundCraft's settings folder.
    pub fn path(config_dir: &Path) -> PathBuf {
        config_dir.join(FOLDER).join(FILE)
    }

    /// Read the settings; the defaults when there is no file yet.
    pub fn load(config_dir: &Path) -> Result<Settings, SettingsError> {
        let path = Self::path(config_dir);
        let size = match std::fs::metadata(&path) {
            Ok(m) => m.len(),
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => return Ok(Settings::default()),
            Err(e) => return Err(SettingsError::Io(path, e.to_string())),
        };
        if size > MAX_BYTES {
            return Err(SettingsError::Format(path, format!("over {MAX_BYTES} bytes")));
        }
        let text = std::fs::read_to_string(&path).map_err(|e| SettingsError::Io(path.clone(), e.to_string()))?;
        serde_json::from_str(&text).map_err(|e| SettingsError::Format(path, e.to_string()))
    }

    /// Write the settings: to a temporary file first, then over the old one, so a crash never
    /// leaves half a file.
    pub fn save(&self, config_dir: &Path) -> Result<(), SettingsError> {
        let path = Self::path(config_dir);
        let io = |e: std::io::Error| SettingsError::Io(path.clone(), e.to_string());
        if let Some(folder) = path.parent() {
            std::fs::create_dir_all(folder).map_err(io)?;
        }
        let text = serde_json::to_string_pretty(self).map_err(|e| SettingsError::Format(path.clone(), e.to_string()))?;
        let temp = path.with_extension("json.tmp");
        std::fs::write(&temp, text).map_err(io)?;
        std::fs::rename(&temp, &path).map_err(io)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// A fresh, empty folder for one test.
    fn folder(name: &str) -> PathBuf {
        let dir = std::env::temp_dir().join(format!("soundcraft-plenio-settings-{name}-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&dir);
        dir
    }

    #[test]
    fn settings_default_until_saved_then_round_trip() {
        let dir = folder("round-trip");
        assert_eq!(Settings::load(&dir).unwrap(), Settings::default());
        let on = Settings { activated: true };
        on.save(&dir).unwrap();
        assert_eq!(Settings::load(&dir).unwrap(), on);
        Settings::default().save(&dir).unwrap();
        assert_eq!(Settings::load(&dir).unwrap(), Settings::default());
        assert!(!Settings::path(&dir).with_extension("json.tmp").exists());
        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn a_broken_or_huge_file_is_an_error_not_a_panic() {
        let dir = folder("broken");
        let path = Settings::path(&dir);
        std::fs::create_dir_all(path.parent().unwrap()).unwrap();
        std::fs::write(&path, "{ not json").unwrap();
        assert!(matches!(Settings::load(&dir), Err(SettingsError::Format(..))));
        std::fs::write(&path, vec![b' '; usize::try_from(MAX_BYTES).unwrap() + 1]).unwrap();
        assert!(matches!(Settings::load(&dir), Err(SettingsError::Format(..))));
        // Unknown keys from a later add-in are ignored.
        std::fs::write(&path, r#"{"activated": true, "comfyui": "later"}"#).unwrap();
        assert_eq!(Settings::load(&dir).unwrap(), Settings { activated: true });
        let _ = std::fs::remove_dir_all(&dir);
    }
}
