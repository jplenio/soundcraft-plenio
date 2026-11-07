//! The add-in's menu, its context menu entries and its small windows: activation, getting started,
//! the studio and its models, and about. The new-song dialog and the song inspector have modules of
//! their own.

mod inspector;
mod song_dialog;

#[cfg(test)]
pub use inspector::INSPECTOR_TITLE;
pub use song_dialog::NewSong;

use crate::{PlenioUi, say};
use serde_json::Value;
use soundcraft_model::{TrackId, TrackKind};
use soundcraft_plenio_backend::{Request, State};
use soundcraft_plenio_project::{Mode, Project};
use soundcraft_ui_egui::SoundApp;

/// The section tags YuE2 learned, as buttons in the lyrics editors.
pub const SECTION_TAGS: [&str; 8] = ["intro", "verse", "pre-chorus", "chorus", "bridge", "inst", "outro", "hook"];

/// The tutorial: making, covering and bringing in songs, step by step.
pub const TUTORIAL_URL: &str = "https://github.com/jplenio/soundcraft-plenio/blob/plenio-addin/addins/plenio/docs/TUTORIAL.md";
/// The add-in's home: its README, its releases and where to report a problem.
pub const HOME_URL: &str = "https://github.com/jplenio/soundcraft-plenio";

pub(crate) fn studio_line(ui: &PlenioUi) -> String {
    match &ui.state {
        State::Stopped => "Studio: stopped".into(),
        State::Starting(step) => format!("Studio: {step} …"),
        State::Ready { plenio, comfyui, .. } => format!("Studio: ready (Plenio {plenio}, ComfyUI {comfyui})"),
        State::Failed(why) => format!("Studio: {why}"),
    }
}

pub fn menu(ui_state: &mut PlenioUi, app: &mut SoundApp, ui: &mut egui::Ui) {
    if !ui_state.settings.activated {
        if ui.button("Activate Plenio Add-in…").clicked() {
            ui_state.show_activation = true;
            ui.close();
        }
    } else {
        if ui.button("New Song…").on_hover_text("A song from a style, an idea or your own lyrics").clicked() {
            ui_state.new_song = Some(NewSong::song(ui_state.settings.stems_right_away));
            ui.close();
        }
        let audio = selected_audio_track(app);
        let cover = ui.add_enabled(audio.is_some(), egui::Button::new("New Cover from Selected Track…"));
        let cover = cover
            .on_disabled_hover_text("Select the audio track of the recording first")
            .on_hover_text("A new version of the recording, in another style");
        if cover.clicked()
            && let Some(t) = audio
        {
            ui_state.new_song = Some(NewSong::cover(t, ui_state.settings.stems_right_away));
            ui.close();
        }
        if ui.button("Import Plenio Song…").on_hover_text("A song Plenio made (its FLAC or its .plenio.json), to edit and make again here").clicked()
        {
            let picked = app.services.pick_open.as_ref().and_then(|pick| pick("Plenio Song", &["flac", "json", "wav", "mp3"]));
            if let Some(path) = picked {
                ui_state.import_record(app, path);
            }
            ui.close();
        }
        ui.separator();
        if ui.button("Song Inspector").on_hover_text("Takes, lyrics, brief and seeds of the selected song").clicked() {
            ui_state.show_inspector = true;
            ui.close();
        }
        if ui
            .button("Open Plenio Player")
            .on_hover_text("Every song the studio made, with the lyrics as they are sung, the sheet music and the visuals")
            .clicked()
        {
            ui_state.open_player();
            ui.close();
        }
        ui.separator();
        if ui.button("Studio and Models…").on_hover_text("Start or stop the studio, choose ComfyUI, download models").clicked() {
            ui_state.show_studio = true;
            ui.close();
        }
        ui.label(egui::RichText::new(studio_line(ui_state)).small().weak());
        ui.separator();
        if ui.button("Deactivate Plenio Add-in").clicked() {
            ui_state.set_activated(app, false);
            ui.close();
        }
    }
    ui.separator();
    if ui.button("Getting Started").clicked() {
        ui_state.show_help = true;
        ui.close();
    }
    if ui.button("About the Plenio Add-in").clicked() {
        ui_state.show_about = true;
        ui.close();
    }
}

fn selected_audio_track(app: &SoundApp) -> Option<TrackId> {
    let s = app.engine.session();
    s.edit.selected_tracks.iter().copied().find(|t| s.track(*t).is_some_and(|tr| tr.kind == TrackKind::Audio && !tr.clips().is_empty()))
}

