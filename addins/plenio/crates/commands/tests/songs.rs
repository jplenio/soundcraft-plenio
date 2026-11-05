//! The song and take commands through the engine, as SoundCraft runs them: registered before the
//! registry is built (a test binary of its own), one undo step each.

use serde_json::{Value, json};
use soundcraft_engine::Engine;
use soundcraft_model::{ClipContent, TrackId};
use soundcraft_plenio_project::{Project, Role};

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
    soundcraft_plenio_commands::register();
    soundcraft_plenio_commands::set_activated(true);
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
    soundcraft_plenio_commands::register();
    soundcraft_plenio_commands::set_activated(true);
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
    soundcraft_plenio_commands::register();
    soundcraft_plenio_commands::set_activated(true);
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
