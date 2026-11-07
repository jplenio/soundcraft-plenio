//! The score on MIDI tracks: Plenio's MIDI export of a take's score laid on the song's score tracks
//! (the sung melody, the instrument line, the chords), and the way back when the owner changed notes.
//!
//! The way back keeps what Plenio needs to read the file as its own: its conductor track (the
//! score's layout - sections and bars - and the tempo) and every track the owner did not change
//! stay byte for byte as Plenio wrote them; only a changed track is written anew, under Plenio's
//! name for it, so Plenio's import gives it its role again.

use serde_json::json;
use soundcraft_engine::{Engine, EngineError, Result};
use soundcraft_midi::{Sequence, Smf, SmfTrack};
use soundcraft_model::{Clip, Session, TrackId};
use soundcraft_plenio_project::{BarMap, PlaylistRef, Role, RoleTrack, Song, Take};
use soundcraft_time::{TICKS_PER_QUARTER, TempoMap};

/// The largest MIDI file read (Plenio's own limit).
pub const MAX_MIDI_BYTES: usize = 8 * 1024 * 1024;
/// The most score tracks laid out.
const MAX_SCORE_TRACKS: usize = 8;
/// The score roles, with Plenio's track names for them.
pub const SCORE_ROLES: [(Role, &str); 3] = [(Role::Melody, "Vocal"), (Role::Accompaniment, "Instrument"), (Role::Chords, "Chords")];

fn io(why: impl Into<String>) -> EngineError {
    EngineError::Io(why.into())
}

/// The role of one of Plenio's MIDI tracks, by its name (`Vocal`, `Instrument`, `Chords`).
pub fn role_for(name: &str) -> Option<Role> {
    let n = name.trim().to_ascii_lowercase();
    match n.as_str() {
        "vocal" | "vocal melody" => Some(Role::Melody),
        "instrument" | "ins" | "ins melody" => Some(Role::Accompaniment),
        "chords" => Some(Role::Chords),
        _ => None,
    }
}

fn label(role: Role) -> &'static str {
    match role {
        Role::Melody => "Melody",
        Role::Accompaniment => "Instrument Line",
        Role::Chords => "Chords",
        _ => "Score",
    }
}

/// A digest of a sequence's notes (pitch, start, length, velocity): what tells an edit.
pub fn digest(seq: &Sequence) -> u64 {
    let mut notes: Vec<(i64, u8, i64, u8)> = seq.notes.iter().map(|n| (n.start, n.pitch, n.length, n.velocity)).collect();
    notes.sort_unstable();
    let mut h: u64 = 0xcbf2_9ce4_8422_2325;
    for (start, pitch, length, velocity) in notes {
        for b in start.to_le_bytes().into_iter().chain([pitch]).chain(length.to_le_bytes()).chain([velocity]) {
            h ^= u64::from(b);
            h = h.wrapping_mul(0x0000_0100_0000_01b3);
        }
    }
    h
}

/// The tempo a take's notes were laid out in: its own, from its bars, else the session's. Another
/// song's take may conduct the session later; the notes of this one are still read in its own bars,
/// so that a tempo it did not choose is not taken for an edit of its notes.
fn take_tempo(s: &Session, take: &Take) -> TempoMap {
    tempo_map(take).unwrap_or_else(|| s.tempo.clone())
}

/// The notes on a track's playlist of a take: its clips' sequences, laid end to end at their
/// places (in ticks of `tempo` from the take's start).
fn playlist_sequence(s: &Session, tempo: &TempoMap, r: &PlaylistRef) -> Option<Sequence> {
    let t = s.track(r.track)?;
    let pl = t.playlists.get(r.index)?;
    let mut out = Sequence::default();
    for clip in &pl.clips {
        if let soundcraft_model::ClipContent::Midi { sequence } = &clip.content {
            let offset = tempo.samples_to_ticks(clip.start, s.sample_rate);
            out.notes.extend(sequence.notes.iter().map(|n| {
                let mut n = *n;
                n.start = n.start.saturating_add(offset);
                n
            }));
        }
    }
    out.sort();
    Some(out)
}

