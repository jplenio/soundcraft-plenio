//! The song and take commands through the engine, as SoundCraft runs them: registered before the
//! registry is built (a test binary of its own), one undo step each.

use serde_json::{Value, json};
use soundcraft_engine::Engine;
use soundcraft_model::{ClipContent, TrackId};
use soundcraft_plenio_project::{Project, Role};

/// The add-in's activation is one switch for the process, and one test turns it off: the tests take
/// turns. Each starts with the commands registered and the add-in activated.
fn turn() -> std::sync::MutexGuard<'static, ()> {
    static ACTIVATION: std::sync::Mutex<()> = std::sync::Mutex::new(());
    let guard = ACTIVATION.lock().unwrap_or_else(std::sync::PoisonError::into_inner);
    soundcraft_plenio_commands::register();
    soundcraft_plenio_commands::set_activated(true);
    guard
}

/// A second of stereo 16-bit silence at 48 kHz.
fn wav(path: &std::path::Path) {
    let frames: u32 = 48_000;
    let data = frames * 4;
    let mut b = Vec::new();
    b.extend_from_slice(b"RIFF");
    b.extend_from_slice(&(36 + data).to_le_bytes());
    b.extend_from_slice(b"WAVEfmt ");
    b.extend_from_slice(&16u32.to_le_bytes());
    b.extend_from_slice(&1u16.to_le_bytes());
    b.extend_from_slice(&2u16.to_le_bytes());
    b.extend_from_slice(&48_000u32.to_le_bytes());
    b.extend_from_slice(&(48_000u32 * 4).to_le_bytes());
    b.extend_from_slice(&4u16.to_le_bytes());
    b.extend_from_slice(&16u16.to_le_bytes());
    b.extend_from_slice(b"data");
    b.extend_from_slice(&data.to_le_bytes());
    b.resize(b.len() + data as usize, 0);
    std::fs::write(path, b).unwrap();
}

fn take(job: &str, lines: Value) -> Value {
    json!({
        "job": job, "title": "Night Drive", "seeds": {"take": 14}, "fields": {"genre": "synthwave"},
        "documents": {"title": "Night Drive", "lyrics": "[verse]\nRain on the road", "score": "X:1"},
        "stars": 4.5, "seconds": 1.0, "bpm": 96.0, "key": "F#m",
        "sections": [{"name": "verse", "start": 0.0, "end": 1.0}], "lines": lines
    })
}

