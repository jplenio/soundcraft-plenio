//! A song Plenio released, as it lies on disk: its audio and the release record that says how it was
//! made. The record is a file beside the song (`<name>.plenio.json`) and also inside the song's FLAC,
//! so that a song can be continued from the audio file alone (`plenio/core/release.py`).

use crate::song::{Cue, parse_srt, record_lines};
use flate2::read::GzDecoder;
use serde_json::Value;
use std::io::{Read, Seek, SeekFrom};
use std::path::{Path, PathBuf};

/// The largest record read, from a file or out of a FLAC.
const MAX_RECORD_BYTES: u64 = 32 * 1024 * 1024;
const RECORD_SUFFIX: &str = ".plenio.json";
const ORIGINAL_SUFFIX: &str = " (original)";
/// What Plenio exports a song as.
const AUDIO: [&str; 3] = ["flac", "wav", "mp3"];
/// The FLAC block type "APPLICATION", which every other reader skips.
const APPLICATION: u8 = 2;
/// The application id of the block that holds the record.
const PROJECT_ID: &[u8] = b"PLNO";
/// The block's layout: the id, this schema name and a NUL, then the record as gzip-compressed JSON.
const PROJECT_PREFIX: &[u8] = b"PLNOplenio.project/1\0";

/// What belongs to a released song.
#[derive(Debug, Clone)]
pub struct SongFiles {
    pub record: Value,
    /// The record as a file: a song's FLAC can carry it alone.
    pub record_file: Option<PathBuf>,
    /// The song as released (mastered).
    pub audio: Option<PathBuf>,
    /// The unmastered take.
    pub original: Option<PathBuf>,
    /// The lyrics' lines as sung, in the audio's time.
    pub lines: Vec<Cue>,
}

fn is_record(v: &Value) -> bool {
    v.get("schema").and_then(Value::as_str).is_some_and(|s| s.starts_with("plenio.record/"))
}

fn has_extension(path: &Path, extension: &str) -> bool {
    path.extension().is_some_and(|e| e.eq_ignore_ascii_case(extension))
}

/// The name the files of a song share, from the name of any of them.
fn song_stem(path: &Path) -> String {
    let name = path.file_name().map(|n| n.to_string_lossy().into_owned()).unwrap_or_default();
    let stem = match name.len().checked_sub(RECORD_SUFFIX.len()).filter(|at| name.is_char_boundary(*at)) {
        Some(at) if name[at..].eq_ignore_ascii_case(RECORD_SUFFIX) => name[..at].to_string(),
        _ => path.file_stem().map(|n| n.to_string_lossy().into_owned()).unwrap_or_default(),
    };
    stem.strip_suffix(ORIGINAL_SUFFIX).map(str::to_string).unwrap_or(stem)
}

/// The release record the FLAC file at `path` carries, reading its metadata only (not the audio).
/// `None`: it carries none, or it is no FLAC.
pub fn read_project(path: &Path) -> Result<Option<Value>, String> {
    let mut file = std::fs::File::open(path).map_err(|e| e.to_string())?;
    let mut magic = [0u8; 4];
    if file.read_exact(&mut magic).is_err() || &magic != b"fLaC" {
        return Ok(None);
    }
    loop {
        let mut header = [0u8; 4];
        file.read_exact(&mut header).map_err(|_| "the FLAC file ends inside its metadata".to_string())?;
        let length = u32::from_be_bytes([0, header[1], header[2], header[3]]);
        if header[0] & 0x7F == APPLICATION {
            let mut body = Vec::new();
            file.by_ref().take(u64::from(length)).read_to_end(&mut body).map_err(|e| e.to_string())?;
            if body.len() < length as usize {
                return Err("the FLAC file ends inside its metadata".into());
            }
            if body.starts_with(PROJECT_ID) {
                return project_record(&body).map(Some);
            }
        } else {
            file.seek(SeekFrom::Current(i64::from(length))).map_err(|e| e.to_string())?;
        }
        if header[0] & 0x80 != 0 {
            return Ok(None);
        }
    }
}

fn project_record(body: &[u8]) -> Result<Value, String> {
    let Some(packed) = body.strip_prefix(PROJECT_PREFIX) else {
        return Err("a newer Plenio wrote the song in this FLAC; choose the .plenio.json beside it".into());
    };
    let mut data = Vec::new();
    GzDecoder::new(packed).take(MAX_RECORD_BYTES + 1).read_to_end(&mut data).map_err(|e| format!("the song in this FLAC is damaged: {e}"))?;
    if data.len() as u64 > MAX_RECORD_BYTES {
        return Err("the song in this FLAC is too large".into());
    }
    let record: Value = serde_json::from_slice(&data).map_err(|e| format!("the song in this FLAC is damaged: {e}"))?;
    if is_record(&record) { Ok(record) } else { Err("the song in this FLAC has no release record".into()) }
}

