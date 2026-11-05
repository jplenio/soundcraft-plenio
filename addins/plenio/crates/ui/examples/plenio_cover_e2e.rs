//! A whole cover through SoundCraft's UI, offscreen: a recording on an audio track, Plenio ›
//! New Cover from Selected Track…, the studio (a real ComfyUI with Plenio) uploads it and makes the
//! cover, and screenshots are saved. Starts ComfyUI and uses the graphics card for a few minutes.
//!
//! `cargo run -p soundcraft-plenio-ui --example plenio_cover_e2e -- <recording> <folder for screenshots> [minutes]`

use egui_kittest::kittest::Queryable;
use serde_json::json;
use soundcraft_plenio_project::{Project, SongKind};
use soundcraft_ui_egui::{Services, SoundApp};
use std::sync::atomic::{AtomicBool, Ordering};
use std::time::{Duration, Instant};

static READY: AtomicBool = AtomicBool::new(false);

fn main() {
    let Some(recording) = std::env::args().nth(1) else {
        eprintln!("usage: plenio_cover_e2e <recording> <folder> [minutes]");
        std::process::exit(2);
    };
    let folder = std::path::PathBuf::from(std::env::args().nth(2).unwrap_or_else(|| ".".into()));
    let minutes: u64 = std::env::args().nth(3).and_then(|m| m.parse().ok()).unwrap_or(20);
    let config = std::env::temp_dir().join(format!("soundcraft-plenio-cover-e2e-{}", std::process::id()));
    soundcraft_plenio_ui::register_commands();
    let mut app = SoundApp::new(soundcraft_engine::Engine::default(), None, Services::default());
    app.add_extension(soundcraft_plenio_ui::extension(Some(config.clone())));
    let imported = app.run("file.import_audio", json!({"path": recording}));
    println!("recording imported: {imported:?}");
    let track = app.engine.session().tracks.first().map(|t| t.id.0);
    let _ = app.run("edit.select", json!({"tracks": [track]}));
    let mut harness = egui_kittest::Harness::builder()
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
    let steps = |h: &mut egui_kittest::Harness<SoundApp>, n: usize| {
        for _ in 0..n {
            h.step();
        }
    };
    let shoot = |h: &mut egui_kittest::Harness<SoundApp>, name: &str| {
        let path = folder.join(name);
        match h.render() {
            Ok(img) => match img.save(&path) {
                Ok(()) => println!("wrote {}", path.display()),
                Err(e) => eprintln!("{}: {e}", path.display()),
            },
            Err(e) => eprintln!("render failed: {e}"),
        }
    };
    steps(&mut harness, 6);
    harness.get_by_label("Plenio").click();
    steps(&mut harness, 3);
    harness.get_by_label("Activate Plenio Add-in…").click();
    steps(&mut harness, 3);
    harness.get_by_label("I accept the models' licences").click();
    steps(&mut harness, 2);
    harness.get_by_label("Activate").click();
    steps(&mut harness, 3);
    harness.get_by_label("Plenio").click();
    steps(&mut harness, 3);
    harness.get_by_label("New Cover from Selected Track…").click();
    steps(&mut harness, 3);
    shoot(&mut harness, "cover-1-dialog.png");
    harness.get_by_label("Make the Cover").click();
    steps(&mut harness, 3);
    println!("cover asked for; waiting (at most {minutes} minutes)");
    let started = Instant::now();
    let mut last = String::new();
    loop {
        steps(&mut harness, 1);
        std::thread::sleep(Duration::from_millis(250));
        let engine = &harness.state().engine;
        if let Some(m) = engine.messages.last()
            && *m != last
        {
            println!("{:>4} s  {m}", started.elapsed().as_secs());
            last = m.clone();
        }
        let project = Project::load(engine.session()).unwrap_or_default();
        if project.songs.iter().any(|s| s.kind == SongKind::Cover && !s.takes.is_empty()) {
            println!("cover delivered after {} s", started.elapsed().as_secs());
            break;
        }
        if last.contains("no take") || last.contains("not sent") || started.elapsed() > Duration::from_secs(minutes * 60) {
            eprintln!("no cover: {last}");
            shoot(&mut harness, "cover-failed.png");
            std::process::exit(1);
        }
    }
    steps(&mut harness, 6);
    shoot(&mut harness, "cover-2-take.png");
    let session = harness.state().engine.session();
    if let Ok(p) = Project::load(session) {
        for s in &p.songs {
            let t = s.active_take();
            println!(
                "{:?} \"{}\": {} take(s), {:.1} s, roles {:?}, source {:?}",
                s.kind,
                s.title,
                s.takes.len(),
                t.map_or(0.0, |t| t.seconds),
                s.tracks.iter().map(|r| r.role).collect::<Vec<_>>(),
                s.source
            );
        }
    }
    drop(harness);
    let _ = std::fs::remove_dir_all(&config);
}
