//! The song and take commands: a song's tracks, its working copy, and its takes on the tracks.
//!
//! Each command is one undo step. Tracks are made and moved with SoundCraft's own commands (run
//! inside this one, so no step of their own); playlists and clips are set on the document directly.

use crate::when_activated;
use serde_json::{Value, json};
use soundcraft_engine::cmd::{CommandSpec, always};
use soundcraft_engine::{Engine, EngineError, Result, find_command};
use soundcraft_model::{Clip, Playlist, Session, TrackId, TrackKind};
use soundcraft_plenio_project::{Doc, DocState, PlaylistRef, Project, Role, RoleTrack, Song, SongKind, Take};

/// The most lyric clips one take puts on the lyrics track.
const MAX_LYRIC_CLIPS: usize = 2000;
/// The most characters of a lyric clip's name.
const MAX_CLIP_NAME: usize = 120;

pub fn specs() -> Vec<CommandSpec> {
    vec![
        soundcraft_engine::cmd!(
            "plenio.song.new",
            "New Plenio Song",
            [],
            None,
            "{kind?: song|cover, title?, template?: yue2-song|yue2-cover, fields?: {name: value}, source_track?: id (a cover's recording)}",
            when_activated,
            song_new
        ),
        soundcraft_engine::cmd!(
            "plenio.song.set",
            "Change Plenio Song",
            [],
            None,
            "{song, title?, fields?: {name: value | null}, documents?: {title|style|lyrics|score|artwork_prompt: text | null}, seeds?: {name: n | null}, unmastered?: bool, source?: uploaded name}",
            always,
            song_set
        ),
        soundcraft_engine::cmd!(
            "plenio.take.add",
            "Add Plenio Take",
            [],
            None,
            "{song, audio: path of the take's audio, midi?: path of the score as Plenio's MIDI file, meter?: [n, d], take: {job, title, seeds, fields, documents, stars, seconds, files, sections, lines, bpm, key}}",
            always,
            take_add
        ),
        soundcraft_engine::cmd!("plenio.take.select", "Select Plenio Take", [], None, "{song, take: number}", always, take_select),
        soundcraft_engine::cmd!(
            "plenio.stems.add",
            "Add Plenio Stems",
            [],
            None,
            "{song, take: number, stems: [[name (vocals|drums|bass|other|rest), path], ...]}",
            always,
            stems_add
        ),
        soundcraft_engine::cmd!(
            "plenio.song.forget",
            "Forget Plenio Song",
            [],
            None,
            "{song}: its tracks stay, as ordinary tracks",
            always,
            song_forget
        ),
    ]
}

fn bad(id: &str, why: impl Into<String>) -> EngineError {
    EngineError::BadParams(id.into(), why.into())
}

/// Run one of SoundCraft's commands inside this one: no undo step of its own.
pub(crate) fn inner(e: &mut Engine, id: &str, p: &Value) -> Result<Value> {
    let spec = find_command(id).ok_or_else(|| EngineError::UnknownCommand(id.into()))?;
    (spec.run)(e, p)
}

fn load(e: &Engine) -> Result<Project> {
    Project::load(e.session()).map_err(|err| EngineError::Unsupported(err.to_string()))
}

fn store(e: &mut Engine, project: &Project) -> Result<()> {
    project.store(e.session_mut()).map_err(|err| EngineError::Unsupported(err.to_string()))
}

fn song_param(id: &str, p: &Value) -> Result<u64> {
    p.get("song").and_then(Value::as_u64).ok_or_else(|| bad(id, "`song` (its id) required"))
}

pub(crate) fn ids_of(v: &Value) -> Vec<TrackId> {
    v.get("tracks").and_then(Value::as_array).map(|a| a.iter().filter_map(Value::as_u64).map(TrackId).collect()).unwrap_or_default()
}

