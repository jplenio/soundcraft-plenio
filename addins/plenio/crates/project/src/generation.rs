//! Takes, and what the next one is made from.
//!
//! A take freezes what it was made from: the fields, the documents (title, style, lyrics, score,
//! artwork prompt) and the seeds. The song's working copy starts as the active take's; what the
//! owner edits becomes *manual*. [`plan`] turns the working copy into the next job: it keeps what
//! still holds and leaves out what an edit made stale, following Plenio's rule that new words need
//! new notes (a score is kept only when the lyrics it was planned for are unchanged, or when the
//! owner wrote the score).

use crate::{MAX_DOCUMENT_CHARS, MAX_FIELDS, MAX_TAKES, Song, SongKind};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use soundcraft_model::{Session, TrackId, truncate_chars};
use std::collections::BTreeMap;

/// The documents a song is made from, in the order they depend on each other.
pub const DOCUMENTS: [&str; 5] = ["title", "style", "lyrics", "score", "artwork_prompt"];
/// The most timed lines and sections one take keeps.
const MAX_SPANS: usize = 4000;

/// Who wrote a working document.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum DocState {
    /// Plenio wrote it (it comes from a take).
    #[default]
    Auto,
    /// The owner wrote or changed it: sent as it is, never replaced.
    Manual,
}

/// A working document.
#[derive(Debug, Clone, PartialEq, Eq, Default, Serialize, Deserialize)]
#[serde(default)]
pub struct Doc {
    pub text: String,
    pub state: DocState,
}

/// A part of the song in time (seconds on the session's timeline, once the take is laid out).
#[derive(Debug, Clone, PartialEq, Default, Serialize, Deserialize)]
#[serde(default)]
pub struct SectionSpan {
    pub name: String,
    pub start: f64,
    pub end: f64,
}

/// A line of the lyrics as sung (seconds on the session's timeline, once the take is laid out).
#[derive(Debug, Clone, PartialEq, Default, Serialize, Deserialize)]
#[serde(default)]
pub struct LineSpan {
    pub start: f64,
    pub end: f64,
    pub text: String,
}

/// Which playlist of a track holds a take.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub struct PlaylistRef {
    pub track: TrackId,
    pub index: usize,
}

/// Where the measures of a score lie in a take's audio, measured from the audio. The take is the master:
/// a YuE2 render keeps no steady tempo, so the session's tempo map follows these times, and the audio
/// stays as it is. The bars of the session are then the take's bars, whatever the tempo does.
#[derive(Debug, Clone, PartialEq, Default, Serialize, Deserialize)]
#[serde(default)]
pub struct BarMap {
    /// Every measure's start and the score's end, in seconds of the score at its own tempo.
    pub score: Vec<f64>,
    /// The same, in seconds of the take's audio (before 0 where the score starts before the audio).
    pub audio: Vec<f64>,
    /// The meter of every measure: one value fewer than the times.
    pub meters: Vec<(u32, u32)>,
}

/// The most measures believed.
const MAX_BARS: usize = 4096;

fn increasing(times: &[f64]) -> bool {
    times.iter().all(|t| t.is_finite()) && times.windows(2).all(|w| w.first() < w.last())
}

/// The value at `x` of the straight pieces through `from` → `to`; the first and last go on outside.
fn through(from: &[f64], to: &[f64], x: f64) -> f64 {
    let k = from.partition_point(|v| *v <= x).saturating_sub(1).min(from.len().saturating_sub(2));
    match (from.get(k), from.get(k + 1), to.get(k), to.get(k + 1)) {
        (Some(a), Some(b), Some(c), Some(d)) if b > a => c + (x - a) * (d - c) / (b - a),
        _ => x,
    }
}

impl BarMap {
    /// Quarter notes in a measure of this meter.
    pub fn quarters(meter: (u32, u32)) -> f64 {
        f64::from(meter.0) * 4.0 / f64::from(meter.1.max(1))
    }