pub fn track_menu(ui_state: &mut PlenioUi, app: &mut SoundApp, ui: &mut egui::Ui, track: TrackId) {
    if !ui_state.settings.activated {
        return;
    }
    let project = Project::load(app.engine.session()).unwrap_or_default();
    ui.separator();
    if let Some((song, _)) = project.role_of(track) {
        let id = song.id;
        let take = song.active_take().map(|t| t.number);
        if ui.button("Plenio: Generate").clicked() {
            ui_state.generate(app, id, Mode::Auto);
            ui.close();
        }
        if ui.button("Plenio: Song Inspector").clicked() {
            ui_state.song = Some(id);
            ui_state.show_inspector = true;
            ui.close();
        }
        if let Some(take) = take
            && ui.add_enabled(ui_state.ready() && !ui_state.splitting.contains_key(&id), egui::Button::new("Plenio: Split Take into Stems")).clicked()
        {
            ui_state.split_stems(app, id, take);
            ui.close();
        }
    } else if app.engine.session().track(track).is_some_and(|t| t.kind == TrackKind::Audio && !t.clips().is_empty())
        && ui.button("Plenio: New Cover from this Track…").clicked()
    {
        ui_state.new_song = Some(NewSong::cover(track, ui_state.settings.stems_right_away));
        ui.close();
    }
}

pub fn show(ui_state: &mut PlenioUi, app: &mut SoundApp, ctx: &egui::Context) {
    if ui_state.show_activation {
        activation(ui_state, app, ctx);
    }
    if ui_state.show_help {
        help(ui_state, ctx);
    }
    if ui_state.show_about {
        about(ui_state, app, ctx);
    }
    if ui_state.show_studio {
        studio(ui_state, app, ctx);
    }
    if ui_state.new_song.is_some() {
        song_dialog::show(ui_state, app, ctx);
    }
    if ui_state.show_inspector {
        inspector::show(ui_state, app, ctx);
    }
}

fn activation(ui_state: &mut PlenioUi, app: &mut SoundApp, ctx: &egui::Context) {
    let mut open = true;
    let mut answer = None;
    egui::Window::new("Activate the Plenio Add-in").open(&mut open).pivot(egui::Align2::CENTER_CENTER).default_pos(ctx.content_rect().center()).collapsible(false).resizable(false).default_width(460.0).show(ctx, |ui| {
        ui.label("Plenio makes songs and covers with YuE2 right in your session: the lyrics, the score and every take are tracks you edit, mix and make again.");
        ui.add_space(6.0);
        ui.label(
            "It runs its own ComfyUI instance with Plenio inside: the ComfyUI on this computer and its models are used, your own ComfyUI setup stays as it is. \
             Missing models can be downloaded in Plenio › Studio and Models.",
        );
        ui.add_space(6.0);
        ui.label(egui::RichText::new("YuE2 and SheetSage2 are licensed CC BY-NC 4.0: what you make with them is for non-commercial use.").strong());
        ui.checkbox(&mut ui_state.settings.licences_accepted, "I accept the models' licences");
        ui.checkbox(&mut ui_state.settings.start_with_soundcraft, "Start the studio with SoundCraft");
        ui.add_space(8.0);
        ui.horizontal(|ui| {
            let activate = ui.add_enabled(ui_state.settings.licences_accepted, egui::Button::new("Activate"));
            if activate.on_disabled_hover_text("Accept the models' licences first").clicked() {
                answer = Some(true);
            }
            if ui.button("Cancel").clicked() {
                answer = Some(false);
            }
        });
    });
    if answer == Some(true) {
        ui_state.set_activated(app, true);
        // What happens next is in view: the studio starting and the models it finds.
        ui_state.show_studio = true;
    }
    ui_state.show_activation = open && answer.is_none();
}

/// The steps, in the app: what the menu entries do and in which order.
const STEPS: [(&str, &str); 6] = [
    ("Activate", "Plenio › Activate Plenio Add-in…: accept the models' licences. The studio starts; Studio and Models shows what is missing."),
    ("Make a song", "Plenio › New Song…: pick a style, say what it is about or write your own lyrics, then Make the Song."),
    ("Find it on its tracks", "The song's folder holds Lyrics, Song (each take a playlist) and the score as MIDI: Melody, Instrument Line, Chords."),
    ("Change and make again", "In the Song Inspector change words, notes or brief; Generate makes a new take of what changed."),
    ("Stems", "Split this take into stems: vocals, drums, bass, other and the rest, on tracks of their own (or tick it before the take comes)."),
    ("Covers and imports", "Select an audio track: New Cover from Selected Track…. Import Plenio Song… brings in a FLAC Plenio made."),
];

