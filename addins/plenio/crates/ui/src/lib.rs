//! The Plenio add-in in SoundCraft's UI: the Plenio menu, the studio (its own ComfyUI with Plenio),
//! new songs and covers, the song inspector (brief, lyrics, seeds, takes), the song's lane and
//! header, and every take landing on the song's tracks.
//!
//! The app installs it with two calls: [`register_commands`] before the first command runs, and
//! `SoundApp::add_extension(soundcraft_plenio_ui::extension(..))`. Everything the UI changes in the
//! document goes through the add-in's commands (`plenio.*`), one undo step each.
#![deny(clippy::unwrap_used, clippy::expect_used, clippy::panic, clippy::unimplemented, clippy::todo, clippy::unreachable)]

mod draw;
mod fields;
mod generate;
mod windows;

use serde_json::{Value, json};
use soundcraft_plenio_backend::song::Job;
use soundcraft_plenio_backend::{Event, Request, Settings, State, Studio};
use soundcraft_plenio_project::{Mode, Project, What};
use soundcraft_ui_egui::SoundApp;
use soundcraft_ui_egui::extension::{Lane, UiExtension};
use std::collections::BTreeMap;
use std::path::PathBuf;

/// The Song API's templates the add-in makes songs with (no MiniMax).
pub(crate) const TEMPLATES: [&str; 2] = ["yue2-song", "yue2-cover"];
/// Where the studio lists its style templates.
const BRIEFS_PATH: &str = "/plenio/api/v1/briefs?kind=song";

/// Tell the owner something: the status line shows it, the log keeps it.
pub(crate) fn say(app: &mut SoundApp, message: impl Into<String>) {
    let message = message.into();
    app.engine.message(message.clone());
    app.ui.status = message;
}

/// Run one of the add-in's commands; when it fails, the owner reads why in the status line.
pub(crate) fn run_or_say(app: &mut SoundApp, id: &str, params: Value) -> Option<Value> {
    match app.run(id, params) {
        Ok(v) => Some(v),
        Err(e) => {
            say(app, format!("Plenio: {e}"));
            None
        }
    }
}

/// Register the add-in's commands; call it once, before the first command runs.
pub fn register_commands() {
    soundcraft_plenio_commands::register();
}

/// The add-in's UI part. `config_dir` is SoundCraft's settings folder, where the add-in keeps its
/// settings and its studio; without one (test runs, a profile without preferences) a folder in the
/// temporary directory is used and nothing is saved.
pub fn extension(config_dir: Option<PathBuf>) -> Box<dyn UiExtension> {
    Box::new(PlenioUi::new(config_dir))
}

/// Whether the session open now still holds the song `(id, uid)` that asked for some work: a take,
/// stems or notes that arrive after their session was closed (or their song forgotten) land nowhere
/// else, also not on another song with the same id.
pub(crate) fn song_here(app: &SoundApp, song: u64, uid: u64) -> bool {
    Project::load(app.engine.session()).ok().and_then(|p| p.song(song).map(|s| s.is(song, uid))).unwrap_or(false)
}

/// The uid of a song of the session open now (0 when there is none).
pub(crate) fn uid_of(app: &SoundApp, song: u64) -> u64 {
    Project::load(app.engine.session()).ok().and_then(|p| p.song(song).map(|s| s.uid)).unwrap_or(0)
}

/// A take being made.
pub(crate) struct Pending {
    pub song: u64,
    /// The song's uid when it was asked for ([`song_here`]).
    pub uid: u64,
    pub title: String,
    pub what: What,
    pub fields: BTreeMap<String, Value>,
    pub job: Option<Job>,
}