    /// Whether it can be laid out: times in order for every measure, meters and tempos that exist.
    pub fn usable(&self) -> bool {
        let count = self.meters.len();
        let lengths_fit = self.score.len() == count + 1 && self.audio.len() == count + 1;
        let meters_exist = self.meters.iter().all(|(n, d)| (1..=64).contains(n) && [1, 2, 4, 8, 16, 32, 64].contains(d));
        (1..=MAX_BARS).contains(&count)
            && lengths_fit
            && meters_exist
            && increasing(&self.score)
            && increasing(&self.audio)
            && self.tempos().all(|t| (5.0..=1000.0).contains(&t))
    }

    /// The tempo of every measure in quarter notes a minute.
    pub fn tempos(&self) -> impl Iterator<Item = f64> + '_ {
        self.meters.iter().zip(self.audio.windows(2)).map(|(meter, times)| match times {
            [a, b] => Self::quarters(*meter) * 60.0 / (b - a),
            _ => 0.0,
        })
    }

    /// The slowest and the fastest tempo of its measures.
    pub fn tempo_range(&self) -> (f64, f64) {
        self.tempos().fold((f64::MAX, f64::MIN), |(low, high), t| (low.min(t), high.max(t)))
    }

    /// A time of the score (seconds at its own tempo) in the take's audio.
    pub fn audio_of(&self, score: f64) -> f64 {
        through(&self.score, &self.audio, score)
    }

    /// A time of the take's audio in the score.
    pub fn score_of(&self, audio: f64) -> f64 {
        through(&self.audio, &self.score, audio)
    }

    /// Where the audio has the score's first measure, and how long that measure lasts.
    fn first_measure(&self) -> (f64, f64) {
        match self.audio.as_slice() {
            [a, b, ..] => (*a, b - a),
            _ => (0.0, 0.0),
        }
    }
}

/// One rendered take of a song.
#[derive(Debug, Clone, PartialEq, Default, Serialize, Deserialize)]
#[serde(default)]
pub struct Take {
    /// 1, 2, 3 … within the song.
    pub number: u32,
    /// The Song API job that made it.
    pub job: String,
    pub title: String,
    pub seeds: BTreeMap<String, u64>,
    pub fields: BTreeMap<String, Value>,
    /// The documents it was made from, as the release record has them.
    pub documents: BTreeMap<String, String>,
    /// Plenio's measured quality, 0 to 5.
    pub stars: Option<f32>,
    pub seconds: f64,
    /// Its files on disk: `song` (released), `original` (unmastered), `record`.
    pub files: BTreeMap<String, String>,
    pub sections: Vec<SectionSpan>,
    pub lines: Vec<LineSpan>,
    pub bpm: Option<f64>,
    pub key: String,
    /// Where the take lies on the song's tracks.
    pub playlists: Vec<PlaylistRef>,
    /// The score's MIDI file: which of its tracks went to which score role (`melody`, …).
    pub midi_tracks: BTreeMap<String, usize>,
    /// What the score tracks held when the take was laid out, to tell the owner's edits.
    pub midi_digests: BTreeMap<String, u64>,
    /// Where the score sits in the take's audio, `(a, b)` with `t_audio = a * t_score + b`: Plenio's
    /// measurement of the sung words against the score's notes, or its estimate from the music. A
    /// YuE2 render is shifted against its score (seconds, and each take by its own amount).
    pub warp: Option<(f64, f64)>,
    /// Where the score's measures lie in the take's audio. With it the session's tempo follows the take;
    /// without it (not measured, or a session from before) the take lies on the straight line of `warp`.
    pub bars: Option<BarMap>,
    /// Where the take's audio starts on the session's timeline (seconds).
    pub audio_at: f64,
    /// Where the first bar of its score lies on the session's timeline (seconds): a bar line, so that
    /// the session's bars are the score's.
    pub score_at: f64,
}

/// The largest shift of a take against its score that is believed (seconds).
const MAX_SHIFT: f64 = 120.0;

/// Whether a measured warp can be true: Plenio looks at scales of 0.92 to 1.08 and shifts of seconds.
pub fn warp_ok(warp: (f64, f64)) -> bool {
    let (a, b) = warp;
    a.is_finite() && b.is_finite() && (0.5..=2.0).contains(&a) && b.abs() <= MAX_SHIFT
}