fn help(ui_state: &mut PlenioUi, ctx: &egui::Context) {
    let mut open = ui_state.show_help;
    egui::Window::new("Getting Started with Plenio")
        .open(&mut open)
        .pivot(egui::Align2::CENTER_CENTER)
        .default_pos(ctx.content_rect().center())
        .collapsible(false)
        .resizable(false)
        .default_width(520.0)
        .show(ctx, |ui| {
            egui::Grid::new("plenio_steps").num_columns(2).spacing([12.0, 8.0]).show(ui, |ui| {
                for (n, (title, what)) in STEPS.iter().enumerate() {
                    ui.label(egui::RichText::new(format!("{}. {title}", n + 1)).strong());
                    ui.add(egui::Label::new(*what).wrap());
                    ui.end_row();
                }
            });
            ui.add_space(8.0);
            ui.horizontal(|ui| {
                if ui.button("Open the Tutorial").on_hover_text(TUTORIAL_URL).clicked() {
                    ui_state.open_url = Some(TUTORIAL_URL.into());
                }
                if ui.button("Add-in Home Page").on_hover_text(HOME_URL).clicked() {
                    ui_state.open_url = Some(HOME_URL.into());
                }
            });
        });
    ui_state.show_help = open;
}

fn about(ui_state: &mut PlenioUi, app: &mut SoundApp, ctx: &egui::Context) {
    let mut open = ui_state.show_about;
    let songs = Project::load(app.engine.session()).map(|p| p.songs.len()).unwrap_or(0);
    egui::Window::new("About the Plenio Add-in")
        .open(&mut open)
        .pivot(egui::Align2::CENTER_CENTER)
        .default_pos(ctx.content_rect().center())
        .collapsible(false)
        .resizable(false)
        .default_width(420.0)
        .show(ctx, |ui| {
            ui.label(egui::RichText::new(format!("Plenio add-in {}", soundcraft_plenio_commands::VERSION)).strong());
            ui.label(
                "YuE2 Song, YuE2 Cover and the Plenio Player in SoundCraft, from the Plenio Music Production System by Johannes Plenio (Apache-2.0).",
            );
            ui.add_space(6.0);
            let state = if ui_state.settings.activated { "activated" } else { "not activated" };
            ui.label(format!("{state} · songs in this session: {songs}"));
            ui.label(studio_line(ui_state));
            ui.add_space(6.0);
            ui.label(
                egui::RichText::new("The add-in's code: MIT OR Apache-2.0. Songs made with YuE2: CC BY-NC 4.0 (non-commercial).").small().weak(),
            );
            if ui.link(HOME_URL).clicked() {
                ui_state.open_url = Some(HOME_URL.into());
            }
        });
    ui_state.show_about = open;
}

