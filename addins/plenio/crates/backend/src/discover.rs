//! Find the ComfyUI the add-in runs its own instance of: the folder, its Python, the models folder
//! and the options its owner starts it with. Nothing is installed or changed here.
//!
//! The first place to look is how Plenio itself last started ComfyUI (the Plenio Player keeps that
//! in `comfyui-start.json`); then the add-in's settings; then the usual install locations.

use std::path::{Path, PathBuf};

/// The oldest ComfyUI that has the native YuE2 nodes Plenio needs.
pub const MIN_VERSION: (u32, u32, u32) = (0, 37, 0);
/// The largest `comfyui-start.json` read.
const MAX_START_FILE: u64 = 1024 * 1024;
/// The most arguments taken over from a start file.
const MAX_ARGS: usize = 64;
/// Arguments the add-in sets itself, or that would open the instance or load other custom nodes:
/// never taken over (with the number of values each takes).
const OWN_ARGS: &[(&str, usize)] = &[
    ("--listen", 1),
    ("--port", 1),
    ("--enable-cors-header", 1),
    ("--tls-keyfile", 1),
    ("--tls-certfile", 1),
    ("--base-directory", 1),
    ("--output-directory", 1),
    ("--input-directory", 1),
    ("--temp-directory", 1),
    ("--user-directory", 1),
    ("--models-directory", 1),
    ("--extra-model-paths-config", 1),
    ("--front-end-version", 1),
    ("--whitelist-custom-nodes", 1),
    ("--enable-manager", 0),
    ("--auto-launch", 0),
    ("--disable-auto-launch", 0),
    ("--disable-all-custom-nodes", 0),
];

/// A ComfyUI installation.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Install {
    /// The folder that holds `main.py`.
    pub root: PathBuf,
    pub python: PathBuf,
    /// The models folder its owner uses, if not the one inside `root`.
    pub models_dir: Option<PathBuf>,
    /// The owner's other options (GPU, precision, memory), safe to repeat for the add-in's instance.
    pub args: Vec<String>,
    /// `comfyui_version.py`'s version, if readable.
    pub version: Option<String>,
}

impl Install {
    pub fn main_py(&self) -> PathBuf {
        self.root.join("main.py")
    }

    /// Why this installation cannot run Plenio, if it cannot.
    pub fn problem(&self) -> Option<String> {
        if !self.main_py().is_file() {
            return Some(format!("{} has no main.py", self.root.display()));
        }
        match self.version.as_deref().and_then(parse_version) {
            Some(v) if v < MIN_VERSION => Some(format!(
                "ComfyUI {} is too old for Plenio (it needs {}.{}.{} or newer)",
                self.version.as_deref().unwrap_or("?"),
                MIN_VERSION.0,
                MIN_VERSION.1,
                MIN_VERSION.2
            )),
            _ => None,
        }
    }
}

/// `"0.43.0"` → `(0, 43, 0)`.
pub fn parse_version(text: &str) -> Option<(u32, u32, u32)> {
    let mut parts = text.trim().trim_start_matches('v').split('.').map(|p| p.chars().take_while(char::is_ascii_digit).collect::<String>());
    let major = parts.next()?.parse().ok()?;
    let minor = parts.next().unwrap_or_default().parse().unwrap_or(0);
    let patch = parts.next().unwrap_or_default().parse().unwrap_or(0);
    Some((major, minor, patch))
}

/// The version in `comfyui_version.py`.
pub fn read_version(root: &Path) -> Option<String> {
    let text = read_small(&root.join("comfyui_version.py"), 64 * 1024)?;
    text.lines().find_map(|l| {
        let rest = l.trim().strip_prefix("__version__")?.trim().strip_prefix('=')?.trim();
        Some(rest.trim_matches(|c| c == '"' || c == '\'').to_string())
    })
}

fn read_small(path: &Path, max: u64) -> Option<String> {
    let size = std::fs::metadata(path).ok()?.len();
    if size > max {
        return None;
    }
    std::fs::read_to_string(path).ok()
}