pub(crate) struct PlenioUi {
    pub config_dir: Option<PathBuf>,
    pub settings: Settings,
    pub studio: Studio,
    pub state: State,
    /// `GET /templates/{id}` answers, by template id.
    pub templates: BTreeMap<String, Value>,
    /// `GET /briefs`: the style templates, as answered (kept for the cache) and as read.
    pub briefs: Option<Value>,
    pub styles: fields::Styles,
    /// `GET /scp/v1/models`.
    pub models: Option<Value>,
    pub downloads: BTreeMap<String, (u64, u64)>,
    pub jobs: BTreeMap<u64, Pending>,
    pub next_tag: u64,
    /// Takes asked for before the studio was ready: (song, its uid, mode).
    pub waiting: Vec<(u64, u64, Mode)>,
    /// Covers whose recording is uploading: upload tag → (song, its uid).
    pub uploads: BTreeMap<u64, (u64, u64)>,
    /// Plenio songs being brought in: tag → (the file chosen, what belongs to the song).
    pub imports: BTreeMap<u64, (PathBuf, soundcraft_plenio_backend::release::SongFiles)>,
    /// The songs of `imports` waiting for the studio: the notes and the song's fields come from it.
    pub waiting_imports: Vec<u64>,
    /// The player's address to open in the browser on the next frame.
    pub open_url: Option<String>,
    /// Songs being split into stems: song → its uid.
    pub splitting: BTreeMap<u64, u64>,
    /// Notes of the owner being read into a song's score: song → its uid.
    pub reading_notes: BTreeMap<u64, u64>,
    /// Takes waiting for their score's MIDI file or their bars: tag → (`plenio.take.add` parameters,
    /// the take's folder, the song's uid).
    pub held: BTreeMap<u64, (Value, PathBuf, u64)>,
    /// The song the inspector shows.
    pub song: Option<u64>,
    pub show_activation: bool,
    pub show_about: bool,
    pub show_help: bool,
    pub show_inspector: bool,
    pub show_studio: bool,
    /// The ComfyUI folder being typed in the studio window.
    pub comfyui_edit: Option<String>,
    pub new_song: Option<windows::NewSong>,
    /// The lyrics being edited: song, the text it started from, the text.
    pub lyrics_edit: Option<(u64, String, String)>,
    /// Plenio's check of the lyrics: song, answer.
    pub lyrics_check: Option<(u64, Result<Value, String>)>,
    /// Start the studio when activated or asked for a take (off in tests: they never start ComfyUI).
    pub auto_start: bool,
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
        // The studio's last description of its templates and styles: the dialogs are complete
        // before it is ready again.
        let cache = config_dir.as_deref().and_then(soundcraft_plenio_backend::settings::load_cache).unwrap_or(Value::Null);
        let templates: BTreeMap<String, Value> = TEMPLATES
            .iter()
            .filter_map(|t| cache.get("templates").and_then(|m| m.get(*t)).filter(|v| v.is_object()).map(|v| (t.to_string(), v.clone())))
            .collect();
        let briefs = cache.get("briefs").filter(|b| b.is_object()).cloned();
        let styles = briefs.as_ref().map(fields::Styles::parse).unwrap_or_default();
        let ui = PlenioUi {
            config_dir,
            settings,
            studio: Studio::spawn(),
            state: State::Stopped,
            templates,
            briefs,
            styles,
            models: None,
            downloads: BTreeMap::new(),
            jobs: BTreeMap::new(),
            next_tag: 1,
            waiting: Vec::new(),
            uploads: BTreeMap::new(),
            held: BTreeMap::new(),
            splitting: BTreeMap::new(),
            reading_notes: BTreeMap::new(),
            open_url: None,
            imports: BTreeMap::new(),
            waiting_imports: Vec::new(),
            song: None,
            show_activation: false,
            show_about: false,
            show_help: false,
            show_inspector: false,
            show_studio: false,
            comfyui_edit: None,
            new_song: None,
            lyrics_edit: None,
            lyrics_check: None,
            auto_start: true,
        };
        if ui.settings.activated && ui.settings.start_with_soundcraft {
            ui.start_studio();
        }
        ui
    }

    /// The add-in's folder for its studio: SoundCraft's settings folder, or a temporary one.
    pub fn studio_root(&self) -> PathBuf {
        self.config_dir.clone().unwrap_or_else(|| std::env::temp_dir().join("soundcraft-plenio"))
    }

    pub fn start_studio(&self) {
        if !self.auto_start {
            return;
        }
        self.studio.send(Request::Start { config_dir: self.studio_root(), comfyui: self.settings.comfyui.clone() });
    }

    pub fn save_settings(&self, app: &mut SoundApp) {
        if let Some(dir) = &self.config_dir
            && let Err(e) = self.settings.save(dir)
        {
            log::warn!("{e}");
            say(app, format!("The Plenio settings could not be saved: {e}"));
        }
    }

    /// Turn the add-in on or off and keep the choice.
    pub fn set_activated(&mut self, app: &mut SoundApp, on: bool) {
        self.settings.activated = on;
        soundcraft_plenio_commands::set_activated(on);
        self.save_settings(app);
        if on {
            self.start_studio();
            say(app, "Plenio add-in activated: its studio is starting.");
        } else {
            self.studio.send(Request::Stop);
            say(app, "Plenio add-in deactivated.");
        }
    }

    pub fn ready(&self) -> bool {
        matches!(self.state, State::Ready { .. })
    }

    pub fn tag(&mut self) -> u64 {
        let t = self.next_tag;
        self.next_tag = self.next_tag.wrapping_add(1).max(1);
        t
    }

    /// A field of a template, from its `GET /templates/{id}` answer.
    pub fn field(&self, template: &str, id: &str) -> Option<&Value> {
        self.templates.get(template)?.get("fields")?.as_array()?.iter().find(|f| f.get("id").and_then(Value::as_str) == Some(id))
    }

    /// Keep the studio's description of its templates and styles for the next start.
    fn save_cache(&self) {
        let Some(dir) = &self.config_dir else { return };
        let cache = json!({"templates": self.templates, "briefs": self.briefs});
        if let Err(e) = soundcraft_plenio_backend::settings::save_cache(dir, &cache) {
            log::warn!("{e}");
        }
    }

    fn handle(&mut self, app: &mut SoundApp, event: Event) {
        match event {
            Event::State(state) => {
                if let State::Ready { .. } = &state {
                    for t in TEMPLATES {
                        self.studio.send(Request::Get { tag: format!("template:{t}"), path: format!("/plenio/api/v1/templates/{t}") });
                    }
                    self.studio.send(Request::Get { tag: "briefs".into(), path: BRIEFS_PATH.into() });
                    self.studio.send(Request::Get { tag: "models".into(), path: "/scp/v1/models".into() });
                }
                if let State::Failed(why) = &state {
                    say(app, format!("Plenio studio: {why}"));
                }
                self.state = state;
                if self.ready() {
                    for (song, uid, mode) in std::mem::take(&mut self.waiting) {
                        if song_here(app, song, uid) {
                            self.generate(app, song, mode);
                        }
                    }
                    for tag in std::mem::take(&mut self.waiting_imports) {
                        self.ask_from_record(tag);
                    }
                } else if matches!(self.state, State::Failed(_) | State::Stopped) {
                    for tag in std::mem::take(&mut self.waiting_imports) {
                        self.imported(app, tag, Err("the studio is not running".into()));
                    }
                }
            }
            Event::Answer { tag, result } => self.answer(app, &tag, result),
            Event::Job { tag, job } => {
                if let Some(p) = self.jobs.get_mut(&tag) {
                    p.job = Some(job);
                }
            }
            Event::Delivered { tag, delivery } => self.deliver(app, tag, *delivery),
            Event::Uploaded { tag, result } => self.uploaded(app, tag, result),
            Event::Player(result) => match result {
                Ok(url) => {
                    say(app, format!("Plenio Player: {url}"));
                    self.open_url = Some(url);
                }
                Err(e) => say(app, format!("Plenio Player: {e}")),
            },
            Event::ModelProgress { file, done, total } => {
                self.downloads.insert(file, (done, total));
            }
            Event::ModelDone { file, result } => {
                self.downloads.remove(&file);
                match result {
                    Ok(()) => say(app, format!("Plenio: {file} downloaded.")),
                    Err(e) => say(app, format!("Plenio: {file} not downloaded: {e}")),
                }
                self.studio.send(Request::Get { tag: "models".into(), path: "/scp/v1/models".into() });
            }
            Event::Failed { tag, message } => {
                let what = tag.and_then(|t| self.jobs.remove(&t)).map(|p| p.title);
                let upload = tag
                    .and_then(|t| self.uploads.remove(&t))
                    .and_then(|(s, _)| Project::load(app.engine.session()).ok()?.song(s).map(|s| s.title.clone()));
                let title = what.or(upload);
                say(
                    app,
                    match title {
                        Some(t) => format!("Plenio: no take of {t}: {message}"),
                        None => format!("Plenio: {message}"),
                    },
                );
            }
        }
    }

    fn answer(&mut self, app: &mut SoundApp, tag: &str, result: Result<Value, String>) {
        if let Some(t) = tag.strip_prefix("from-record:").and_then(|t| t.parse().ok()) {
            self.imported(app, t, result);
        } else if let Some((song, take)) = tag.strip_prefix("stems:").and_then(|r| r.split_once(':')) {
            if let (Ok(song), Ok(take)) = (song.parse(), take.parse()) {
                self.stems_done(app, song, take, result);
            }
        } else if let Some(t) = tag.strip_prefix("midi:").and_then(|t| t.parse().ok()) {
            self.score_midi(app, t, result);
        } else if let Some(t) = tag.strip_prefix("beats:").and_then(|t| t.parse().ok()) {
            self.beats_found(app, t, result);
        } else if let Some((song, mode)) = tag.strip_prefix("score-import:").and_then(|r| r.split_once(':')) {
            if let Ok(song) = song.parse() {
                self.score_imported(app, song, generate::mode_from(mode), result);
            }
        } else if let Some(template) = tag.strip_prefix("template:") {
            match result {
                Ok(v) if v.is_object() => {
                    self.templates.insert(template.to_string(), v);
                    self.save_cache();
                }
                Ok(_) => log::warn!("Plenio: template {template}: not a description"),
                Err(e) => log::warn!("Plenio: template {template}: {e}"),
            }
        } else if tag == "briefs" {
            match result {
                Ok(v) if v.is_object() => {
                    self.styles = fields::Styles::parse(&v);
                    self.briefs = Some(v);
                    self.save_cache();
                }
                Ok(_) => log::warn!("Plenio: the styles are not a list"),
                Err(e) => log::warn!("Plenio: the styles: {e}"),
            }
        } else if tag == "models" {
            self.models = result.ok();
        } else if let Some(song) = tag.strip_prefix("lyrics-check:").and_then(|s| s.parse().ok()) {
            self.lyrics_check = Some((song, result));
        }
    }

    /// Select the song of a selected track for the inspector.
    fn follow_selection(&mut self, app: &SoundApp) {
        let s = app.engine.session();
        let Ok(project) = Project::load(s) else { return };
        if let Some(song) = s.edit.selected_tracks.iter().find_map(|t| project.role_of(*t).map(|(song, _)| song.id)) {
            self.song = Some(song);
        }
        if self.song.is_some_and(|id| project.song(id).is_none()) {
            self.song = project.songs.first().map(|s| s.id);
        }
    }
}