#[test]
fn a_song_gets_its_tracks_and_every_take_its_playlists() {
    let _turn = turn();
    let dir = std::env::temp_dir().join(format!("scp-songs-{}", std::process::id()));
    std::fs::create_dir_all(&dir).unwrap();
    let audio = dir.join("take.wav");
    wav(&audio);

    let mut e = Engine::default();
    let made = e.execute("plenio.song.new", &json!({"title": "Night Drive", "fields": {"genre": "synthwave"}})).unwrap();
    let song = made["song"].as_u64().unwrap();
    let (folder, lyrics, mix) = (
        TrackId(made["tracks"]["song"].as_u64().unwrap()),
        TrackId(made["tracks"]["lyrics"].as_u64().unwrap()),
        TrackId(made["tracks"]["mix"].as_u64().unwrap()),
    );
    let s = e.session();
    assert_eq!(s.track(folder).map(|t| t.name.as_str()), Some("Night Drive"));
    assert_eq!(s.track(lyrics).and_then(|t| t.folder), Some(folder));
    assert_eq!(s.track(mix).and_then(|t| t.folder), Some(folder));

    // The first take: on the tracks' first playlists, with the tempo and key of its score.
    e.execute("plenio.take.add", &json!({"song": song, "audio": audio.to_string_lossy(), "take": take("job-1", json!([])), "meter": [3, 4]}))
        .unwrap();
    let s = e.session();
    let mix_track = s.track(mix).unwrap();
    assert_eq!(mix_track.playlists.len(), 1);
    assert_eq!(mix_track.playlists[0].name, "Take 1 · 4.5 stars");
    assert_eq!(mix_track.playlists[0].clips.len(), 1);
    let lyric = &s.track(lyrics).unwrap().playlists[0].clips;
    assert_eq!(lyric.len(), 1);
    assert_eq!(lyric[0].name, "[verse] Rain on the road");
    assert!(matches!(lyric[0].content, ClipContent::Midi { .. }));
    assert_eq!(s.tempo.tempos()[0].bpm, 96.0);
    assert_eq!(s.tempo.meters()[0].numerator, 3);
    assert_eq!(s.key_signatures, vec![(0, "F# minor".to_string())]);

    // An edit to the lyrics makes the song stale; the second take lands on new playlists.
    let changed = e.execute("plenio.song.set", &json!({"song": song, "documents": {"lyrics": "[verse]\nSnow on the road"}})).unwrap();
    assert_eq!(changed["changes"], json!(["lyrics"]));
    let lines = json!([{"start": 0.2, "end": 0.8, "text": "Snow on the road"}]);
    e.execute("plenio.take.add", &json!({"song": song, "audio": audio.to_string_lossy(), "take": take("job-2", lines)})).unwrap();
    let s = e.session();
    assert_eq!(s.track(mix).unwrap().playlists.len(), 2);
    assert_eq!(s.track(mix).unwrap().active_playlist, 1);
    assert_eq!(s.track(lyrics).unwrap().playlists[1].clips[0].name, "Snow on the road");
    let p = Project::load(s).unwrap();
    let song_data = p.song(song).unwrap();
    assert_eq!((song_data.takes.len(), song_data.active), (2, Some(1)));
    assert!(song_data.changes().is_empty(), "the edit is in the new take");
    assert_eq!(p.role_of(lyrics).map(|(_, r)| r), Some(Role::Lyrics));

    // Back to take 1: every track of the song shows it.
    e.execute("plenio.take.select", &json!({"song": song, "take": 1})).unwrap();
    assert_eq!(e.session().track(mix).unwrap().active_playlist, 0);
    assert_eq!(e.session().track(lyrics).unwrap().active_playlist, 0);
    // One undo step per command.
    assert!(e.undo());
    assert_eq!(e.session().track(mix).unwrap().active_playlist, 1);
    assert!(e.undo());
    assert_eq!(e.session().track(mix).unwrap().playlists.len(), 1);

    status_and_bad_parameters(&mut e, song);
    let _ = std::fs::remove_dir_all(&dir);
}

/// Status lists the song; bad parameters are errors, not panics; without activation no new songs.
fn status_and_bad_parameters(e: &mut Engine, song: u64) {
    let status = e.execute("plenio.status", &json!({})).unwrap();
    assert_eq!(status["songs"][0]["title"], "Night Drive");
    for (cmd, params) in [
        ("plenio.take.add", json!({"song": song})),
        ("plenio.take.add", json!({"song": 999, "audio": "x"})),
        ("plenio.take.select", json!({"song": song, "take": 77})),
        ("plenio.song.set", json!({"song": song, "documents": {"poem": "x"}})),
        ("plenio.song.new", json!({"kind": "remix"})),
        ("plenio.song.new", json!({"source_track": 123456})),
    ] {
        assert!(e.execute(cmd, &params).is_err(), "{cmd} {params}");
    }
    soundcraft_plenio_commands::set_activated(false);
    assert!(e.execute("plenio.song.new", &json!({})).is_err());
}