fn studio(ui_state: &mut PlenioUi, app: &mut SoundApp, ctx: &egui::Context) {
    let mut open = ui_state.show_studio;
    egui::Window::new("Plenio Studio and Models")
        .open(&mut open)
        .pivot(egui::Align2::CENTER_TOP)
        .default_pos(ctx.content_rect().center_top() + egui::vec2(0.0, 80.0))
        .default_width(600.0)
        .show(ctx, |ui| {
            ui.horizontal(|ui| {
                if matches!(ui_state.state, State::Starting(_)) {
                    ui.add(egui::Spinner::new());
                }
                let line = egui::RichText::new(studio_line(ui_state));
                ui.label(if matches!(ui_state.state, State::Failed(_)) { line.color(ui.visuals().error_fg_color) } else { line });
            });
            ui.horizontal(|ui| {
                let starting = matches!(ui_state.state, State::Starting(_));
                if ui.add_enabled(!ui_state.ready() && !starting, egui::Button::new("Start Studio")).clicked() {
                    ui_state.start_studio();
                }
                if ui.add_enabled(ui_state.ready(), egui::Button::new("Stop Studio")).on_hover_text("Frees the graphics card's memory").clicked() {
                    ui_state.studio.send(Request::Stop);
                }
                if ui.add_enabled(ui_state.ready(), egui::Button::new("Check Models")).clicked() {
                    ui_state.studio.send(Request::Get { tag: "models".into(), path: "/scp/v1/models".into() });
                }
            });
            ui.horizontal(|ui| {
                ui.label("ComfyUI folder:");
                let saved = ui_state.settings.comfyui.as_ref().map(|p| p.to_string_lossy().into_owned()).unwrap_or_default();
                let text = ui_state.comfyui_edit.get_or_insert_with(|| saved.clone());
                let edit = ui.add(egui::TextEdit::singleline(text).hint_text("found by itself (as Plenio last started it)").desired_width(300.0));
                let mut chosen = edit.lost_focus().then(|| text.clone());
                if !edit.has_focus() && !edit.lost_focus() {
                    ui_state.comfyui_edit = None;
                }
                if ui.button("Browse…").clicked() {
                    let start = ui_state.settings.comfyui.clone().unwrap_or_default();
                    if let Some(folder) = app.services.pick_folder.as_ref().and_then(|pick| pick(&start)) {
                        chosen = Some(folder.to_string_lossy().into_owned());
                    }
                }
                if let Some(text) = chosen {
                    ui_state.comfyui_edit = None;
                    let path = Some(text.trim()).filter(|t| !t.is_empty()).map(std::path::PathBuf::from);
                    if path != ui_state.settings.comfyui {
                        ui_state.settings.comfyui = path;
                        ui_state.save_settings(app);
                        say(app, "Plenio: the ComfyUI folder is kept; it is used the next time the studio starts.");
                    }
                }
            });
            if ui.checkbox(&mut ui_state.settings.start_with_soundcraft, "Start the studio with SoundCraft").changed() {
                ui_state.save_settings(app);
            }
            ui.separator();
            models(ui_state, ui);
        });
    ui_state.show_studio = open;
}

/// A model file as the studio lists it, and whether it may be downloaded now.
struct ModelRow {
    role: String,
    file: String,
    licence: String,
    status: String,
    bytes: u64,
    url: String,
    target: String,
    allowed: bool,
}

fn model_rows(ui_state: &PlenioUi, models: &Value) -> Vec<ModelRow> {
    models
        .get("models")
        .and_then(Value::as_array)
        .into_iter()
        .flatten()
        .map(|m| {
            let s = |k: &str| m.get(k).and_then(Value::as_str).unwrap_or_default().to_string();
            ModelRow {
                role: s("role"),
                file: s("file"),
                licence: s("licence"),
                status: s("status"),
                bytes: m.get("bytes").and_then(Value::as_u64).unwrap_or(0),
                url: s("url"),
                target: s("target"),
                allowed: !m.get("non_commercial").and_then(Value::as_bool).unwrap_or(false) || ui_state.settings.licences_accepted,
            }
        })
        .collect()
}

/// The start of a long description: up to the first of `stops`, at most `max` characters (an ellipsis
/// when cut). The catalogue's descriptions of the models run to a paragraph; the table shows a line.
pub fn short(text: &str, stops: &[&str], max: usize) -> String {
    let end = stops.iter().filter_map(|s| text.find(s)).min().unwrap_or(text.len());
    let head = text[..end].trim();
    if head.chars().count() <= max {
        head.to_string()
    } else {
        format!("{}…", head.chars().take(max.saturating_sub(1)).collect::<String>().trim_end())
    }
}

fn gigabytes(bytes: u64) -> String {
    format!("{:.1} GB", bytes as f64 / 1e9)
}