impl Take {
    /// The scale of the score's time in the take's audio (1 when nothing was measured).
    fn scale(&self) -> f64 {
        self.warp.filter(|w| warp_ok(*w)).map_or(1.0, |w| w.0)
    }

    /// A time of the score (seconds from its first bar) on the session's timeline.
    pub fn score_to_session(&self, seconds: f64) -> f64 {
        match &self.bars {
            Some(bars) => self.audio_at + bars.audio_of(seconds),
            None => self.score_at + self.scale() * seconds,
        }
    }

    /// A time on the session's timeline as a time of the score.
    pub fn session_to_score(&self, seconds: f64) -> f64 {
        match &self.bars {
            Some(bars) => bars.score_of(seconds - self.audio_at),
            None => (seconds - self.score_at) / self.scale(),
        }
    }

    /// Lay the take out on the session's timeline so that audio, words and notes meet: the score's
    /// first bar on a bar line (the first one it can reach), the audio where the bars (or else the warp)
    /// put it against the score. `bar_seconds` is the session's bar for a take without bars of its own.
    /// `lines` come in audio time and `sections` in score time; both leave in session time. A section
    /// ends with the audio at the latest.
    pub fn lay_out(&mut self, bar_seconds: f64) {
        self.warp = self.warp.filter(|w| warp_ok(*w));
        self.bars = self.bars.take().filter(BarMap::usable);
        let (shift, bar_seconds) = match &self.bars {
            Some(bars) => bars.first_measure(),
            None => (self.warp.map_or(0.0, |w| w.1), bar_seconds),
        };
        self.score_at = if shift > 0.0 && bar_seconds > 0.0 { (shift / bar_seconds).ceil() * bar_seconds } else { 0.0 };
        self.audio_at = (self.score_at - shift).max(0.0);
        let audio_at = self.audio_at;
        for line in &mut self.lines {
            line.start += audio_at;
            line.end += audio_at;
        }
        let audio_end = if self.seconds > 0.0 { audio_at + self.seconds } else { f64::MAX };
        let sections: Vec<(f64, f64)> = self.sections.iter().map(|s| (self.score_to_session(s.start), self.score_to_session(s.end))).collect();
        for (section, (start, end)) in self.sections.iter_mut().zip(sections) {
            section.start = start;
            section.end = end.min(audio_end).max(start);
        }
    }

    /// `Take 3 · 4.5 stars`.
    pub fn label(&self) -> String {
        match self.stars {
            Some(s) => format!("Take {} · {} stars", self.number, trim_number(f64::from(s))),
            None => format!("Take {}", self.number),
        }
    }
}

fn trim_number(v: f64) -> String {
    if (v - v.round()).abs() < 1e-6 { format!("{}", v.round()) } else { format!("{v:.1}") }
}

/// How to make the next take.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Mode {
    /// Whatever the changes call for (Generate).
    Auto,
    /// The same title, words and notes, sung and played anew.
    NewTake,
    /// Keep the words, plan new notes.
    Recompose,
    /// Write the song anew from the brief (keeping only what the owner wrote).
    Rewrite,
}

/// What the next take will be.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum What {
    /// The first take: written, planned and rendered from the brief.
    NewSong,
    /// The same song again: a new take of the same words and notes.
    NewTake,
    /// The owner's notes, sung as written.
    SingYourNotes,
    /// New notes for the (changed) words.
    Recompose,
    /// Written anew from the (changed) brief.
    Rewrite,
}

impl What {
    pub fn label(self) -> &'static str {
        match self {
            What::NewSong => "write, compose and render the song",
            What::NewTake => "render a new take of the same song",
            What::SingYourNotes => "render a take of your notes",
            What::Recompose => "compose new notes for the words, then render",
            What::Rewrite => "write the song anew from the brief, then render",
        }
    }
}

/// The next job: its fields, the documents it is given and the seeds it keeps.
#[derive(Debug, Clone, PartialEq)]
pub struct Plan {
    pub what: What,
    pub fields: BTreeMap<String, Value>,
    pub documents: BTreeMap<String, String>,
    pub seeds: BTreeMap<String, u64>,
}

