//! The song inspector: the song's takes and what can be done with them, its lyrics, its brief (every
//! field of the Song API, with the style's values as hints) and its seeds.

use super::{SECTION_TAGS, studio_line};
use crate::fields::{self, Edit};
use crate::{PlenioUi, run_or_say};
use serde_json::{Value, json};
use soundcraft_plenio_backend::Request;
use soundcraft_plenio_project::{DocState, Mode, Project, Song};
use soundcraft_ui_egui::SoundApp;

/// The inspector's title (which is also its window's identity).
pub const INSPECTOR_TITLE: &str = "Plenio Song";
/// What the inspector shows above and below the lyrics, about (points).
const AROUND_THE_LYRICS: f32 = 300.0;

pub fn show(ui_state: &mut PlenioUi, app: &mut SoundApp, ctx: &egui::Context) {
    let mut open = ui_state.show_inspector;
    let project = Project::load(app.engine.session()).unwrap_or_default();
    let song = ui_state.song.and_then(|id| project.song(id)).or_else(|| project.songs.first()).cloned();
    // Its size is the owner's, in both directions: the content takes what the window gives.
    egui::Window::new(INSPECTOR_TITLE)
        .id(egui::Id::unique(INSPECTOR_TITLE))
        .open(&mut open)
        .resizable(true)
        .default_width(440.0)
        .default_height(ctx.content_rect().height() * 0.7)
        .min_height(160.0)
        .default_pos(ctx.content_rect().right_top() + egui::vec2(-460.0, 80.0))
        .show(ctx, |ui| {
            let Some(song) = song else {
                ui.label("No Plenio song in this session yet.");
                if ui.button("New Song…").clicked() {
                    ui_state.new_song = Some(super::NewSong::song(ui_state.settings.stems_right_away));
                }
                return;
            };
            ui_state.song = Some(song.id);
            egui::ScrollArea::vertical().auto_shrink([false, false]).show(ui, |ui| body(ui_state, app, ui, &song));
        });
    ui_state.show_inspector = open;
}

