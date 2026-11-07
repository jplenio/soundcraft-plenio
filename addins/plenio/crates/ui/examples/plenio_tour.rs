//! A tour of the add-in through SoundCraft's UI with a real studio, as a person would click it:
//! activate, make a song in the New Song dialog (typed lyrics, stems right away), a second take,
//! a cover of the song, and bring a Plenio song in. Every step is rendered offscreen: `shots/` holds
//! the named screenshots of the README and the tutorial, `frames/` every frame for the animations.
//! Starts ComfyUI and uses the graphics card for about 20 minutes.
//!
//! `cargo run --release -p soundcraft-plenio-ui --example plenio_tour -- docs/media/tour.json <folder> [minutes per take]`
//!
//! The add-in keeps its settings and its studio in `<folder>/config`; the session, its takes, stems
//! and scores lie in `<folder>/session`.

use egui_kittest::kittest::Queryable;
use serde_json::{Value, json};
use soundcraft_plenio_project::{Project, Role, SongKind};
use soundcraft_ui_egui::{Services, SoundApp};
use std::cell::RefCell;
use std::path::{Path, PathBuf};
use std::rc::Rc;
use std::sync::atomic::{AtomicBool, Ordering};
use std::time::{Duration, Instant};

static READY: AtomicBool = AtomicBool::new(false);

type H = egui_kittest::Harness<'static, SoundApp>;

/// The tour's output: frames numbered in order, and named shots.
struct Out {
    frames: PathBuf,
    shots: PathBuf,
    count: usize,
}

impl Out {
    fn save(&mut self, h: &mut H, label: &str, shot: Option<&str>) {
        let img = match h.render() {
            Ok(img) => img,
            Err(e) => {
                eprintln!("render failed: {e}");
                return;
            }
        };
        self.count += 1;
        let frame = self.frames.join(format!("{:04}-{label}.png", self.count));
        if let Err(e) = img.save(&frame) {
            eprintln!("{}: {e}", frame.display());
        }
        if let Some(name) = shot {
            let path = self.shots.join(format!("{name}.png"));
            match img.save(&path) {
                Ok(()) => println!("shot {}", path.display()),
                Err(e) => eprintln!("{}: {e}", path.display()),
            }
        }
    }
}

fn steps(h: &mut H, n: usize) {
    for _ in 0..n {
        h.step();
    }
}

/// Click what has this label; false (and a note) when it is not there.
fn click(h: &mut H, label: &str) -> bool {
    let found = h.query_all_by_label(label).next().is_some();
    if found {
        if let Some(node) = h.query_all_by_label(label).next() {
            node.click();
        }
        steps(h, 3);
    } else {
        eprintln!("not found: {label:?}");
    }
    found
}

/// Type into the text field with this hint, a line at a time (a frame after each when `out` is given).
fn type_into(h: &mut H, hint: &str, text: &str, mut out: Option<(&mut Out, &str)>) -> bool {
    let hint = hint.to_string();
    let Some(node) = h.query_by(move |n| n.placeholder() == Some(hint.as_str())) else {
        eprintln!("no text field with the hint {:?}", text.lines().next().unwrap_or_default());
        return false;
    };
    node.focus();
    steps(h, 2);
    let lines: Vec<&str> = text.split('\n').collect();
    for (i, line) in lines.iter().enumerate() {
        if !line.is_empty()
            && let Some(n) = h.query_by(|n| n.is_focused())
        {
            n.type_text(line);
        }
        if i + 1 < lines.len() {
            h.key_press(egui::Key::Enter);
        }
        steps(h, 2);
        if let Some((o, label)) = out.as_mut()
            && (line.starts_with('[') || i + 1 == lines.len() || i % 2 == 1)
        {
            o.save(h, label, None);
        }
    }
    h.key_press(egui::Key::Tab);
    steps(h, 2);
    true
}