fn song_new(e: &mut Engine, p: &Value) -> Result<Value> {
    const ID: &str = "plenio.song.new";
    let kind = match p.get("kind").and_then(Value::as_str).unwrap_or("song") {
        "song" => SongKind::Song,
        "cover" => SongKind::Cover,
        other => return Err(bad(ID, format!("unknown kind `{other}` (song or cover)"))),
    };
    let template = p.get("template").and_then(Value::as_str).unwrap_or(if kind == SongKind::Cover { "yue2-cover" } else { "yue2-song" });
    if !matches!(template, "yue2-song" | "yue2-cover") {
        return Err(bad(ID, format!("unknown template `{template}`")));
    }
    let title: String = p
        .get("title")
        .and_then(Value::as_str)
        .map(str::trim)
        .filter(|t| !t.is_empty())
        .unwrap_or(if kind == SongKind::Cover { "New Cover" } else { "New Song" })
        .chars()
        .take(soundcraft_plenio_project::MAX_TITLE_CHARS)
        .collect();
    let source = match p.get("source_track") {
        Some(v) => {
            let t = TrackId(v.as_u64().ok_or_else(|| bad(ID, "`source_track` must be a track id"))?);
            if e.session().track(t).is_none_or(|tr| tr.kind != TrackKind::Audio) {
                return Err(bad(ID, "`source_track` must be an audio track"));
            }
            Some(t)
        }
        None => None,
    };
    let fields: std::collections::BTreeMap<String, Value> = match p.get("fields") {
        Some(Value::Object(m)) => m.iter().take(soundcraft_plenio_project::MAX_FIELDS).map(|(k, v)| (k.clone(), v.clone())).collect(),
        Some(_) => return Err(bad(ID, "`fields` must be an object")),
        None => Default::default(),
    };
    let made = inner(
        e,
        "track.new",
        &json!({"rows": [
            {"kind": "folder", "name": title, "format": "stereo"},
            {"kind": "midi", "name": "Lyrics"},
            {"kind": "audio", "format": "stereo", "name": "Song"},
        ]}),
    )?;
    let [folder, lyrics, mix] = ids_of(&made)[..] else { return Err(bad(ID, "the tracks were not made")) };
    let mut members = vec![lyrics.0, mix.0];
    if let Some(s) = source {
        members.insert(0, s.0);
    }
    inner(e, "track.move_to_folder", &json!({"tracks": members, "folder": folder.0}))?;
    let mut project = load(e)?;
    let id = project.next_song_id();
    let mut tracks = vec![
        RoleTrack { role: Role::Song, track: folder },
        RoleTrack { role: Role::Lyrics, track: lyrics },
        RoleTrack { role: Role::Mix, track: mix },
    ];
    if let Some(s) = source {
        tracks.push(RoleTrack { role: Role::Source, track: s });
    }
    project.songs.push(Song { id, kind, title: title.clone(), tracks, template: template.into(), fields, ..Song::default() });
    store(e, &project)?;
    Ok(json!({"song": id, "title": title, "tracks": {"song": folder.0, "lyrics": lyrics.0, "mix": mix.0, "source": source.map(|s| s.0)}}))
}

fn song_set(e: &mut Engine, p: &Value) -> Result<Value> {
    const ID: &str = "plenio.song.set";
    let id = song_param(ID, p)?;
    let mut project = load(e)?;
    let song = project.song_mut(id).ok_or_else(|| bad(ID, format!("no Plenio song {id}")))?;
    if let Some(t) = p.get("title").and_then(Value::as_str) {
        song.title = t.chars().take(soundcraft_plenio_project::MAX_TITLE_CHARS).collect();
    }
    if let Some(fields) = p.get("fields").and_then(Value::as_object) {
        for (k, v) in fields.iter().take(soundcraft_plenio_project::MAX_FIELDS) {
            if v.is_null() {
                song.fields.remove(k);
            } else if song.fields.len() < soundcraft_plenio_project::MAX_FIELDS || song.fields.contains_key(k) {
                song.fields.insert(k.clone(), v.clone());
            }
        }
    }
    if let Some(docs) = p.get("documents").and_then(Value::as_object) {
        for (k, v) in docs {
            if !soundcraft_plenio_project::DOCUMENTS.contains(&k.as_str()) {
                return Err(bad(ID, format!("unknown document `{k}`")));
            }
            match v.as_str() {
                Some(text) => {
                    let text: String = text.chars().take(soundcraft_plenio_project::MAX_DOCUMENT_CHARS).collect();
                    song.documents.insert(k.clone(), Doc { text, state: DocState::Manual });
                }
                None => {
                    // Back to the active take's text.
                    match song.active_take().and_then(|t| t.documents.get(k)).cloned() {
                        Some(text) => {
                            song.documents.insert(k.clone(), Doc { text, state: DocState::Auto });
                        }
                        None => {
                            song.documents.remove(k);
                        }
                    }
                }
            }
        }
    }
    if let Some(seeds) = p.get("seeds").and_then(Value::as_object) {
        for (k, v) in seeds.iter().take(16) {
            match v.as_u64() {
                Some(n) if n <= u64::from(u32::MAX) => {
                    song.seeds.insert(k.clone(), n);
                }
                _ => {
                    song.seeds.remove(k);
                }
            }
        }
    }
    if let Some(u) = p.get("unmastered").and_then(Value::as_bool) {
        song.unmastered = u;
    }
    if let Some(s) = p.get("source").and_then(Value::as_str) {
        song.source = Some(s.chars().take(512).collect());
    }
    let changes = song.changes();
    store(e, &project)?;
    Ok(json!({"song": id, "changes": changes}))
}