/// The session's tempo and meters while a laid-out take plays, from the bars measured in its audio: each
/// of the session's bar lines from the score's first on lies where the audio has that measure, to the
/// sample. The bars before the score last as long as its first measure.
pub fn tempo_map(take: &Take) -> Option<TempoMap> {
    let bars = take.bars.as_ref()?;
    let first_meter = *bars.meters.first()?;
    let first = bars.tempos().next()?;
    let mut map = TempoMap::new(first, first_meter.0, first_meter.1).ok()?;
    let first_length = BarMap::quarters(first_meter) * 60.0 / first;
    let ticks_of = |meter: (u32, u32)| (BarMap::quarters(meter) * TICKS_PER_QUARTER as f64).round() as i64;
    let mut tick = (take.score_at / first_length).round() as i64 * ticks_of(first_meter);
    let mut meter = first_meter;
    for (now, tempo) in bars.meters.iter().copied().zip(bars.tempos()) {
        if now != meter {
            map.set_meter(tick, now.0, now.1).ok()?;
            meter = now;
        }
        map.set_tempo(tick, tempo).ok()?;
        tick += ticks_of(now);
    }
    Some(map)
}

/// A score tick (at [`soundcraft_midi::PPQ`], `bpm` being the score's tempo) in seconds of the score.
fn score_seconds(tick: i64, bpm: f64) -> f64 {
    tick as f64 / f64::from(soundcraft_midi::PPQ) * 60.0 / bpm
}

/// A score tick as a tick of the session's timeline: where the take plays it.
fn session_tick(s: &Session, take: &Take, bpm: f64, tick: i64) -> i64 {
    let at = take.score_to_session(score_seconds(tick, bpm));
    s.tempo.samples_to_ticks(s.sample_rate.samples(at), s.sample_rate)
}

/// A score track's notes as a clip starting at the score's first bar holds them. The score's tempo
/// and the take's warp become the session's ticks; a note on the grid of a take that keeps the score's
/// tempo stays on it.
fn laid_out(s: &Session, take: &Take, bpm: f64, seq: &Sequence) -> Sequence {
    let origin = session_tick(s, take, bpm, 0);
    let mut out = seq.clone();
    for n in &mut out.notes {
        let (start, end) = (session_tick(s, take, bpm, n.start), session_tick(s, take, bpm, n.end()));
        n.start = start.saturating_sub(origin).max(0);
        n.length = end.saturating_sub(start).max(1);
    }
    for c in &mut out.ctrls {
        c.tick = session_tick(s, take, bpm, c.tick).saturating_sub(origin).max(0);
    }
    out
}

/// Notes of the session's timeline (ticks from its start) as the score's: the way back of [`laid_out`].
fn back_to_score(s: &Session, take: &Take, seq: &Sequence) -> Sequence {
    let bpm = take.bpm.filter(|b| *b > 0.0).unwrap_or(120.0);
    let tempo = take_tempo(s, take);
    let tick = |t: i64| -> i64 {
        let seconds = s.sample_rate.seconds(tempo.tick_to_samples(t, s.sample_rate));
        (take.session_to_score(seconds) * bpm / 60.0 * f64::from(soundcraft_midi::PPQ)).round() as i64
    };
    let mut out = seq.clone();
    for n in &mut out.notes {
        let (start, end) = (tick(n.start).max(0), tick(n.end()));
        n.start = start;
        n.length = end.saturating_sub(start).max(1);
    }
    out
}

