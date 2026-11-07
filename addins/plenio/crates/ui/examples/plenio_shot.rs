//! Render SoundCraft with the Plenio add-in offscreen (no window, no focus stealing, no studio) and
//! save PNGs of its menu and windows: activation, getting started, the New Song dialog (empty, with
//! own lyrics, with More options), about.
//!
//! `cargo run -p soundcraft-plenio-ui --example plenio_shot -- [folder] [config folder] [session]`
//!
//! With a session (`.scraft`) that holds Plenio songs, such as the tour's, it also renders each song
//! on its tracks with the inspector open (`session-song-<id>.png`): its folder open, the others closed.
//!
//! With `PLENIO_SHOT_STUDIO=1` it also starts a studio (a real ComfyUI, for about a minute) to render
//! the Studio and Models window with the models it finds (`plenio-studio.png`).
//!
//! With the config folder of an add-in that met its studio before (its `Plenio/api-cache.json`, such
//! as the one `examples/plenio_tour.rs` leaves), the dialogs show the studio's styles and fields.
//! Nothing is written there: the shots work on a copy, and never start a studio.

use egui_kittest::kittest::Queryable;
use soundcraft_ui_egui::{Services, SoundApp};
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicBool, Ordering};

static READY: AtomicBool = AtomicBool::new(false);

type H = egui_kittest::Harness<'static, SoundApp>;

fn steps(h: &mut H, n: usize) {
    for _ in 0..n {
        h.step();
    }
}

fn click(h: &mut H, label: &str) {
    if let Some(node) = h.query_all_by_label(label).next() {
        node.click();
    } else {
        eprintln!("not found: {label:?}");
    }
    steps(h, 4);
}

fn shoot(h: &mut H, folder: &Path, name: &str) {
    let path = folder.join(name);
    match h.render() {
        Ok(img) => match img.save(&path) {
            Ok(()) => println!("wrote {}", path.display()),
            Err(e) => eprintln!("{}: {e}", path.display()),
        },
        Err(e) => eprintln!("render failed: {e}"),
    }
}

/// The demo session with the add-in, its settings in `config` (activated or not).
fn harness(config: &Path, activated: bool) -> H {
    let settings = serde_json::json!({"activated": activated, "licences_accepted": activated, "start_with_soundcraft": false});
    let _ = std::fs::write(config.join("Plenio").join("settings.json"), settings.to_string());
    let mut app = SoundApp::new(soundcraft_engine::demo::demo_engine(), None, Services::default());
    app.add_extension(soundcraft_plenio_ui::extension(Some(config.to_path_buf())));
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
    h
}

fn main() {
    let folder = PathBuf::from(std::env::args().nth(1).unwrap_or_else(|| ".".into()));
    let config = std::env::temp_dir().join(format!("plenio-shot-{}", std::process::id()));
    let _ = std::fs::create_dir_all(config.join("Plenio"));
    if let Some(given) = std::env::args().nth(2) {
        let _ = std::fs::copy(Path::new(&given).join("Plenio").join("api-cache.json"), config.join("Plenio").join("api-cache.json"));
    }
    soundcraft_plenio_ui::register_commands();

    // Before activation: the menu and the activation window (left with Cancel: no studio starts).
    let mut h = harness(&config, false);
    click(&mut h, "Plenio");
    shoot(&mut h, &folder, "plenio-menu.png");
    click(&mut h, "Activate Plenio Add-in…");
    shoot(&mut h, &folder, "plenio-activate.png");
    click(&mut h, "Cancel");
    drop(h);

    // Activated, the studio stopped.
    let mut h = harness(&config, true);
    click(&mut h, "Plenio");
    shoot(&mut h, &folder, "plenio-menu-activated.png");
    click(&mut h, "Getting Started");
    shoot(&mut h, &folder, "plenio-getting-started.png");
    click(&mut h, "Close window");
    click(&mut h, "Plenio");
    click(&mut h, "New Song…");
    shoot(&mut h, &folder, "plenio-new-song.png");
    click(&mut h, "My own lyrics, sung as written");
    if let Some(node) = h.query_by(|n| n.placeholder() == Some("[verse]\n…\n\n[chorus]\n…")) {
        node.focus();
        steps(&mut h, 2);
        let verse = "[verse]\nHum it in the dark and write it on the screen\nEvery word I wanted finds a melody";
        for (i, line) in verse.lines().enumerate() {
            if i > 0 {
                h.key_press(egui::Key::Enter);
            }
            if let Some(n) = h.query_by(|n| n.is_focused()) {
                n.type_text(line);
            }
            steps(&mut h, 1);
        }
        h.key_press(egui::Key::Tab);
    }
    steps(&mut h, 4);
    shoot(&mut h, &folder, "plenio-new-song-lyrics.png");
    click(&mut h, "More options");
    shoot(&mut h, &folder, "plenio-new-song-more.png");
    click(&mut h, "Cancel");
    click(&mut h, "Plenio");
    click(&mut h, "About the Plenio Add-in");
    shoot(&mut h, &folder, "plenio-about.png");
    click(&mut h, "Close window");
    if std::env::var("PLENIO_SHOT_STUDIO").is_ok_and(|v| v == "1") {
        studio(&mut h, &folder);
    }
    if let Some(session) = std::env::args().nth(3) {
        songs(&mut h, &folder, &session);
    }
    drop(h);
    let _ = std::fs::remove_dir_all(&config);
}

/// Start the studio from its window, wait for it and its models, render the window, stop it.
fn studio(h: &mut H, folder: &Path) {
    click(h, "Plenio");
    click(h, "Studio and Models…");
    click(h, "Start Studio");
    let started = std::time::Instant::now();
    while h.query_by_label_contains("Studio: ready").is_none() && started.elapsed() < std::time::Duration::from_secs(300) {
        steps(h, 1);
        std::thread::sleep(std::time::Duration::from_millis(250));
    }
    let settle = std::time::Instant::now();
    while settle.elapsed() < std::time::Duration::from_secs(4) {
        steps(h, 1);
        std::thread::sleep(std::time::Duration::from_millis(200));
    }
    shoot(h, folder, "plenio-studio.png");
    click(h, "Stop Studio");
    click(h, "Close window");
}

fn run(h: &mut H, id: &str, params: serde_json::Value) {
    if let Err(e) = h.state_mut().run(id, params) {
        eprintln!("{id}: {e}");
    }
}

/// Every Plenio song of a session on its tracks: its folder open and scrolled to, the others closed,
/// the session fitted into the window, the inspector showing it.
fn songs(h: &mut H, folder: &Path, session: &str) {
    run(h, "session.open", serde_json::json!({"path": session}));
    steps(h, 6);
    let project = soundcraft_plenio_project::Project::load(h.state().engine.session()).unwrap_or_default();
    let folders: Vec<(u64, u64)> = project.songs.iter().filter_map(|s| s.track(soundcraft_plenio_project::Role::Song).map(|t| (s.id, t.0))).collect();
    click(h, "Plenio");
    click(h, "Song Inspector");
    for (song, track) in &folders {
        for (_, other) in &folders {
            run(h, "track.folder_toggle", serde_json::json!({"track": other, "open": other == track}));
        }
        run(h, "edit.select", serde_json::json!({"tracks": [track]}));
        run(h, "track.scroll_to", serde_json::json!({"track": track}));
        run(h, "view.zoom_fit", serde_json::json!({"width_px": 1150}));
        steps(h, 6);
        shoot(h, folder, &format!("session-song-{song}.png"));
    }
}
