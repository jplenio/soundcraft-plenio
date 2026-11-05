//! Render SoundCraft with the Plenio add-in offscreen (no window, no focus stealing) and save PNGs
//! of the Plenio menu and the activation window.
//!
//! `cargo run -p soundcraft-plenio-ui --example plenio_shot -- [folder]`

use egui_kittest::kittest::Queryable;
use soundcraft_ui_egui::{Services, SoundApp};
use std::sync::atomic::{AtomicBool, Ordering};

static READY: AtomicBool = AtomicBool::new(false);

fn main() {
    let folder = std::path::PathBuf::from(std::env::args().nth(1).unwrap_or_else(|| ".".into()));
    soundcraft_plenio_ui::register_commands();
    let mut app = SoundApp::new(soundcraft_engine::demo::demo_engine(), None, Services::default());
    app.add_extension(soundcraft_plenio_ui::extension(None));
    let mut harness = egui_kittest::Harness::builder()
        .with_size(egui::vec2(1600.0, 1000.0))
        .with_pixels_per_point(1.5)
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
    steps(&mut harness, 4);
    shoot(&mut harness, "plenio-menu.png");
    harness.get_by_label("Activate Plenio Add-in…").click();
    steps(&mut harness, 4);
    shoot(&mut harness, "plenio-activate.png");
    harness.get_by_label("Activate").click();
    steps(&mut harness, 4);
    harness.get_by_label("Plenio").click();
    steps(&mut harness, 4);
    shoot(&mut harness, "plenio-menu-activated.png");
}