/// Lay the score's MIDI tracks on the song's score tracks (made the first time, inside the song's
/// folder and muted: the take already plays these notes), each take on a playlist of its own. Each
/// clip lasts from the score's first bar to its end, whatever its track's last note; the session's
/// tempo and the take's place ([`Take::lay_out`]) must be set before.
/// Returns the role tracks it made.
pub fn place_score(e: &mut Engine, song: &Song, bytes: &[u8], playlist: &str, take: &mut Take) -> Result<Vec<RoleTrack>> {
    if bytes.len() > MAX_MIDI_BYTES {
        return Err(io("the score's MIDI file is too large"));
    }
    let smf = soundcraft_midi::read_smf(bytes).map_err(|err| io(format!("the score's MIDI file: {err}")))?;
    let bpm = take.bpm.or_else(|| smf.tempos.first().map(|t| t.1)).filter(|b| b.is_finite() && *b > 0.0).unwrap_or(120.0);
    take.bpm = Some(bpm);
    let score_end = smf.tracks.iter().map(|t| t.sequence.end_tick()).max().unwrap_or(0).max(1);
    let folder = song.track(Role::Song);
    let mut made: Vec<RoleTrack> = Vec::new();
    let mut used: Vec<(Role, TrackId, usize)> = Vec::new();
    for (index, tr) in smf.tracks.iter().enumerate().filter(|(_, t)| !t.sequence.notes.is_empty()).take(MAX_SCORE_TRACKS) {
        let Some(role) = role_for(&tr.name) else { continue };
        let known = song.track(role).or_else(|| made.iter().find(|r| r.role == role).map(|r| r.track)).filter(|t| e.session().track(*t).is_some());
        let track = match known {
            Some(t) => t,
            None => {
                let v = crate::songs::inner(
                    e,
                    "track.new",
                    &json!({"kind": "instrument", "name": label(role), "format": "stereo", "instrument": "subtractive_synth"}),
                )?;
                let t = crate::songs::ids_of(&v).first().copied().ok_or_else(|| io("the score track was not made"))?;
                if let Some(f) = folder {
                    crate::songs::inner(e, "track.move_to_folder", &json!({"tracks": [t.0], "folder": f.0}))?;
                }
                if let Some(tr) = e.session_mut().track_mut(t) {
                    tr.mixer.mute = true;
                }
                made.push(RoleTrack { role, track: t });
                t
            }
        };
        let s = e.session_mut();
        let index_in_take = match used.iter().find(|(r, _, _)| *r == role) {
            Some((_, _, i)) => *i,
            None => {
                let Some(i) = crate::songs::take_playlist(s, track, playlist) else { continue };
                used.push((role, track, i));
                take.playlists.push(PlaylistRef { track, index: i });
                i
            }
        };
        let start = s.sample_rate.samples(take.score_at);
        let length = s.tempo.tick_to_samples(session_tick(s, take, bpm, score_end), s.sample_rate).saturating_sub(start).max(1);
        let notes = laid_out(s, take, bpm, &tr.sequence);
        let id = s.new_clip_id();
        if let Some(pl) = s.track_mut(track).and_then(|t| t.playlists.get_mut(index_in_take)) {
            pl.clips.push(Clip::midi(id, label(role), start, length, notes));
            pl.sort();
        }
        take.midi_tracks.insert(role_key(role).into(), index);
    }
    // What the tracks hold now, to tell an edit later.
    let tempo = take_tempo(e.session(), take);
    for (role, track, i) in &used {
        if let Some(seq) = playlist_sequence(e.session(), &tempo, &PlaylistRef { track: *track, index: *i }) {
            take.midi_digests.insert(role_key(*role).into(), digest(&seq));
        }
    }
    Ok(made)
}

pub fn role_key(role: Role) -> &'static str {
    match role {
        Role::Melody => "melody",
        Role::Accompaniment => "accompaniment",
        Role::Chords => "chords",
        _ => "other",
    }
}

/// The score tracks of the active take whose notes the owner changed: role key → the notes now.
pub fn changed_notes(s: &Session, song: &Song) -> Vec<(String, Sequence)> {
    let Some(take) = song.active_take() else { return Vec::new() };
    let tempo = take_tempo(s, take);
    let mut out = Vec::new();
    for (role, _) in SCORE_ROLES {
        let key = role_key(role);
        let Some(track) = song.track(role) else { continue };
        let Some(r) = take.playlists.iter().find(|p| p.track == track) else { continue };
        let Some(seq) = playlist_sequence(s, &tempo, r) else { continue };
        if take.midi_digests.get(key).is_some_and(|d| *d != digest(&seq)) {
            out.push((key.to_string(), seq));
        }
    }
    out
}

