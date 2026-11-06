//! The add-in's menu, context menu and windows: activation, studio, new song or cover, the song
//! inspector (takes, brief, lyrics, seeds) and about.

use crate::{PlenioUi, say};
use serde_json::{Value, json};
use soundcraft_model::{TrackId, TrackKind};
use soundcraft_plenio_backend::{Request, State};
use soundcraft_plenio_project::{DocState, Mode, Project, Song, SongKind};
use soundcraft_ui_egui::SoundApp;

/// The section tags YuE2 learned, as buttons in the lyrics editor.
pub const SECTION_TAGS: [&str; 8] = ["intro", "verse", "pre-chorus", "chorus", "bridge", "inst", "outro", "hook"];

/// The new-song dialog.
pub struct NewSong {
    pub kind: SongKind,
    pub template: String,
    pub idea: String,
    pub vocals: String,
    pub length: String,
    pub language: String,
    pub own_lyrics: bool,
    pub lyrics: String,
    pub source: Option<TrackId>,
    pub filter: String,
}

impl NewSong {
    fn song() -> Self {
        NewSong {
            kind: SongKind::Song,
            template: "pop/singer-songwriter-acoustic-vocal".into(),
            idea: String::new(),
            vocals: "sung".into(),
            length: "short (about 1:30)".into(),
            language: "English".into(),
            own_lyrics: false,
            lyrics: String::new(),
            source: None,
            filter: String::new(),
        }
    }
    fn cover(source: TrackId) -> Self {
        NewSong { kind: SongKind::Cover, template: String::new(), vocals: "original lyrics".into(), source: Some(source), ..Self::song() }
    }
}

fn studio_line(ui: &PlenioUi) -> String {
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
        if ui.button("New Song…").clicked() {
            ui_state.new_song = Some(NewSong::song());
            ui.close();
        }
        let audio = selected_audio_track(app);
        let cover = ui.add_enabled(audio.is_some(), egui::Button::new("New Cover from Selected Track…"));
        let cover = cover.on_disabled_hover_text("Select the audio track of the recording first");
        if cover.clicked()
            && let Some(t) = audio
        {
            ui_state.new_song = Some(NewSong::cover(t));
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
        if ui.button("Song Inspector").clicked() {
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
        if ui.button("Studio and Models…").clicked() {
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
        if ui.button("Plenio: Generate").clicked() {
            ui_state.generate(app, id, Mode::Auto);
            ui.close();
        }
        if ui.button("Plenio: Song Inspector").clicked() {
            ui_state.song = Some(id);
            ui_state.show_inspector = true;
            ui.close();
        }
    } else if app.engine.session().track(track).is_some_and(|t| t.kind == TrackKind::Audio && !t.clips().is_empty())
        && ui.button("Plenio: New Cover from this Track…").clicked()
    {
        ui_state.new_song = Some(NewSong::cover(track));
        ui.close();
    }
}

pub fn show(ui_state: &mut PlenioUi, app: &mut SoundApp, ctx: &egui::Context) {
    if ui_state.show_activation {
        activation(ui_state, app, ctx);
    }
    if ui_state.show_about {
        about(ui_state, app, ctx);
    }
    if ui_state.show_studio {
        studio(ui_state, app, ctx);
    }
    if ui_state.new_song.is_some() {
        new_song(ui_state, app, ctx);
    }
    if ui_state.show_inspector {
        inspector(ui_state, app, ctx);
    }
}

fn activation(ui_state: &mut PlenioUi, app: &mut SoundApp, ctx: &egui::Context) {
    let mut open = true;
    let mut answer = None;
    egui::Window::new("Activate the Plenio Add-in").open(&mut open).collapsible(false).resizable(false).default_width(460.0).show(ctx, |ui| {
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
            if ui.add_enabled(ui_state.settings.licences_accepted, egui::Button::new("Activate")).clicked() {
                answer = Some(true);
            }
            if ui.button("Cancel").clicked() {
                answer = Some(false);
            }
        });
    });
    if answer == Some(true) {
        ui_state.set_activated(app, true);
    }
    ui_state.show_activation = open && answer.is_none();
}

