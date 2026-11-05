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

/// A part of the song in time (seconds from the take's start).
#[derive(Debug, Clone, PartialEq, Default, Serialize, Deserialize)]
#[serde(default)]
pub struct SectionSpan {
    pub name: String,
    pub start: f64,
    pub end: f64,
}

/// A line of the lyrics as sung (seconds from the take's start).
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
}

impl Take {
    /// `Take 3 ★4.5`.
    pub fn label(&self) -> String {
        match self.stars {
            Some(s) => format!("Take {} ★{}", self.number, trim_number(f64::from(s))),
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
    }
    if song.active.is_some_and(|i| i >= song.takes.len()) {
        song.active = song.takes.len().checked_sub(1);
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

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
        assert_eq!(Take { number: 3, stars: Some(4.5), ..Take::default() }.label(), "Take 3 ★4.5");
        assert_eq!(Take { number: 2, stars: Some(4.0), ..Take::default() }.label(), "Take 2 ★4");
        assert_eq!(Take { number: 1, ..Take::default() }.label(), "Take 1");
    }
}