#[test]
fn stems_play_instead_of_the_mix_and_only_for_their_take() {
    let _turn = turn();
    let dir = std::env::temp_dir().join(format!("scp-stems-{}", std::process::id()));
    std::fs::create_dir_all(&dir).unwrap();
    let audio = dir.join("take.wav");
    wav(&audio);
    let path = audio.to_string_lossy().to_string();
    let mut e = Engine::default();
    let made = e.execute("plenio.song.new", &json!({"title": "Stems"})).unwrap();
    let song = made["song"].as_u64().unwrap();
    let mix = TrackId(made["tracks"]["mix"].as_u64().unwrap());
    for job in ["a", "b"] {
        e.execute("plenio.take.add", &json!({"song": song, "audio": path, "take": take(job, json!([]))})).unwrap();
    }
    e.execute("plenio.stems.add", &json!({"song": song, "take": 2, "stems": [["vocals", path], ["rest", path]]})).unwrap();
    let p = Project::load(e.session()).unwrap();
    let data = p.song(song).unwrap();
    let vocals = data.track(Role::Vocals).unwrap();
    assert!(data.track(Role::Rest).is_some());
    assert!(e.session().track(mix).unwrap().mixer.mute, "the stems play, not the mix");
    assert_eq!(e.session().track(vocals).unwrap().clips().len(), 1);
    // Take 1 has no stems: the mix plays, the stem tracks are silent.
    e.execute("plenio.take.select", &json!({"song": song, "take": 1})).unwrap();
    assert!(!e.session().track(mix).unwrap().mixer.mute);
    assert!(e.session().track(vocals).unwrap().clips().is_empty());
    e.execute("plenio.take.select", &json!({"song": song, "take": 2})).unwrap();
    assert!(e.session().track(mix).unwrap().mixer.mute);
    assert_eq!(e.session().track(vocals).unwrap().clips().len(), 1);
    // The folder took the song's title from its first take.
    let folder = data.track(Role::Song).unwrap();
    assert_eq!(e.session().track(folder).unwrap().name, "Night Drive");
    assert!(e.execute("plenio.stems.add", &json!({"song": song, "take": 2, "stems": [["kazoo", path]]})).is_err());
    let _ = std::fs::remove_dir_all(&dir);
}

#[test]
fn a_covers_first_take_mutes_the_original() {
    let _turn = turn();
    let dir = std::env::temp_dir().join(format!("scp-cover-{}", std::process::id()));
    std::fs::create_dir_all(&dir).unwrap();
    let audio = dir.join("take.wav");
    wav(&audio);
    let mut e = Engine::default();
    let imported = e.execute("file.import_audio", &json!({"path": audio.to_string_lossy()})).unwrap();
    let source = TrackId(imported["imported"][0]["track"].as_u64().unwrap());
    let made = e.execute("plenio.song.new", &json!({"kind": "cover", "source_track": source.0})).unwrap();
    let song = made["song"].as_u64().unwrap();
    let folder = TrackId(made["tracks"]["song"].as_u64().unwrap());
    assert_eq!(e.session().track(source).unwrap().folder, Some(folder), "the recording moves into the cover's folder");
    assert!(!e.session().track(source).unwrap().mixer.mute);
    e.execute("plenio.take.add", &json!({"song": song, "audio": audio.to_string_lossy(), "take": take("c", json!([]))})).unwrap();
    assert!(e.session().track(source).unwrap().mixer.mute);
    let p = Project::load(e.session()).unwrap();
    assert_eq!(p.song(song).unwrap().track(Role::Source), Some(source));
    let _ = std::fs::remove_dir_all(&dir);
}

/// Plenio's MIDI file of a score at 84 BPM, 4/4: thirty-two bars (91.43 s). The melody has one note in
/// bar 3 and stops long before the end, as a song's words do; the chords last to the score's end.
fn score_file(path: &std::path::Path) {
    use soundcraft_midi::{Note, Sequence, Smf, SmfTrack};
    const BAR: i64 = 960 * 4;
    let note = |start: i64, pitch: u8, length: i64| Note { pitch, velocity: 90, release_velocity: 64, channel: 0, start, length };
    let track = |name: &str, notes: Vec<Note>| SmfTrack { name: name.into(), sequence: Sequence { notes, ctrls: Vec::new() } };
    let smf = Smf {
        format: 1,
        tracks: vec![
            track("Vocal", vec![note(2 * BAR, 60, 960)]),
            track("Instrument", vec![note(0, 48, 960), note(30 * BAR, 50, 960)]),
            track("Chords", vec![note(0, 60, 32 * BAR)]),
        ],
        tempos: vec![(0, 84.0)],
        meters: vec![(0, 4, 4)],
        ..Smf::default()
    };
    std::fs::write(path, soundcraft_midi::write_smf(&smf).unwrap()).unwrap();
}

