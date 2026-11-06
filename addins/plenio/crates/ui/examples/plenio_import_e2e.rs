//! A Plenio song brought in through SoundCraft's UI, offscreen: activate the add-in, choose
//! "Import Plenio Song…" from its menu with a file dialog that answers with the given file, wait for
//! the studio (a real ComfyUI with Plenio), and report what arrived. No model is loaded, unless asked
//! for what comes next: `stems` splits the take, `make-again` also makes a new take (the graphics card
//! for a few minutes).
//!
//! `cargo run -p soundcraft-plenio-ui --example plenio_import_e2e -- <file> <folder for screenshots> [stems|make-again]`

use egui_kittest::kittest::Queryable;
use soundcraft_plenio_project::Project;
use soundcraft_ui_egui::{Services, SoundApp};
use std::path::PathBuf;
use std::sync::atomic::{AtomicBool, Ordering};
use std::time::{Duration, Instant};

static READY: AtomicBool = AtomicBool::new(false);

/// Where the metronome clicks in the audio of the active take: every beat as the click renderer steps
/// through the tempo map (`mix/src/click.rs`), in seconds of the audio file. For a measure from outside.
fn write_clicks(s: &soundcraft_model::Session, path: &std::path::Path) {
    let Ok(p) = Project::load(s) else { return };
    let Some(take) = p.songs.first().and_then(|song| song.active_take()) else { return };
    let rate = s.sample_rate;
    let last = rate.samples(take.audio_at + take.seconds);
    let mut tick = 0;
    let (mut beats, mut bars) = (Vec::new(), Vec::new());
    while s.tempo.tick_to_samples(tick, rate) <= last {
        let at = rate.seconds(s.tempo.tick_to_samples(tick, rate)) - take.audio_at;
        beats.push(at);
        if s.tempo.bar_beat_at_tick(tick).beat == 1 {
            bars.push(at);
        }
        tick += s.tempo.meter_at_tick(tick).ticks_per_beat();
    }
    let answer = serde_json::json!({
        "audio": take.files.get("song"), "audio_at": take.audio_at, "seconds": take.seconds, "warp": take.warp,
        "tempos": s.tempo.tempos().len(), "beats": beats, "bars": bars,
    });
    if let Err(e) = std::fs::write(path, answer.to_string()) {
        eprintln!("{}: {e}", path.display());
    }
}

fn report(s: &soundcraft_model::Session) {
    let rate = s.sample_rate;
    println!("session: {} tracks, tempo {:?}", s.tracks.len(), s.tempo.tempos()[0].bpm);
    let Ok(p) = Project::load(s) else { return };
    for song in &p.songs {
        println!("song {} \"{}\": template {}, {} fields, {} takes", song.id, song.title, song.template, song.fields.len(), song.takes.len());
        let Some(take) = song.active_take() else { continue };
        println!(
            "take {}: {:.2} s, warp {:?}, audio at {:.3} s, score at {:.3} s, {} lines, {} sections, stars {:?}, seeds {:?}",
            take.number,
            take.seconds,
            take.warp,
            take.audio_at,
            take.score_at,
            take.lines.len(),
            take.sections.len(),
            take.stars,
            take.seeds
        );
        println!("files: {:?}", take.files);
        for role in &song.tracks {
            let Some(track) = s.track(role.track) else { continue };
            let Some(clip) = track.clips().first() else {
                println!("  {:?} \"{}\": no clip", role.role, track.name);
                continue;
            };
            let notes = if let soundcraft_model::ClipContent::Midi { sequence } = &clip.content {
                format!(", {} notes", sequence.notes.len())
            } else {
                String::new()
            };
            println!(
                "  {:?} \"{}\": {} clip(s), first {:.3} s to {:.3} s{notes}",
                role.role,
                track.name,
                track.clips().len(),
                rate.seconds(clip.start),
                rate.seconds(clip.start + clip.length)
            );
        }
    }
}

