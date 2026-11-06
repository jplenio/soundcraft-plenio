//! The Plenio add-in's document data: the songs a session holds, and which of the session's
//! tracks play which part of each song. It lives in the session as JSON, in
//! `Session::extensions["plenio"]`, so it is saved, undone, autosaved and bundled with the rest of
//! the document.
//!
//! Every track a song uses is an ordinary SoundCraft track; this data only names their roles. A
//! session opened without the add-in keeps all its audio and MIDI, and a role whose track is gone
//! is simply dropped.
#![deny(clippy::unwrap_used, clippy::expect_used, clippy::panic, clippy::unimplemented, clippy::todo, clippy::unreachable)]

mod generation;

pub use generation::{DOCUMENTS, Doc, DocState, LineSpan, Mode, Plan, PlaylistRef, SectionSpan, Take, What, warp_ok};

use serde::{Deserialize, Serialize};
use serde_json::Value;
use soundcraft_model::{Session, TrackId, truncate_chars};
use std::collections::BTreeMap;

/// The key of the add-in's entry in `Session::extensions`.
pub const KEY: &str = "plenio";
/// The version of the data this build writes; newer data is refused rather than misread.
pub const VERSION: u32 = 1;
/// The most songs a session keeps.
pub const MAX_SONGS: usize = 256;
/// The most role tracks one song keeps.
pub const MAX_ROLE_TRACKS: usize = 64;
/// The most characters of a song title.
pub const MAX_TITLE_CHARS: usize = 256;
/// The most fields one song keeps.
pub const MAX_FIELDS: usize = 128;
/// The most characters of one document (the Song API's limit).
pub const MAX_DOCUMENT_CHARS: usize = 200_000;
/// The most takes one song keeps.
pub const MAX_TAKES: usize = 512;

#[derive(Debug, thiserror::Error)]
pub enum ProjectError {
    #[error("the Plenio data in this session is not readable: {0}")]
    Format(String),
    #[error("the Plenio data in this session was written by a newer add-in (version {0})")]
    Version(u32),
    #[error("{0}")]
    Session(String),
}

/// What a song is made from.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum SongKind {
    /// A new song from a brief (YuE2 · Song).
    #[default]
    Song,
    /// A new version of a recording (YuE2 · Cover).
    Cover,
}

/// The part a track plays in a song.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Role {
    /// The song's routing folder: its form lane and its controls.
    Song,
    /// The lyrics, one clip per section.
    Lyrics,
    /// The sung melody of the score, as MIDI.
    Melody,
    /// The chords of the score, as MIDI.
    Chords,
    /// The instrument line under the singing, as MIDI.
    Accompaniment,
    /// The rendered take, as one audio track.
    Mix,
    Vocals,
    Drums,
    Bass,
    Other,
    /// What the stems leave out, so that the stems sum to the take.
    Rest,
    /// A cover's original recording.
    Source,
}

/// A track and its role.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub struct RoleTrack {
    pub role: Role,
    pub track: TrackId,
}

/// One Plenio song in the session.
#[derive(Debug, Clone, PartialEq, Default, Serialize, Deserialize)]
#[serde(default)]
pub struct Song {
    /// Unique within the session's Plenio data.
    pub id: u64,
    pub kind: SongKind,
    pub title: String,
    pub tracks: Vec<RoleTrack>,
    /// The Song API template: `yue2-song` or `yue2-cover`.
    pub template: String,
    /// The brief's and the other nodes' fields, named as the Song API names them (`genre`,
    /// `vocals`, `finish.cover_art` …). A field left out keeps the template's value.
    pub fields: BTreeMap<String, Value>,
    /// The working documents (`title`, `style`, `lyrics`, `score`, `artwork_prompt`): what the next
    /// take is made from.
    pub documents: BTreeMap<String, Doc>,
    /// Seeds kept for the next take (locked); every other seed is drawn anew.
    pub seeds: BTreeMap<String, u64>,
    pub takes: Vec<Take>,
    /// The take the song's tracks show (an index into `takes`).
    pub active: Option<usize>,
    /// Put the unmastered take on the tracks instead of the released (mastered) one.
    pub unmastered: bool,
    /// A cover's recording as uploaded to the studio (the field `source.audio`).
    pub source: Option<String>,
}

impl Song {
    /// The track that plays `role`, if any.
    pub fn track(&self, role: Role) -> Option<TrackId> {
        self.tracks.iter().find(|t| t.role == role).map(|t| t.track)
    }

    /// The take the tracks show.
    pub fn active_take(&self) -> Option<&Take> {
        self.active.and_then(|i| self.takes.get(i))
    }
}

impl Project {
    pub fn song(&self, id: u64) -> Option<&Song> {
        self.songs.iter().find(|s| s.id == id)
    }
    pub fn song_mut(&mut self, id: u64) -> Option<&mut Song> {
        self.songs.iter_mut().find(|s| s.id == id)
    }
}

/// The add-in's data in one session.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct Project {
    pub version: u32,
    pub songs: Vec<Song>,
}

impl Default for Project {
    fn default() -> Self {
        Project { version: VERSION, songs: Vec::new() }
    }
}

impl Project {
    /// The session's Plenio data: empty when it has none. Read as untrusted, since it comes from
    /// a file: bounded, and roles whose track is not in the session are dropped.
    pub fn load(session: &Session) -> Result<Project, ProjectError> {
        let Some(text) = session.extension(KEY) else { return Ok(Project::default()) };
        let mut project: Project = serde_json::from_str(text).map_err(|e| ProjectError::Format(e.to_string()))?;
        if project.version > VERSION {
            return Err(ProjectError::Version(project.version));
        }
        project.version = VERSION;
        project.sanitize(session);
        Ok(project)
    }