/// The chunks of a standard MIDI file: its division and its track chunks (each whole, with its
/// `MTrk` header).
fn chunks(bytes: &[u8]) -> std::result::Result<(u16, Vec<Vec<u8>>), String> {
    let u32_at = |at: usize| -> Option<usize> {
        let b: [u8; 4] = bytes.get(at..at.checked_add(4)?)?.try_into().ok()?;
        usize::try_from(u32::from_be_bytes(b)).ok()
    };
    if bytes.get(0..4) != Some(b"MThd") {
        return Err("not a MIDI file".into());
    }
    let header = u32_at(4).ok_or("short MIDI header")?;
    let division = bytes.get(12..14).and_then(|b| <[u8; 2]>::try_from(b).ok()).map(u16::from_be_bytes).ok_or("short MIDI header")?;
    let mut at = 8usize.checked_add(header).ok_or("bad MIDI header")?;
    let mut tracks = Vec::new();
    while at < bytes.len() {
        let len = u32_at(at.saturating_add(4)).ok_or("cut MIDI chunk")?;
        let end = at.checked_add(8).and_then(|a| a.checked_add(len)).ok_or("bad MIDI chunk")?;
        let chunk = bytes.get(at..end).ok_or("cut MIDI chunk")?;
        if chunk.get(0..4) == Some(b"MTrk") {
            tracks.push(chunk.to_vec());
        }
        at = end;
        if tracks.len() > 256 {
            return Err("too many MIDI tracks".into());
        }
    }
    Ok((division, tracks))
}

/// Plenio's MIDI file with some tracks' notes replaced (`index` in the file → new notes, named as
/// Plenio names that track). Everything else stays as Plenio wrote it.
pub fn splice(original: &[u8], replacements: &[(usize, String, Sequence)]) -> std::result::Result<Vec<u8>, String> {
    if original.len() > MAX_MIDI_BYTES {
        return Err("the score's MIDI file is too large".into());
    }
    let (division, mut tracks) = chunks(original)?;
    if division & 0x8000 != 0 || division == 0 {
        return Err("the score's MIDI file has no musical time base".into());
    }
    for (index, name, seq) in replacements {
        let mut scaled = seq.clone();
        let per = i64::from(division);
        for n in &mut scaled.notes {
            n.start = n.start.saturating_mul(per) / i64::from(soundcraft_midi::PPQ);
            n.length = (n.length.saturating_mul(per) / i64::from(soundcraft_midi::PPQ)).max(1);
        }
        scaled.ctrls.clear();
        let smf = Smf {
            format: 1,
            tracks: vec![SmfTrack { name: name.clone(), sequence: scaled }],
            tempos: vec![(0, 120.0)],
            meters: vec![(0, 4, 4)],
            ..Smf::default()
        };
        let written = soundcraft_midi::write_smf(&smf).map_err(|e| e.to_string())?;
        let (_, new_tracks) = chunks(&written)?;
        let chunk = new_tracks.last().cloned().ok_or("the track was not written")?;
        match tracks.get_mut(*index) {
            Some(slot) if *index > 0 => *slot = chunk,
            _ => return Err(format!("the score's MIDI file has no track {index}")),
        }
    }
    let mut out = Vec::with_capacity(original.len());
    out.extend_from_slice(b"MThd");
    out.extend_from_slice(&6u32.to_be_bytes());
    out.extend_from_slice(&1u16.to_be_bytes());
    out.extend_from_slice(&u16::try_from(tracks.len()).map_err(|_| "too many tracks")?.to_be_bytes());
    out.extend_from_slice(&division.to_be_bytes());
    for t in tracks {
        out.extend_from_slice(&t);
    }
    Ok(out)
}