fn scored_take(job: &str, warp: Value) -> Value {
    json!({
        "job": job, "title": "Winter", "documents": {"title": "Winter", "score": "X:1"}, "seconds": 91.0, "bpm": 84.0, "key": "Eb",
        "sections": [{"name": "intro", "start": 0.0, "end": 5.714}, {"name": "verse", "start": 5.714, "end": 91.43}],
        "lines": [{"start": 4.434, "end": 7.0, "text": "He watches"}], "warp": warp
    })
}

struct Scored {
    _turn: std::sync::MutexGuard<'static, ()>,
    e: Engine,
    song: u64,
    mix: TrackId,
    lyrics: TrackId,
    audio: String,
    midi: String,
    dir: std::path::PathBuf,
}

fn scored_song(name: &str) -> Scored {
    let turn = turn();
    let dir = std::env::temp_dir().join(format!("scp-sync-{name}-{}", std::process::id()));
    std::fs::create_dir_all(&dir).unwrap();
    let (audio, midi) = (dir.join("take.wav"), dir.join("score.mid"));
    wav(&audio);
    score_file(&midi);
    let mut e = Engine::default();
    assert_ne!(e.session().tempo.tempos()[0].bpm, 84.0, "the session starts at another tempo than the score");
    let made = e.execute("plenio.song.new", &json!({"title": "Winter"})).unwrap();
    Scored {
        _turn: turn,
        song: made["song"].as_u64().unwrap(),
        mix: TrackId(made["tracks"]["mix"].as_u64().unwrap()),
        lyrics: TrackId(made["tracks"]["lyrics"].as_u64().unwrap()),
        e,
        audio: audio.to_string_lossy().into_owned(),
        midi: midi.to_string_lossy().into_owned(),
        dir,
    }
}

impl Scored {
    fn add(&mut self, job: &str, warp: Value) {
        let params = json!({"song": self.song, "audio": self.audio, "midi": self.midi, "take": scored_take(job, warp), "meter": [4, 4]});
        self.e.execute("plenio.take.add", &params).unwrap();
    }
    fn role(&self, role: Role) -> TrackId {
        Project::load(self.e.session()).unwrap().song(self.song).unwrap().track(role).unwrap()
    }
    fn samples(&self, seconds: f64) -> i64 {
        self.e.session().sample_rate.samples(seconds)
    }
    fn near(&self, got: i64, seconds: f64, what: &str) {
        let want = self.samples(seconds);
        assert!((got - want).abs() <= 2, "{what}: at {got} samples, wanted {want} ({seconds} s)");
    }
    /// The notes of a score track as seconds on the session's timeline (start, end).
    fn note_times(&self, role: Role) -> Vec<(f64, f64)> {
        let s = self.e.session();
        let clip = s.track(self.role(role)).unwrap().clips()[0].clone();
        let ClipContent::Midi { sequence } = &clip.content else { panic!("not a MIDI clip") };
        let origin = s.tempo.samples_to_ticks(clip.start, s.sample_rate);
        let at = |tick: i64| s.sample_rate.seconds(s.tempo.tick_to_samples(origin + tick, s.sample_rate));
        sequence.notes.iter().map(|n| (at(n.start), at(n.end()))).collect()
    }
}

impl Drop for Scored {
    fn drop(&mut self) {
        let _ = std::fs::remove_dir_all(&self.dir);
    }
}

/// The owner's report of 2026-11-06: at the end of the first take the MIDI tracks stopped too early,
/// because their clips were measured at the session's tempo from before the take set it.
#[test]
fn the_score_tracks_of_a_first_take_last_to_the_end_of_the_score() {
    let mut t = scored_song("end");
    t.add("first", json!([1.0, -1.28]));
    let s = t.e.session();
    assert_eq!(s.tempo.tempos()[0].bpm, 84.0);
    let whole_score = 32.0 * 4.0 * 60.0 / 84.0;
    for role in [Role::Melody, Role::Accompaniment, Role::Chords] {
        let clip = &s.track(t.role(role)).unwrap().clips()[0];
        t.near(clip.start + clip.length, whole_score, &format!("the end of the {role:?} clip"));
    }
    let chords = t.note_times(Role::Chords);
    assert!((chords[0].1 - whole_score).abs() < 0.001, "no note is cut: {chords:?}");
}