/// Step the UI until `done`, printing the add-in's messages and saving a frame every `every`.
fn wait(h: &mut H, out: &mut Out, label: &str, limit: Duration, every: Duration, done: impl Fn(&H) -> bool) -> bool {
    let started = Instant::now();
    let mut last_frame = Instant::now();
    let mut last = String::new();
    loop {
        steps(h, 1);
        std::thread::sleep(Duration::from_millis(250));
        if let Some(m) = h.state().engine.messages.last()
            && *m != last
        {
            println!("{:>5} s  {m}", started.elapsed().as_secs());
            last = m.clone();
        }
        if last_frame.elapsed() >= every {
            out.save(h, label, None);
            last_frame = Instant::now();
        }
        if done(h) {
            println!("{label}: after {} s", started.elapsed().as_secs());
            steps(h, 4);
            return true;
        }
        if last.contains("no take") || last.contains("no stems") || started.elapsed() > limit {
            eprintln!("{label}: not done ({last})");
            return false;
        }
    }
}

fn project(h: &H) -> Project {
    Project::load(h.state().engine.session()).unwrap_or_default()
}

fn song_of(h: &H, kind: SongKind) -> Option<u64> {
    project(h).songs.iter().find(|s| s.kind == kind).map(|s| s.id)
}

fn takes(h: &H, song: Option<u64>) -> usize {
    song.and_then(|id| project(h).song(id).map(|s| s.takes.len())).unwrap_or(0)
}

fn has_stems(h: &H, song: Option<u64>, take: usize) -> bool {
    let Some(s) = song.and_then(|id| project(h).song(id).cloned()) else { return false };
    let Some(track) = s.track(Role::Vocals) else { return false };
    // One playlist per take on a stem track: the newest take's has clips.
    h.state().engine.session().track(track).is_some_and(|t| t.playlists.len() >= take && t.playlists.iter().all(|p| !p.clips.is_empty()))
}

fn run(h: &mut H, id: &str, params: Value) -> Option<Value> {
    match h.state_mut().run(id, params) {
        Ok(v) => Some(v),
        Err(e) => {
            eprintln!("{id}: {e}");
            None
        }
    }
}

/// Show `song` in the inspector and on its tracks: its folder open and scrolled to, the other songs'
/// folders closed, its folder selected (the inspector follows the selection), the session fitted into
/// the window.
fn focus_song(h: &mut H, song: Option<u64>) {
    let folders: Vec<(u64, u64)> = project(h).songs.iter().filter_map(|s| s.track(Role::Song).map(|t| (s.id, t.0))).collect();
    for (id, track) in &folders {
        run(h, "track.folder_toggle", json!({"track": track, "open": Some(*id) == song}));
    }
    if let Some((_, track)) = folders.iter().find(|(id, _)| Some(*id) == song) {
        run(h, "edit.select", json!({"tracks": [track]}));
        run(h, "track.scroll_to", json!({"track": track}));
    }
    run(h, "view.zoom_fit", json!({"width_px": 1150}));
    steps(h, 4);
}

