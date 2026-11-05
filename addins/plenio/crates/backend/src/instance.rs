//! The add-in's own ComfyUI instance: its folder, the custom node package installed into it, and
//! the process.
//!
//! The instance uses the owner's ComfyUI program and models but a base folder of its own
//! (`--base-directory`): only the add-in's package is loaded there, and its input, output and user
//! folders are the add-in's. The owner's ComfyUI, its custom nodes and its Plenio stay as they are.
//! Plenio's own state (how ComfyUI was started) goes to a state folder of the add-in's
//! (`PLENIO_PLAYER_STATE`), not to the owner's Plenio Player.

use crate::discover::Install;
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};

/// The custom node package's folder name in the instance.
pub const PACKAGE: &str = "soundcraft-plenio";
/// The copied Plenio's folder inside the package.
pub const VENDOR_FOLDER: &str = "plenio_vendor";
/// The file that records which add-in build the installed package came from.
const STAMP: &str = ".installed";
/// The most files copied into the instance (the copy of Plenio has about a thousand).
const MAX_FILES: usize = 20_000;

#[derive(Debug, thiserror::Error)]
pub enum InstanceError {
    #[error("the add-in's Python files were not found (looked in {0})")]
    NoSource(String),
    #[error("{0}: {1}")]
    Io(PathBuf, String),
    #[error("ComfyUI could not be started: {0}")]
    Start(String),
    #[error("{0}")]
    Unusable(String),
}

/// The add-in's folders below SoundCraft's settings folder.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Layout {
    /// `<settings>/Plenio`.
    pub root: PathBuf,
}

impl Layout {
    pub fn new(config_dir: &Path) -> Self {
        Layout { root: config_dir.join(crate::settings::FOLDER) }
    }
    /// The instance's base folder (`--base-directory`).
    pub fn base(&self) -> PathBuf {
        self.root.join("comfyui")
    }
    pub fn package(&self) -> PathBuf {
        self.base().join("custom_nodes").join(PACKAGE)
    }
    /// Where the instance's songs are written (its output folder).
    pub fn output(&self) -> PathBuf {
        self.base().join("output")
    }
    /// Plenio's state for the instance and the add-in's Plenio Player.
    pub fn player_state(&self) -> PathBuf {
        self.root.join("player-state")
    }
    pub fn log(&self) -> PathBuf {
        self.root.join("comfyui.log")
    }
}

/// Where the add-in's Python files are: `SOUNDCRAFT_PLENIO_DIR`, a `plenio-addin` folder beside
/// the program, or the source tree this build came from.
pub fn source_dir() -> Result<PathBuf, InstanceError> {
    let mut tried = Vec::new();
    let mut candidates = Vec::new();
    if let Some(dir) = std::env::var_os("SOUNDCRAFT_PLENIO_DIR").filter(|v| !v.is_empty()) {
        candidates.push(PathBuf::from(dir));
    }
    if let Some(dir) = std::env::current_exe().ok().and_then(|e| e.parent().map(|p| p.join("plenio-addin"))) {
        candidates.push(dir);
    }
    candidates.push(Path::new(env!("CARGO_MANIFEST_DIR")).join("..").join(".."));
    for dir in candidates {
        if dir.join("backend").join("soundcraft_plenio").join("__init__.py").is_file() && dir.join("vendor").join("plenio").join("plenio").is_dir() {
            return Ok(dir);
        }
        tried.push(dir.display().to_string());
    }
    Err(InstanceError::NoSource(tried.join(", ")))
}

/// What identifies an add-in build's Python files: the copied Plenio's record and the wrapper's
/// files (their sizes and modification times are enough to notice a change).
fn stamp_of(source: &Path) -> String {
    let vendor = std::fs::read_to_string(source.join("vendor").join("VENDOR.sha256")).unwrap_or_default();
    let mut wrapper = Vec::new();
    if let Ok(entries) = std::fs::read_dir(source.join("backend").join("soundcraft_plenio")) {
        for e in entries.flatten() {
            if let Ok(m) = e.metadata()
                && m.is_file()
            {
                let mtime = m.modified().ok().and_then(|t| t.duration_since(std::time::UNIX_EPOCH).ok()).map_or(0, |d| d.as_secs());
                wrapper.push(format!("{}:{}:{}", e.file_name().to_string_lossy(), m.len(), mtime));
            }
        }
    }
    wrapper.sort();
    format!("{}\n{}", hash_text(&vendor), wrapper.join("\n"))
}