/// The owner's report of 2026-11-06: song and lyrics lay about half a bar from the notes. A YuE2 render
/// is shifted against its score, and Plenio measures by how much.
#[test]
fn a_take_that_starts_before_its_score_is_laid_so_that_they_meet() {
    let mut t = scored_song("early");
    t.add("first", json!([1.0, -1.28]));
    let s = t.e.session();
    // The score's bars are the session's bars; the audio moves, by what Plenio measured.
    t.near(s.track(t.role(Role::Accompaniment)).unwrap().clips()[0].start, 0.0, "the score");
    t.near(s.track(t.mix).unwrap().clips()[0].start, 1.28, "the audio");
    // The sung line and its note meet: the line was measured in the audio at 4.434 s, its note is in bar 3.
    let line = s.track(t.lyrics).unwrap().clips()[0].start;
    t.near(line, 4.434 + 1.28, "the line");
    let note = t.note_times(Role::Melody)[0].0;
    t.near(s.sample_rate.samples(note), 2.0 * 4.0 * 60.0 / 84.0, "the note");
    assert!((s.sample_rate.seconds(line) - note).abs() < 0.001, "line and note start together");
    // A note stays where the score has it: on the grid, untouched.
    let clip = &s.track(t.role(Role::Melody)).unwrap().clips()[0];
    let ClipContent::Midi { sequence } = &clip.content else { panic!("not a MIDI clip") };
    assert_eq!(sequence.notes[0].start, 2 * 960 * 4);
    // The sections lie on the score's bars, and end with the score or the audio, whichever ends first.
    let p = Project::load(s).unwrap();
    let take = p.song(t.song).unwrap().active_take().unwrap().clone();
    assert!((take.sections[1].start - 5.714).abs() < 0.001);
    assert!((take.sections[1].end - 91.43).abs() < 0.01, "{:?}", take.sections[1]);
    assert!((take.lines[0].start - (4.434 + 1.28)).abs() < 0.001);
}

#[test]
fn a_take_that_starts_after_its_score_moves_the_score_to_a_bar_line() {
    let mut t = scored_song("late");
    t.add("first", json!([1.0, 0.5]));
    let s = t.e.session();
    let bar = 4.0 * 60.0 / 84.0;
    let score = s.track(t.role(Role::Accompaniment)).unwrap().clips()[0].start;
    t.near(score, bar, "the score, on bar 2");
    t.near(s.track(t.mix).unwrap().clips()[0].start, bar - 0.5, "the audio");
    let ticks = s.tempo.samples_to_ticks(score, s.sample_rate);
    assert_eq!(ticks, s.tempo.bar_start_tick(2));
    let note = t.note_times(Role::Melody)[0].0;
    t.near(s.sample_rate.samples(note), bar + 2.0 * bar, "the note");
}

#[test]
fn a_take_that_runs_faster_keeps_its_notes_on_its_audio_and_gives_them_back_as_written() {
    let mut t = scored_song("faster");
    t.add("first", json!([1.0, -1.28]));
    t.add("second", json!([0.998, -1.3]));
    let s = t.e.session();
    assert_eq!(s.tempo.tempos()[0].bpm, 84.0, "the session keeps the first take's tempo");
    t.near(s.track(t.mix).unwrap().clips()[0].start, 1.3, "the audio of take 2");
    // A note thirty bars into the score sits where take 2 plays it, not where the grid has it.
    let bar = 4.0 * 60.0 / 84.0;
    let notes = t.note_times(Role::Accompaniment);
    assert!((notes[1].0 - 0.998 * 30.0 * bar).abs() < 0.001, "{notes:?}");
    // Take 1 is as it was.
    t.e.execute("plenio.take.select", &json!({"song": t.song, "take": 1})).unwrap();
    assert!((t.note_times(Role::Accompaniment)[1].0 - 30.0 * bar).abs() < 0.001);
    t.e.execute("plenio.take.select", &json!({"song": t.song, "take": 2})).unwrap();

    // An edit of take 2 goes back to Plenio in the score's own time: the other notes as written.
    let track = t.role(Role::Accompaniment);
    let session = t.e.session_mut();
    let tr = session.track_mut(track).unwrap();
    let active = tr.active_playlist;
    let ClipContent::Midi { sequence } = &mut tr.playlists[active].clips[0].content else { panic!("not a MIDI clip") };
    sequence.notes[0].pitch = 55;
    let p = Project::load(t.e.session()).unwrap();
    let file = soundcraft_plenio_commands::notes_for_plenio(t.e.session(), p.song(t.song).unwrap()).unwrap().unwrap();
    let read = soundcraft_midi::read_smf(&file).unwrap();
    let back = &read.tracks.iter().find(|x| x.name == "Instrument").unwrap().sequence.notes;
    assert_eq!(back.iter().map(|n| (n.start, n.pitch, n.length)).collect::<Vec<_>>(), vec![(0, 55, 960), (30 * 960 * 4, 50, 960)]);
}

