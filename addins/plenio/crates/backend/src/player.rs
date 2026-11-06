//! The Plenio Player (copied with Plenio, unchanged) as the add-in runs it: its own state folder
//! and port, the studio's output as its library, and songs sent from SoundCraft.
//!
//! A song sent from SoundCraft is the session's mix (with the owner's effects) next to a release
//! record made from the take's record: the documents, the lyrics' timing and how the song was made
//! stay Plenio's, the audio is SoundCraft's. The player finds a song's audio and lyrics by name
//! beside its record (`<name>.flac`, `<name> (lines).srt`).

use crate::discover::Install;
use crate::instance::{InstanceError, Layout, PACKAGE, VENDOR_FOLDER};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};

/// The folder, below the studio's output, that songs sent from SoundCraft go to.
pub const SENT_FOLDER: &str = "SoundCraft mixes";

/// The player's script in the installed package.
pub fn script(layout: &Layout) -> PathBuf {
    layout.base().join("custom_nodes").join(PACKAGE).join(VENDOR_FOLDER).join("plenio_player.py")
}

/// Where songs sent from SoundCraft go.
pub fn sent_folder(layout: &Layout) -> PathBuf {
    layout.output().join("plenio").join(SENT_FOLDER)
}

/// The player's address.
pub fn url(port: u16) -> String {
    format!("http://127.0.0.1:{port}/")
}

/// The player's own studio settings: it makes party songs through the add-in's studio (when it
/// runs) and never starts a ComfyUI of its own.
fn write_studio_settings(layout: &Layout, install: &Install, studio_port: Option<u16>) -> std::io::Result<()> {
    std::fs::create_dir_all(layout.player_state())?;
    let settings = json!({"root": install.root, "args": "", "port": studio_port.unwrap_or(8188), "auto": false, "idle_stop_min": 0});
    std::fs::write(layout.player_state().join("studio.json"), settings.to_string())
}

/// The running player.
pub struct Player {
    child: Child,
    pub port: u16,
}

impl Player {
    pub fn start(install: &Install, layout: &Layout, studio_port: Option<u16>, port: u16) -> Result<Player, InstanceError> {
        let io = |p: &Path, e: std::io::Error| InstanceError::Io(p.to_path_buf(), e.to_string());
        let script = script(layout);
        if !script.is_file() {
            return Err(InstanceError::Unusable("the Plenio Player is not installed yet: start the studio once".into()));
        }
        write_studio_settings(layout, install, studio_port).map_err(|e| io(&layout.player_state(), e))?;
        std::fs::create_dir_all(layout.output()).map_err(|e| io(&layout.output(), e))?;
        let log_path = layout.root.join("player.log");
        let log = std::fs::File::create(&log_path).map_err(|e| io(&log_path, e))?;
        let err = log.try_clone().map_err(|e| io(&log_path, e))?;
        let mut command = Command::new(&install.python);
        command
            .arg(&script)
            .args(["--folder".into(), layout.output().to_string_lossy().into_owned(), "--port".into(), port.to_string(), "--no-browser".into()])
            .args(studio_port.map(|p| vec!["--comfyui".to_string(), format!("http://127.0.0.1:{p}")]).unwrap_or_default())
            .current_dir(layout.root.clone())
            .env("PLENIO_PLAYER_STATE", layout.player_state())
            .env("PYTHONUNBUFFERED", "1")
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
        log::info!("Plenio add-in: Plenio Player started on port {port}");
        Ok(Player { child, port })
    }

    pub fn ended(&mut self) -> bool {
        !matches!(self.child.try_wait(), Ok(None))
    }

    pub fn stop(&mut self) {
        if !self.ended() {
            let _ = self.child.kill();
            let _ = self.child.wait();
        }
    }
}

impl Drop for Player {
    fn drop(&mut self) {
        self.stop();
    }
}

/// SHA-256 and size of a file.
fn digest(path: &Path) -> std::io::Result<(String, u64)> {
    let mut file = std::fs::File::open(path)?;
    let mut hasher = Sha256::new();
    let bytes = std::io::copy(&mut file, &mut hasher)?;
    Ok((format!("{:x}", hasher.finalize()), bytes))
}

/// `00:01:02,500`.
fn srt_time(seconds: f64) -> String {
    let ms = (seconds.max(0.0) * 1000.0).round() as u64;
    format!("{:02}:{:02}:{:02},{:03}", ms / 3_600_000, ms / 60_000 % 60, ms / 1000 % 60, ms % 1000)
}

/// Timed lines as an `.srt` file.
pub fn srt(lines: &[(f64, f64, String)]) -> String {
    let mut out = String::new();
    for (i, (start, end, text)) in lines.iter().enumerate() {
        out.push_str(&format!("{}\n{} --> {}\n{}\n\n", i + 1, srt_time(*start), srt_time(*end), text.replace(" / ", "\n")));
    }
    out
}