/// Give a track a playlist for a new take: its active one when that is still empty, else a new one.
/// Returns the playlist's index.
pub(crate) fn take_playlist(s: &mut Session, track: TrackId, name: &str) -> Option<usize> {
    let t = s.track_mut(track)?;
    let empty = t.playlists.get(t.active_playlist).is_some_and(|pl| pl.clips.is_empty());
    if empty {
        if let Some(pl) = t.playlists.get_mut(t.active_playlist) {
            pl.name = name.to_string();
        }
    } else {
        t.playlists.push(Playlist::new(name));
        t.active_playlist = t.playlists.len() - 1;
    }
    Some(t.active_playlist)
}

/// `F#m` → `F# minor`, `Eb` → `Eb major` (as Event › Add Key Change takes it).
pub fn key_name(abc: &str) -> Option<String> {
    let k = abc.trim();
    let mut chars = k.chars();
    let letter = chars.next().filter(|c| ('A'..='G').contains(&c.to_ascii_uppercase()))?.to_ascii_uppercase();
    let rest: String = chars.collect();
    let (accidental, mode) = match rest.chars().next() {
        Some(c @ ('#' | 'b')) => (c.to_string(), rest.get(1..).unwrap_or_default().to_string()),
        _ => (String::new(), rest),
    };
    let minor = matches!(mode.to_ascii_lowercase().as_str(), "m" | "min" | "minor");
    Some(format!("{letter}{accidental} {}", if minor { "minor" } else { "major" }))
}

/// Whether anything but Plenio's own tracks has clips (then the session's tempo is the owner's).
fn others_have_clips(s: &Session, project: &Project) -> bool {
    s.tracks.iter().filter(|t| project.role_of(t.id).is_none()).any(|t| t.playlists.iter().any(|pl| !pl.clips.is_empty()))
}

/// Lyric clips for a take: one per line as sung when the take has timed lines, else one per block
/// of the lyrics, laid on the score's section of the same name, in order.
fn lyric_clips(take: &Take) -> Vec<(String, f64, f64)> {
    if !take.lines.is_empty() {
        return take.lines.iter().take(MAX_LYRIC_CLIPS).map(|l| (l.text.replace('\n', " / "), l.start, l.end)).collect();
    }
    let lyrics = take.documents.get("lyrics").map(String::as_str).unwrap_or_default();
    let mut blocks: Vec<(String, Vec<&str>)> = Vec::new();
    for line in lyrics.lines() {
        let line = line.trim();
        if let Some(tag) = line.strip_prefix('[').and_then(|l| l.split_once(']')).map(|(t, _)| t.trim().to_ascii_lowercase()) {
            blocks.push((tag, Vec::new()));
        } else if !line.is_empty()
            && let Some(b) = blocks.last_mut()
        {
            b.1.push(line);
        }
    }
    let mut out = Vec::new();
    let mut next_section = 0usize;
    for (tag, lines) in blocks.into_iter().filter(|(_, l)| !l.is_empty()) {
        let found = take.sections.iter().enumerate().skip(next_section).find(|(_, s)| {
            let name = s.name.to_ascii_lowercase();
            name.contains(&tag) || tag.contains(&name)
        });
        if let Some((i, s)) = found {
            next_section = i + 1;
            out.push((format!("[{tag}] {}", lines.join(" / ")), s.start, s.end));
        }
    }
    out
}