/// What the audio of a take has: 32 measures of 4/4 from `first`, wandering around the score's tempo.
fn wandering_bars(first: f64, depth: f64) -> Value {
    let bar = 4.0 * 60.0 / 84.0;
    let score: Vec<f64> = (0..=32).map(|k| f64::from(k) * bar).collect();
    let audio: Vec<f64> = score.iter().map(|t| first + t + depth * (t / (32.0 * bar) * std::f64::consts::TAU).sin()).collect();
    json!({"score": score, "audio": audio, "meters": vec![[4, 4]; 32]})
}

impl Scored {
    fn add_measured(&mut self, job: &str, bars: Value) {
        let mut take = scored_take(job, json!([1.0, 0.0]));
        take["bars"] = bars;
        let params = json!({"song": self.song, "audio": self.audio, "midi": self.midi, "take": take, "meter": [4, 4]});
        self.e.execute("plenio.take.add", &params).unwrap();
    }
    /// Every measure of the bars against the session: its bar line, at the sample where the audio has it.
    fn assert_bars_on_audio(&self, bars: &Value, first_bar: i64) {
        let s = self.e.session();
        let audio_start = s.track(self.mix).unwrap().clips()[0].start;
        for (k, at) in bars["audio"].as_array().unwrap().iter().enumerate() {
            let tick = s.tempo.bar_start_tick(first_bar + k as i64);
            let want = audio_start + self.samples(at.as_f64().unwrap());
            let got = s.tempo.tick_to_samples(tick, s.sample_rate);
            assert!((got - want).abs() <= 1, "bar {} at {got} samples, the audio has it at {want}", first_bar + k as i64);
        }
    }
}

#[test]
fn the_sessions_bars_are_the_bars_of_a_take_whose_tempo_wanders() {
    let mut t = scored_song("bars");
    let bars = wandering_bars(-1.28, 0.25);
    t.add_measured("first", bars.clone());
    let s = t.e.session();
    // The audio starts 1.28 s after the score's first bar, which lies at the session's start.
    t.near(s.track(t.mix).unwrap().clips()[0].start, 1.28, "the audio");
    t.assert_bars_on_audio(&bars, 1);
    // A tempo for every measure, and none of them is the score's.
    assert_eq!(s.tempo.tempos().len(), 32);
    assert!(s.tempo.tempos().iter().all(|e| (e.bpm - 84.0).abs() > 0.01 && (e.bpm - 84.0).abs() < 4.0), "{:?}", s.tempo.tempos());
    // The audio stays as it is; the notes stay on the grid, tick by tick, as written.
    let track = t.role(Role::Accompaniment);
    let clip = &s.track(track).unwrap().clips()[0];
    assert_eq!(clip.start, 0);
    let ClipContent::Midi { sequence } = &clip.content else { panic!("not a MIDI clip") };
    assert_eq!(sequence.notes.iter().map(|n| (n.start, n.length)).collect::<Vec<_>>(), [(0, 960), (30 * 3840, 960)]);
    // The clip lasts to the score's end, which is a bar line.
    assert_eq!(clip.length, s.tempo.tick_to_samples(32 * 3840, s.sample_rate));
    // Words stay on the audio, sections on the bars.
    let p = Project::load(s).unwrap();
    let take = p.song(t.song).unwrap().active_take().unwrap();
    assert!((take.lines[0].start - (4.434 + 1.28)).abs() < 1e-9);
    assert!((take.score_to_session(2.0 * 4.0 * 60.0 / 84.0) - (bars["audio"][2].as_f64().unwrap() + 1.28)).abs() < 1e-9);
    // One undo takes it all back.
    let tempo = s.tempo.clone();
    assert!(t.e.undo());
    assert_ne!(t.e.session().tempo, tempo);
    assert_eq!(t.e.session().tempo.tempos().len(), 1);
}