fn about(ui_state: &mut PlenioUi, app: &mut SoundApp, ctx: &egui::Context) {
    let mut open = ui_state.show_about;
    let songs = Project::load(app.engine.session()).map(|p| p.songs.len()).unwrap_or(0);
    egui::Window::new("About the Plenio Add-in").open(&mut open).collapsible(false).resizable(false).default_width(400.0).show(ctx, |ui| {
        ui.label(format!("Plenio add-in {}", soundcraft_plenio_commands::VERSION));
        ui.label(
            "YuE2 Song, YuE2 Cover and the Plenio Player in SoundCraft, from the Plenio Music Production System by Johannes Plenio (Apache-2.0).",
        );
        ui.add_space(6.0);
        let state = if ui_state.settings.activated { "activated" } else { "not activated" };
        ui.label(format!("{state} · songs in this session: {songs}"));
        ui.label(studio_line(ui_state));
    });
    ui_state.show_about = open;
}

fn studio(ui_state: &mut PlenioUi, app: &mut SoundApp, ctx: &egui::Context) {
    let mut open = ui_state.show_studio;
    egui::Window::new("Plenio Studio and Models").open(&mut open).default_width(560.0).show(ctx, |ui| {
        ui.label(studio_line(ui_state));
        ui.horizontal(|ui| {
            if ui.add_enabled(!ui_state.ready(), egui::Button::new("Start Studio")).clicked() {
                ui_state.start_studio();
            }
            if ui.add_enabled(ui_state.ready(), egui::Button::new("Stop Studio")).on_hover_text("Frees the graphics card's memory").clicked() {
                ui_state.studio.send(Request::Stop);
            }
            if ui.button("Check Models").clicked() {
                ui_state.studio.send(Request::Get { tag: "models".into(), path: "/scp/v1/models".into() });
            }
        });
        ui.horizontal(|ui| {
            ui.label("ComfyUI folder:");
            let mut text = ui_state.settings.comfyui.as_ref().map(|p| p.to_string_lossy().into_owned()).unwrap_or_default();
            let edit = ui.add(egui::TextEdit::singleline(&mut text).hint_text("as Plenio last started it").desired_width(300.0));
            if edit.lost_focus() {
                ui_state.settings.comfyui = Some(text.trim()).filter(|t| !t.is_empty()).map(std::path::PathBuf::from);
                ui_state.save_settings(app);
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

fn models(ui_state: &mut PlenioUi, ui: &mut egui::Ui) {
    let Some(models) = ui_state.models.clone() else {
        ui.label(egui::RichText::new("Start the studio to see which models are installed.").weak());
        return;
    };
    if let Some(templates) = models.get("templates").and_then(Value::as_object) {
        for (id, t) in templates {
            let ready = t.get("ready").and_then(Value::as_bool).unwrap_or(false);
            let missing = t.get("missing").and_then(Value::as_array).map_or(0, Vec::len);
            ui.label(format!(
                "{id}: {}",
                if ready {
                    "ready".to_string()
                } else if missing == 0 {
                    "ready (a file differs in size)".into()
                } else {
                    format!("{missing} model file(s) missing")
                }
            ));
        }
    }
    let mut wanted = Vec::new();
    egui::ScrollArea::vertical().max_height(260.0).show(ui, |ui| {
        egui::Grid::new("plenio_models").striped(true).show(ui, |ui| {
            for m in models.get("models").and_then(Value::as_array).into_iter().flatten() {
                let s = |k: &str| m.get(k).and_then(Value::as_str).unwrap_or_default().to_string();
                let bytes = m.get("bytes").and_then(Value::as_u64).unwrap_or(0);
                ui.label(s("role"));
                ui.label(format!("{} GB", bytes / 1_000_000 / 1000));
                ui.label(s("licence"));
                let status = s("status");
                if let Some((done, total)) = ui_state.downloads.get(&s("file")) {
                    let f = if *total > 0 { *done as f32 / *total as f32 } else { 0.0 };
                    ui.add(egui::ProgressBar::new(f).desired_width(120.0).show_percentage());
                } else if status == "missing" {
                    let allowed = !m.get("non_commercial").and_then(Value::as_bool).unwrap_or(false) || ui_state.settings.licences_accepted;
                    if ui.add_enabled(allowed, egui::Button::new("Download")).clicked() {
                        wanted.push(m.clone());
                    }
                } else {
                    ui.label(status);
                }
                ui.end_row();
            }
        });
    });
    let files: Vec<(String, std::path::PathBuf, u64)> = wanted
        .iter()
        .filter_map(|m| {
            Some((
                m.get("url")?.as_str()?.to_string(),
                std::path::PathBuf::from(m.get("target")?.as_str()?),
                m.get("bytes").and_then(Value::as_u64).unwrap_or(0),
            ))
        })
        .collect();
    if !files.is_empty() {
        ui_state.studio.send(Request::DownloadModels { files });
    }
}

fn new_song(ui_state: &mut PlenioUi, app: &mut SoundApp, ctx: &egui::Context) {
    let Some(mut d) = ui_state.new_song.take() else { return };
    let mut open = true;
    let mut create = false;
    let template_id = if d.kind == SongKind::Cover { "yue2-cover" } else { "yue2-song" };
    let title = if d.kind == SongKind::Cover { "New Plenio Cover" } else { "New Plenio Song" };
    egui::Window::new(title).open(&mut open).collapsible(false).default_width(480.0).show(ctx, |ui| {
        if !ui_state.ready() {
            ui.label(egui::RichText::new(format!("{} - the song is made when it is ready.", studio_line(ui_state))).weak());
        }
        egui::Grid::new("plenio_new_song").num_columns(2).show(ui, |ui| {
            if d.kind == SongKind::Song {
                ui.label("Template");
                ui.vertical(|ui| {
                    ui.add(egui::TextEdit::singleline(&mut d.filter).hint_text("search 250 templates: jazz, trance, ballad …").desired_width(300.0));
                    let choices = choices(ui_state.field(template_id, "template"));
                    let filter = d.filter.to_lowercase();
                    egui::ScrollArea::vertical().id_salt("plenio_templates").max_height(140.0).show(ui, |ui| {
                        for c in choices.iter().filter(|c| filter.is_empty() || c.to_lowercase().contains(&filter)).take(400) {
                            if ui.selectable_label(d.template == *c, c).clicked() {
                                d.template = c.clone();
                            }
                        }
                    });
                });
                ui.end_row();
                ui.label("Idea");
                ui.add(egui::TextEdit::multiline(&mut d.idea).hint_text("what the song is about (optional)").desired_rows(2).desired_width(300.0));
                ui.end_row();
            }
            let vocal_choices = choices(ui_state.field(template_id, "vocals"));
            choice_row(ui, "Vocals", "plenio_new_vocals", &mut d.vocals, &vocal_choices);
            if d.kind == SongKind::Song {
                let lengths = choices(ui_state.field(template_id, "length"));
                choice_row(ui, "Length", "plenio_new_length", &mut d.length, &lengths);
            }
            ui.label("Language");
            ui.text_edit_singleline(&mut d.language);
            ui.end_row();
        });
        if d.kind == SongKind::Song {
            ui.checkbox(&mut d.own_lyrics, "My own lyrics, sung as written");
            if d.own_lyrics {
                ui.add(egui::TextEdit::multiline(&mut d.lyrics).hint_text("[verse]\n…\n\n[chorus]\n…").desired_rows(6).desired_width(f32::INFINITY));
            }
        } else {
            ui.label(egui::RichText::new("The recording's melody, form and tempo stay; use only recordings you own or may use.").weak());
        }
        ui.add_space(6.0);
        if ui.button(if d.kind == SongKind::Cover { "Make the Cover" } else { "Make the Song" }).clicked() {
            create = true;
        }
    });
    if create {
        let mut fields = serde_json::Map::new();
        if d.kind == SongKind::Song {
            fields.insert("template".into(), json!(d.template));
            if !d.idea.trim().is_empty() {
                fields.insert("description".into(), json!(d.idea.trim()));
            }
            fields.insert("length".into(), json!(d.length));
        }
        fields.insert("vocals".into(), json!(d.vocals));
        fields.insert("language".into(), json!(d.language));
        let mut params = json!({"kind": if d.kind == SongKind::Cover { "cover" } else { "song" }, "fields": fields});
        if let Some(t) = d.source {
            if let Some((start, duration)) = excerpt(app, t) {
                params["fields"]["excerpt.enabled"] = json!(true);
                params["fields"]["excerpt.start_index"] = json!(start);
                params["fields"]["excerpt.duration"] = json!(duration);
            }
            params["source_track"] = json!(t.0);
            let name = app.engine.session().track(t).map(|t| format!("{} (Cover)", t.name)).unwrap_or_default();
            params["title"] = json!(name);
        }
        match app.run("plenio.song.new", params) {
            Ok(v) => {
                if let Some(id) = v.get("song").and_then(Value::as_u64) {
                    if d.own_lyrics && !d.lyrics.trim().is_empty() {
                        let _ = app.run("plenio.song.set", json!({"song": id, "documents": {"lyrics": d.lyrics}}));
                    }
                    ui_state.song = Some(id);
                    ui_state.show_inspector = true;
                    ui_state.generate(app, id, Mode::Auto);
                }
            }
            Err(e) => say(app, format!("Plenio: {e}")),
        }
        return;
    }
    if open {
        ui_state.new_song = Some(d);
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

pub fn choices(field: Option<&Value>) -> Vec<String> {
    field
        .and_then(|f| f.get("choices"))
        .and_then(Value::as_array)
        .map(|a| a.iter().filter_map(|c| c.as_str().map(str::to_string)).collect())
        .unwrap_or_default()
}

fn choice_row(ui: &mut egui::Ui, label: &str, id: &str, value: &mut String, choices: &[String]) {
    ui.label(label);
    craft_ui::ComboBox::from_id_salt(id).selected_text(value.as_str()).show_ui(ui, |ui| {
        for c in choices {
            ui.selectable_value(value, c.clone(), c);
        }
    });
    ui.end_row();
}

/// The inspector's title (which is also its window's identity).
pub(crate) const INSPECTOR_TITLE: &str = "Plenio Song";
/// What the inspector shows above and below the lyrics, about (points).
const AROUND_THE_LYRICS: f32 = 300.0;

fn inspector(ui_state: &mut PlenioUi, app: &mut SoundApp, ctx: &egui::Context) {
    let mut open = ui_state.show_inspector;
    let project = Project::load(app.engine.session()).unwrap_or_default();
    let song = ui_state.song.and_then(|id| project.song(id)).or_else(|| project.songs.first()).cloned();
    // Its size is the owner's, in both directions: the content takes what the window gives.
    egui::Window::new(INSPECTOR_TITLE)
        .id(egui::Id::unique(INSPECTOR_TITLE))
        .open(&mut open)
        .resizable(true)
        .default_width(420.0)
        .default_height(ctx.content_rect().height() * 0.7)
        .min_height(160.0)
        .default_pos(ctx.content_rect().right_top() + egui::vec2(-440.0, 80.0))
        .show(ctx, |ui| {
            let Some(song) = song else {
                ui.label("No Plenio song in this session yet: Plenio › New Song…");
                return;
            };
            ui_state.song = Some(song.id);
            egui::ScrollArea::vertical().auto_shrink([false, false]).show(ui, |ui| inspector_body(ui_state, app, ui, &song));
        });
    ui_state.show_inspector = open;
}

fn inspector_body(ui_state: &mut PlenioUi, app: &mut SoundApp, ui: &mut egui::Ui, song: &Song) {
    ui.heading(&song.title);
    ui.label(egui::RichText::new(studio_line(ui_state)).small().weak());
    takes_row(ui_state, app, ui, song);
    ui.separator();
    let job = ui_state.jobs.values().find(|p| p.song == song.id).map(|p| (p.what, p.job.clone()));
    if let Some((what, job)) = job {
        let (text, f) = match &job {
            Some(j) => (
                match (j.queue_position, j.stage.as_str()) {
                    (Some(q), _) if q > 0 => format!("waiting in the queue ({q})"),
                    (_, "") => what.label().to_string(),
                    (_, stage) => stage.to_string(),
                },
                j.progress.unwrap_or(0.0),
            ),
            None => ("sending to the studio".into(), 0.0),
        };
        ui.add(egui::ProgressBar::new(f).text(text).animate(true));
        if ui.button("Cancel").clicked() {
            ui_state.cancel(song.id);
        }
    } else if ui_state.waiting.iter().any(|(s, _)| *s == song.id) {
        ui.label("Waiting for the studio …");
    } else {
        let mut changes = song.changes();
        let notes = !soundcraft_plenio_commands::changed_notes(app.engine.session(), song).is_empty();
        if notes {
            changes.push("notes on the score tracks".into());
        }
        let plan = song.plan(Mode::Auto);
        if !changes.is_empty() {
            ui.label(egui::RichText::new(format!("Changed: {}", changes.join(", "))).color(ui.visuals().warn_fg_color));
        }
        let what = if notes { soundcraft_plenio_project::What::SingYourNotes } else { plan.what };
        ui.label(egui::RichText::new(format!("Generate will {}.", what.label())).small());
        ui.horizontal(|ui| {
            if ui.button("Generate").clicked() {
                ui_state.generate(app, song.id, Mode::Auto);
            }
            ui.menu_button("More…", |ui| {
                for (label, mode) in
                    [("New take of the same song", Mode::NewTake), ("Compose new notes", Mode::Recompose), ("Write the song anew", Mode::Rewrite)]
                {
                    if ui.add_enabled(!song.takes.is_empty(), egui::Button::new(label)).clicked() {
                        ui_state.generate(app, song.id, mode);
                        ui.close();
                    }
                }
            });
        });
    }
    take_actions(ui_state, app, ui, song);
    ui.separator();
    egui::CollapsingHeader::new("Lyrics").default_open(true).show(ui, |ui| lyrics(ui_state, app, ui, song));
    egui::CollapsingHeader::new("Brief").default_open(false).show(ui, |ui| brief(ui_state, app, ui, song));
    egui::CollapsingHeader::new("Seeds and take").default_open(false).show(ui, |ui| seeds(ui_state, app, ui, song));
}

fn takes_row(_ui_state: &mut PlenioUi, app: &mut SoundApp, ui: &mut egui::Ui, song: &Song) {
    if song.takes.is_empty() {
        ui.label(egui::RichText::new("No take yet.").weak());
        return;
    }
    let current = song.active_take().map(soundcraft_plenio_project::Take::label).unwrap_or_default();
    ui.horizontal(|ui| {
        ui.label("Take");
        craft_ui::ComboBox::from_id_salt(("plenio_take", song.id)).selected_text(current).show_ui(ui, |ui| {
            for (i, t) in song.takes.iter().enumerate() {
                if ui.selectable_label(song.active == Some(i), t.label()).clicked() {
                    let _ = app.run("plenio.take.select", json!({"song": song.id, "take": t.number}));
                }
            }
        });
        if let Some(t) = song.active_take() {
            ui.label(egui::RichText::new(format!("{:.0} s", t.seconds)).weak());
        }
    });
}

fn lyrics(ui_state: &mut PlenioUi, app: &mut SoundApp, ui: &mut egui::Ui, song: &Song) {
    let doc = song.documents.get("lyrics").cloned().unwrap_or_default();
    // A new take or another song brings other words: the editor starts from them.
    if ui_state.lyrics_edit.as_ref().is_none_or(|(s, base, _)| *s != song.id || *base != doc.text) {
        ui_state.lyrics_edit = Some((song.id, doc.text.clone(), doc.text.clone()));
    }
    let Some((_, _, text)) = ui_state.lyrics_edit.as_mut() else { return };
    ui.horizontal_wrapped(|ui| {
        for tag in SECTION_TAGS {
            if ui.small_button(format!("[{tag}]")).clicked() {
                if !text.is_empty() && !text.ends_with('\n') {
                    text.push('\n');
                }
                text.push_str(&format!("\n[{tag}]\n"));
            }
        }
    });
    // A taller window shows more of the words.
    let row = ui.text_style_height(&egui::TextStyle::Monospace).max(1.0);
    let rows = ((ui.clip_rect().height() - AROUND_THE_LYRICS) / row).clamp(10.0, 400.0) as usize;
    ui.add(egui::TextEdit::multiline(text).desired_rows(rows).desired_width(f32::INFINITY).font(egui::TextStyle::Monospace));
    let edited = *text != doc.text;
    let text = text.clone();
    ui.horizontal(|ui| {
        let state = if doc.state == DocState::Manual {
            "yours"
        } else if doc.text.is_empty() {
            "written by Plenio"
        } else {
            "from the take"
        };
        ui.label(egui::RichText::new(state).small().weak());
        if ui.add_enabled(edited, egui::Button::new("Apply")).clicked() {
            let _ = app.run("plenio.song.set", json!({"song": song.id, "documents": {"lyrics": text}}));
        }
        if ui.add_enabled(doc.state == DocState::Manual, egui::Button::new("Back to the take's")).clicked() {
            let _ = app.run("plenio.song.set", json!({"song": song.id, "documents": {"lyrics": Value::Null}}));
            ui_state.lyrics_edit = None;
        }
        if ui.add_enabled(ui_state.ready(), egui::Button::new("Check")).on_hover_text("Plenio's YuE2 rules: tags, sections, lines").clicked() {
            ui_state.studio.send(Request::Post {
                tag: format!("lyrics-check:{}", song.id),
                path: "/plenio/lyrics/analyze".into(),
                body: json!({"lyrics": text, "engine": "yue2"}),
            });
        }
    });
    if let Some((id, result)) = &ui_state.lyrics_check
        && *id == song.id
    {
        match result {
            Ok(v) => {
                let findings = v.get("findings").and_then(Value::as_array).cloned().unwrap_or_default();
                if findings.is_empty() {
                    ui.label(egui::RichText::new("Plenio finds nothing to fix.").small());
                }
                for f in findings.iter().take(20) {
                    let severity = f.get("severity").and_then(Value::as_str).unwrap_or("info");
                    let message = f.get("message").and_then(Value::as_str).unwrap_or_default();
                    let color = if severity == "error" { ui.visuals().error_fg_color } else { ui.visuals().warn_fg_color };
                    ui.label(egui::RichText::new(format!("{severity}: {message}")).small().color(color));
                }
            }
            Err(e) => {
                ui.label(egui::RichText::new(e).small().color(ui.visuals().error_fg_color));
            }
        }
    }
}

fn brief(ui_state: &mut PlenioUi, app: &mut SoundApp, ui: &mut egui::Ui, song: &Song) {
    let Some(fields) = ui_state.templates.get(&song.template).and_then(|t| t.get("fields")).and_then(Value::as_array).cloned() else {
        ui.label(egui::RichText::new("The brief's fields come from the studio: start it to change them.").weak());
        return;
    };
    egui::Grid::new(("plenio_brief", song.id)).num_columns(2).striped(true).show(ui, |ui| {
        for f in fields.iter().filter(|f| !f.get("fixed").and_then(Value::as_bool).unwrap_or(false)) {
            let Some(id) = f.get("id").and_then(Value::as_str) else { continue };
            if id == "source.audio" {
                continue;
            }
            let current = song.fields.get(id).cloned().or_else(|| f.get("default").cloned()).unwrap_or(Value::Null);
            let label = ui.label(f.get("label").and_then(Value::as_str).unwrap_or(id));
            if let Some(d) = f.get("description").and_then(Value::as_str) {
                label.on_hover_text(d);
            }
            if let Some(v) = field_editor(ui, song.id, id, f, &current) {
                let _ = app.run("plenio.song.set", json!({"song": song.id, "fields": {id: v}}));
            }
            ui.end_row();
        }
    });
}

/// An editor for one field of the Song API; the new value when it changed.
fn field_editor(ui: &mut egui::Ui, song: u64, id: &str, field: &Value, current: &Value) -> Option<Value> {
    match field.get("type").and_then(Value::as_str).unwrap_or("string") {
        "choice" => {
            let options = choices(Some(field));
            let mut value = current.as_str().unwrap_or_default().to_string();
            let before = value.clone();
            craft_ui::ComboBox::from_id_salt(("plenio_field", song, id)).width(220.0).selected_text(value.clone()).show_ui(ui, |ui| {
                for c in &options {
                    ui.selectable_value(&mut value, c.clone(), c);
                }
            });
            (value != before).then_some(Value::String(value))
        }
        "boolean" => {
            let mut on = current.as_bool().unwrap_or(false);
            ui.checkbox(&mut on, "").changed().then_some(Value::Bool(on))
        }
        "integer" => {
            let mut n = current.as_i64().unwrap_or(0);
            let min = field.get("min").and_then(Value::as_i64).unwrap_or(i64::MIN / 2);
            let max = field.get("max").and_then(Value::as_i64).unwrap_or(i64::MAX / 2);
            ui.add(egui::DragValue::new(&mut n).range(min..=max)).changed().then(|| json!(n))
        }
        "text" => {
            let mut t = current.as_str().unwrap_or_default().to_string();
            ui.add(egui::TextEdit::multiline(&mut t).desired_rows(2).desired_width(220.0)).lost_focus().then_some(Value::String(t))
        }
        _ => {
            let mut t = current.as_str().map(str::to_string).unwrap_or_else(|| if current.is_null() { String::new() } else { current.to_string() });
            ui.add(egui::TextEdit::singleline(&mut t).desired_width(220.0)).lost_focus().then_some(Value::String(t))
        }
    }
}

/// What can be done with the take on the tracks: stems, and the mix to the player.
fn take_actions(ui_state: &mut PlenioUi, app: &mut SoundApp, ui: &mut egui::Ui, song: &Song) {
    let Some(t) = song.active_take() else { return };
    let number = t.number;
    ui.horizontal_wrapped(|ui| {
        let busy = ui_state.splitting.contains(&song.id);
        let label = if busy { "Splitting into stems…" } else { "Split this take into stems" };
        let button = ui.add_enabled(!busy && ui_state.ready(), egui::Button::new(label));
        if button.on_hover_text("Vocals, drums, bass, other and the rest, which together are the take (Plenio's BS-RoFormer)").clicked() {
            ui_state.split_stems(app, song.id, number);
        }
        let send = ui.button("Send the mix to the Plenio Player");
        if send.on_hover_text("Bounces the session's mix, with your effects, and plays it with the take's lyrics and notes").clicked() {
            ui_state.send_to_player(app, song.id);
        }
    });
}

fn seeds(ui_state: &mut PlenioUi, app: &mut SoundApp, ui: &mut egui::Ui, song: &Song) {
    let names: Vec<String> = ui_state
        .templates
        .get(&song.template)
        .and_then(|t| t.get("seeds"))
        .and_then(Value::as_array)
        .map(|a| a.iter().filter_map(|s| s.get("id").and_then(Value::as_str).map(str::to_string)).collect())
        .unwrap_or_else(|| ["draft", "plan", "arrangement", "take", "cover"].map(String::from).to_vec());
    ui.label(egui::RichText::new("A locked seed is kept for the next take; the others are drawn anew.").small().weak());
    for name in names {
        let locked = song.seeds.get(&name).copied();
        let from_take = song.active_take().and_then(|t| t.seeds.get(&name)).copied();
        let mut on = locked.is_some();
        let value = locked.or(from_take);
        let text = format!("{name}: {}", value.map_or("drawn anew".to_string(), |v| v.to_string()));
        if ui.add_enabled(value.is_some(), egui::Checkbox::new(&mut on, text)).changed() {
            let v = if on { value.map_or(Value::Null, |v| json!(v)) } else { Value::Null };
            let _ = app.run("plenio.song.set", json!({"song": song.id, "seeds": {name: v}}));
        }
    }
    let mut unmastered = song.unmastered;
    if ui.checkbox(&mut unmastered, "Put the unmastered take on the track (for your own mastering)").changed() {
        let _ = app.run("plenio.song.set", json!({"song": song.id, "unmastered": unmastered}));
    }
}