/// A short, stable digest (FNV-1a, 64 bits): enough to tell two builds apart.
fn hash_text(text: &str) -> String {
    let mut h: u64 = 0xcbf2_9ce4_8422_2325;
    for b in text.bytes() {
        h ^= u64::from(b);
        h = h.wrapping_mul(0x0000_0100_0000_01b3);
    }
    format!("{h:016x}")
}

/// Copy the add-in's custom node package into the instance, unless the same build is there.
/// Returns whether it copied.
pub fn install_package(source: &Path, layout: &Layout) -> Result<bool, InstanceError> {
    let target = layout.package();
    let stamp = stamp_of(source);
    if std::fs::read_to_string(target.join(STAMP)).is_ok_and(|s| s == stamp) {
        return Ok(false);
    }
    let io = |p: &Path, e: std::io::Error| InstanceError::Io(p.to_path_buf(), e.to_string());
    if target.exists() {
        std::fs::remove_dir_all(&target).map_err(|e| io(&target, e))?;
    }
    let mut count = 0usize;
    copy_tree(&source.join("backend").join("soundcraft_plenio"), &target, &mut count)?;
    copy_tree(&source.join("vendor").join("plenio"), &target.join(VENDOR_FOLDER), &mut count)?;
    for file in ["VENDOR.toml", "VENDOR.sha256"] {
        let from = source.join("vendor").join(file);
        std::fs::copy(&from, target.join(VENDOR_FOLDER).join(file)).map_err(|e| io(&from, e))?;
    }
    std::fs::write(target.join(STAMP), stamp).map_err(|e| io(&target, e))?;
    log::info!("Plenio add-in: installed {count} files into {}", target.display());
    Ok(true)
}

fn copy_tree(from: &Path, to: &Path, count: &mut usize) -> Result<(), InstanceError> {
    let io = |p: &Path, e: std::io::Error| InstanceError::Io(p.to_path_buf(), e.to_string());
    std::fs::create_dir_all(to).map_err(|e| io(to, e))?;
    for entry in std::fs::read_dir(from).map_err(|e| io(from, e))? {
        let entry = entry.map_err(|e| io(from, e))?;
        let name = entry.file_name();
        if name == "__pycache__" || name == ".pytest_cache" {
            continue;
        }
        let kind = entry.file_type().map_err(|e| io(&entry.path(), e))?;
        if kind.is_dir() {
            copy_tree(&entry.path(), &to.join(&name), count)?;
        } else if kind.is_file() {
            *count += 1;
            if *count > MAX_FILES {
                return Err(InstanceError::Unusable(format!("more than {MAX_FILES} files to copy from {}", from.display())));
            }
            std::fs::copy(entry.path(), to.join(&name)).map_err(|e| io(&entry.path(), e))?;
        }
    }
    Ok(())
}

/// A free port on this computer.
pub fn free_port() -> Result<u16, InstanceError> {
    let listener = std::net::TcpListener::bind(("127.0.0.1", 0)).map_err(|e| InstanceError::Start(format!("no free port: {e}")))?;
    listener.local_addr().map(|a| a.port()).map_err(|e| InstanceError::Start(e.to_string()))
}

/// The instance's command line (without the program).
pub fn arguments(install: &Install, layout: &Layout, port: u16) -> Vec<String> {
    let mut args = vec![
        install.main_py().to_string_lossy().into_owned(),
        "--base-directory".into(),
        layout.base().to_string_lossy().into_owned(),
        "--listen".into(),
        "127.0.0.1".into(),
        "--port".into(),
        port.to_string(),
        "--disable-auto-launch".into(),
    ];
    if let Some(models) = &install.models_dir {
        args.push("--models-directory".into());
        args.push(models.to_string_lossy().into_owned());
    } else {
        // Without its own models folder the owner's ComfyUI keeps them in its folder: use that one,
        // not an empty one in the instance's base folder.
        args.push("--models-directory".into());
        args.push(install.root.join("models").to_string_lossy().into_owned());
    }
    args.extend(install.args.iter().cloned());
    args
}

/// The running instance.
pub struct Instance {
    child: Child,
    pub port: u16,
}

