//! A whole song through SoundCraft's UI, offscreen: activate the add-in from its menu, make a song
//! from the New Song dialog, wait for the studio (a real ComfyUI with Plenio) to deliver the take,
//! and save screenshots. Starts ComfyUI and uses the graphics card for a few minutes.
//!
//! `cargo run -p soundcraft-plenio-ui --example plenio_e2e -- <folder for screenshots> [minutes]`

use egui_kittest::kittest::Queryable;
use soundcraft_plenio_project::Project;
use soundcraft_ui_egui::{Services, SoundApp};
use std::sync::atomic::{AtomicBool, Ordering};
use std::time::{Duration, Instant};

static READY: AtomicBool = AtomicBool::new(false);

fn main() {
    let folder = std::path::PathBuf::from(std::env::args().nth(1).unwrap_or_else(|| ".".into()));
    let minutes: u64 = std::env::args().nth(2).and_then(|m| m.parse().ok()).unwrap_or(15);
    let config = std::env::temp_dir().join(format!("soundcraft-plenio-e2e-{}", std::process::id()));
    soundcraft_plenio_ui::register_commands();
    let mut app = SoundApp::new(soundcraft_engine::Engine::default(), None, Services::default());
    app.add_extension(soundcraft_plenio_ui::extension(Some(config.clone())));
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
    harness.get_by_label("New Song…").click();
    steps(&mut harness, 3);
    shoot(&mut harness, "e2e-1-new-song.png");
    harness.get_by_label("Make the Song").click();
    steps(&mut harness, 3);
    println!("song asked for; waiting for the take (at most {minutes} minutes)");
    let started = Instant::now();
    let mut shot_progress = false;
    let mut last_message = String::new();
    loop {
        steps(&mut harness, 1);
        std::thread::sleep(Duration::from_millis(250));
        let engine = &harness.state().engine;
        if let Some(m) = engine.messages.last()
            && *m != last_message
        {
            println!("{:>4} s  {m}", started.elapsed().as_secs());
            last_message = m.clone();
        }
        let takes = Project::load(engine.session()).ok().map_or(0, |p| p.songs.iter().map(|s| s.takes.len()).sum::<usize>());
        if takes > 0 {
            println!("take delivered after {} s", started.elapsed().as_secs());
            break;
        }
        if !shot_progress && started.elapsed() > Duration::from_secs(60) {
            shoot(&mut harness, "e2e-2-making.png");
            shot_progress = true;
        }
        if last_message.contains("no take") || started.elapsed() > Duration::from_secs(minutes * 60) {
            eprintln!("no take: {last_message}");
            shoot(&mut harness, "e2e-failed.png");
            std::process::exit(1);
        }
    }
    steps(&mut harness, 6);
    shoot(&mut harness, "e2e-3-take.png");
    // The score's notes are on their tracks; then stems, then the mix to the player.
    let roles = |h: &egui_kittest::Harness<SoundApp>| {
        Project::load(h.state().engine.session())
            .ok()
            .and_then(|p| p.songs.first().map(|s| s.tracks.iter().map(|t| t.role).collect::<Vec<_>>()))
            .unwrap_or_default()
    };
    println!("roles after the take: {:?}", roles(&harness));
    harness.get_by_label("Split this take into stems").click();
    steps(&mut harness, 2);
    let split = Instant::now();
    while !roles(&harness).contains(&soundcraft_plenio_project::Role::Vocals) && split.elapsed() < Duration::from_secs(300) {
        steps(&mut harness, 1);
        std::thread::sleep(Duration::from_millis(250));
    }
    println!("stems after {} s: {:?}", split.elapsed().as_secs(), roles(&harness));
    steps(&mut harness, 4);
    shoot(&mut harness, "e2e-4-stems.png");
    harness.get_by_label("Send the mix to the Plenio Player").click();
    let sent = Instant::now();
    while !harness.state().engine.messages.iter().any(|m| m.starts_with("Plenio Player")) && sent.elapsed() < Duration::from_secs(120) {
        steps(&mut harness, 1);
        std::thread::sleep(Duration::from_millis(250));
    }
    for m in harness.state().engine.messages.iter().rev().take(4) {
        println!("message: {m}");
    }
    let session = harness.state().engine.session();
    if let Ok(p) = Project::load(session) {
        for s in &p.songs {
            let take = s.active_take();
            println!(
                "song {} \"{}\": {} take(s), {:.1} s, {} sections, {} timed lines, bpm {:?}",
                s.id,
                s.title,
                s.takes.len(),
                take.map_or(0.0, |t| t.seconds),
                take.map_or(0, |t| t.sections.len()),
                take.map_or(0, |t| t.lines.len()),
                take.and_then(|t| t.bpm)
            );
        }
    }
    println!("tracks: {:?}", session.tracks.iter().map(|t| (t.name.clone(), t.clips().len(), t.playlists.len())).collect::<Vec<_>>());
    // Dropping the app stops the studio.
    drop(harness);
    let _ = std::fs::remove_dir_all(&config);
}