/// Write the record of a song sent from SoundCraft beside its audio: the take's record with the
/// title and the files of the sent song. Returns the record's path.
///
/// `shift`: how much later the take's audio starts in the mix than in its own file (the mix starts
/// where the session's sound starts). The record's measured times move with it, so that the Player's
/// words and notes stay on the music.
pub fn write_sent_record(take_record: &Value, title: &str, audio: &Path, lines: Option<&Path>, seconds: f64, shift: f64) -> Result<PathBuf, String> {
    let mut record = if take_record.is_object() { take_record.clone() } else { json!({"schema": "plenio.record/1", "versions": {"plenio": ""}}) };
    shift_timing(&mut record, shift);
    let stem = audio.file_stem().map(|s| s.to_string_lossy().into_owned()).ok_or("the sent song has no name")?;
    let folder = audio.parent().ok_or("the sent song has no folder")?;
    let mut files = Vec::new();
    let (sha, bytes) = digest(audio).map_err(|e| format!("{}: {e}", audio.display()))?;
    let format = audio.extension().map(|e| e.to_string_lossy().to_ascii_lowercase()).unwrap_or_else(|| "flac".into());
    files.push(json!({"name": format!("{stem}.{format}"), "bytes": bytes, "sha256": sha, "format": format}));
    if let Some(lines) = lines {
        let (sha, bytes) = digest(lines).map_err(|e| format!("{}: {e}", lines.display()))?;
        let name = lines.file_name().map(|n| n.to_string_lossy().into_owned()).unwrap_or_default();
        files.push(json!({"name": name, "role": "subtitles", "subtitles": "lines", "bytes": bytes, "sha256": sha}));
    }
    record["title"] = json!(title);
    record["files"] = Value::Array(files);
    if let Some(audio_facts) = record.get_mut("audio").and_then(Value::as_object_mut) {
        audio_facts.insert("seconds".into(), json!(seconds));
    }
    let path = folder.join(format!("{stem}.plenio.json"));
    let text = serde_json::to_string_pretty(&record).map_err(|e| e.to_string())?;
    std::fs::write(&path, text).map_err(|e| format!("{}: {e}", path.display()))?;
    Ok(path)
}

/// Move a record's measured times by `by` seconds: each take's warp, its lines and syllables, and
/// the lines as heard.
fn shift_timing(record: &mut Value, by: f64) {
    fn moved(v: &mut Value, by: f64) {
        if let Some(t) = v.as_f64() {
            *v = json!(t + by);
        }
    }
    fn move_lines(lines: Option<&mut Value>, by: f64) {
        for line in lines.and_then(Value::as_array_mut).into_iter().flatten() {
            for key in ["start", "end"] {
                if let Some(t) = line.get_mut(key) {
                    moved(t, by);
                }
            }
            // Each unit is `[start, cut]` or `[start, cut, score]`: only the first is the audio's time.
            for unit in line.get_mut("units").and_then(Value::as_array_mut).into_iter().flatten() {
                if let Some(t) = unit.get_mut(0) {
                    moved(t, by);
                }
            }
        }
    }
    if by == 0.0 {
        return;
    }
    for take in record.get_mut("timing").and_then(Value::as_array_mut).into_iter().flatten() {
        if let Some(b) = take.get_mut("warp").and_then(|w| w.get_mut(1)) {
            moved(b, by);
        }
        move_lines(take.get_mut("lines"), by);
        move_lines(take.get_mut("sung").and_then(|s| s.get_mut("lines")), by);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_measured_times_move_with_the_mix() {
        let mut record = json!({"timing": [{
            "warp": [1.0, -1.5],
            "lines": [{"start": 28.5, "end": 34.0, "units": [[28.5, 2, 29.78], [29.0, 6]]}],
            "sung": {"lines": [{"start": 0.25, "end": 1.0, "units": [[0.25, 2]]}]},
        }]});
        shift_timing(&mut record, 1.25);
        let take = &record["timing"][0];
        assert_eq!(take["warp"], json!([1.0, -0.25]));
        assert_eq!(take["lines"][0]["start"], json!(29.75));
        assert_eq!(take["lines"][0]["units"], json!([[29.75, 2, 29.78], [30.25, 6]]), "the score's time stays");
        assert_eq!(take["sung"]["lines"][0]["units"][0], json!([1.5, 2]));
        let mut none = json!({"title": "no timing"});
        shift_timing(&mut none, 1.25);
        assert_eq!(none, json!({"title": "no timing"}));
    }

    #[test]
    fn timed_lines_become_an_srt_the_player_reads() {
        let text = srt(&[(1.5, 3.0, "Rain / on the road".into()), (61.25, 62.0, "We drive".into())]);
        assert!(text.starts_with("1\n00:00:01,500 --> 00:00:03,000\nRain\non the road\n\n2\n00:01:01,250"));
        let back = crate::song::parse_srt(&text);
        assert_eq!(back.len(), 2);
        assert_eq!(back[0].text, "Rain\non the road");
    }

    #[test]
    fn a_sent_song_has_a_record_with_its_files() {
        let dir = std::env::temp_dir().join(format!("scp-player-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&dir);
        std::fs::create_dir_all(&dir).unwrap();
        let audio = dir.join("Night Drive (SoundCraft mix).flac");
        std::fs::write(&audio, b"fLaC fake").unwrap();
        let lines = dir.join("Night Drive (SoundCraft mix) (lines).srt");
        std::fs::write(&lines, srt(&[(0.0, 1.0, "hi".into())])).unwrap();
        let take =
            json!({"schema": "plenio.record/1", "title": "Night Drive", "documents": {"lyrics": {"text": "[verse] hi"}}, "audio": {"seconds": 90.0}});
        let path = write_sent_record(&take, "Night Drive (SoundCraft mix)", &audio, Some(&lines), 92.5, 0.0).unwrap();
        assert_eq!(path.file_name().unwrap(), "Night Drive (SoundCraft mix).plenio.json");
        let record: Value = serde_json::from_str(&std::fs::read_to_string(&path).unwrap()).unwrap();
        assert_eq!(record["title"], "Night Drive (SoundCraft mix)");
        assert_eq!(record["documents"]["lyrics"]["text"], "[verse] hi");
        assert_eq!(record["files"][0]["format"], "flac");
        assert_eq!(record["files"][0]["bytes"], 9);
        assert_eq!(record["files"][1]["role"], "subtitles");
        assert_eq!(record["audio"]["seconds"], 92.5);
        let _ = std::fs::remove_dir_all(&dir);
    }
}