fn read_record(path: &Path) -> Result<Value, String> {
    let size = std::fs::metadata(path).map_err(|e| e.to_string())?.len();
    if size > MAX_RECORD_BYTES {
        return Err("the record is too large".into());
    }
    let bytes = std::fs::read(path).map_err(|e| e.to_string())?;
    serde_json::from_slice(&bytes).ok().filter(is_record).ok_or_else(|| "this is not a Plenio release record".to_string())
}

/// The song the file at `path` belongs to: its record (`.plenio.json`), its FLAC, or any other file of
/// it, with whatever else of it lies beside it.
pub fn find_song(path: &Path) -> Result<SongFiles, String> {
    let folder = path.parent().map(PathBuf::from).unwrap_or_default();
    let stem = song_stem(path);
    let beside = |suffix: &str| Some(folder.join(format!("{stem}{suffix}"))).filter(|p| p.is_file());
    let picked_record = has_extension(path, "json");
    let record_file = if picked_record { Some(path.to_path_buf()) } else { beside(RECORD_SUFFIX) };
    let record = if picked_record {
        read_record(path)?
    } else if let Some(record) = read_project(path)? {
        record
    } else if let Some(file) = &record_file {
        read_record(file)?
    } else if let Some(record) = beside(".flac").map(|flac| read_project(&flac)).transpose()?.flatten() {
        record
    } else {
        return Err("no Plenio song in this file. Plain audio comes in with File > Import Audio.".into());
    };
    let is_original = path.file_stem().is_some_and(|s| s.to_string_lossy().ends_with(ORIGINAL_SUFFIX));
    let picked_audio = !is_original && AUDIO.iter().any(|extension| has_extension(path, extension));
    let audio = if picked_audio { Some(path.to_path_buf()) } else { AUDIO.iter().find_map(|extension| beside(&format!(".{extension}"))) };
    let original = beside(&format!("{ORIGINAL_SUFFIX}.flac"));
    let lines = beside(" (lines).srt").and_then(|srt| std::fs::read_to_string(srt).ok()).map(|t| parse_srt(&t)).unwrap_or_default();
    let lines = if lines.is_empty() { record_lines(&record) } else { lines };
    Ok(SongFiles { record, record_file, audio, original, lines })
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;
    use std::io::Write;

    fn temp(name: &str) -> PathBuf {
        let dir = std::env::temp_dir().join(format!("scp-release-{name}-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&dir);
        std::fs::create_dir_all(&dir).unwrap();
        dir
    }

    fn block(kind: u8, last: bool, body: &[u8]) -> Vec<u8> {
        let mut out = vec![kind | if last { 0x80 } else { 0 }];
        out.extend_from_slice(&(body.len() as u32).to_be_bytes()[1..]);
        out.extend_from_slice(body);
        out
    }

    fn packed(data: &[u8]) -> Vec<u8> {
        let mut gz = flate2::write::GzEncoder::new(Vec::new(), flate2::Compression::default());
        gz.write_all(data).unwrap();
        gz.finish().unwrap()
    }

    fn project(record: &Value) -> Vec<u8> {
        [PROJECT_PREFIX, &packed(record.to_string().as_bytes())].concat()
    }

    /// A FLAC's metadata as Plenio writes it: stream info, a tag block, the project, padding.
    fn flac(project_body: Option<&[u8]>) -> Vec<u8> {
        let mut out = b"fLaC".to_vec();
        out.extend(block(0, false, &[0; 34]));
        out.extend(block(4, false, b"tags"));
        // Another program's application block comes first: only Plenio's is the project.
        out.extend(block(APPLICATION, false, b"ATCHsomething else"));
        if let Some(body) = project_body {
            out.extend(block(APPLICATION, false, body));
        }
        out.extend(block(1, true, &[0; 16]));
        out.extend_from_slice(&[0xFF, 0xF8, 0, 0]);
        out
    }

    fn record() -> Value {
        json!({"schema": "plenio.record/1", "title": "Garden", "timing": [{"lines": [
            {"text": "Later", "start": 3.0, "end": 4.0, "units": []},
            {"text": "Morning light", "start": 0.5, "end": 2.0, "units": []},
        ]}]})
    }

    #[test]
    fn the_record_comes_out_of_the_flac_that_carries_it() {
        let dir = temp("carried");
        let path = dir.join("song.flac");
        std::fs::write(&path, flac(Some(&project(&record())))).unwrap();
        assert_eq!(read_project(&path).unwrap().unwrap()["title"], "Garden");

        let plain = dir.join("plain.flac");
        std::fs::write(&plain, flac(None)).unwrap();
        assert_eq!(read_project(&plain).unwrap(), None);

        let wav = dir.join("named wrongly.flac");
        std::fs::write(&wav, b"RIFF....WAVE").unwrap();
        assert_eq!(read_project(&wav).unwrap(), None);
        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn a_damaged_project_is_refused_with_a_reason() {
        let dir = temp("damaged");
        let path = dir.join("song.flac");
        let refused = |content: Vec<u8>| {
            std::fs::write(&path, content).unwrap();
            read_project(&path).unwrap_err()
        };
        assert!(refused(flac(Some(b"PLNOplenio.project/2\0whatever"))).contains("newer Plenio"));
        assert!(refused(flac(Some(&[PROJECT_PREFIX, b"not gzip"].concat()))).contains("damaged"));
        assert!(refused(flac(Some(&[PROJECT_PREFIX, &packed(b"not json")].concat()))).contains("damaged"));
        assert!(refused(flac(Some(&project(&json!({"schema": "something/1"}))))).contains("no release record"));
        // The metadata ends before its blocks do.
        let whole = flac(Some(&project(&record())));
        assert!(refused(whole[..50].to_vec()).contains("ends inside"));
        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn a_flac_alone_is_a_whole_song() {
        let dir = temp("alone");
        let path = dir.join("2026-11-05 Garden.flac");
        std::fs::write(&path, flac(Some(&project(&record())))).unwrap();
        let song = find_song(&path).unwrap();
        assert_eq!(song.record["title"], "Garden");
        assert_eq!(song.audio.as_deref(), Some(path.as_path()));
        assert_eq!((song.record_file, song.original), (None, None));
        // The lines come from the record, in order.
        assert_eq!(song.lines.iter().map(|l| l.text.as_str()).collect::<Vec<_>>(), ["Morning light", "Later"]);
        assert_eq!((song.lines[0].start, song.lines[0].end), (0.5, 2.0));
        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn every_file_of_a_song_finds_the_rest_of_it() {
        let dir = temp("beside");
        let main = dir.join("Garden.flac");
        let original = dir.join("Garden (original).flac");
        let file = dir.join("Garden.plenio.json");
        std::fs::write(&main, flac(Some(&project(&record())))).unwrap();
        // As Plenio writes it: the original carries no record.
        std::fs::write(&original, flac(None)).unwrap();
        std::fs::write(&file, record().to_string()).unwrap();
        std::fs::write(dir.join("Garden (lines).srt"), "1\n00:00:01,000 --> 00:00:02,000\nFrom the file\n").unwrap();
        for picked in [&main, &original, &file] {
            let song = find_song(picked).unwrap();
            assert_eq!(song.audio.as_deref(), Some(main.as_path()), "{}", picked.display());
            assert_eq!(song.original.as_deref(), Some(original.as_path()), "{}", picked.display());
            assert_eq!(song.record_file.as_deref(), Some(file.as_path()), "{}", picked.display());
            assert_eq!(song.lines.iter().map(|l| l.text.as_str()).collect::<Vec<_>>(), ["From the file"], "{}", picked.display());
        }
        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn audio_without_a_project_has_its_record_beside_it() {
        let dir = temp("sidecar");
        let mp3 = dir.join("Garden.MP3");
        std::fs::write(&mp3, b"ID3 not a flac").unwrap();
        std::fs::write(dir.join("Garden.plenio.json"), record().to_string()).unwrap();
        let song = find_song(&mp3).unwrap();
        assert_eq!(song.audio.as_deref(), Some(mp3.as_path()));
        assert_eq!(song.record["title"], "Garden");
        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn a_record_finds_no_audio_when_there_is_none() {
        let dir = temp("no-audio");
        let file = dir.join("Garden.plenio.json");
        std::fs::write(&file, record().to_string()).unwrap();
        let song = find_song(&file).unwrap();
        assert_eq!((song.audio, song.original), (None, None));
        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn a_file_that_is_no_plenio_song_is_refused_and_says_where_plain_audio_goes() {
        let dir = temp("no-song");
        let plain = dir.join("Holiday.flac");
        std::fs::write(&plain, flac(None)).unwrap();
        assert!(find_song(&plain).unwrap_err().contains("Import Audio"));
        let json = dir.join("settings.json");
        std::fs::write(&json, "{\"hello\": 1}").unwrap();
        assert!(find_song(&json).unwrap_err().contains("not a Plenio release record"));
        std::fs::write(&json, "not json").unwrap();
        assert!(find_song(&json).unwrap_err().contains("not a Plenio release record"));
        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn the_name_of_a_song_comes_from_any_of_its_files() {
        for (file, stem) in [
            ("Garden.flac", "Garden"),
            ("Garden (original).flac", "Garden"),
            ("Garden.plenio.json", "Garden"),
            ("Garden.PLENIO.JSON", "Garden"),
            ("Garden.json", "Garden"),
            ("Mr. Blue.flac", "Mr. Blue"),
            ("Café.plenio.json", "Café"),
            ("é.flac", "é"),
        ] {
            assert_eq!(song_stem(Path::new(file)), stem, "{file}");
        }
    }
}
