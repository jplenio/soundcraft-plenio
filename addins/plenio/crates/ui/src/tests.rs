//! The add-in's UI without a studio: settings, a take arriving, and every window drawn.

use super::*;
use serde_json::json;
use soundcraft_plenio_backend::song::{Document, Job, JobStatus, Record};
use soundcraft_plenio_project::Role;
use soundcraft_ui_egui::Services;

/// The add-in's activation is one switch for the process: the tests that use it take turns.
static ACTIVATION: std::sync::Mutex<()> = std::sync::Mutex::new(());

fn turn() -> std::sync::MutexGuard<'static, ()> {
    ACTIVATION.lock().unwrap_or_else(std::sync::PoisonError::into_inner)
}

/// Commands first: the registry of this test binary is built on its first read.
fn app() -> SoundApp {
    register_commands();
    soundcraft_plenio_commands::set_activated(true);
    SoundApp::new(soundcraft_engine::Engine::default(), None, Services::default())
}

fn quiet_ui() -> PlenioUi {
    let mut ui = PlenioUi::new(None);
    ui.auto_start = false;
    ui
}

fn temp(name: &str) -> PathBuf {
    let dir = std::env::temp_dir().join(format!("scp-ui-{name}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dir);
    std::fs::create_dir_all(&dir).unwrap();
    dir
}

/// Half a second of stereo 16-bit silence at 48 kHz.
fn wav(path: &std::path::Path) {
    let frames: u32 = 24_000;
    let data = frames * 4;
    let mut b = Vec::new();
    for part in [&b"RIFF"[..], &(36 + data).to_le_bytes(), b"WAVEfmt ", &16u32.to_le_bytes(), &1u16.to_le_bytes(), &2u16.to_le_bytes()] {
        b.extend_from_slice(part);
    }
    for part in
        [&48_000u32.to_le_bytes()[..], &(48_000u32 * 4).to_le_bytes(), &4u16.to_le_bytes(), &16u16.to_le_bytes(), b"data", &data.to_le_bytes()]
    {
        b.extend_from_slice(part);
    }
    b.resize(b.len() + data as usize, 0);
    std::fs::write(path, b).unwrap();
}

fn frames(app: &mut SoundApp, n: usize) {
    let ctx = egui::Context::default();
    let rect = egui::Rect::from_min_size(egui::Pos2::ZERO, egui::vec2(1400.0, 900.0));
    for _ in 0..n {
        let mut out = ctx.run_ui(egui::RawInput { screen_rect: Some(rect), ..Default::default() }, |ui| {
            app.logic(ui.ctx());
            app.ui(ui);
        });
        out.textures_delta.clear();
    }
}

#[test]
fn activation_is_kept_in_the_settings_folder() {
    let _turn = turn();
    let dir = temp("activation");
    let mut app = app();
    let mut ui = PlenioUi::new(Some(dir.clone()));
    ui.auto_start = false;
    assert!(!ui.settings.activated);
    ui.settings.licences_accepted = true;
    ui.set_activated(&mut app, true);
    let saved = Settings::load(&dir).unwrap();
    assert!(saved.activated && saved.licences_accepted);
    let mut again = PlenioUi::new(Some(dir.clone()));
    again.auto_start = false;
    assert!(again.settings.activated);
    again.set_activated(&mut app, false);
    assert!(!Settings::load(&dir).unwrap().activated);
    let _ = std::fs::remove_dir_all(&dir);
}

#[test]
fn a_delivered_take_lands_on_the_songs_tracks() {
    let _turn = turn();
    let dir = temp("deliver");
    let audio = dir.join("take.flac.wav");
    wav(&audio);
    // The add-in reads its activation from its settings: made first, the app activates it.
    let mut ui = quiet_ui();
    let mut app = app();
    let made = app.run("plenio.song.new", json!({"title": "Garden", "fields": {"vocals": "sung"}})).unwrap();
    let song = made["song"].as_u64().unwrap();
    let score = "X:1\nM:2/4\nL:1/16\nQ:1/4=120\nV: Vocal clef=treble\nK:Am\n% verse\nV: Vocal\nz8|z8|\n% chorus\nV: Vocal\nz8|z8|\n";
    let documents = [("title", "Garden"), ("lyrics", "[verse]\nMorning light\n[chorus]\nWe sing"), ("score", score)]
        .into_iter()
        .map(|(k, v)| (k.to_string(), Document { text: v.into(), state: "auto".into() }))
        .collect();
    let record = Record { title: "Garden".into(), documents, seconds: 0.5, sample_rate: 48_000, stars: Some(4.0), warp: None };
    let job = Job {
        id: "job-1".into(),
        status: JobStatus::Succeeded,
        queue_position: None,
        stage: String::new(),
        progress: None,
        seeds: [("take".to_string(), 7u64)].into_iter().collect(),
        title: "Garden".into(),
        seconds: 0.5,
        folder: String::new(),
        files: Vec::new(),
        error: String::new(),
        warnings: Vec::new(),
    };
    ui.jobs.insert(9, Pending { song, what: What::NewSong, fields: BTreeMap::new(), job: None });
    let delivery =
        soundcraft_plenio_backend::Delivery { job, song: Some(audio), original: None, record: Some(record), record_file: None, lines: Vec::new() };
    ui.deliver(&mut app, 9, delivery);
    assert!(ui.jobs.is_empty());
    let s = app.engine.session();
    let project = Project::load(s).unwrap();
    let data = project.song(song).unwrap();
    let take = data.active_take().unwrap();
    assert_eq!((take.number, take.stars, take.bpm), (1, Some(4.0), Some(120.0)));
    // Two bars of 2/4 at 120 = 2 s each; the take is half a second long, so the chorus starts after it ends.
    assert_eq!(take.sections.first().map(|x| (x.name.as_str(), x.start)), Some(("verse", 0.0)));
    let mix = data.track(Role::Mix).unwrap();
    assert_eq!(s.track(mix).unwrap().clips().len(), 1);
    let lyrics = data.track(Role::Lyrics).unwrap();
    assert_eq!(s.track(lyrics).unwrap().clips().first().map(|c| c.name.as_str()), Some("[verse] Morning light"));
    assert_eq!(s.tempo.tempos()[0].bpm, 120.0);
    assert_eq!(s.key_signatures, vec![(0, "A minor".to_string())]);
    assert_eq!(data.documents.get("lyrics").map(|d| d.text.as_str()), Some("[verse]\nMorning light\n[chorus]\nWe sing"));
    assert!(crate::draw::badge(&ui, data).starts_with("Plenio · Take 1 · 4 stars (of 1)"));
    let _ = std::fs::remove_dir_all(&dir);
}

/// The owner's wish of 2026-11-06: the inspector's height is theirs to change, to see more.
#[test]
fn the_inspectors_height_follows_the_window() {
    let _turn = turn();
    let mut app = app();
    app.run("plenio.song.new", json!({"title": "Garden"})).unwrap();
    let mut ui = quiet_ui();
    ui.settings.activated = true;
    ui.show_inspector = true;
    app.add_extension(Box::new(ui));
    let ctx = egui::Context::default();
    let screen = egui::Rect::from_min_size(egui::Pos2::ZERO, egui::vec2(1400.0, 1000.0));
    let run = |app: &mut SoundApp, events: Vec<egui::Event>| {
        let mut out = ctx.run_ui(egui::RawInput { screen_rect: Some(screen), events, ..Default::default() }, |ui| {
            app.logic(ui.ctx());
            app.ui(ui);
        });
        out.textures_delta.clear();
    };
    // Press on the window's lower edge, pull it by `by` points, let go.
    let drag = |app: &mut SoundApp, rect: egui::Rect, by: f32| {
        let from = egui::pos2(rect.center().x, rect.max.y);
        let at = |k: f32| from + egui::vec2(0.0, by * k / 5.0);
        let button =
            |pos, pressed| egui::Event::PointerButton { pos, button: egui::PointerButton::Primary, pressed, modifiers: egui::Modifiers::NONE };
        run(app, vec![egui::Event::PointerMoved(from)]);
        run(app, vec![egui::Event::PointerMoved(from)]);
        run(app, vec![button(from, true)]);
        for k in 1..=5 {
            run(app, vec![egui::Event::PointerMoved(at(k as f32))]);
        }
        run(app, vec![button(at(5.0), false)]);
        for _ in 0..3 {
            run(app, Vec::new());
        }
    };
    for _ in 0..4 {
        run(&mut app, Vec::new());
    }
    let id = egui::Id::unique(windows::INSPECTOR_TITLE);
    let before = egui::AreaState::load(&ctx, id).and_then(|a| a.rect().is_finite().then(|| a.rect())).expect("the inspector is shown");
    assert!(before.height() > 400.0, "it opens tall enough to see the lyrics: {before:?}");

    // Up: the window follows, its content does not hold it open.
    drag(&mut app, before, -250.0);
    let smaller = egui::AreaState::load(&ctx, id).map(|a| a.rect()).expect("the inspector is shown");
    assert!((before.height() - smaller.height() - 250.0).abs() < 20.0, "from {before:?} to {smaller:?}");
    // Down, past where it started: the window is taller than its content needs.
    drag(&mut app, smaller, 350.0);
    let taller = egui::AreaState::load(&ctx, id).map(|a| a.rect()).expect("the inspector is shown");
    assert!((taller.height() - smaller.height() - 350.0).abs() < 20.0, "from {smaller:?} to {taller:?}");
    assert!(taller.height() > before.height());
    assert_eq!(app.extensions(), vec![("plenio", true)]);
}

#[test]
fn every_window_draws_without_a_studio() {
    let _turn = turn();
    let mut app = app();
    app.run("plenio.song.new", json!({"title": "Garden"})).unwrap();
    let mut ui = quiet_ui();
    ui.settings.activated = true;
    ui.show_inspector = true;
    ui.show_studio = true;
    ui.show_about = true;
    ui.show_activation = true;
    ui.new_song = Some(windows::NewSong {
        kind: soundcraft_plenio_project::SongKind::Song,
        template: "pop/x".into(),
        idea: String::new(),
        vocals: "sung".into(),
        length: "short (about 1:30)".into(),
        language: "English".into(),
        own_lyrics: true,
        lyrics: "[verse]\nhi".into(),
        source: None,
        filter: String::new(),
    });
    ui.templates.insert(
        "yue2-song".into(),
        json!({"fields": [
            {"id": "vocals", "type": "choice", "choices": ["sung", "instrumental"], "default": "sung"},
            {"id": "creativity", "type": "integer", "min": 0, "max": 200, "default": 100},
            {"id": "finish.cover_art", "type": "boolean", "default": true},
            {"id": "description", "type": "text", "default": ""},
            {"id": "genre", "type": "string", "default": "pop"},
            {"id": "mode", "type": "choice", "fixed": true, "choices": ["x"]}
        ], "seeds": [{"id": "take"}]}),
    );
    app.add_extension(Box::new(ui));
    frames(&mut app, 4);
    assert_eq!(app.extensions(), vec![("plenio", true)]);
}

#[test]
fn a_plenio_song_is_brought_in_with_its_take_and_lyrics() {
    let _turn = turn();
    let dir = temp("import");
    let mut ui = quiet_ui();
    let mut app = app();
    wav(&dir.join("2026-11-05 Garden.flac"));
    std::fs::write(dir.join("2026-11-05 Garden (lines).srt"), "1\n00:00:00,100 --> 00:00:00,400\nMorning light\n").unwrap();
    let record = json!({"schema": "plenio.record/1", "title": "Garden", "documents": {
        "lyrics": {"state": "auto", "status": "", "sha256": "", "text": "[verse]\nMorning light"},
        "score": {"state": "auto", "status": "", "sha256": "", "text": "X:1\nM:4/4\nQ:1/4=100\nK:C\n% verse\nV: Vocal\nz8|\n"}},
        "audio": {"seconds": 0.5, "sample_rate": 48000}, "quality": {"stars": 3.5}});
    let path = dir.join("2026-11-05 Garden.plenio.json");
    std::fs::write(&path, record.to_string()).unwrap();
    ui.import_record(&mut app, path);
    let p = Project::load(app.engine.session()).unwrap();
    let song = p.songs.first().unwrap();
    assert_eq!(song.title, "Garden");
    let take = song.active_take().unwrap();
    assert_eq!((take.stars, take.lines.len(), take.bpm), (Some(3.5), 1, Some(100.0)));
    let lyrics = song.track(Role::Lyrics).unwrap();
    assert_eq!(app.engine.session().track(lyrics).unwrap().clips().first().map(|c| c.name.as_str()), Some("Morning light"));
    // Not a Plenio record: refused with a message, nothing made.
    let other = dir.join("other.plenio.json");
    std::fs::write(&other, "{\"hello\": 1}").unwrap();
    ui.import_record(&mut app, other);
    assert_eq!(Project::load(app.engine.session()).unwrap().songs.len(), 1);
    let _ = std::fs::remove_dir_all(&dir);
}