fn take_add(e: &mut Engine, p: &Value) -> Result<Value> {
    const ID: &str = "plenio.take.add";
    let id = song_param(ID, p)?;
    let audio =
        p.get("audio").and_then(Value::as_str).filter(|a| !a.is_empty()).ok_or_else(|| bad(ID, "`audio` (the take's file) required"))?.to_string();
    let mut take: Take = serde_json::from_value(p.get("take").cloned().unwrap_or(Value::Null)).map_err(|err| bad(ID, format!("`take`: {err}")))?;
    let mut project = load(e)?;
    let song = project.song(id).ok_or_else(|| bad(ID, format!("no Plenio song {id}")))?.clone();
    let mix = song.track(Role::Mix).ok_or_else(|| bad(ID, "the song has no audio track any more"))?;
    take.number = song.takes.iter().map(|t| t.number).max().unwrap_or(0).saturating_add(1);
    take.playlists.clear();
    let label = take.label();
    let first_of_session = project.songs.iter().all(|s| s.takes.is_empty()) && !others_have_clips(e.session(), &project);
    // The first take of a session that holds nothing else sets its tempo, meter and key: before
    // anything is laid out, for the bars and the notes are measured with them. The tempo is the one
    // the take really plays, so that the session's bars stay on its audio.
    if first_of_session && let Some(bpm) = take.bpm {
        let meter = p
            .get("meter")
            .and_then(Value::as_array)
            .and_then(|m| Some((u32::try_from(m.first()?.as_u64()?).ok()?, u32::try_from(m.get(1)?.as_u64()?).ok()?)));
        let (n, d) = meter.unwrap_or((4, 4));
        let scale = take.warp.filter(|w| soundcraft_plenio_project::warp_ok(*w)).map_or(1.0, |w| w.0);
        let played = if (scale - 1.0).abs() > 0.0005 { bpm / scale } else { bpm };
        if let Ok(map) = soundcraft_time::TempoMap::new(played, n, d) {
            e.session_mut().tempo = map;
        }
        if let Some(key) = key_name(&take.key) {
            e.session_mut().key_signatures = vec![(0, key)];
        }
    }
    let (rate, bar) = {
        let s = e.session();
        (s.sample_rate, s.sample_rate.seconds(s.tempo.tick_to_samples(s.tempo.bar_start_tick(2), s.sample_rate)))
    };
    take.lay_out(bar);
    // The take's audio on a playlist of its own.
    let index = take_playlist(e.session_mut(), mix, &label).ok_or_else(|| bad(ID, "the song's audio track is gone"))?;
    inner(e, "file.import_audio", &json!({"path": audio, "track": mix.0, "at": rate.samples(take.audio_at)}))?;
    // A cover's first take: the original is muted, so the two do not play at once (unmute it for A/B).
    if song.takes.is_empty()
        && let Some(source) = song.track(Role::Source).and_then(|t| e.session_mut().track_mut(t))
    {
        source.mixer.mute = true;
    }
    take.playlists.push(PlaylistRef { track: mix, index });
    // Its lyrics on the lyrics track.
    if let Some(lyrics) = song.track(Role::Lyrics) {
        let clips = lyric_clips(&take);
        let s = e.session_mut();
        let rate = s.sample_rate;
        if let Some(index) = take_playlist(s, lyrics, &label) {
            let made: Vec<Clip> = clips
                .into_iter()
                .filter_map(|(name, start, end)| {
                    let (a, b) = (rate.samples(start.max(0.0)), rate.samples(end.max(start)));
                    (b > a).then(|| Clip::midi(s.new_clip_id(), name.chars().take(MAX_CLIP_NAME).collect::<String>(), a, b - a, Default::default()))
                })
                .collect();
            if let Some(pl) = s.track_mut(lyrics).and_then(|t| t.playlists.get_mut(index)) {
                pl.clips.extend(made);
                pl.sort();
            }
            take.playlists.push(PlaylistRef { track: lyrics, index });
        }
    }
    // The score's notes on the score tracks.
    let mut made = Vec::new();
    if let Some(midi) = p.get("midi").and_then(Value::as_str).filter(|m| !m.is_empty()) {
        let size = std::fs::metadata(midi).map(|m| m.len()).map_err(|err| bad(ID, format!("`midi`: {err}")))?;
        if size > crate::score::MAX_MIDI_BYTES as u64 {
            return Err(bad(ID, "`midi`: the file is too large"));
        }
        let bytes = std::fs::read(midi).map_err(|err| bad(ID, format!("`midi`: {err}")))?;
        made = crate::score::place_score(e, &song, &bytes, &label, &mut take)?;
        take.files.insert("midi".into(), midi.to_string());
    }
    let number = take.number;
    // The song's folder takes the song's title from its first take (it was named before there was one).
    if let Some(folder) = song.track(Role::Song)
        && song.takes.is_empty()
        && !take.title.trim().is_empty()
        && let Some(t) = e.session_mut().track_mut(folder)
        && t.name == song.title
    {
        t.name = take.title.chars().take(soundcraft_model::MAX_NAME_CHARS).collect();
    }
    let song = project.song_mut(id).ok_or_else(|| bad(ID, format!("no Plenio song {id}")))?;
    song.tracks.extend(made);
    song.takes.push(take);
    song.adopt(song.takes.len() - 1);
    store(e, &project)?;
    Ok(json!({"song": id, "take": number}))
}

