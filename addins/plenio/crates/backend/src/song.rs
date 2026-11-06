//! What the add-in reads from Plenio: a Song API job, a song's release record, the YuE2 score (ABC)
//! and timed lyrics (`.srt`). All of it is hostile input: parsed leniently and bounded, never
//! trusted to be well formed.

use serde_json::Value;
use std::collections::BTreeMap;

/// The most characters of one document kept (the Song API's own limit).
pub const MAX_DOCUMENT_CHARS: usize = 200_000;
/// The most files of one job read.
const MAX_FILES: usize = 64;
/// The most sections of a score read.
const MAX_SECTIONS: usize = 256;
/// The most subtitle cues read.
const MAX_CUES: usize = 20_000;

fn text(v: &Value, key: &str) -> String {
    v.get(key).and_then(Value::as_str).map(|s| s.chars().take(MAX_DOCUMENT_CHARS).collect()).unwrap_or_default()
}

/// A job's state (`GET /plenio/api/v1/jobs/{id}`).
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum JobStatus {
    Queued,
    Running,
    Succeeded,
    Failed,
    Cancelled,
    /// A state this add-in does not know (a later API).
    Other(String),
}

impl JobStatus {
    pub fn finished(&self) -> bool {
        matches!(self, JobStatus::Succeeded | JobStatus::Failed | JobStatus::Cancelled)
    }
}

/// A file of a finished job.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct JobFile {
    pub name: String,
    /// `original` (the unmastered take), `record`, `subtitles`, `sheet_music`, `cover`, or empty for
    /// the song itself.
    pub role: String,
    pub url: String,
}

/// A Song API job, as far as the add-in needs it.
#[derive(Debug, Clone, PartialEq)]
pub struct Job {
    pub id: String,
    pub status: JobStatus,
    pub queue_position: Option<u64>,
    /// What the studio does now (`stage.text`).
    pub stage: String,
    /// Nodes done and in all, as a fraction 0 … 1.
    pub progress: Option<f32>,
    pub seeds: BTreeMap<String, u64>,
    pub title: String,
    pub seconds: f64,
    /// The folder of the release in the studio's output (on this computer).
    pub folder: String,
    pub files: Vec<JobFile>,
    pub error: String,
    pub warnings: Vec<String>,
}

impl Job {
    pub fn parse(v: &Value) -> Option<Job> {
        let id = v.get("id")?.as_str()?.chars().take(128).collect::<String>();
        let status = match v.get("status").and_then(Value::as_str).unwrap_or_default() {
            "queued" => JobStatus::Queued,
            "running" => JobStatus::Running,
            "succeeded" => JobStatus::Succeeded,
            "failed" => JobStatus::Failed,
            "cancelled" => JobStatus::Cancelled,
            other => JobStatus::Other(other.chars().take(64).collect()),
        };
        let stage = v.get("stage").map(|s| text(s, "text")).unwrap_or_default();
        let progress = v.get("progress").and_then(|p| {
            let done = p.get("nodes_done")?.as_f64()?;
            let all = p.get("nodes")?.as_f64()?;
            (all > 0.0 && done.is_finite() && all.is_finite()).then(|| (done / all).clamp(0.0, 1.0) as f32)
        });
        let seeds = v
            .get("seeds")
            .and_then(Value::as_object)
            .map(|m| m.iter().take(16).filter_map(|(k, s)| Some((k.chars().take(32).collect(), s.as_u64()?))).collect())
            .unwrap_or_default();
        let result = v.get("result").filter(|r| r.is_object());
        let files = result
            .and_then(|r| r.get("files"))
            .and_then(Value::as_array)
            .map(|a| {
                a.iter()
                    .take(MAX_FILES)
                    .filter_map(|f| {
                        let name = f.get("name")?.as_str()?.to_string();
                        let url = f.get("url")?.as_str()?.to_string();
                        // Only the API's own file paths: never a path or a server the answer chose.
                        url.starts_with("/plenio/api/v1/jobs/").then(|| JobFile { name, role: text(f, "role"), url })
                    })
                    .collect()
            })
            .unwrap_or_default();
        let error = v.get("error").filter(|e| e.is_object()).map(|e| {
            let node = e.get("title").and_then(Value::as_str).unwrap_or_default();
            let message = text(e, "message");
            if node.is_empty() { message } else { format!("{node}: {message}") }
        });
        Some(Job {
            id,
            status,
            queue_position: v.get("queue_position").and_then(Value::as_u64),
            stage,
            progress,
            seeds,
            title: result.map(|r| text(r, "title")).unwrap_or_default(),
            folder: result.map(|r| text(r, "folder")).unwrap_or_default(),
            seconds: result.and_then(|r| r.get("seconds")).and_then(Value::as_f64).filter(|s| s.is_finite() && *s >= 0.0).unwrap_or(0.0),
            files,
            error: error.unwrap_or_default(),
            warnings: v
                .get("warnings")
                .and_then(Value::as_array)
                .map(|a| a.iter().take(32).filter_map(|w| w.as_str().map(str::to_string)).collect())
                .unwrap_or_default(),
        })
    }