fn models(ui_state: &mut PlenioUi, ui: &mut egui::Ui) {
    let Some(models) = ui_state.models.clone() else {
        ui.label(egui::RichText::new("Start the studio to see which models are installed.").weak());
        return;
    };
    if let Some(templates) = models.get("templates").and_then(Value::as_object) {
        // Only the templates the add-in makes songs with (the wrapper also knows Plenio's others).
        for (id, t) in templates.iter().filter(|(id, _)| crate::TEMPLATES.contains(&id.as_str())) {
            let ready = t.get("ready").and_then(Value::as_bool).unwrap_or(false);
            let missing = t.get("missing").and_then(Value::as_array).map_or(0, Vec::len);
            let name = if id == "yue2-song" {
                "New songs (YuE2 · Song)"
            } else if id == "yue2-cover" {
                "Covers (YuE2 · Cover)"
            } else {
                id.as_str()
            };
            let (text, warn) = if ready {
                ("ready".to_string(), false)
            } else if missing == 0 {
                ("ready (a file differs in size)".into(), false)
            } else {
                (format!("{missing} model file(s) missing"), true)
            };
            let line = egui::RichText::new(format!("{name}: {text}"));
            ui.label(if warn { line.color(ui.visuals().warn_fg_color) } else { line });
        }
    }
    let rows = model_rows(ui_state, &models);
    let missing: Vec<&ModelRow> = rows.iter().filter(|r| r.status == "missing" && !ui_state.downloads.contains_key(&r.file)).collect();
    let mut wanted: Vec<&ModelRow> = Vec::new();
    if !missing.is_empty() {
        let total: u64 = missing.iter().map(|r| r.bytes).sum();
        let allowed = missing.iter().all(|r| r.allowed);
        let files = if missing.len() == 1 { "1 file".to_string() } else { format!("{} files", missing.len()) };
        let button = ui.add_enabled(allowed, egui::Button::new(format!("Download All Missing ({files}, {})", gigabytes(total))));
        if button.on_disabled_hover_text("Accept the models' licences first (Plenio › Activate)").clicked() {
            wanted.extend(missing.iter().copied());
        }
    }
    egui::ScrollArea::vertical().max_height(280.0).show(ui, |ui| {
        egui::Grid::new("plenio_models").striped(true).show(ui, |ui| {
            for row in &rows {
                ui.label(short(&row.role, &[":", " ("], 44)).on_hover_text(format!("{}\n{}", row.role, row.file));
                ui.label(gigabytes(row.bytes));
                ui.label(short(&row.licence, &[";"], 28)).on_hover_text(&row.licence);
                if let Some((done, total)) = ui_state.downloads.get(&row.file) {
                    let f = if *total > 0 { *done as f32 / *total as f32 } else { 0.0 };
                    ui.add(egui::ProgressBar::new(f).desired_width(120.0).show_percentage());
                } else if row.status == "missing" {
                    if ui.add_enabled(row.allowed, egui::Button::new("Download")).clicked() {
                        wanted.push(row);
                    }
                } else {
                    ui.label(&row.status);
                }
                ui.end_row();
            }
        });
    });
    let files: Vec<(String, std::path::PathBuf, u64)> = wanted
        .iter()
        .filter(|r| !r.url.is_empty() && !r.target.is_empty())
        .map(|r| (r.url.clone(), std::path::PathBuf::from(&r.target), r.bytes))
        .collect();
    if !files.is_empty() {
        for (_, target, bytes) in &files {
            let name = target.file_name().map(|n| n.to_string_lossy().into_owned()).unwrap_or_default();
            ui_state.downloads.insert(name, (0, *bytes));
        }
        ui_state.studio.send(Request::DownloadModels { files });
    }
}

/// The part of a cover's recording the edit selection covers, in seconds into its file, when there
/// is a selection on the recording's track.
pub fn excerpt(app: &SoundApp, track: TrackId) -> Option<(f64, f64)> {
    let s = app.engine.session();
    let sel = s.edit.selection;
    if sel.is_empty() || !s.edit.selected_tracks.contains(&track) {
        return None;
    }
    let clip = s.track(track)?.clips().first()?.clone();
    let soundcraft_model::ClipContent::Audio { offset, .. } = clip.content else { return None };
    let into_file = sel.start.saturating_sub(clip.start).saturating_add(offset).max(0);
    let rate = f64::from(s.sample_rate.hz());
    let start = into_file as f64 / rate;
    let duration = (sel.end.saturating_sub(sel.start)) as f64 / rate;
    (duration >= 1.0 && start.is_finite()).then_some(((start * 100.0).round() / 100.0, (duration * 100.0).round() / 100.0))
}

/// The choices of a field, from its `GET /templates/{id}` description.
pub fn choices(field: Option<&Value>) -> Vec<String> {
    field
        .and_then(|f| f.get("choices"))
        .and_then(Value::as_array)
        .map(|a| a.iter().filter_map(|c| c.as_str().map(str::to_string)).collect())
        .unwrap_or_default()
}

/// Tidy minutes and seconds: `1:05`.
pub fn clock(seconds: f64) -> String {
    let s = seconds.max(0.0).round() as u64;
    format!("{}:{:02}", s / 60, s % 60)
}
