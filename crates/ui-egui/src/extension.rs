//! Extensions: add-ins built into an app add menus, windows and drawing on tracks through
//! [`UiExtension`], without changes to the UI's own code.
//!
//! An extension acts like the rest of the UI: it reads engine state and changes the document by
//! executing commands (its own ones register with `soundcraft_engine::cmd::register_extension_commands`).
//! It keeps its document data in `Session::extensions` under its [`UiExtension::id`].
//!
//! Every hook runs on the UI thread and must return quickly: background work (network, processes,
//! files) belongs on a thread of the extension's own, polled in [`UiExtension::logic`]. A hook that
//! panics stops that extension for the rest of the run; the app and the other extensions go on.

use crate::SoundApp;
use soundcraft_model::{Session, TrackId};
use soundcraft_time::{Range, Samples};
use std::panic::{AssertUnwindSafe, catch_unwind};

/// A track's lane on screen, for an extension that draws in it.
pub struct Lane<'a> {
    pub track: TrackId,
    /// The lane: the track's main row on the timeline (alternate playlist lanes are below it).
    pub rect: egui::Rect,
    /// The session time on screen.
    pub view: Range,
    session: &'a Session,
    timeline: egui::Rect,
}

impl Lane<'_> {
    /// The screen x of a session position.
    pub fn x_of(&self, at: Samples) -> f32 {
        crate::edit_window::x_of(self.session, self.timeline, at)
    }

    /// The session position at a screen x.
    pub fn sample_at(&self, x: f32) -> Samples {
        crate::edit_window::sample_at(self.session, self.timeline, x)
    }

    /// The session as drawn this frame.
    pub fn session(&self) -> &Session {
        self.session
    }
}

/// An add-in's part in the UI. Every hook has a default that does nothing, so an extension
/// implements only what it needs and a hook added later breaks none.
pub trait UiExtension {
    /// A short, stable id such as `"plenio"`: the key of the extension's entry in
    /// `Session::extensions` and the name logs use.
    fn id(&self) -> &'static str;

    /// Per-frame logic, once per host frame and also on ticks while the window is hidden: poll
    /// background work and apply its results through commands.
    fn logic(&mut self, _app: &mut SoundApp, _ctx: &egui::Context) {}

    /// Menus of its own in the window's menu bar, after SoundCraft's (`ui.menu_button(…)`).
    fn menu_bar(&mut self, _app: &mut SoundApp, _ui: &mut egui::Ui) {}

    /// Windows and other floating UI, after SoundCraft's own windows.
    fn windows(&mut self, _app: &mut SoundApp, _ctx: &egui::Context) {}

    /// Drawing over a track's header in the Edit window, after SoundCraft's own controls.
    fn track_header(&mut self, _app: &mut SoundApp, _ui: &mut egui::Ui, _track: TrackId, _head: egui::Rect) {}

    /// Drawing in a track's lane in the Edit window, over its clips and under the selection.
    fn lane(&mut self, _app: &mut SoundApp, _painter: &egui::Painter, _lane: &Lane<'_>) {}

    /// Items at the end of a track's context menu.
    fn track_context_menu(&mut self, _app: &mut SoundApp, _ui: &mut egui::Ui, _track: TrackId) {}
}

/// An installed extension, and whether it stopped after a panic.
pub(crate) struct Installed {
    extension: Box<dyn UiExtension>,
    stopped: bool,
}

impl SoundApp {
    /// Install an extension; its hooks run from the next frame on, in the order installed.
    pub fn add_extension(&mut self, extension: Box<dyn UiExtension>) {
        log::info!("extension {} installed", extension.id());
        self.extensions.push(Installed { extension, stopped: false });
    }

