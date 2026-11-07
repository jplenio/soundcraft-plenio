//! The add-in's settings for this computer (not for one session): whether it is activated. Kept as
//! `Plenio/settings.json` in SoundCraft's settings folder. Beside it, `Plenio/api-cache.json` keeps
//! the studio's last description of its templates and styles, so the dialogs are complete before
//! the studio is ready ([`load_cache`], [`save_cache`]).

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
    /// The ComfyUI folder chosen by hand; empty: the one Plenio last started, else a usual place.
    pub comfyui: Option<PathBuf>,
    /// The owner accepted the models' licences (YuE2 and SheetSage2: CC BY-NC 4.0, non-commercial).
    pub licences_accepted: bool,
    /// Start the studio with SoundCraft when the add-in is activated.
    pub start_with_soundcraft: bool,
    /// The last choice of "split every take into stems right away": what a new song starts with.
    pub stems_right_away: bool,
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

/// The cache of the studio's answers in the add-in's folder.
pub const CACHE_FILE: &str = "api-cache.json";
/// The largest cache read: the templates and the 250 styles take about 250 kB.
pub const MAX_CACHE_BYTES: u64 = 8 * 1024 * 1024;

/// The cached answers (`{"templates": {id: answer}, "briefs": {kind: answer}}`), or nothing when there
/// is no cache or it is not readable: it is only a convenience.
pub fn load_cache(config_dir: &Path) -> Option<serde_json::Value> {
    let path = config_dir.join(FOLDER).join(CACHE_FILE);
    if std::fs::metadata(&path).ok()?.len() > MAX_CACHE_BYTES {
        return None;
    }
    let value: serde_json::Value = serde_json::from_str(&std::fs::read_to_string(&path).ok()?).ok()?;
    value.is_object().then_some(value)
}

/// Write the cache like the settings: a temporary file first, then over the old one.
pub fn save_cache(config_dir: &Path, value: &serde_json::Value) -> Result<(), SettingsError> {
    let path = config_dir.join(FOLDER).join(CACHE_FILE);
    let io = |e: std::io::Error| SettingsError::Io(path.clone(), e.to_string());
    if let Some(folder) = path.parent() {
        std::fs::create_dir_all(folder).map_err(io)?;
    }
    let temp = path.with_extension("json.tmp");
    std::fs::write(&temp, value.to_string()).map_err(io)?;
    std::fs::rename(&temp, &path).map_err(io)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_cache_round_trips_and_a_broken_one_is_no_cache() {
        let dir = folder("cache");
        assert!(load_cache(&dir).is_none());
        let value = serde_json::json!({"templates": {"yue2-song": {"fields": []}}});
        save_cache(&dir, &value).unwrap();
        assert_eq!(load_cache(&dir), Some(value));
        std::fs::write(dir.join(FOLDER).join(CACHE_FILE), "[1, 2").unwrap();
        assert!(load_cache(&dir).is_none());
        std::fs::write(dir.join(FOLDER).join(CACHE_FILE), "[1, 2]").unwrap();
        assert!(load_cache(&dir).is_none(), "only an object is a cache");
        let _ = std::fs::remove_dir_all(&dir);
    }

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
        let on = Settings { activated: true, comfyui: Some(PathBuf::from("D:/ComfyUI")), ..Settings::default() };
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
        std::fs::write(&path, r#"{"activated": true, "a_later_option": "x"}"#).unwrap();
        assert_eq!(Settings::load(&dir).unwrap(), Settings { activated: true, ..Settings::default() });
        let _ = std::fs::remove_dir_all(&dir);
    }
}