fn main() {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let (Some(tour), Some(folder)) = (args.first(), args.get(1)) else {
        eprintln!("usage: plenio_tour <tour.json> <folder> [minutes per take]");
        std::process::exit(2);
    };
    let minutes: u64 = args.get(2).and_then(|m| m.parse().ok()).unwrap_or(15);
    let tour: Value = match std::fs::read_to_string(tour).map_err(|e| e.to_string()).and_then(|t| serde_json::from_str(&t).map_err(|e| e.to_string()))
    {
        Ok(v) => v,
        Err(e) => {
            eprintln!("{tour}: {e}");
            std::process::exit(2);
        }
    };
    let s = |v: &Value, k: &str| v.get(k).and_then(Value::as_str).unwrap_or_default().to_string();
    let folder = PathBuf::from(folder);
    let config = folder.join("config");
    let mut out = Out { frames: folder.join("frames"), shots: folder.join("shots"), count: 0 };
    for dir in [&config, &out.frames, &out.shots, &folder.join("session")] {
        if let Err(e) = std::fs::create_dir_all(dir) {
            eprintln!("{}: {e}", dir.display());
            std::process::exit(2);
        }
    }
    // The file dialog of "Import Plenio Song…" answers with the file the tour chose.
    let pick: Rc<RefCell<Option<PathBuf>>> = Rc::new(RefCell::new(None));
    let picked = Rc::clone(&pick);
    let services = Services { pick_open: Some(Box::new(move |_, _| picked.borrow().clone())), ..Services::default() };
    soundcraft_plenio_ui::register_commands();
    let mut app = SoundApp::new(soundcraft_engine::Engine::default(), None, services);
    app.add_extension(soundcraft_plenio_ui::extension(Some(config.clone())));
    let mut h: H = egui_kittest::Harness::builder()
        .with_size(egui::vec2(1600.0, 1000.0))
        .with_pixels_per_point(1.25)
        .with_max_steps(1_000_000)
        .wgpu()
        .build_ui_state(
            |ui, app: &mut SoundApp| {
                if !READY.load(Ordering::Relaxed) {
                    return;
                }
                let ctx = ui.ctx().clone();
                app.logic(&ctx);
                app.ui(ui);
            },
            app,
        );
    READY.store(true, Ordering::Relaxed);
    steps(&mut h, 6);
    let song_brief = &tour["song"];
    let session = folder.join("session").join(s(&tour, "session"));
    run(&mut h, "session.save_as", json!({"path": session.to_string_lossy(), "replace": true}));

    // 1. Activate, and watch the studio start.
    out.save(&mut h, "start", Some("00-empty"));
    click(&mut h, "Plenio");
    out.save(&mut h, "menu", Some("01-menu-inactive"));
    if click(&mut h, "Activate Plenio Add-in…") {
        out.save(&mut h, "activate", Some("02-activate"));
        click(&mut h, "I accept the models' licences");
        click(&mut h, "Activate");
    } else {
        h.key_press(egui::Key::Escape);
        steps(&mut h, 2);
    }
    if !wait(&mut h, &mut out, "studio", Duration::from_secs(600), Duration::from_secs(3), |h| h.query_by_label_contains("Studio: ready").is_some()) {
        std::process::exit(1);
    }
    // The styles, the fields and the models come right after.
    let settle = Instant::now();
    while settle.elapsed() < Duration::from_secs(4) {
        steps(&mut h, 1);
        std::thread::sleep(Duration::from_millis(200));
    }
    out.save(&mut h, "studio", Some("03-studio"));
    click(&mut h, "Close window");

    // 2. A new song in the dialog.
    click(&mut h, "Plenio");
    out.save(&mut h, "menu", Some("04-menu"));
    click(&mut h, "New Song…");
    out.save(&mut h, "dialog", Some("05-new-song"));
    type_into(&mut h, "search the styles: jazz, trance, ballad, female …", &s(song_brief, "search"), None);
    out.save(&mut h, "style", None);
    // The style brings its own shape (vocals, length); the lyrics decide how long the song is.
    click(&mut h, &format!("   {}", s(song_brief, "style")));
    out.save(&mut h, "style", Some("06-new-song-style"));
    type_into(&mut h, "Plenio writes one", &s(song_brief, "title"), None);
    click(&mut h, "My own lyrics, sung as written");
    type_into(&mut h, "[verse]\n…\n\n[chorus]\n…", s(song_brief, "lyrics").trim_end(), Some((&mut out, "lyrics")));
    click(&mut h, "Split every take into stems right away");
    out.save(&mut h, "dialog", Some("07-new-song-filled"));
    click(&mut h, "More options");
    out.save(&mut h, "more", Some("08-new-song-more-options"));
    click(&mut h, "More options");
    click(&mut h, "Make the Song");
    out.save(&mut h, "making", Some("09-making"));

    // 3. The first take and its stems, right away.
    let limit = Duration::from_secs(minutes * 60);
    let song = song_of(&h, SongKind::Song);
    if !wait(&mut h, &mut out, "making", limit, Duration::from_secs(3), |h| takes(h, song) >= 1) {
        std::process::exit(1);
    }
    focus_song(&mut h, song);
    out.save(&mut h, "take", Some("10-take-1"));
    wait(&mut h, &mut out, "stems", Duration::from_secs(600), Duration::from_secs(2), |h| has_stems(h, song, 1));
    focus_song(&mut h, song);
    out.save(&mut h, "stems", Some("11-stems"));

    // 4. A second take: nothing changed, so Generate makes a new take of the same song.
    click(&mut h, "Generate");
    out.save(&mut h, "again", Some("12-take-2-making"));
    if wait(&mut h, &mut out, "again", limit, Duration::from_secs(4), |h| takes(h, song) >= 2) {
        wait(&mut h, &mut out, "stems", Duration::from_secs(600), Duration::from_secs(3), |h| has_stems(h, song, 2));
    }
    // The better take is the one on the tracks.
    let best = song
        .and_then(|id| project(&h).song(id)?.takes.iter().max_by(|a, b| a.stars.unwrap_or(0.0).total_cmp(&b.stars.unwrap_or(0.0))).map(|t| t.number));
    if let (Some(id), Some(take)) = (song, best) {
        run(&mut h, "plenio.take.select", json!({"song": id, "take": take}));
    }
    focus_song(&mut h, song);
    out.save(&mut h, "hero", Some("13-song"));
    run(&mut h, "session.save", json!({}));

    // 5. A cover of the song in another style: its take on a track of its own, covered.
    let audio = song.and_then(|id| project(&h).song(id)?.active_take()?.files.get("song").cloned()).filter(|a| Path::new(a).is_file());
    let cover = &tour["cover"];
    if let Some(audio) = audio.filter(|_| cover.is_object()) {
        let before: Vec<u64> = h.state().engine.session().tracks.iter().map(|t| t.id.0).collect();
        run(&mut h, "file.import_audio", json!({"path": audio, "at": 0}));
        let source = h.state().engine.session().tracks.iter().map(|t| t.id.0).find(|id| !before.contains(id));
        if let Some(source) = source {
            run(&mut h, "track.rename", json!({"track": source, "name": s(cover, "source_name")}));
            run(&mut h, "edit.select", json!({"tracks": [source]}));
            steps(&mut h, 3);
            click(&mut h, "Plenio");
            click(&mut h, "New Cover from Selected Track…");
            out.save(&mut h, "cover-dialog", None);
            type_into(&mut h, "search the styles: jazz, trance, ballad, female …", &s(cover, "search"), None);
            click(&mut h, &format!("   {}", s(cover, "style")));
            type_into(&mut h, "the recording's name with (Cover)", &s(cover, "title"), None);
            out.save(&mut h, "cover-dialog", Some("14-new-cover"));
            click(&mut h, "Make the Cover");
            let covered = |h: &H| takes(h, song_of(h, SongKind::Cover)) >= 1;
            if wait(&mut h, &mut out, "cover", limit, Duration::from_secs(4), covered) {
                let covered_song = song_of(&h, SongKind::Cover);
                focus_song(&mut h, covered_song);
                out.save(&mut h, "cover", Some("15-cover"));
            }
            run(&mut h, "session.save", json!({}));
        }
    }

    // 6. A Plenio song brought in from its FLAC, into a session of its own.
    let flac = song.and_then(|id| project(&h).song(id)?.takes.first()?.files.get("song").cloned()).map(PathBuf::from);
    if let Some(flac) = flac.filter(|f| f.is_file()) {
        run(&mut h, "session.new", json!({"name": "Imported"}));
        steps(&mut h, 4);
        *pick.borrow_mut() = Some(flac);
        click(&mut h, "Plenio");
        out.save(&mut h, "import", Some("16-import-menu"));
        click(&mut h, "Import Plenio Song…");
        let imported = |h: &H| takes(h, song_of(h, SongKind::Song)) >= 1;
        if wait(&mut h, &mut out, "import", Duration::from_secs(300), Duration::from_secs(2), imported) {
            let imported_song = song_of(&h, SongKind::Song);
            focus_song(&mut h, imported_song);
            out.save(&mut h, "import", Some("17-imported"));
        }
    }
    for s in &project(&h).songs {
        for t in &s.takes {
            println!("song {} \"{}\" take {}: {:.1} s, stars {:?}, bpm {:?}", s.id, s.title, t.number, t.seconds, t.stars, t.bpm);
        }
    }
    println!("frames: {}", out.count);
    // Dropping the app stops the studio.
    drop(h);
}