impl UiExtension for PlenioUi {
    fn id(&self) -> &'static str {
        "plenio"
    }

    fn logic(&mut self, app: &mut SoundApp, ctx: &egui::Context) {
        for event in self.studio.poll() {
            self.handle(app, event);
        }
        self.follow_selection(app);
        if !self.jobs.is_empty() || matches!(self.state, State::Starting(_)) || !self.downloads.is_empty() {
            ctx.request_repaint_after(std::time::Duration::from_millis(500));
        }
    }

    fn menu_bar(&mut self, app: &mut SoundApp, ui: &mut egui::Ui) {
        ui.menu_button("Plenio", |ui| windows::menu(self, app, ui));
    }

    fn windows(&mut self, app: &mut SoundApp, ctx: &egui::Context) {
        if let Some(url) = self.open_url.take() {
            ctx.open_url(egui::OpenUrl::new_tab(url));
        }
        windows::show(self, app, ctx);
    }

    fn track_header(&mut self, app: &mut SoundApp, ui: &mut egui::Ui, track: soundcraft_model::TrackId, head: egui::Rect) {
        draw::header(self, app, ui, track, head);
    }

    fn lane(&mut self, app: &mut SoundApp, painter: &egui::Painter, lane: &Lane<'_>) {
        draw::lane(self, app, painter, lane);
    }

    fn track_context_menu(&mut self, app: &mut SoundApp, ui: &mut egui::Ui, track: soundcraft_model::TrackId) {
        windows::track_menu(self, app, ui, track);
    }
}

#[cfg(test)]
mod tests;
