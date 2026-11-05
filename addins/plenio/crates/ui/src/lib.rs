//! The Plenio add-in in SoundCraft's UI: the Plenio menu, the activation window and, to come, the
//! song tracks, the inspector and the lyrics editor (see `addins/plenio/docs/PLAN.md`).
//!
//! The app installs it with two calls: [`register_commands`] before the first command runs, and
//! `SoundApp::add_extension(soundcraft_plenio_ui::extension(..))`.
#![deny(clippy::unwrap_used, clippy::expect_used, clippy::panic, clippy::unimplemented, clippy::todo, clippy::unreachable)]

use serde_json::json;
use soundcraft_plenio_backend::Settings;
use soundcraft_ui_egui::SoundApp;
use soundcraft_ui_egui::extension::UiExtension;
use std::path::PathBuf;

/// Register the add-in's commands; call it once, before the first command runs.
pub fn register_commands() {
    soundcraft_plenio_commands::register();
}

/// The add-in's UI part. `config_dir` is SoundCraft's settings folder, where the add-in keeps its
/// own settings; without one (test runs, a profile without preferences) nothing is saved.
pub fn extension(config_dir: Option<PathBuf>) -> Box<dyn UiExtension> {
    Box::new(PlenioUi::new(config_dir))
}

/// What the menu leads to before the setup assistant and song making exist.
const COMING: &str = "Comes with the next milestones of the add-in: the setup (ComfyUI, models), then songs and covers.";

struct PlenioUi {
    config_dir: Option<PathBuf>,
    settings: Settings,
    show_activation: bool,
    show_about: bool,
}

impl PlenioUi {
    fn new(config_dir: Option<PathBuf>) -> Self {
        let settings = match config_dir.as_deref().map(Settings::load) {
            Some(Ok(s)) => s,
            Some(Err(e)) => {
                log::warn!("{e}; the Plenio add-in starts deactivated");
                Settings::default()
            }
            None => Settings::default(),
        };
        soundcraft_plenio_commands::set_activated(settings.activated);
        PlenioUi { config_dir, settings, show_activation: false, show_about: false }
    }

    /// Turn the add-in on or off and keep the choice.
    fn set_activated(&mut self, app: &mut SoundApp, on: bool) {
        self.settings.activated = on;
        soundcraft_plenio_commands::set_activated(on);
        if let Some(dir) = &self.config_dir
            && let Err(e) = self.settings.save(dir)
        {
            log::warn!("{e}");
            app.engine.message(format!("The Plenio setting could not be saved: {e}"));
        }
        app.engine.message(if on { "Plenio add-in activated." } else { "Plenio add-in deactivated." });
    }

    fn menu(&mut self, app: &mut SoundApp, ui: &mut egui::Ui) {
        if self.settings.activated {
            for item in ["New Song…", "New Cover from Selection…", "Open Plenio Player"] {
                ui.add_enabled(false, egui::Button::new(item)).on_disabled_hover_text(COMING);
            }
            ui.separator();
            if ui.button("Deactivate Plenio Add-in").clicked() {
                self.set_activated(app, false);
                ui.close();
            }
        } else if ui.button("Activate Plenio Add-in…").clicked() {
            self.show_activation = true;
            ui.close();
        }
        ui.separator();
        if ui.button("About the Plenio Add-in").clicked() {
            self.show_about = true;
            ui.close();
        }
    }

    fn activation_window(&mut self, app: &mut SoundApp, ctx: &egui::Context) {
        let mut open = self.show_activation;
        let mut answer = None;
        egui::Window::new("Activate the Plenio Add-in").open(&mut open).collapsible(false).resizable(false).default_width(440.0).show(ctx, |ui| {
            ui.label("Plenio makes songs and covers with YuE2 right in your session: the lyrics, the score and every take are tracks you edit, mix and make again.");
            ui.add_space(6.0);
            ui.label(
                "Activating it will set up its studio: a ComfyUI instance of its own (your own ComfyUI stays as it is) and the models, \
                 downloaded once. YuE2 and SheetSage2 are licensed CC BY-NC 4.0: non-commercial use only.",
            );
            ui.add_space(6.0);
            ui.label(egui::RichText::new(format!("This build: the setup itself is not here yet. {COMING}")).small().weak());
            ui.add_space(8.0);
            ui.horizontal(|ui| {
                if ui.button("Activate").clicked() {
                    answer = Some(true);
                }
                if ui.button("Cancel").clicked() {
                    answer = Some(false);
                }
            });
        });
        if let Some(on) = answer {
            open = false;
            if on {
                self.set_activated(app, true);
            }
        }
        self.show_activation = open;
    }

    fn about_window(&mut self, app: &mut SoundApp, ctx: &egui::Context) {
        let mut open = self.show_about;
        let status = app.engine.execute("plenio.status", &json!({}));
        egui::Window::new("About the Plenio Add-in").open(&mut open).collapsible(false).resizable(false).default_width(380.0).show(ctx, |ui| {
            ui.label(format!("Plenio add-in {}", soundcraft_plenio_commands::VERSION));
            ui.label("YuE2 Song, YuE2 Cover and the Plenio Player in SoundCraft, from the Plenio Music Production System by Johannes Plenio.");
            ui.add_space(6.0);
            match &status {
                Ok(v) => {
                    let songs = v["songs"].as_array().map_or(0, Vec::len);
                    let state = if self.settings.activated { "activated" } else { "not activated" };
                    ui.label(format!("Status: {state} · songs in this session: {songs}"));
                }
                Err(e) => {
                    ui.label(format!("Status: {e}"));
                }
            }
        });
        self.show_about = open;
    }
}

impl UiExtension for PlenioUi {
    fn id(&self) -> &'static str {
        "plenio"
    }

    fn menu_bar(&mut self, app: &mut SoundApp, ui: &mut egui::Ui) {
        ui.menu_button("Plenio", |ui| self.menu(app, ui));
    }

    fn windows(&mut self, app: &mut SoundApp, ctx: &egui::Context) {
        if self.show_activation {
            self.activation_window(app, ctx);
        }
        if self.show_about {
            self.about_window(app, ctx);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use soundcraft_ui_egui::Services;

    fn temp_config(name: &str) -> PathBuf {
        let dir = std::env::temp_dir().join(format!("soundcraft-plenio-ui-{name}-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&dir);
        dir
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
        let dir = temp_config("activation");
        let mut app = SoundApp::new(soundcraft_engine::Engine::default(), None, Services::default());
        let mut ui = PlenioUi::new(Some(dir.clone()));
        assert!(!ui.settings.activated);
        ui.set_activated(&mut app, true);
        assert!(soundcraft_plenio_commands::activated());
        assert!(Settings::load(&dir).unwrap().activated);
        // A new start reads it back.
        let again = PlenioUi::new(Some(dir.clone()));
        assert!(again.settings.activated);
        let mut again = again;
        again.set_activated(&mut app, false);
        assert!(!Settings::load(&dir).unwrap().activated);
        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn the_extension_draws_its_menu_and_windows_without_errors() {
        let mut app = SoundApp::new(soundcraft_engine::demo::demo_engine(), None, Services::default());
        let mut ui = PlenioUi::new(None);
        ui.show_activation = true;
        ui.show_about = true;
        app.add_extension(Box::new(ui));
        frames(&mut app, 3);
        assert_eq!(app.extensions(), vec![("plenio", true)]);
    }
}