fn take_select(e: &mut Engine, p: &Value) -> Result<Value> {
    const ID: &str = "plenio.take.select";
    let id = song_param(ID, p)?;
    let number = p.get("take").and_then(Value::as_u64).ok_or_else(|| bad(ID, "`take` (its number) required"))?;
    let mut project = load(e)?;
    let song = project.song_mut(id).ok_or_else(|| bad(ID, format!("no Plenio song {id}")))?;
    let index = song.takes.iter().position(|t| u64::from(t.number) == number).ok_or_else(|| bad(ID, format!("the song has no take {number}")))?;
    let refs = song.takes.get(index).map(|t| t.playlists.clone()).unwrap_or_default();
    song.adopt(index);
    let song = song.clone();
    let s = e.session_mut();
    for r in &refs {
        if let Some(t) = s.track_mut(r.track)
            && r.index < t.playlists.len()
        {
            t.active_playlist = r.index;
        }
    }
    show_stems(s, &song, &refs);
    store(e, &project)?;
    Ok(json!({"song": id, "take": number}))
}

/// The stem roles, with the track names they get.
pub const STEMS: [(Role, &str, &str); 5] = [
    (Role::Vocals, "vocals", "Vocals"),
    (Role::Drums, "drums", "Drums"),
    (Role::Bass, "bass", "Bass"),
    (Role::Other, "other", "Other"),
    (Role::Rest, "rest", "Rest"),
];

/// After a take was chosen: a take with stems plays them (the mix track is muted), a take without
/// them plays the mix (the stem tracks show an empty playlist, so nothing plays twice).
fn show_stems(s: &mut Session, song: &Song, refs: &[PlaylistRef]) {
    let stem_tracks: Vec<TrackId> = STEMS.iter().filter_map(|(role, _, _)| song.track(*role)).collect();
    let has_stems = refs.iter().any(|r| stem_tracks.contains(&r.track));
    if let Some(mix) = song.track(Role::Mix).and_then(|m| s.track_mut(m)) {
        mix.mixer.mute = has_stems;
    }
    for t in stem_tracks.iter().filter(|t| !refs.iter().any(|r| r.track == **t)) {
        if let Some(track) = s.track_mut(*t) {
            let empty = track.playlists.iter().position(|p| p.clips.is_empty() && p.name == NO_STEMS);
            let i = match empty {
                Some(i) => i,
                None => {
                    track.playlists.push(Playlist::new(NO_STEMS));
                    track.playlists.len() - 1
                }
            };
            track.active_playlist = i;
        }
    }
}

/// The playlist a stem track shows for a take without stems.
const NO_STEMS: &str = "(no stems for this take)";