    /// The file with this role (`""` for the song itself).
    pub fn file(&self, role: &str) -> Option<&JobFile> {
        self.files.iter().find(|f| f.role == role)
    }

    /// The timed lyrics: whole lines (`… (lines).srt`), the cue file the lyrics track shows.
    pub fn line_subtitles(&self) -> Option<&JobFile> {
        self.files.iter().find(|f| f.role == "subtitles" && f.name.ends_with("(lines).srt"))
    }
}

/// One of the Song Sheets' documents.
#[derive(Debug, Clone, PartialEq, Eq, Default)]
pub struct Document {
    pub text: String,
    /// `auto`, `edited` or `manual`.
    pub state: String,
}

/// A song's release record (`<name>.plenio.json`), as far as the add-in needs it.
#[derive(Debug, Clone, PartialEq, Default)]
pub struct Record {
    pub title: String,
    /// `title`, `style`, `lyrics`, `score`, `artwork_prompt`.
    pub documents: BTreeMap<String, Document>,
    pub seconds: f64,
    pub sample_rate: u32,
    /// Measured quality, 0 to 5 in halves.
    pub stars: Option<f32>,
    /// Where the score sits in the audio, `(a, b)` with `t_audio = a * t_score + b`: Plenio's
    /// measurement of the sung words against the score (none for a song without words).
    pub warp: Option<(f64, f64)>,
}

impl Record {
    pub fn parse(v: &Value) -> Record {
        let documents = v
            .get("documents")
            .and_then(Value::as_object)
            .map(|m| {
                m.iter()
                    .filter(|(k, _)| matches!(k.as_str(), "title" | "style" | "lyrics" | "score" | "artwork_prompt"))
                    .map(|(k, d)| (k.clone(), Document { text: text(d, "text"), state: text(d, "state") }))
                    .collect()
            })
            .unwrap_or_default();
        let audio = v.get("audio");
        let warp = v
            .get("timing")
            .and_then(Value::as_array)
            .and_then(|takes| takes.first())
            .and_then(|take| take.get("warp"))
            .and_then(Value::as_array)
            .and_then(|w| Some((w.first()?.as_f64()?, w.get(1)?.as_f64()?)));
        Record {
            warp,
            title: text(v, "title"),
            documents,
            seconds: audio.and_then(|a| a.get("seconds")).and_then(Value::as_f64).filter(|s| s.is_finite() && *s >= 0.0).unwrap_or(0.0),
            sample_rate: audio.and_then(|a| a.get("sample_rate")).and_then(Value::as_u64).and_then(|r| u32::try_from(r).ok()).unwrap_or(0),
            stars: v.get("quality").and_then(|q| q.get("stars")).and_then(Value::as_f64).filter(|s| s.is_finite()).map(|s| s.clamp(0.0, 5.0) as f32),
        }
    }

    pub fn document(&self, key: &str) -> &str {
        self.documents.get(key).map_or("", |d| d.text.as_str())
    }
}

/// A section of the score: its name and its bars.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Section {
    pub name: String,
    /// The first bar (0-based) and the number of bars.
    pub start_bar: u32,
    pub bars: u32,
}

/// What the add-in reads from a YuE2 score (ABC): tempo, meter, key and the sections.
#[derive(Debug, Clone, PartialEq)]
pub struct ScoreInfo {
    /// Quarter notes per minute.
    pub bpm: f64,
    pub meter: (u32, u32),
    /// `K:` as written (`F#m`).
    pub key: String,
    pub sections: Vec<Section>,
}