/// The Python of a ComfyUI folder: the portable build's embedded one, a `.venv` or `venv`, else
/// the `python` on the PATH.
pub fn python_for(root: &Path) -> PathBuf {
    let candidates: Vec<PathBuf> = if cfg!(windows) {
        vec![
            root.join("..").join("python_embeded").join("python.exe"),
            root.join(".venv").join("Scripts").join("python.exe"),
            root.join("venv").join("Scripts").join("python.exe"),
        ]
    } else {
        vec![root.join(".venv").join("bin").join("python"), root.join("venv").join("bin").join("python")]
    };
    candidates.into_iter().find(|p| p.is_file()).unwrap_or_else(|| PathBuf::from(if cfg!(windows) { "python.exe" } else { "python3" }))
}

/// Split a start file's arguments into the models folder and the options worth repeating.
pub fn split_args(args: &[String]) -> (Option<PathBuf>, Vec<String>) {
    let mut models = None;
    let mut kept = Vec::new();
    let mut i = 0;
    while i < args.len() && kept.len() < MAX_ARGS {
        let arg = args.get(i).cloned().unwrap_or_default();
        let (name, inline) = match arg.split_once('=') {
            Some((n, v)) if n.starts_with("--") => (n.to_string(), Some(v.to_string())),
            _ => (arg.clone(), None),
        };
        if let Some(&(_, values)) = OWN_ARGS.iter().find(|(n, _)| *n == name) {
            let value = inline.clone().or_else(|| if values > 0 { args.get(i + 1).cloned() } else { None });
            if name == "--models-directory" {
                models = value.map(PathBuf::from);
            }
            i += 1 + if inline.is_none() { values } else { 0 };
            continue;
        }
        if !arg.chars().any(char::is_control) {
            kept.push(arg);
        }
        i += 1;
    }
    (models, kept)
}

/// The Plenio Player's state folder: `PLENIO_PLAYER_STATE`, else `~/.plenio/player`.
pub fn plenio_player_state() -> Option<PathBuf> {
    match std::env::var_os("PLENIO_PLAYER_STATE").filter(|v| !v.is_empty()) {
        Some(v) => Some(PathBuf::from(v)),
        None => home().map(|h| h.join(".plenio").join("player")),
    }
}

fn home() -> Option<PathBuf> {
    std::env::var_os(if cfg!(windows) { "USERPROFILE" } else { "HOME" }).filter(|v| !v.is_empty()).map(PathBuf::from)
}

/// The installation Plenio last started, from the Plenio Player's `comfyui-start.json`
/// (`{"<main.py>": {"python": …, "args": […], "at": seconds}}`): the newest one that still exists.
pub fn from_plenio_start_file(state: &Path) -> Option<Install> {
    let text = read_small(&state.join("comfyui-start.json"), MAX_START_FILE)?;
    let value: serde_json::Value = serde_json::from_str(&text).ok()?;
    let mut found: Vec<(f64, Install)> = value
        .as_object()?
        .iter()
        .filter_map(|(main, entry)| {
            let main = PathBuf::from(main);
            let root = main.parent()?.to_path_buf();
            if !main.is_file() {
                return None;
            }
            let python = entry.get("python").and_then(|p| p.as_str()).map(PathBuf::from).filter(|p| p.is_file()).unwrap_or_else(|| python_for(&root));
            let args: Vec<String> = entry
                .get("args")
                .and_then(|a| a.as_array())
                .map(|a| a.iter().filter_map(|v| v.as_str().map(str::to_string)).collect())
                .unwrap_or_default();
            let (models_dir, args) = split_args(&args);
            let at = entry.get("at").and_then(serde_json::Value::as_f64).filter(|t| t.is_finite()).unwrap_or(0.0);
            let version = read_version(&root);
            Some((at, Install { root, python, models_dir, args, version }))
        })
        .collect();
    found.sort_by(|a, b| b.0.total_cmp(&a.0));
    found.into_iter().map(|(_, i)| i).next()
}