/// The file to send back for the changed notes of the active take: Plenio's file of that take
/// with the changed tracks replaced. `None` when nothing changed or the take has no score file.
pub fn notes_for_plenio(s: &Session, song: &Song) -> Option<std::result::Result<Vec<u8>, String>> {
    let changed = changed_notes(s, song);
    if changed.is_empty() {
        return None;
    }
    let take = song.active_take()?;
    let path = take.files.get("midi")?;
    let original = match std::fs::metadata(path).map(|m| m.len()) {
        Ok(n) if n as usize <= MAX_MIDI_BYTES => std::fs::read(path).map_err(|e| e.to_string()),
        Ok(_) => Err("the score's MIDI file is too large".into()),
        Err(e) => Err(format!("{path}: {e}")),
    };
    let original = match original {
        Ok(o) => o,
        Err(e) => return Some(Err(e)),
    };
    let replacements: Vec<(usize, String, Sequence)> = changed
        .into_iter()
        .filter_map(|(key, seq)| {
            let index = *take.midi_tracks.get(&key)?;
            let name = SCORE_ROLES.iter().find(|(r, _)| role_key(*r) == key).map(|(_, n)| (*n).to_string())?;
            Some((index, name, back_to_score(s, take, &seq)))
        })
        .collect();
    Some(splice(&original, &replacements))
}

#[cfg(test)]
mod tests {
    use super::*;
    use soundcraft_midi::Note;

    fn note(start: i64, pitch: u8) -> Note {
        Note { pitch, velocity: 90, release_velocity: 64, channel: 0, start, length: 240 }
    }

    fn plenio_like_file() -> Vec<u8> {
        let track = |name: &str, pitch: u8| SmfTrack {
            name: name.into(),
            sequence: Sequence { notes: vec![note(0, pitch), note(480, pitch + 2)], ctrls: Vec::new() },
        };
        let smf = Smf {
            format: 1,
            tracks: vec![track("Vocal", 60), track("Instrument", 48)],
            tempos: vec![(0, 96.0)],
            meters: vec![(0, 4, 4)],
            ..Smf::default()
        };
        soundcraft_midi::write_smf(&smf).unwrap()
    }

    #[test]
    fn roles_follow_plenios_track_names() {
        assert_eq!(role_for("Vocal"), Some(Role::Melody));
        assert_eq!(role_for("Instrument"), Some(Role::Accompaniment));
        assert_eq!(role_for("chords"), Some(Role::Chords));
        assert_eq!(role_for("Guide"), None);
    }

    #[test]
    fn a_changed_track_is_replaced_and_the_rest_kept_byte_for_byte() {
        let original = plenio_like_file();
        let (_, before) = chunks(&original).unwrap();
        let edited = Sequence { notes: vec![note(0, 64), note(960, 67)], ctrls: Vec::new() };
        let out = splice(&original, &[(1, "Vocal".into(), edited)]).unwrap();
        let (_, after) = chunks(&out).unwrap();
        assert_eq!(after.len(), before.len());
        assert_eq!(after[0], before[0], "the conductor track is Plenio's");
        assert_eq!(after[2], before[2], "the unchanged track is Plenio's");
        let read = soundcraft_midi::read_smf(&out).unwrap();
        let vocal = read.tracks.iter().find(|t| t.name == "Vocal").unwrap();
        assert_eq!(vocal.sequence.notes.iter().map(|n| (n.start, n.pitch)).collect::<Vec<_>>(), vec![(0, 64), (960, 67)]);
        assert_eq!(read.tempos.first().map(|t| t.1), Some(96.0));
    }

    #[test]
    fn broken_files_are_errors() {
        assert!(splice(b"nonsense", &[]).is_err());
        let mut cut = plenio_like_file();
        cut.truncate(cut.len() - 5);
        assert!(splice(&cut, &[]).is_err());
        assert!(splice(&plenio_like_file(), &[(9, "Vocal".into(), Sequence::default())]).is_err());
        assert!(splice(&plenio_like_file(), &[(0, "Vocal".into(), Sequence::default())]).is_err(), "never the conductor track");
    }

    #[test]
    fn the_digest_tells_an_edit() {
        let a = Sequence { notes: vec![note(0, 60)], ctrls: Vec::new() };
        let mut b = a.clone();
        assert_eq!(digest(&a), digest(&b));
        b.notes[0].pitch = 61;
        assert_ne!(digest(&a), digest(&b));
    }
}