impl Instance {
    /// Start ComfyUI in the background, without a window, its output in the add-in's log file.
    pub fn start(install: &Install, layout: &Layout, port: u16) -> Result<Instance, InstanceError> {
        if let Some(problem) = install.problem() {
            return Err(InstanceError::Unusable(problem));
        }
        let io = |p: &Path, e: std::io::Error| InstanceError::Io(p.to_path_buf(), e.to_string());
        std::fs::create_dir_all(layout.player_state()).map_err(|e| io(&layout.player_state(), e))?;
        let log = std::fs::File::create(layout.log()).map_err(|e| io(&layout.log(), e))?;
        let err = log.try_clone().map_err(|e| io(&layout.log(), e))?;
        let mut command = Command::new(&install.python);
        command
            .args(arguments(install, layout, port))
            .current_dir(&install.root)
            .env("PLENIO_PLAYER_STATE", layout.player_state())
            .env("PYTHONUNBUFFERED", "1")
            .env("SCP_PARENT_PID", std::process::id().to_string())
            .stdin(Stdio::null())
            .stdout(Stdio::from(log))
            .stderr(Stdio::from(err));
        #[cfg(windows)]
        {
            use std::os::windows::process::CommandExt;
            /// No console window (CREATE_NO_WINDOW).
            const NO_WINDOW: u32 = 0x0800_0000;
            command.creation_flags(NO_WINDOW);
        }
        let child = command.spawn().map_err(|e| InstanceError::Start(format!("{}: {e}", install.python.display())))?;
        log::info!("Plenio add-in: ComfyUI started on port {port} (process {})", child.id());
        Ok(Instance { child, port })
    }

    /// Whether the process still runs; `Some(code)` once it ended.
    pub fn ended(&mut self) -> Option<String> {
        match self.child.try_wait() {
            Ok(Some(status)) => Some(status.to_string()),
            Ok(None) => None,
            Err(e) => Some(e.to_string()),
        }
    }

    /// Stop the instance (it holds GPU memory while it runs).
    pub fn stop(&mut self) {
        if self.ended().is_none() {
            let _ = self.child.kill();
            let _ = self.child.wait();
            log::info!("Plenio add-in: ComfyUI on port {} stopped", self.port);
        }
    }
}

impl Drop for Instance {
    fn drop(&mut self) {
        self.stop();
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_instance_has_its_own_folder_and_the_owners_models() {
        let layout = Layout::new(Path::new("C:/cfg"));
        let install = Install {
            root: PathBuf::from("D:/ComfyUI"),
            python: PathBuf::from("D:/ComfyUI/.venv/Scripts/python.exe"),
            models_dir: Some(PathBuf::from("F:/models")),
            args: vec!["--bf16-unet".into()],
            version: Some("0.43.0".into()),
        };
        let args = arguments(&install, &layout, 8291);
        let after = |flag: &str| args.iter().position(|a| a == flag).and_then(|i| args.get(i + 1)).cloned();
        assert_eq!(after("--base-directory").map(PathBuf::from), Some(layout.base()));
        assert_eq!(after("--models-directory").as_deref(), Some("F:/models"));
        assert_eq!(after("--listen").as_deref(), Some("127.0.0.1"));
        assert_eq!(after("--port").as_deref(), Some("8291"));
        assert_eq!(args.last().map(String::as_str), Some("--bf16-unet"));
        let own_models = Install { models_dir: None, ..install };
        assert_eq!(
            after_of(&arguments(&own_models, &layout, 1), "--models-directory").map(PathBuf::from),
            Some(PathBuf::from("D:/ComfyUI").join("models"))
        );
    }

    fn after_of(args: &[String], flag: &str) -> Option<String> {
        args.iter().position(|a| a == flag).and_then(|i| args.get(i + 1)).cloned()
    }

    #[test]
    fn the_package_is_copied_once_per_build() {
        let source = source_dir().unwrap();
        let dir = std::env::temp_dir().join(format!("scp-instance-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&dir);
        let layout = Layout::new(&dir);
        assert!(install_package(&source, &layout).unwrap());
        assert!(layout.package().join("__init__.py").is_file());
        assert!(layout.package().join(VENDOR_FOLDER).join("plenio").join("__init__.py").is_file());
        assert!(layout.package().join(VENDOR_FOLDER).join("VENDOR.toml").is_file());
        assert!(!install_package(&source, &layout).unwrap(), "the same build is not copied again");
        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn a_free_port_is_found() {
        assert!(free_port().unwrap() > 0);
    }
}