impl Song {
    /// The manual documents that differ from the active take's.
    fn edited(&self) -> Vec<&'static str> {
        let take = self.active_take();
        DOCUMENTS
            .iter()
            .copied()
            .filter(|k| {
                self.documents.get(*k).is_some_and(|d| d.state == DocState::Manual && take.and_then(|t| t.documents.get(*k)) != Some(&d.text))
            })
            .collect()
    }

    /// What changed since the active take, for the song's header: `brief`, `lyrics`, `score` ….
    pub fn changes(&self) -> Vec<String> {
        let Some(take) = self.active_take() else { return Vec::new() };
        let mut out = Vec::new();
        let changed_fields: Vec<&String> = self.fields.iter().filter(|(k, v)| take.fields.get(*k) != Some(*v)).map(|(k, _)| k).collect();
        if !changed_fields.is_empty() || take.fields.keys().any(|k| !self.fields.contains_key(k)) {
            out.push("brief".to_string());
        }
        out.extend(self.edited().into_iter().map(|k| k.replace('_', " ")));
        out
    }

    /// The next job for `mode`.
    pub fn plan(&self, mode: Mode) -> Plan {
        let mut fields = self.fields.clone();
        if self.kind == SongKind::Cover
            && let Some(source) = &self.source
        {
            fields.insert("source.audio".into(), Value::String(source.clone()));
        }
        let manual: BTreeMap<String, String> = self
            .documents
            .iter()
            .filter(|(_, d)| d.state == DocState::Manual && !d.text.trim().is_empty())
            .map(|(k, d)| (k.clone(), d.text.clone()))
            .collect();
        let seeds = self.seeds.clone();
        let Some(take) = self.active_take() else {
            return Plan { what: What::NewSong, fields, documents: manual, seeds };
        };
        let edited = self.edited();
        let brief_changed = self.changes().first().is_some_and(|c| c == "brief");
        let words_changed = edited.iter().any(|k| matches!(*k, "title" | "style" | "lyrics"));
        let score_written = manual.contains_key("score");
        let what = match mode {
            Mode::Rewrite => What::Rewrite,
            Mode::Recompose => What::Recompose,
            Mode::NewTake => What::NewTake,
            Mode::Auto if brief_changed => What::Rewrite,
            Mode::Auto if words_changed && !score_written => What::Recompose,
            Mode::Auto if edited.contains(&"score") => What::SingYourNotes,
            Mode::Auto => What::NewTake,
        };
        // Start from the take's documents, put the owner's over them, then leave out what is stale.
        let mut documents: BTreeMap<String, String> = take.documents.clone();
        documents.extend(manual.clone());
        match what {
            What::Rewrite => documents = manual,
            What::Recompose => {
                // Manual notes were written for other words or are being replaced on purpose.
                documents.remove("score");
            }
            What::NewTake if words_changed && !score_written => {
                // Asked for the same notes, but the words changed: they would not fit.
                documents.remove("score");
            }
            _ => {}
        }
        documents.retain(|_, text| !text.trim().is_empty());
        Plan { what, fields, documents, seeds }
    }

    /// After a take: its documents become the working copy, the owner's edits are in it now.
    pub fn adopt(&mut self, index: usize) {
        let Some(take) = self.takes.get(index) else { return };
        self.documents = take.documents.iter().map(|(k, text)| (k.clone(), Doc { text: text.clone(), state: DocState::Auto })).collect();
        self.fields = take.fields.clone();
        if !take.title.is_empty() {
            self.title = take.title.clone();
        }
        self.active = Some(index);
    }
}