fn stems_add(e: &mut Engine, p: &Value) -> Result<Value> {
    const ID: &str = "plenio.stems.add";
    let id = song_param(ID, p)?;
    let number = p.get("take").and_then(Value::as_u64).ok_or_else(|| bad(ID, "`take` (its number) required"))?;
    let stems: Vec<(String, String)> = p
        .get("stems")
        .and_then(Value::as_array)
        .map(|a| a.iter().filter_map(|s| Some((s.get(0)?.as_str()?.to_string(), s.get(1)?.as_str()?.to_string()))).collect())
        .unwrap_or_default();
    if stems.is_empty() || stems.len() > STEMS.len() {
        return Err(bad(ID, "`stems` must name 1 to 5 stems"));
    }
    let mut project = load(e)?;
    let song = project.song(id).ok_or_else(|| bad(ID, format!("no Plenio song {id}")))?.clone();
    let index = song.takes.iter().position(|t| u64::from(t.number) == number).ok_or_else(|| bad(ID, format!("the song has no take {number}")))?;
    let label = song.takes.get(index).map(Take::label).unwrap_or_default();
    // The stems are the take's audio taken apart: they lie where it lies.
    let at = e.session().sample_rate.samples(song.takes.get(index).map_or(0.0, |t| t.audio_at));
    let folder = song.track(Role::Song);
    let mut made = Vec::new();
    let mut refs = Vec::new();
    for (name, path) in &stems {
        let Some((role, _, track_name)) = STEMS.iter().find(|(_, key, _)| key == name) else {
            return Err(bad(ID, format!("unknown stem `{name}`")));
        };
        let track = match song.track(*role).filter(|t| e.session().track(*t).is_some()) {
            Some(t) => t,
            None => {
                let v = inner(e, "track.new", &json!({"kind": "audio", "format": "stereo", "name": track_name}))?;
                let t = ids_of(&v).first().copied().ok_or_else(|| bad(ID, "the stem track was not made"))?;
                if let Some(f) = folder {
                    inner(e, "track.move_to_folder", &json!({"tracks": [t.0], "folder": f.0}))?;
                }
                made.push(RoleTrack { role: *role, track: t });
                t
            }
        };
        // A take split again replaces its stems on the playlist it has.
        let existing = song.takes.get(index).and_then(|t| t.playlists.iter().find(|r| r.track == track)).map(|r| r.index);
        let s = e.session_mut();
        let playlist = match existing.filter(|i| s.track(track).is_some_and(|t| *i < t.playlists.len())) {
            Some(i) => {
                if let Some(t) = s.track_mut(track) {
                    t.active_playlist = i;
                    if let Some(pl) = t.playlists.get_mut(i) {
                        pl.clips.clear();
                    }
                }
                i
            }
            None => take_playlist(s, track, &label).ok_or_else(|| bad(ID, "the stem track is gone"))?,
        };
        inner(e, "file.import_audio", &json!({"path": path, "track": track.0, "at": at}))?;
        refs.push(PlaylistRef { track, index: playlist });
    }
    let song_mut = project.song_mut(id).ok_or_else(|| bad(ID, format!("no Plenio song {id}")))?;
    song_mut.tracks.extend(made);
    if let Some(take) = song_mut.takes.get_mut(index) {
        for r in &refs {
            if !take.playlists.contains(r) {
                take.playlists.push(*r);
            }
        }
    }
    let shown = song_mut.clone();
    let all = shown.takes.get(index).map(|t| t.playlists.clone()).unwrap_or_default();
    if shown.active == Some(index) {
        show_stems(e.session_mut(), &shown, &all);
    }
    store(e, &project)?;
    Ok(json!({"song": id, "take": number, "stems": stems.len()}))
}

fn song_forget(e: &mut Engine, p: &Value) -> Result<Value> {
    const ID: &str = "plenio.song.forget";
    let id = song_param(ID, p)?;
    let mut project = load(e)?;
    let before = project.songs.len();
    project.songs.retain(|s| s.id != id);
    if project.songs.len() == before {
        return Err(bad(ID, format!("no Plenio song {id}")));
    }
    store(e, &project)?;
    Ok(json!({"song": id}))
}

#[cfg(test)]
mod tests {
    use super::*;
    use soundcraft_plenio_project::{LineSpan, SectionSpan};

    #[test]
    fn keys_are_named_as_soundcraft_takes_them() {
        assert_eq!(key_name("F#m").as_deref(), Some("F# minor"));
        assert_eq!(key_name("Eb").as_deref(), Some("Eb major"));
        assert_eq!(key_name("c").as_deref(), Some("C major"));
        assert_eq!(key_name("Amin").as_deref(), Some("A minor"));
        assert_eq!(key_name("H"), None);
        assert_eq!(key_name(""), None);
    }

    #[test]
    fn lyrics_lie_on_their_lines_or_their_sections() {
        let mut take = Take { lines: vec![LineSpan { start: 1.0, end: 3.0, text: "Rain\non the road".into() }], ..Take::default() };
        assert_eq!(lyric_clips(&take), vec![("Rain / on the road".to_string(), 1.0, 3.0)]);
        take.lines.clear();
        take.documents.insert("lyrics".into(), "[verse]\nRain on the road\nLights\n\n[chorus]\nWe drive\n[bridge]\nnowhere".into());
        take.sections = vec![
            SectionSpan { name: "intro".into(), start: 0.0, end: 5.0 },
            SectionSpan { name: "verse".into(), start: 5.0, end: 20.0 },
            SectionSpan { name: "chorus".into(), start: 20.0, end: 30.0 },
        ];
        assert_eq!(
            lyric_clips(&take),
            vec![("[verse] Rain on the road / Lights".to_string(), 5.0, 20.0), ("[chorus] We drive".to_string(), 20.0, 30.0)]
        );
    }
}