fn body(ui_state: &mut PlenioUi, app: &mut SoundApp, ui: &mut egui::Ui, song: &Song) {
    ui.heading(&song.title);
    let style = song.fields.get("template").and_then(Value::as_str).map(|id| fields::style_title(&ui_state.styles, id));
    let kind = if song.kind == soundcraft_plenio_project::SongKind::Cover { "Cover" } else { "Song" };
    ui.label(egui::RichText::new(match style {
        Some(s) => format!("{kind} · {s}"),
        None => kind.to_string(),
    }));
    ui.label(egui::RichText::new(studio_line(ui_state)).small().weak());
    takes_row(app, ui, song);
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
    } else if ui_state.waiting.iter().any(|(s, _, _)| *s == song.id) {
        ui.horizontal(|ui| {
            ui.add(egui::Spinner::new());
            ui.label("Waiting for the studio …");
        });
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
            if ui.button(egui::RichText::new("Generate").strong()).clicked() {
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

fn takes_row(app: &mut SoundApp, ui: &mut egui::Ui, song: &Song) {
    if song.takes.is_empty() {
        ui.label(egui::RichText::new("No take yet: Generate makes the first.").weak());
        return;
    }
    let current = song.active_take().map(soundcraft_plenio_project::Take::label).unwrap_or_default();
    ui.horizontal(|ui| {
        ui.label("Take");
        craft_ui::ComboBox::from_id_salt(("plenio_take", song.id)).selected_text(current).show_ui(ui, |ui| {
            for (i, t) in song.takes.iter().enumerate() {
                if ui.selectable_label(song.active == Some(i), t.label()).clicked() {
                    run_or_say(app, "plenio.take.select", json!({"song": song.id, "take": t.number}));
                }
            }
        });
        if let Some(t) = song.active_take() {
            let mut facts = vec![super::clock(t.seconds)];
            if let Some(bpm) = t.bpm {
                facts.push(format!("{bpm:.0} BPM"));
            }
            if !t.key.is_empty() {
                facts.push(t.key.clone());
            }
            ui.label(egui::RichText::new(facts.join(" · ")).weak());
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
    // The hint also names the editor for screen readers.
    let editor = egui::TextEdit::multiline(text).hint_text(
        "[verse]
…

[chorus]
…",
    );
    ui.add(editor.desired_rows(rows).desired_width(f32::INFINITY).font(egui::TextStyle::Monospace));
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
        if ui.add_enabled(edited, egui::Button::new("Apply")).on_hover_text("The next take sings these words").clicked() {
            run_or_say(app, "plenio.song.set", json!({"song": song.id, "documents": {"lyrics": text}}));
        }
        if ui.add_enabled(doc.state == DocState::Manual, egui::Button::new("Back to the take's")).clicked() {
            run_or_say(app, "plenio.song.set", json!({"song": song.id, "documents": {"lyrics": Value::Null}}));
            ui_state.lyrics_edit = None;
        }
        let check = ui.add_enabled(ui_state.ready(), egui::Button::new("Check")).on_hover_text("Plenio's YuE2 rules: tags, sections, lines");
        if check.on_disabled_hover_text("Needs the studio").clicked() {
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

/// Every field of the song's template. A text field left empty takes the style's value (its hint);
/// emptying a field gives it back to the style.
fn brief(ui_state: &mut PlenioUi, app: &mut SoundApp, ui: &mut egui::Ui, song: &Song) {
    let Some(all) = ui_state.templates.get(&song.template).and_then(|t| t.get("fields")).and_then(Value::as_array).cloned() else {
        ui.label(egui::RichText::new("The brief's fields come from the studio: start it to change them.").weak());
        return;
    };
    let style_id = song.fields.get("template").and_then(Value::as_str).unwrap_or_default().to_string();
    let style = ui_state.styles.get(&style_id).cloned();
    let value_of = |id: &str| -> Option<String> {
        song.fields
            .get(id)
            .and_then(fields::as_text)
            .or_else(|| style.as_ref().and_then(|s| s.field(id)).map(str::to_string))
            .or_else(|| all.iter().find(|f| fields::id(f) == id).and_then(|f| f.get("default")).and_then(fields::as_text))
    };
    let mut changed: Option<(String, Value)> = None;
    egui::Grid::new(("plenio_brief", song.id)).num_columns(2).striped(true).spacing([10.0, 6.0]).show(ui, |ui| {
        for f in all.iter().filter(|f| fields::editable(f)) {
            let id = fields::id(f).to_string();
            if id.starts_with("excerpt.") || !fields::applies(f, value_of) {
                continue;
            }
            let label = ui.label(if id == "template" { "Style".to_string() } else { fields::label(f) });
            if let Some(text) = fields::description(f) {
                label.on_hover_text(text);
            }
            if id == "template" {
                if let Some(v) = style_choice(ui_state, ui, song.id, &style_id, f) {
                    changed = Some((id, v));
                }
                ui.end_row();
                continue;
            }
            let fills = ui_state.styles.fills(&id);
            let edit = Edit {
                current: song.fields.get(&id),
                fallback: if fills { Some(style.as_ref().and_then(|s| s.field(&id)).unwrap_or_default().to_string()) } else { None },
                suggestions: if f.get("type").and_then(Value::as_str) == Some("string") { ui_state.styles.suggestions(&id) } else { &[] },
                width: 240.0,
            };
            if let Some(v) = fields::editor(ui, ("plenio_field", song.id, &id), f, &edit) {
                changed = Some((id, v));
            }
            ui.end_row();
        }
    });
    if let Some((id, v)) = changed {
        run_or_say(app, "plenio.song.set", json!({"song": song.id, "fields": {id: v}}));
    }
}

/// The style of a song, by its name.
fn style_choice(ui_state: &PlenioUi, ui: &mut egui::Ui, song: u64, current: &str, field: &Value) -> Option<Value> {
    let ids: Vec<String> =
        if ui_state.styles.list.is_empty() { super::choices(Some(field)) } else { ui_state.styles.list.iter().map(|s| s.id.clone()).collect() };
    let mut value = current.to_string();
    craft_ui::ComboBox::from_id_salt(("plenio_style", song)).width(240.0).selected_text(fields::style_title(&ui_state.styles, current)).show_ui(
        ui,
        |ui| {
            for id in &ids {
                ui.selectable_value(&mut value, id.clone(), fields::style_title(&ui_state.styles, id));
            }
        },
    );
    (value != current).then_some(Value::String(value))
}

/// What can be done with the take on the tracks: stems, and the mix to the player.
fn take_actions(ui_state: &mut PlenioUi, app: &mut SoundApp, ui: &mut egui::Ui, song: &Song) {
    let take = song.active_take().map(|t| t.number);
    ui.horizontal_wrapped(|ui| {
        if let Some(number) = take {
            let busy = ui_state.splitting.contains_key(&song.id);
            let label = if busy { "Splitting into stems…" } else { "Split this take into stems" };
            let button = ui.add_enabled(!busy && ui_state.ready(), egui::Button::new(label));
            let button = button.on_disabled_hover_text(if busy { "Splitting into stems…" } else { "Needs the studio" });
            if button.on_hover_text("Vocals, drums, bass, other and the rest, which together are the take (Plenio's BS-RoFormer)").clicked() {
                ui_state.split_stems(app, song.id, number);
            }
            let send = ui.button("Send the mix to the Plenio Player");
            if send.on_hover_text("Bounces the session's mix, with your effects, and plays it with the take's lyrics and notes").clicked() {
                ui_state.send_to_player(app, song.id);
            }
        }
    });
    let mut stems = song.stems_right_away;
    if ui
        .checkbox(&mut stems, "Split every new take into stems right away")
        .on_hover_text("As soon as a take is on its tracks, its stems follow on tracks of their own")
        .changed()
    {
        run_or_say(app, "plenio.song.set", json!({"song": song.id, "stems_right_away": stems}));
    }
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
            run_or_say(app, "plenio.song.set", json!({"song": song.id, "seeds": {name: v}}));
        }
    }
    let mut unmastered = song.unmastered;
    if ui.checkbox(&mut unmastered, "Put the unmastered take on the track (for your own mastering)").changed() {
        run_or_say(app, "plenio.song.set", json!({"song": song.id, "unmastered": unmastered}));
    }
}