impl ScoreInfo {
    /// Read the header and the `% section` comments; the bars of a section are counted in its first
    /// voice (each voice repeats the same bars).
    pub fn parse(abc: &str) -> Option<ScoreInfo> {
        let mut bpm = None;
        let mut meter = (4, 4);
        let mut key = String::new();
        let mut sections: Vec<Section> = Vec::new();
        let mut first_voice: Option<String> = None;
        let mut current_voice: Option<String> = None;
        let mut bar = 0u32;
        for line in abc.lines().take(100_000) {
            let line = line.trim();
            if let Some(q) = line.strip_prefix("Q:") {
                bpm = parse_tempo(q);
            } else if let Some(m) = line.strip_prefix("M:") {
                meter = parse_meter(m).unwrap_or(meter);
            } else if let Some(k) = line.strip_prefix("K:") {
                key = k.split_whitespace().next().unwrap_or_default().chars().take(16).collect();
            } else if let Some(name) = line.strip_prefix('%') {
                let name = name.trim();
                if !name.is_empty() && !name.starts_with('%') && sections.len() < MAX_SECTIONS && !name.contains(':') {
                    sections.push(Section { name: name.chars().take(64).collect(), start_bar: bar, bars: 0 });
                }
            } else if let Some(v) = line.strip_prefix("V:") {
                let id = v.split_whitespace().next().unwrap_or_default().to_string();
                if first_voice.is_none() && !line.contains("clef=") {
                    first_voice = Some(id.clone());
                }
                current_voice = Some(id);
            } else if !line.is_empty() && current_voice.is_some() && current_voice == first_voice {
                let bars = line.matches('|').count() as u32;
                bar = bar.saturating_add(bars);
                if let Some(s) = sections.last_mut() {
                    s.bars = s.bars.saturating_add(bars);
                }
            }
        }
        sections.retain(|s| s.bars > 0);
        Some(ScoreInfo { bpm: bpm?, meter, key, sections })
    }

    /// The length of `bars` bars in seconds.
    pub fn bar_seconds(&self) -> f64 {
        let quarters = f64::from(self.meter.0) * 4.0 / f64::from(self.meter.1.max(1));
        quarters * 60.0 / self.bpm
    }
}

/// `1/4=70`, `70`, `"Allegro" 1/4=120` → quarter notes per minute.
fn parse_tempo(q: &str) -> Option<f64> {
    let q = q.trim();
    let (beat, rate) = match q.rsplit_once('=') {
        Some((beat, rate)) => (beat.split_whitespace().last().unwrap_or("1/4"), rate),
        None => ("1/4", q),
    };
    let rate: f64 = rate.split_whitespace().next()?.parse().ok()?;
    let (n, d) = beat.split_once('/').unwrap_or(("1", "4"));
    let beat_quarters = n.trim().parse::<f64>().ok()? * 4.0 / d.trim().parse::<f64>().ok().filter(|d| *d > 0.0)?;
    let bpm = rate * beat_quarters;
    (bpm.is_finite() && (10.0..=400.0).contains(&bpm)).then_some(bpm)
}

fn parse_meter(m: &str) -> Option<(u32, u32)> {
    let m = m.trim();
    match m {
        "C" => return Some((4, 4)),
        "C|" => return Some((2, 2)),
        _ => {}
    }
    let (n, d) = m.split_once('/')?;
    let n: u32 = n.trim().parse().ok().filter(|n| (1..=32).contains(n))?;
    let d: u32 = d.trim().parse().ok().filter(|d| [1, 2, 4, 8, 16, 32].contains(d))?;
    Some((n, d))
}

/// One cue of timed lyrics.
#[derive(Debug, Clone, PartialEq)]
pub struct Cue {
    pub start: f64,
    pub end: f64,
    pub text: String,
}

/// Read an `.srt` file's cues (`hh:mm:ss,mmm --> hh:mm:ss,mmm`), sorted by start.
pub fn parse_srt(srt: &str) -> Vec<Cue> {
    let mut cues = Vec::new();
    let normalized = srt.replace("\r\n", "\n");
    for block in normalized.split("\n\n").take(MAX_CUES) {
        let mut lines = block.lines().filter(|l| !l.trim().is_empty());
        let Some(first) = lines.next() else { continue };
        let timing = if first.contains("-->") { first } else { lines.next().unwrap_or_default() };
        let Some((a, b)) = timing.split_once("-->") else { continue };
        let (Some(start), Some(end)) = (srt_time(a), srt_time(b)) else { continue };
        let text: Vec<&str> = lines.collect();
        if end >= start {
            cues.push(Cue { start, end, text: text.join("\n").chars().take(2000).collect() });
        }
    }
    cues.sort_by(|x, y| x.start.total_cmp(&y.start));
    cues
}