/// Bound a song read from a file.
pub(crate) fn sanitize(song: &mut Song, session: &Session) {
    while song.fields.len() > MAX_FIELDS {
        let Some(last) = song.fields.keys().next_back().cloned() else { break };
        song.fields.remove(&last);
    }
    song.fields.retain(|k, v| k.len() <= 128 && v.to_string().len() <= MAX_DOCUMENT_CHARS);
    song.documents.retain(|k, _| DOCUMENTS.contains(&k.as_str()));
    song.documents.values_mut().for_each(|d| truncate_chars(&mut d.text, MAX_DOCUMENT_CHARS));
    song.seeds.retain(|k, _| k.len() <= 32);
    song.takes.truncate(MAX_TAKES);
    for take in &mut song.takes {
        take.documents.retain(|k, _| DOCUMENTS.contains(&k.as_str()));
        take.documents.values_mut().for_each(|t| truncate_chars(t, MAX_DOCUMENT_CHARS));
        take.fields.retain(|k, v| k.len() <= 128 && v.to_string().len() <= MAX_DOCUMENT_CHARS);
        take.sections.truncate(MAX_SPANS);
        take.lines.truncate(MAX_SPANS);
        take.sections.retain(|s| s.start.is_finite() && s.end.is_finite() && s.end >= s.start);
        take.lines.retain(|l| l.start.is_finite() && l.end.is_finite() && l.end >= l.start);
        take.lines.iter_mut().for_each(|l| truncate_chars(&mut l.text, 2000));
        take.playlists.retain(|p| session.track(p.track).is_some_and(|t| p.index < t.playlists.len()));
        if !take.seconds.is_finite() || take.seconds < 0.0 {
            take.seconds = 0.0;
        }
        take.stars = take.stars.filter(|s| s.is_finite()).map(|s| s.clamp(0.0, 5.0));
        take.bpm = take.bpm.filter(|b| b.is_finite() && (10.0..=400.0).contains(b));
        take.warp = take.warp.filter(|w| warp_ok(*w));
        take.bars = take.bars.take().filter(BarMap::usable);
        for at in [&mut take.audio_at, &mut take.score_at] {
            if !at.is_finite() || *at < 0.0 {
                *at = 0.0;
            }
        }
    }
    if song.active.is_some_and(|i| i >= song.takes.len()) {
        song.active = song.takes.len().checked_sub(1);
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    /// Four measures of 4/4 that run at 120, 100, 150 and 120, the first at `first` in the audio.
    fn bars(first: f64) -> BarMap {
        BarMap {
            score: vec![0.0, 2.0, 4.0, 6.0, 8.0],
            audio: vec![first, first + 2.0, first + 4.4, first + 6.0, first + 8.0],
            meters: vec![(4, 4); 4],
        }
    }

    #[test]
    fn a_bar_map_goes_both_ways_through_its_measures_and_on_outside_them() {
        let map = bars(1.0);
        assert!(map.usable());
        let near = |a: f64, b: f64| (a - b).abs() < 1e-9;
        let tempos: Vec<f64> = map.tempos().collect();
        assert!(tempos.iter().zip([120.0, 100.0, 150.0, 120.0]).all(|(a, b)| near(*a, b)), "{tempos:?}");
        let (low, high) = map.tempo_range();
        assert!(near(low, 100.0) && near(high, 150.0));
        for (score, audio) in [(0.0, 1.0), (2.0, 3.0), (3.0, 4.2), (4.0, 5.4), (8.0, 9.0), (9.0, 10.0), (-1.0, 0.0)] {
            assert!((map.audio_of(score) - audio).abs() < 1e-9, "{score}");
            assert!((map.score_of(audio) - score).abs() < 1e-9, "{audio}");
        }
    }

    #[test]
    fn a_bar_map_that_cannot_be_true_is_not_used() {
        let usable = bars(0.0);
        let broken = [
            BarMap { meters: vec![(4, 4); 3], ..usable.clone() },
            BarMap { audio: vec![0.0, 2.0, 2.0, 4.0, 6.0], ..usable.clone() },
            BarMap { audio: vec![0.0, 2.0, f64::NAN, 4.0, 6.0], ..usable.clone() },
            BarMap { meters: vec![(4, 3); 4], ..usable.clone() },
            BarMap { audio: vec![0.0, 0.001, 2.0, 4.0, 6.0], ..usable.clone() },
            BarMap::default(),
        ];
        for map in broken {
            assert!(!map.usable(), "{map:?}");
        }
        let mut take = Take { bars: Some(BarMap { meters: Vec::new(), ..usable }), ..Take::default() };
        take.lay_out(2.0);
        assert_eq!(take.bars, None);
    }

    #[test]
    fn a_take_with_bars_lies_where_they_say() {
        // The audio has the first measure 0.5 s in: the score moves to the first bar line it can reach.
        let mut take = Take {
            bars: Some(bars(0.5)),
            warp: Some((0.9, 7.0)),
            lines: vec![LineSpan { start: 0.5, end: 1.0, text: "first".into() }],
            sections: vec![SectionSpan { name: "verse".into(), start: 2.0, end: 4.0 }],
            ..Take::default()
        };
        take.lay_out(99.0);
        assert_eq!((take.score_at, take.audio_at), (2.0, 1.5));
        // Measure by measure through the audio, not by the warp's straight line.
        assert!((take.score_to_session(4.0) - (1.5 + 4.9)).abs() < 1e-9);
        assert!((take.session_to_score(1.5 + 4.9) - 4.0).abs() < 1e-9);
        assert_eq!((take.lines[0].start, take.sections[0].start), (2.0, 1.5 + 2.5));

        // The audio starts after the score's first measure: the score starts at the session's start.
        let mut late = Take { bars: Some(bars(-1.25)), ..Take::default() };
        late.lay_out(99.0);
        assert_eq!((late.score_at, late.audio_at), (0.0, 1.25));
        assert!((late.score_to_session(2.0) - 2.0).abs() < 1e-9);
    }

    fn timed(warp: Option<(f64, f64)>) -> Take {
        Take {
            warp,
            seconds: 100.0,
            lines: vec![LineSpan { start: 10.0, end: 12.0, text: "hi".into() }],
            sections: vec![SectionSpan { name: "verse".into(), start: 4.0, end: 200.0 }],
            ..Take::default()
        }
    }

    #[test]
    fn a_take_that_starts_early_moves_its_audio_and_keeps_the_score_on_the_first_bar() {
        let mut t = timed(Some((1.0, -1.28)));
        t.lay_out(2.0);
        assert_eq!((t.score_at, t.audio_at), (0.0, 1.28));
        assert_eq!((t.lines[0].start, t.lines[0].end), (11.28, 13.28));
        assert_eq!(t.sections[0].start, 4.0);
        assert_eq!(t.sections[0].end, 101.28, "a section ends with the audio");
    }

    #[test]
    fn a_take_that_starts_late_moves_the_score_to_the_next_bar_line() {
        let mut t = timed(Some((1.0, 2.5)));
        t.lay_out(2.0);
        assert_eq!((t.score_at, t.audio_at), (4.0, 1.5));
        assert_eq!(t.sections[0].start, 8.0);
    }

    #[test]
    fn the_scale_is_applied_both_ways() {
        let mut t = timed(Some((0.998, -1.3)));
        t.lay_out(2.0);
        assert_eq!(t.audio_at, 1.3);
        assert!((t.score_to_session(100.0) - 99.8).abs() < 1e-9);
        assert!((t.session_to_score(t.score_to_session(123.4)) - 123.4).abs() < 1e-9);
    }

    #[test]
    fn a_warp_that_cannot_be_true_is_ignored() {
        for bad in [(0.0, 0.0), (9.0, 0.0), (1.0, 1e300), (f64::NAN, 0.0), (1.0, f64::INFINITY)] {
            let mut t = timed(Some(bad));
            t.lay_out(2.0);
            assert_eq!((t.warp, t.score_at, t.audio_at, t.lines[0].start), (None, 0.0, 0.0, 10.0));
        }
        let mut t = timed(None);
        t.lay_out(0.0);
        assert_eq!((t.score_at, t.audio_at), (0.0, 0.0));
    }

    fn take(lyrics: &str, score: &str) -> Take {
        Take {
            number: 1,
            documents: [("title", "Night Drive"), ("style", "synthwave"), ("lyrics", lyrics), ("score", score)]
                .into_iter()
                .map(|(k, v)| (k.to_string(), v.to_string()))
                .collect(),
            fields: [("genre".to_string(), json!("synthwave"))].into_iter().collect(),
            ..Take::default()
        }
    }

    fn song_with_take() -> Song {
        let mut s = Song { template: "yue2-song".into(), takes: vec![take("[verse] rain", "X:1 notes")], ..Song::default() };
        s.adopt(0);
        s
    }

    fn manual(s: &mut Song, key: &str, text: &str) {
        s.documents.insert(key.into(), Doc { text: text.into(), state: DocState::Manual });
    }

    #[test]
    fn the_first_take_sends_only_what_the_owner_wrote() {
        let mut s = Song::default();
        manual(&mut s, "lyrics", "[verse] my own words");
        let p = s.plan(Mode::Auto);
        assert_eq!(p.what, What::NewSong);
        assert_eq!(p.documents.keys().collect::<Vec<_>>(), vec!["lyrics"]);
    }

    #[test]
    fn nothing_changed_is_a_new_take_of_the_same_song() {
        let s = song_with_take();
        assert!(s.changes().is_empty());
        let p = s.plan(Mode::Auto);
        assert_eq!(p.what, What::NewTake);
        assert_eq!(p.documents.get("score").map(String::as_str), Some("X:1 notes"));
        assert_eq!(p.documents.get("lyrics").map(String::as_str), Some("[verse] rain"));
    }

    #[test]
    fn new_words_need_new_notes() {
        let mut s = song_with_take();
        manual(&mut s, "lyrics", "[verse] snow");
        assert_eq!(s.changes(), vec!["lyrics"]);
        let p = s.plan(Mode::Auto);
        assert_eq!(p.what, What::Recompose);
        assert_eq!(p.documents.get("lyrics").map(String::as_str), Some("[verse] snow"));
        assert!(!p.documents.contains_key("score"));
        // Even when a new take of the same notes is asked for.
        assert!(!s.plan(Mode::NewTake).documents.contains_key("score"));
    }

    #[test]
    fn the_owners_notes_are_sung_as_written() {
        let mut s = song_with_take();
        manual(&mut s, "score", "X:1 my notes");
        let p = s.plan(Mode::Auto);
        assert_eq!(p.what, What::SingYourNotes);
        assert_eq!(p.documents.get("score").map(String::as_str), Some("X:1 my notes"));
        // New words and the owner's notes for them: both are kept.
        manual(&mut s, "lyrics", "[verse] snow");
        assert_eq!(s.plan(Mode::Auto).documents.get("score").map(String::as_str), Some("X:1 my notes"));
    }

    #[test]
    fn a_changed_brief_rewrites_but_keeps_the_owners_words() {
        let mut s = song_with_take();
        s.fields.insert("genre".into(), json!("jazz"));
        manual(&mut s, "title", "My Title");
        assert_eq!(s.changes(), vec!["brief", "title"]);
        let p = s.plan(Mode::Auto);
        assert_eq!(p.what, What::Rewrite);
        assert_eq!(p.documents.keys().collect::<Vec<_>>(), vec!["title"]);
        assert_eq!(p.fields.get("genre"), Some(&json!("jazz")));
    }

    #[test]
    fn recompose_drops_the_notes_and_rewrite_keeps_only_manual_documents() {
        let s = song_with_take();
        assert!(!s.plan(Mode::Recompose).documents.contains_key("score"));
        assert!(s.plan(Mode::Rewrite).documents.is_empty());
    }

    #[test]
    fn a_cover_sends_its_recording() {
        let s = Song { kind: SongKind::Cover, source: Some("plenio-api-1-x.mp3".into()), ..Song::default() };
        assert_eq!(s.plan(Mode::Auto).fields.get("source.audio"), Some(&json!("plenio-api-1-x.mp3")));
    }

    #[test]
    fn take_labels_show_the_stars() {
        assert_eq!(Take { number: 3, stars: Some(4.5), ..Take::default() }.label(), "Take 3 · 4.5 stars");
        assert_eq!(Take { number: 2, stars: Some(4.0), ..Take::default() }.label(), "Take 2 · 4 stars");
        assert_eq!(Take { number: 1, ..Take::default() }.label(), "Take 1");
    }
}