#[test]
fn a_take_that_starts_before_its_score_gets_a_bar_of_its_tempo_before_it() {
    let mut t = scored_song("bars-lead");
    let bars = wandering_bars(0.5, 0.1);
    t.add_measured("first", bars.clone());
    // The first measure lasts 2.86 s or so, so the score starts on bar 2 and the audio a bit before it.
    t.assert_bars_on_audio(&bars, 2);
    let s = t.e.session();
    let audio = s.sample_rate.seconds(s.track(t.mix).unwrap().clips()[0].start);
    assert!(audio > 2.0 && audio < 3.0, "{audio}");
    assert_eq!(s.track(t.role(Role::Accompaniment)).unwrap().clips()[0].start, s.tempo.tick_to_samples(3840, s.sample_rate));
    assert_eq!(s.tempo.tempo_at_tick(0), s.tempo.tempo_at_tick(3840));
}

#[test]
fn a_meter_change_in_the_score_is_a_meter_change_in_the_session() {
    let mut t = scored_song("bars-meters");
    // 3 measures of 4/4, one of 2/4, then 4/4 again.
    let meters: Vec<[u32; 2]> = (0..30).map(|k| if k == 3 { [2, 4] } else { [4, 4] }).collect();
    let quarter = 60.0 / 84.0;
    let mut score = vec![0.0];
    for m in &meters {
        score.push(score.last().unwrap() + f64::from(m[0]) * quarter);
    }
    let audio: Vec<f64> = score.iter().map(|t| t * 1.01 - 0.75).collect();
    let bars = json!({"score": score, "audio": audio, "meters": meters});
    t.add_measured("first", bars.clone());
    t.assert_bars_on_audio(&bars, 1);
    let s = t.e.session();
    let changes: Vec<(i64, u32)> = s.tempo.meters().iter().map(|m| (m.tick, m.numerator)).collect();
    assert_eq!(changes, [(0, 4), (3 * 3840, 2), (3 * 3840 + 1920, 4)]);
}

#[test]
fn another_take_brings_its_own_bars_and_the_owners_midi_keeps_its_place_in_them() {
    let mut t = scored_song("bars-takes");
    let (one, two) = (wandering_bars(-1.28, 0.25), wandering_bars(-0.5, -0.3));
    t.add_measured("first", one.clone());
    // The owner's own MIDI, on bar 9, and audio at a time of its own.
    let made = t.e.execute("track.new", &json!({"kind": "midi", "name": "Mine"})).unwrap();
    let mine = TrackId(made["tracks"][0]["id"].as_u64().or(made["ids"][0].as_u64()).or(made["tracks"][0].as_u64()).unwrap());
    let bar_9 = t.e.session().tempo.bar_start_tick(9);
    let session = t.e.session_mut();
    let rate = session.sample_rate;
    let start = session.tempo.tick_to_samples(bar_9, rate);
    let end = session.tempo.tick_to_samples(bar_9 + 3840, rate);
    let id = session.new_clip_id();
    let note = soundcraft_midi::Note { pitch: 64, velocity: 90, release_velocity: 64, channel: 0, start: 960, length: 480 };
    let notes = soundcraft_midi::Sequence { notes: vec![note], ctrls: Vec::new() };
    let tr = session.track_mut(mine).unwrap();
    let pl = tr.active_playlist;
    tr.playlists[pl].clips.push(soundcraft_model::Clip::midi(id, "Mine", start, end - start, notes));
    let where_mine = |e: &Engine| {
        let s = e.session();
        let clip = &s.track(mine).unwrap().clips()[0];
        (s.tempo.samples_to_ticks(clip.start, s.sample_rate), s.tempo.samples_to_ticks(clip.start + clip.length, s.sample_rate), clip.start)
    };
    assert_eq!(where_mine(&t.e), (bar_9, bar_9 + 3840, start));

    t.add_measured("second", two.clone());
    t.assert_bars_on_audio(&two, 1);
    let (from, to, moved) = where_mine(&t.e);
    assert_eq!((from, to), (bar_9, bar_9 + 3840), "the clip stays on bar 9");
    assert_ne!(moved, start, "whose time moved with the take's bars");
    let ClipContent::Midi { sequence } = &t.e.session().track(mine).unwrap().clips()[0].content else { panic!("not a MIDI clip") };
    assert_eq!(sequence.notes[0].start, 960, "and its notes in it");

    // Back and forth: each take brings its bars back, to the sample.
    t.e.execute("plenio.take.select", &json!({"song": t.song, "take": 1})).unwrap();
    t.assert_bars_on_audio(&one, 1);
    assert_eq!(where_mine(&t.e), (bar_9, bar_9 + 3840, start));
    t.e.execute("plenio.take.select", &json!({"song": t.song, "take": 2})).unwrap();
    t.assert_bars_on_audio(&two, 1);
}