fn main() {
    let file = PathBuf::from(std::env::args().nth(1).expect("the file to bring in"));
    let folder = PathBuf::from(std::env::args().nth(2).unwrap_or_else(|| ".".into()));
    let config = std::env::temp_dir().join(format!("soundcraft-plenio-import-e2e-{}", std::process::id()));
    soundcraft_plenio_ui::register_commands();
    let services = Services {
        pick_open: Some(Box::new(move |purpose: &str, extensions: &[&str]| {
            println!("file dialog: {purpose} {extensions:?}");
            Some(file.clone())
        })),
        ..Services::default()
    };
    let mut app = SoundApp::new(soundcraft_engine::Engine::default(), None, services);
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
    steps(&mut harness, 6);
    harness.get_by_label("Plenio").click();
    steps(&mut harness, 3);
    harness.get_by_label("Activate Plenio Add-in…").click();
    steps(&mut harness, 3);
    harness.get_by_label("I accept the models' licences").click();
    steps(&mut harness, 2);
    harness.get_by_label("Activate").click();
    steps(&mut harness, 3);
    // At once, while the studio is starting: the song has to wait for it.
    harness.get_by_label("Plenio").click();
    steps(&mut harness, 3);
    harness.get_by_label("Import Plenio Song…").click();
    steps(&mut harness, 3);
    println!("status line: {}", harness.state().ui.status);
    let started = Instant::now();
    let mut status = String::new();
    loop {
        steps(&mut harness, 1);
        std::thread::sleep(Duration::from_millis(250));
        if harness.state().ui.status != status {
            status.clone_from(&harness.state().ui.status);
            println!("{:>4} s  status line: {status}", started.elapsed().as_secs());
        }
        let arrived = Project::load(harness.state().engine.session()).ok().is_some_and(|p| p.songs.iter().any(|s| !s.takes.is_empty()));
        if arrived {
            println!("arrived after {} s", started.elapsed().as_secs());
            break;
        }
        if started.elapsed() > Duration::from_secs(300) {
            eprintln!("nothing arrived");
            break;
        }
    }
    steps(&mut harness, 12);
    match harness.render() {
        Ok(image) => {
            let path = folder.join("import-e2e.png");
            match image.save(&path) {
                Ok(()) => println!("wrote {}", path.display()),
                Err(e) => eprintln!("{}: {e}", path.display()),
            }
        }
        Err(e) => eprintln!("render failed: {e}"),
    }
    report(harness.state().engine.session());
    write_clicks(harness.state().engine.session(), &folder.join("clicks.json"));
    let then = std::env::args().nth(3).unwrap_or_default();
    if then == "stems" || then == "make-again" {
        harness.get_by_label("Split this take into stems").click();
        steps(&mut harness, 3);
        let roles = |h: &egui_kittest::Harness<SoundApp>| {
            Project::load(h.state().engine.session())
                .ok()
                .and_then(|p| p.songs.first().map(|s| s.tracks.iter().map(|t| t.role).collect::<Vec<_>>()))
                .unwrap_or_default()
        };
        let split = Instant::now();
        while !roles(&harness).contains(&soundcraft_plenio_project::Role::Vocals) && split.elapsed() < Duration::from_secs(300) {
            steps(&mut harness, 1);
            std::thread::sleep(Duration::from_millis(250));
            if harness.state().ui.status != status {
                status.clone_from(&harness.state().ui.status);
                println!("{:>4} s  status line: {status}", split.elapsed().as_secs());
                if status.contains("no stems") || status.contains("not in the studio") {
                    break;
                }
            }
        }
        println!("stems after {} s: {:?}", split.elapsed().as_secs(), roles(&harness));
    }
    if then == "make-again" {
        let takes = |h: &egui_kittest::Harness<SoundApp>| {
            Project::load(h.state().engine.session()).ok().and_then(|p| p.songs.first().map(|s| s.takes.len())).unwrap_or(0)
        };
        harness.get_by_label("Generate").click();
        steps(&mut harness, 3);
        let again = Instant::now();
        while takes(&harness) < 2 && again.elapsed() < Duration::from_secs(900) {
            steps(&mut harness, 1);
            std::thread::sleep(Duration::from_millis(250));
            if harness.state().ui.status != status {
                status.clone_from(&harness.state().ui.status);
                println!("{:>4} s  status line: {status}", again.elapsed().as_secs());
                if status.contains("no take") {
                    break;
                }
            }
        }
        println!("a new take after {} s: {} takes", again.elapsed().as_secs(), takes(&harness));
        steps(&mut harness, 12);
        match harness.render() {
            Ok(image) => {
                let _ = image.save(folder.join("import-e2e-again.png"));
            }
            Err(e) => eprintln!("render failed: {e}"),
        }
        report(harness.state().engine.session());
    }
    for m in harness.state().engine.messages.iter().rev().take(6).rev() {
        println!("message: {m}");
    }
    // Dropping the app stops the studio.
    drop(harness);
    let _ = std::fs::remove_dir_all(&config);
}