    /// Write this data into the session; an empty project removes the entry.
    pub fn store(&self, session: &mut Session) -> Result<(), ProjectError> {
        if self.songs.is_empty() {
            return session.set_extension(KEY, "").map_err(|e| ProjectError::Session(e.to_string()));
        }
        let text = serde_json::to_string(self).map_err(|e| ProjectError::Format(e.to_string()))?;
        session.set_extension(KEY, text).map_err(|e| ProjectError::Session(e.to_string()))
    }

    /// The song a track belongs to, and the track's role in it.
    pub fn role_of(&self, track: TrackId) -> Option<(&Song, Role)> {
        self.songs.iter().find_map(|s| s.tracks.iter().find(|t| t.track == track).map(|t| (s, t.role)))
    }

    /// A song id not used yet.
    pub fn next_song_id(&self) -> u64 {
        self.songs.iter().map(|s| s.id).max().map_or(1, |m| m.saturating_add(1))
    }

    /// Keep what a session can hold: at most [`MAX_SONGS`] songs with distinct ids, at most
    /// [`MAX_ROLE_TRACKS`] roles each, every role on a track of the session, and no track in two
    /// roles or two songs.
    fn sanitize(&mut self, session: &Session) {
        self.songs.truncate(MAX_SONGS);
        let mut ids = std::collections::HashSet::new();
        self.songs.retain(|s| ids.insert(s.id));
        let mut used = std::collections::HashSet::new();
        for song in &mut self.songs {
            truncate_chars(&mut song.title, MAX_TITLE_CHARS);
            song.tracks.truncate(MAX_ROLE_TRACKS);
            song.tracks.retain(|t| session.track(t.track).is_some() && used.insert(t.track));
            generation::sanitize(song, session);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use soundcraft_model::{ChannelFormat, TrackKind};

    fn session_with_tracks(n: usize) -> (Session, Vec<TrackId>) {
        let mut s = Session::default();
        let ids = (0..n).map(|_| s.add_track(TrackKind::Audio, ChannelFormat::Stereo, None)).collect();
        (s, ids)
    }

    #[test]
    fn a_session_without_plenio_data_has_an_empty_project() {
        let s = Session::default();
        assert_eq!(Project::load(&s).unwrap(), Project::default());
    }

    #[test]
    fn a_project_round_trips_through_the_session_file() {
        let (mut s, t) = session_with_tracks(3);
        let mut p = Project::default();
        p.songs.push(Song {
            id: p.next_song_id(),
            kind: SongKind::Cover,
            title: "Night Drive".into(),
            tracks: vec![
                RoleTrack { role: Role::Song, track: t[0] },
                RoleTrack { role: Role::Lyrics, track: t[1] },
                RoleTrack { role: Role::Source, track: t[2] },
            ],
            ..Song::default()
        });
        p.store(&mut s).unwrap();
        let back = Session::from_json(&s.to_json().unwrap()).unwrap();
        let loaded = Project::load(&back).unwrap();
        assert_eq!(loaded, p);
        assert_eq!(loaded.role_of(t[1]).map(|(song, role)| (song.id, role)), Some((1, Role::Lyrics)));
        assert_eq!(loaded.songs[0].track(Role::Source), Some(t[2]));
        // An empty project leaves nothing in the session.
        Project::default().store(&mut s).unwrap();
        assert_eq!(s.extension(KEY), None);
    }

    #[test]
    fn hostile_data_is_bounded_and_dangling_roles_are_dropped() {
        let (mut s, t) = session_with_tracks(2);
        let gone = TrackId(9_999);
        let song = |id: u64| {
            serde_json::json!({"id": id, "title": "x".repeat(10_000), "tracks": [
                {"role": "lyrics", "track": t[0].0}, {"role": "melody", "track": gone.0}, {"role": "mix", "track": t[0].0}
            ]})
        };
        let songs: Vec<_> = (0..MAX_SONGS as u64 + 10).map(song).chain([song(0)]).collect();
        s.set_extension(KEY, serde_json::json!({"version": 1, "songs": songs}).to_string()).unwrap();
        let p = Project::load(&s).unwrap();
        assert_eq!(p.songs.len(), MAX_SONGS);
        assert!(p.songs.iter().all(|s| s.title.chars().count() == MAX_TITLE_CHARS));
        // The missing track and the second use of t[0] are gone; only the first song keeps t[0].
        assert_eq!(p.songs[0].tracks, vec![RoleTrack { role: Role::Lyrics, track: t[0] }]);
        assert!(p.songs[1..].iter().all(|s| s.tracks.is_empty()));
    }

    #[test]
    fn newer_or_broken_data_is_refused_not_misread() {
        let mut s = Session::default();
        s.set_extension(KEY, r#"{"version": 2, "songs": []}"#).unwrap();
        assert!(matches!(Project::load(&s), Err(ProjectError::Version(2))));
        s.set_extension(KEY, "not json").unwrap();
        assert!(matches!(Project::load(&s), Err(ProjectError::Format(_))));
        s.set_extension(KEY, r#"{"songs": [{"kind": "remix"}]}"#).unwrap();
        assert!(matches!(Project::load(&s), Err(ProjectError::Format(_))));
    }
}