fn srt_time(t: &str) -> Option<f64> {
    let t = t.trim().replace(',', ".");
    let mut parts = t.split(':');
    let h: f64 = parts.next()?.trim().parse().ok()?;
    let m: f64 = parts.next()?.trim().parse().ok()?;
    let s: f64 = parts.next()?.split_whitespace().next()?.parse().ok()?;
    let v = h * 3600.0 + m * 60.0 + s;
    (v.is_finite() && v >= 0.0).then_some(v)
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn a_finished_job_names_its_files_and_seeds() {
        let job = Job::parse(&json!({
            "id": "abc", "status": "succeeded", "seeds": {"take": 14, "plan": 12, "bad": -1},
            "result": {"title": "Night Drive", "seconds": 92.4, "files": [
                {"name": "a.flac", "url": "/plenio/api/v1/jobs/abc/files/a.flac"},
                {"name": "a (original).flac", "role": "original", "url": "/plenio/api/v1/jobs/abc/files/a%20(original).flac"},
                {"name": "a (lines).srt", "role": "subtitles", "url": "/plenio/api/v1/jobs/abc/files/a%20(lines).srt"},
                {"name": "evil", "url": "http://elsewhere/x"}
            ]}
        }))
        .unwrap();
        assert!(job.status.finished());
        assert_eq!(job.seeds.get("take"), Some(&14));
        assert!(!job.seeds.contains_key("bad"));
        assert_eq!(job.files.len(), 3, "a file somewhere else is never taken");
        assert_eq!(job.file("original").map(|f| f.name.as_str()), Some("a (original).flac"));
        assert!(job.line_subtitles().is_some());
        assert_eq!(job.title, "Night Drive");
    }

    #[test]
    fn a_running_or_failed_job_says_where_it_is() {
        let job = Job::parse(&json!({"id": "x", "status": "running", "stage": {"text": "composing"}, "progress": {"nodes_done": 27, "nodes": 87}}))
            .unwrap();
        assert_eq!(job.stage, "composing");
        assert!(job.progress.is_some_and(|p| (p - 27.0 / 87.0).abs() < 1e-4));
        let failed = Job::parse(&json!({"id": "x", "status": "failed", "error": {"message": "out of memory", "title": "YuE2 Render"}})).unwrap();
        assert_eq!(failed.error, "YuE2 Render: out of memory");
        assert!(Job::parse(&json!({"status": "running"})).is_none());
        assert_eq!(Job::parse(&json!({"id": "x", "status": "later"})).unwrap().status, JobStatus::Other("later".into()));
    }

    #[test]
    fn a_record_gives_documents_length_and_stars() {
        let r = Record::parse(&json!({"title": "T", "documents": {"lyrics": {"state": "auto", "text": "[verse]\nhi"}, "junk": {"text": "x"}},
            "audio": {"seconds": 61.08, "sample_rate": 48000}, "quality": {"stars": 4.0}}));
        assert_eq!(r.document("lyrics"), "[verse]\nhi");
        assert_eq!(r.documents.len(), 1);
        assert_eq!((r.seconds, r.sample_rate, r.stars), (61.08, 48000, Some(4.0)));
        assert_eq!(Record::parse(&json!([1])), Record::default());
    }

    #[test]
    fn the_score_header_and_sections_are_read() {
        let abc = "X:1\nT:\nM:2/4\nL:1/16\nQ:1/4=70\nV: Vocal clef=treble name=\"Vocal Melody\"\nV: Ins clef=treble\nK:F#m\n% intro\nV: Vocal\n\"F#m\"z8|\"F#m\"z8|z8|z8|\nV: Ins\nZ|F2z2F2z2|Z|Z|\nV: Vocal\nz8|z8|\n% chorus\nV: Vocal\nz8|z8|z8|\nV: Ins\nZ|Z|Z|\n";
        let s = ScoreInfo::parse(abc).unwrap();
        assert_eq!((s.bpm, s.meter, s.key.as_str()), (70.0, (2, 4), "F#m"));
        assert_eq!(
            s.sections,
            vec![Section { name: "intro".into(), start_bar: 0, bars: 6 }, Section { name: "chorus".into(), start_bar: 6, bars: 3 }]
        );
        assert!((s.bar_seconds() - 2.0 * 60.0 / 70.0).abs() < 1e-9);
        assert_eq!(parse_tempo("3/8=40"), Some(60.0));
        assert_eq!(parse_tempo("1/4=99999"), None);
        assert!(ScoreInfo::parse("no header").is_none());
    }

    #[test]
    fn timed_lyrics_are_read_and_bad_cues_skipped() {
        let srt = "1\r\n00:00:01,500 --> 00:00:03,000\r\nRain on the road\r\n\r\n2\n00:00:03,250 --> 00:00:02,000\nbackwards\n\n3\n00:01:00,000 --> 00:01:02,500\nWe drive\non\n\nnonsense";
        let cues = parse_srt(srt);
        assert_eq!(cues.len(), 2);
        assert_eq!(cues[0], Cue { start: 1.5, end: 3.0, text: "Rain on the road".into() });
        assert_eq!(cues[1].text, "We drive\non");
        assert!((cues[1].start - 60.0).abs() < 1e-9);
    }
}