#[test]
fn notes_of_a_measured_take_go_back_as_written() {
    let mut t = scored_song("bars-back");
    t.add_measured("first", wandering_bars(-1.28, 0.25));
    let track = t.role(Role::Accompaniment);
    let session = t.e.session_mut();
    let tr = session.track_mut(track).unwrap();
    let active = tr.active_playlist;
    let ClipContent::Midi { sequence } = &mut tr.playlists[active].clips[0].content else { panic!("not a MIDI clip") };
    sequence.notes[0].pitch = 55;
    let p = Project::load(t.e.session()).unwrap();
    let file = soundcraft_plenio_commands::notes_for_plenio(t.e.session(), p.song(t.song).unwrap()).unwrap().unwrap();
    let read = soundcraft_midi::read_smf(&file).unwrap();
    let back = &read.tracks.iter().find(|x| x.name == "Instrument").unwrap().sequence.notes;
    assert_eq!(back.iter().map(|n| (n.start, n.pitch, n.length)).collect::<Vec<_>>(), vec![(0, 55, 960), (30 * 960 * 4, 50, 960)]);
}

#[test]
fn bars_that_cannot_be_true_leave_the_take_on_its_warp() {
    let mut t = scored_song("bars-bad");
    let mut bars = wandering_bars(-1.28, 0.25);
    bars["audio"][5] = bars["audio"][4].clone();
    let mut take = scored_take("first", json!([1.0, -1.28]));
    take["bars"] = bars;
    t.e.execute("plenio.take.add", &json!({"song": t.song, "audio": t.audio, "midi": t.midi, "take": take, "meter": [4, 4]})).unwrap();
    let s = t.e.session();
    assert_eq!(s.tempo.tempos().len(), 1);
    assert_eq!(s.tempo.tempos()[0].bpm, 84.0);
    t.near(s.track(t.mix).unwrap().clips()[0].start, 1.28, "the audio");
}

#[test]
fn stems_lie_where_the_audio_of_their_take_lies() {
    let mut t = scored_song("stems");
    t.add("first", json!([1.0, -1.28]));
    let audio = t.audio.clone();
    t.e.execute("plenio.stems.add", &json!({"song": t.song, "take": 1, "stems": [["vocals", audio]]})).unwrap();
    let vocals = t.role(Role::Vocals);
    t.near(t.e.session().track(vocals).unwrap().clips()[0].start, 1.28, "the stem");
}

#[test]
fn without_a_usable_measurement_everything_starts_at_the_start() {
    for warp in [Value::Null, json!([0.0, -1.0]), json!([1.0, 1e300]), json!([9.0, 0.0])] {
        let mut t = scored_song("none");
        t.add("first", warp.clone());
        let s = t.e.session();
        t.near(s.track(t.mix).unwrap().clips()[0].start, 0.0, "the audio");
        let clip = &s.track(t.role(Role::Chords)).unwrap().clips()[0];
        t.near(clip.start, 0.0, "the score");
        t.near(clip.start + clip.length, 32.0 * 4.0 * 60.0 / 84.0, "the end of the score");
    }
}