    /// The installed extensions' ids, with whether each still runs (`false` after a panic).
    pub fn extensions(&self) -> Vec<(&'static str, bool)> {
        self.extensions.iter().map(|e| (e.extension.id(), !e.stopped)).collect()
    }
}

/// Run `hook` on every running extension. The extensions are taken out of the app while their
/// hooks run, so a hook gets the whole app; one installed meanwhile is kept, after the others.
fn each(app: &mut SoundApp, hook: &str, mut run: impl FnMut(&mut dyn UiExtension, &mut SoundApp)) {
    if app.extensions.is_empty() {
        return;
    }
    let mut installed = std::mem::take(&mut app.extensions);
    for e in installed.iter_mut().filter(|e| !e.stopped) {
        let extension = e.extension.as_mut();
        if let Err(p) = catch_unwind(AssertUnwindSafe(|| run(extension, app))) {
            e.stopped = true;
            let why =
                p.downcast_ref::<&str>().map(ToString::to_string).or_else(|| p.downcast_ref::<String>().cloned()).unwrap_or_else(|| "panic".into());
            log::error!("extension {} stopped: its {hook} hook panicked: {why}", e.extension.id());
            app.engine.message(format!("The {} add-in stopped after an internal error; SoundCraft goes on without it.", e.extension.id()));
        }
    }
    installed.append(&mut app.extensions);
    app.extensions = installed;
}

pub(crate) fn logic(app: &mut SoundApp, ctx: &egui::Context) {
    each(app, "logic", |e, app| e.logic(app, ctx));
}

pub(crate) fn menu_bar(app: &mut SoundApp, ui: &mut egui::Ui) {
    each(app, "menu bar", |e, app| e.menu_bar(app, ui));
}

pub(crate) fn windows(app: &mut SoundApp, ctx: &egui::Context) {
    each(app, "windows", |e, app| e.windows(app, ctx));
}

pub(crate) fn track_header(app: &mut SoundApp, ui: &mut egui::Ui, track: TrackId, head: egui::Rect) {
    each(app, "track header", |e, app| e.track_header(app, ui, track, head));
}

pub(crate) fn lane(
    app: &mut SoundApp,
    painter: &egui::Painter,
    session: &Session,
    track: TrackId,
    rect: egui::Rect,
    timeline: egui::Rect,
    view: Range,
) {
    if app.extensions.is_empty() {
        return;
    }
    let lane = Lane { track, rect, view, session, timeline };
    each(app, "lane", |e, app| e.lane(app, painter, &lane));
}

pub(crate) fn track_context_menu(app: &mut SoundApp, ui: &mut egui::Ui, track: TrackId) {
    each(app, "track context menu", |e, app| e.track_context_menu(app, ui, track));
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::{Arc, Mutex};

    /// What the probe saw: the hooks that ran, the lanes it drew in.
    #[derive(Default)]
    struct Seen {
        hooks: Vec<&'static str>,
        lanes: Vec<TrackId>,
    }

    struct Probe {
        name: &'static str,
        seen: Arc<Mutex<Seen>>,
        /// The hook that panics, if any.
        panics_in: Option<&'static str>,
    }

    impl Probe {
        fn note(&self, hook: &'static str) {
            if self.panics_in == Some(hook) {
                panic!("probe panics in {hook}");
            }
            self.seen.lock().unwrap().hooks.push(hook);
        }
    }

    impl UiExtension for Probe {
        fn id(&self) -> &'static str {
            self.name
        }
        fn logic(&mut self, _: &mut SoundApp, _: &egui::Context) {
            self.note("logic");
        }
        fn menu_bar(&mut self, _: &mut SoundApp, ui: &mut egui::Ui) {
            self.note("menu_bar");
            ui.menu_button("Probe", |ui| ui.label("probe"));
        }
        fn windows(&mut self, _: &mut SoundApp, _: &egui::Context) {
            self.note("windows");
        }
        fn track_header(&mut self, _: &mut SoundApp, _: &mut egui::Ui, _: TrackId, _: egui::Rect) {
            self.note("track_header");
        }
        fn lane(&mut self, _: &mut SoundApp, _: &egui::Painter, lane: &Lane<'_>) {
            self.note("lane");
            // Screen x and session time convert both ways.
            let x = lane.rect.center().x;
            assert!((lane.x_of(lane.sample_at(x)) - x).abs() < 1.0);
            assert!(lane.session().track(lane.track).is_some());
            self.seen.lock().unwrap().lanes.push(lane.track);
        }
    }

    fn frames(ctx: &egui::Context, app: &mut SoundApp, n: usize) {
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
    fn an_extension_draws_its_menus_windows_headers_and_lanes() {
        let mut app = SoundApp::new(soundcraft_engine::demo::demo_engine(), None, crate::Services::default());
        let seen = Arc::new(Mutex::new(Seen::default()));
        app.add_extension(Box::new(Probe { name: "probe", seen: Arc::clone(&seen), panics_in: None }));
        let ctx = egui::Context::default();
        frames(&ctx, &mut app, 3);
        let seen = seen.lock().unwrap();
        for hook in ["logic", "menu_bar", "windows", "track_header", "lane"] {
            assert!(seen.hooks.contains(&hook), "{hook} never ran: {:?}", seen.hooks);
        }
        let first = app.engine.session().tracks.first().map(|t| t.id);
        assert!(first.is_some_and(|t| seen.lanes.contains(&t)), "the first track's lane was drawn");
        assert_eq!(app.extensions(), vec![("probe", true)]);
    }

    #[test]
    fn a_panicking_extension_stops_and_the_app_goes_on() {
        let mut app = SoundApp::new(soundcraft_engine::demo::demo_engine(), None, crate::Services::default());
        let crashy = Arc::new(Mutex::new(Seen::default()));
        let calm = Arc::new(Mutex::new(Seen::default()));
        app.add_extension(Box::new(Probe { name: "crashy", seen: Arc::clone(&crashy), panics_in: Some("windows") }));
        app.add_extension(Box::new(Probe { name: "calm", seen: Arc::clone(&calm), panics_in: None }));
        let ctx = egui::Context::default();
        frames(&ctx, &mut app, 3);
        assert_eq!(app.extensions(), vec![("crashy", false), ("calm", true)]);
        // Stopped after its first panic: later frames run none of its hooks, the other's go on.
        let ran = |seen: &Arc<Mutex<Seen>>| seen.lock().unwrap().hooks.len();
        let (crashy_before, calm_before) = (ran(&crashy), ran(&calm));
        frames(&ctx, &mut app, 2);
        assert_eq!(ran(&crashy), crashy_before);
        assert!(ran(&calm) > calm_before);
        assert!(app.engine.messages.iter().any(|m| m.contains("crashy add-in stopped")), "{:?}", app.engine.messages);
    }
}