/// An installation in a folder the owner chose.
pub fn at(root: &Path) -> Install {
    Install { root: root.to_path_buf(), python: python_for(root), models_dir: None, args: Vec::new(), version: read_version(root) }
}

/// The usual install locations.
fn usual_places() -> Vec<PathBuf> {
    let mut places = Vec::new();
    if let Some(h) = home() {
        places.push(h.join("ComfyUI"));
        places.push(h.join("Documents").join("ComfyUI"));
    }
    if cfg!(windows) {
        for drive in ["C:", "D:", "E:", "F:"] {
            places.push(PathBuf::from(format!("{drive}\\ComfyUI")));
            places.push(PathBuf::from(format!("{drive}\\ComfyUI_windows_portable\\ComfyUI")));
        }
    }
    places
}

/// The ComfyUI to use: the one chosen in the settings, else the one Plenio last started, else one in
/// a usual place.
pub fn find(chosen: Option<&Path>) -> Option<Install> {
    if let Some(root) = chosen {
        return Some(at(root));
    }
    if let Some(found) = plenio_player_state().and_then(|s| from_plenio_start_file(&s)) {
        return Some(found);
    }
    usual_places().into_iter().find(|p| p.join("main.py").is_file()).map(|p| at(&p))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn strings(a: &[&str]) -> Vec<String> {
        a.iter().map(ToString::to_string).collect()
    }

    #[test]
    fn the_owners_options_are_kept_and_the_instances_own_ones_dropped() {
        let (models, kept) = split_args(&strings(&[
            "--models-directory",
            "F:\\ComfyUI\\models",
            "--disable-pinned-memory",
            "--listen",
            "0.0.0.0",
            "--port=9000",
            "--enable-manager",
            "--bf16-unet",
            "--cuda-device",
            "1",
        ]));
        assert_eq!(models, Some(PathBuf::from("F:\\ComfyUI\\models")));
        assert_eq!(kept, strings(&["--disable-pinned-memory", "--bf16-unet", "--cuda-device", "1"]));
    }

    #[test]
    fn versions_are_compared_by_number() {
        assert_eq!(parse_version("0.43.0"), Some((0, 43, 0)));
        assert_eq!(parse_version("v0.37"), Some((0, 37, 0)));
        assert!(parse_version("0.36.9") < Some(MIN_VERSION));
        assert_eq!(parse_version("x"), None);
    }

    #[test]
    fn the_newest_existing_start_is_taken_and_hostile_files_are_ignored() {
        let dir = std::env::temp_dir().join(format!("scp-discover-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&dir);
        let comfy = dir.join("ComfyUI");
        std::fs::create_dir_all(&comfy).unwrap();
        std::fs::write(comfy.join("main.py"), "").unwrap();
        std::fs::write(comfy.join("comfyui_version.py"), "__version__ = \"0.43.0\"\n").unwrap();
        let state = dir.join("state");
        std::fs::create_dir_all(&state).unwrap();
        let start = serde_json::json!({
            comfy.join("main.py").to_string_lossy(): {"args": ["--models-directory", "M:\\models", "--bf16-unet"], "at": 2.0},
            dir.join("gone").join("main.py").to_string_lossy(): {"args": [], "at": 9.0},
        });
        std::fs::write(state.join("comfyui-start.json"), start.to_string()).unwrap();
        let found = from_plenio_start_file(&state).unwrap();
        assert_eq!(found.root, comfy);
        assert_eq!(found.models_dir, Some(PathBuf::from("M:\\models")));
        assert_eq!(found.args, strings(&["--bf16-unet"]));
        assert_eq!(found.version.as_deref(), Some("0.43.0"));
        assert_eq!(found.problem(), None);
        std::fs::write(state.join("comfyui-start.json"), "[1, 2").unwrap();
        assert!(from_plenio_start_file(&state).is_none());
        std::fs::write(comfy.join("comfyui_version.py"), "__version__ = '0.30.1'").unwrap();
        assert!(at(&comfy).problem().is_some_and(|p| p.contains("too old")));
        let _ = std::fs::remove_dir_all(&dir);
    }
}
