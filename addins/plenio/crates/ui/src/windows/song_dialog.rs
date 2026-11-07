//! The new-song and new-cover dialog: a style, the few choices most songs need, and every other
//! field of the Song API under "More options".
//!
//! The fields come from the studio's description of its templates (or the add-in's copy of the
//! last one), so what a later Plenio adds shows up here by itself. A text field left empty takes the
//! chosen style's value, which the dialog shows as the field's hint.

use super::{SECTION_TAGS, choices, excerpt, studio_line};
use crate::fields::{self, Edit, Style};
use crate::{PlenioUi, run_or_say, say};
use serde_json::{Value, json};
use soundcraft_model::TrackId;
use soundcraft_plenio_project::{Mode, SongKind};
use soundcraft_ui_egui::SoundApp;
use std::collections::BTreeMap;

/// The style a new song starts with (Plenio's own default).
pub const SONG_STYLE: &str = "pop/singer-songwriter-acoustic-vocal";
/// The style a new cover starts with (Plenio's own default).
pub const COVER_STYLE: &str = "pop/dance-pop-vocal";

/// Plenio's choices, for a dialog opened before the studio ever described its templates.
const SONG_VOCALS: [&str; 3] = ["sung", "sparse vocals", "instrumental"];
const COVER_VOCALS: [&str; 3] = ["original lyrics", "new lyrics", "instrumental"];
const HARMONY: [&str; 2] = ["keep original chords", "new accompaniment"];
const LENGTHS: [&str; 10] = [
    "very short (about 1:00)",
    "short (about 1:30)",
    "about 2:00",
    "about 2:30",
    "standard (about 3:00)",
    "about 3:30",
    "about 4:00",
    "long (about 4:30)",
    "about 5:00",
    "very long (about 6:00)",
];

/// The fields the dialog shows above "More options" (or handles by itself): every other editable
/// field of the template is under "More options".
const SONG_BASIC: [&str; 6] = ["template", "vocals", "length", "language", "lyrics", "lyrics_from"];
const COVER_BASIC: [&str; 6] = ["template", "vocals", "language", "harmony", "theme", "title"];

/// What the dialog holds while it is open.
#[derive(Debug, Clone, PartialEq)]
pub struct NewSong {
    pub kind: SongKind,
    /// The style template's id (`electronic/synth-pop-vocal`).
    pub style: String,
    /// The search over the styles.
    pub filter: String,
    pub vocals: String,
    pub length: String,
    pub language: String,
    /// What the song is about: the idea the lyrics are written from.
    pub idea: String,
    pub own_lyrics: bool,
    pub lyrics: String,
    /// A title of the owner's; empty: Plenio writes one (a cover: the recording's name).
    pub title: String,
    /// A cover's harmony: keep the original chords or a new accompaniment.
    pub harmony: String,
    /// A cover's theme for new lyrics.
    pub theme: String,
    /// The fields changed under "More options".
    pub extra: BTreeMap<String, Value>,
    /// Split every take into stems as soon as it is on the tracks.
    pub stems: bool,
    /// A cover's recording.
    pub source: Option<TrackId>,
}

impl NewSong {
    pub fn song(stems: bool) -> Self {
        NewSong {
            kind: SongKind::Song,
            style: SONG_STYLE.into(),
            filter: String::new(),
            vocals: "sung".into(),
            length: "short (about 1:30)".into(),
            language: "English".into(),
            idea: String::new(),
            own_lyrics: false,
            lyrics: String::new(),
            title: String::new(),
            harmony: String::new(),
            theme: String::new(),
            extra: BTreeMap::new(),
            stems,
            source: None,
        }
    }

    pub fn cover(source: TrackId, stems: bool) -> Self {
        NewSong {
            kind: SongKind::Cover,
            style: COVER_STYLE.into(),
            vocals: "original lyrics".into(),
            length: String::new(),
            language: String::new(),
            harmony: "keep original chords".into(),
            source: Some(source),
            ..Self::song(stems)
        }
    }

    pub fn template_id(&self) -> &'static str {
        if self.kind == SongKind::Cover { "yue2-cover" } else { "yue2-song" }
    }

    fn sung(&self) -> bool {
        self.vocals != "instrumental"
    }

    /// Choosing a style: what it says about the song's shape becomes the dialog's starting point.
    pub fn take_style(&mut self, style: &Style) {
        self.style = style.id.clone();
        if self.kind == SongKind::Song {
            if let Some(v) = style.field("vocals").filter(|v| SONG_VOCALS.contains(v)) {
                self.vocals = v.to_string();
            }
            if let Some(l) = style.field("length").filter(|l| LENGTHS.contains(l)) {
                self.length = l.to_string();
            }
        }
    }

    /// A field's value as the job would carry it: the dialog's, else the style's, else the
    /// template's default. Decides which fields apply (their `when`).
    fn value_of(&self, ui_state: &PlenioUi, id: &str) -> Option<String> {
        match id {
            "vocals" => return Some(self.vocals.clone()),
            "length" if self.kind == SongKind::Song => return Some(self.length.clone()),
            "harmony" if self.kind == SongKind::Cover => return Some(self.harmony.clone()),
            _ => {}
        }
        self.extra
            .get(id)
            .and_then(fields::as_text)
            .or_else(|| ui_state.styles.get(&self.style).and_then(|s| s.field(id)).map(str::to_string))
            .or_else(|| ui_state.field(self.template_id(), id).and_then(|f| f.get("default")).and_then(fields::as_text))
    }

    /// The job's fields: what the dialog shows, and what was changed under "More options".
    pub fn fields(&self) -> serde_json::Map<String, Value> {
        let mut f = serde_json::Map::new();
        f.insert("template".into(), json!(self.style));
        f.insert("vocals".into(), json!(self.vocals));
        match self.kind {
            SongKind::Song => {
                f.insert("length".into(), json!(self.length));
                if self.sung() {
                    f.insert("language".into(), json!(self.language.trim()));
                    if !self.own_lyrics && !self.idea.trim().is_empty() {
                        f.insert("lyrics".into(), json!(self.idea.trim()));
                    }
                }
            }
            SongKind::Cover => {
                f.insert("harmony".into(), json!(self.harmony));
                if self.sung() && !self.language.trim().is_empty() {
                    f.insert("language".into(), json!(self.language.trim()));
                }
                if self.vocals == "new lyrics" && !self.theme.trim().is_empty() {
                    f.insert("theme".into(), json!(self.theme.trim()));
                }
                if !self.title.trim().is_empty() {
                    f.insert("title".into(), json!(self.title.trim()));
                }
            }
        }
        for (k, v) in &self.extra {
            f.insert(k.clone(), v.clone());
        }
        f
    }
}

fn basic(kind: SongKind) -> &'static [&'static str] {
    if kind == SongKind::Cover { &COVER_BASIC } else { &SONG_BASIC }
}

/// The choices of a field from the studio's description, else Plenio's as the add-in knows them.
fn choices_or(ui_state: &PlenioUi, template: &str, id: &str, known: &[&str]) -> Vec<String> {
    let live = choices(ui_state.field(template, id));
    if live.is_empty() { known.iter().map(|s| s.to_string()).collect() } else { live }
}

fn combo(ui: &mut egui::Ui, salt: &str, value: &mut String, options: &[String], width: f32) {
    craft_ui::ComboBox::from_id_salt(salt).width(width).selected_text(value.as_str()).show_ui(ui, |ui| {
        for c in options {
            ui.selectable_value(value, c.clone(), c);
        }
    });
}

/// A text field with a list of values to pick from.
fn text_with_suggestions(ui: &mut egui::Ui, value: &mut String, hint: &str, suggestions: &[String], width: f32) {
    ui.horizontal(|ui| {
        let w = if suggestions.is_empty() { width } else { (width - 28.0).max(60.0) };
        ui.add(egui::TextEdit::singleline(value).hint_text(hint).desired_width(w));
        if !suggestions.is_empty() {
            ui.menu_button("…", |ui| {
                egui::ScrollArea::vertical().max_height(260.0).show(ui, |ui| {
                    for s in suggestions {
                        if ui.button(s).clicked() {
                            *value = s.clone();
                            ui.close();
                        }
                    }
                });
            });
        }
    });
}

/// The style list: searchable, grouped, and what the chosen style sounds like.
fn style_picker(ui_state: &PlenioUi, d: &mut NewSong, ui: &mut egui::Ui) {
    ui.add(egui::TextEdit::singleline(&mut d.filter).hint_text("search the styles: jazz, trance, ballad, female …").desired_width(f32::INFINITY));
    let styles = &ui_state.styles;
    egui::ScrollArea::vertical().id_salt("plenio_styles").max_height(150.0).auto_shrink([false, true]).show(ui, |ui| {
        if styles.list.is_empty() {
            // Before the studio described its styles: the template's plain list.
            let filter = d.filter.to_lowercase();
            let ids = choices(ui_state.field(d.template_id(), "template"));
            for id in ids.iter().filter(|c| *c != "none" && (filter.is_empty() || c.to_lowercase().contains(&filter))) {
                if ui.selectable_label(d.style == *id, fields::style_title(styles, id)).clicked() {
                    d.style = id.clone();
                }
            }
            if ids.is_empty() {
                ui.label(egui::RichText::new("The styles come from the studio when it is ready.").weak());
            }
            return;
        }
        let mut group = "";
        let found = styles.matching(&d.filter);
        if found.is_empty() {
            ui.label(egui::RichText::new("No style has all of these words.").weak());
        }
        for s in found {
            if s.group != group {
                group = &s.group;
                ui.label(egui::RichText::new(group).small().strong());
            }
            let row = ui.selectable_label(d.style == s.id, format!("   {}", s.name));
            if row.on_hover_text(s.summary()).clicked() {
                d.take_style(s);
            }
        }
    });
    ui.label(egui::RichText::new(fields::style_title(styles, &d.style)).strong());
    if let Some(s) = styles.get(&d.style) {
        let summary = s.summary();
        if !summary.is_empty() {
            ui.label(egui::RichText::new(summary).small());
        }
        if let Some(description) = s.field("description") {
            ui.add(egui::Label::new(egui::RichText::new(description).small().weak()).wrap());
        }
    }
}

/// Every other field of the template, with the style's values as hints.
fn more_options(ui_state: &PlenioUi, d: &mut NewSong, ui: &mut egui::Ui) {
    let Some(all) = ui_state.templates.get(d.template_id()).and_then(|t| t.get("fields")).and_then(Value::as_array) else {
        ui.label(egui::RichText::new("The other options come from the studio when it is ready.").weak());
        return;
    };
    let shown: Vec<&Value> = all
        .iter()
        .filter(|f| fields::editable(f))
        .filter(|f| {
            let id = fields::id(f);
            !basic(d.kind).contains(&id) && !id.starts_with("excerpt.")
        })
        .collect();
    egui::Grid::new("plenio_new_more").num_columns(2).striped(true).spacing([10.0, 6.0]).show(ui, |ui| {
        for f in shown {
            let id = fields::id(f).to_string();
            if !fields::applies(f, |other| d.value_of(ui_state, other)) {
                continue;
            }
            let label = ui.label(fields::label(f));
            if let Some(text) = fields::description(f) {
                label.on_hover_text(text);
            }
            let style_value = ui_state.styles.get(&d.style).and_then(|s| s.field(&id)).map(str::to_string);
            let fills = ui_state.styles.fills(&id);
            let edit = Edit {
                current: d.extra.get(&id),
                fallback: if fills { Some(style_value.unwrap_or_default()) } else { None },
                suggestions: if f.get("type").and_then(Value::as_str) == Some("string") { ui_state.styles.suggestions(&id) } else { &[] },
                width: 280.0,
            };
            if let Some(v) = fields::editor(ui, ("plenio_new", &id), f, &edit) {
                if v.is_null() {
                    d.extra.remove(&id);
                } else {
                    d.extra.insert(id, v);
                }
            }
            ui.end_row();
        }
    });
}

pub fn show(ui_state: &mut PlenioUi, app: &mut SoundApp, ctx: &egui::Context) {
    let Some(mut d) = ui_state.new_song.take() else { return };
    let mut open = true;
    let mut create = false;
    let mut cancel = false;
    let cover = d.kind == SongKind::Cover;
    let template = d.template_id();
    let title = if cover { "New Plenio Cover" } else { "New Plenio Song" };
    let screen = ctx.content_rect();
    // It sizes itself to what it holds; everything but the switch for stems and the buttons scrolls,
    // so Make the Song is always in view.
    egui::Window::new(title)
        .id(egui::Id::unique("plenio_new_song"))
        .open(&mut open)
        .collapsible(false)
        .resizable(false)
        .pivot(egui::Align2::CENTER_TOP)
        .default_pos(screen.center_top() + egui::vec2(0.0, 60.0))
        .show(ctx, |ui| {
            ui.set_width(540.0);
            egui::ScrollArea::vertical()
                .id_salt("plenio_new_song_body")
                .max_height((screen.height() - 260.0).max(240.0))
                .auto_shrink([false, true])
                .show(ui, |ui| {
                    if !ui_state.ready() {
                        ui.label(egui::RichText::new(format!("{} - the song is made when it is ready.", studio_line(ui_state))).weak());
                    }
                    if let Some(t) = d.source {
                        let name = app.engine.session().track(t).map(|t| t.name.clone()).unwrap_or_default();
                        let part =
                            excerpt(app, t).map(|(start, len)| format!(" · the selection, {} to {}", super::clock(start), super::clock(start + len)));
                        ui.label(format!(
                            "Recording: {name}{}",
                            part.unwrap_or_else(|| " · all of it (select a part on its track for an excerpt)".into())
                        ));
                        ui.add_space(4.0);
                    }
                    ui.label(egui::RichText::new(if cover { "Target style" } else { "Style" }).strong());
                    style_picker(ui_state, &mut d, ui);
                    ui.add_space(6.0);
                    egui::Grid::new("plenio_new_song").num_columns(2).spacing([10.0, 6.0]).show(ui, |ui| {
                        let vocals = choices_or(ui_state, template, "vocals", if cover { &COVER_VOCALS } else { &SONG_VOCALS });
                        ui.label("Vocals");
                        combo(ui, "plenio_new_vocals", &mut d.vocals, &vocals, 220.0);
                        ui.end_row();
                        if !cover {
                            ui.label("Length");
                            combo(ui, "plenio_new_length", &mut d.length, &choices_or(ui_state, template, "length", &LENGTHS), 220.0);
                            ui.end_row();
                        } else {
                            ui.label("Harmony");
                            combo(ui, "plenio_new_harmony", &mut d.harmony, &choices_or(ui_state, template, "harmony", &HARMONY), 220.0);
                            ui.end_row();
                        }
                        if d.sung() {
                            ui.label("Language");
                            let hint = if cover { "auto: heard from the singing" } else { "English" };
                            text_with_suggestions(ui, &mut d.language, hint, ui_state.styles.suggestions("language"), 220.0);
                            ui.end_row();
                        }
                        if cover && d.vocals == "new lyrics" {
                            ui.label("New lyrics about");
                            ui.add(egui::TextEdit::singleline(&mut d.theme).hint_text("leaving home, a summer night …").desired_width(300.0));
                            ui.end_row();
                        }
                        ui.label("Title");
                        let hint = if cover { "the recording's name with (Cover)" } else { "Plenio writes one" };
                        ui.add(egui::TextEdit::singleline(&mut d.title).hint_text(hint).desired_width(300.0));
                        ui.end_row();
                    });
                    if !cover && d.sung() {
                        ui.add_space(4.0);
                        ui.checkbox(&mut d.own_lyrics, "My own lyrics, sung as written");
                        if d.own_lyrics {
                            ui.horizontal_wrapped(|ui| {
                                for tag in SECTION_TAGS {
                                    if ui.small_button(format!("[{tag}]")).clicked() {
                                        if !d.lyrics.is_empty() && !d.lyrics.ends_with('\n') {
                                            d.lyrics.push('\n');
                                        }
                                        d.lyrics.push_str(&format!("\n[{tag}]\n"));
                                    }
                                }
                            });
                            egui::ScrollArea::vertical().id_salt("plenio_new_lyrics").max_height(220.0).show(ui, |ui| {
                                ui.add(
                                    egui::TextEdit::multiline(&mut d.lyrics)
                                        .hint_text("[verse]\n…\n\n[chorus]\n…")
                                        .desired_rows(8)
                                        .desired_width(f32::INFINITY),
                                );
                            });
                        } else {
                            ui.label("What it is about");
                            let hint = ui_state
                                .styles
                                .get(&d.style)
                                .and_then(|s| s.field("lyrics"))
                                .unwrap_or("a story, an image, a message (optional)")
                                .to_string();
                            ui.add(egui::TextEdit::multiline(&mut d.idea).hint_text(hint).desired_rows(2).desired_width(f32::INFINITY));
                        }
                    }
                    if cover {
                        ui.label(
                            egui::RichText::new("The recording's melody, form and tempo stay; use only recordings you own or may use.")
                                .small()
                                .weak(),
                        );
                    }
                    ui.add_space(4.0);
                    egui::CollapsingHeader::new("More options").id_salt("plenio_new_more_header").show(ui, |ui| more_options(ui_state, &mut d, ui));
                });
            ui.separator();
            ui.checkbox(&mut d.stems, "Split every take into stems right away").on_hover_text(
            "Vocals, drums, bass, other and the rest on tracks of their own as soon as a take is on its tracks (about half a minute more per take)",
        );
            ui.add_space(6.0);
            ui.horizontal(|ui| {
                let ready_to_go = !(d.own_lyrics && d.lyrics.trim().is_empty() && !cover);
                let make = ui.add_enabled(
                    ready_to_go,
                    egui::Button::new(egui::RichText::new(if cover { "Make the Cover" } else { "Make the Song" }).strong()),
                );
                if make.on_disabled_hover_text("Write your lyrics first, or untick My own lyrics").clicked() {
                    create = true;
                }
                if ui.button("Cancel").clicked() {
                    cancel = true;
                }
            });
        });
    if create {
        make(ui_state, app, &d);
        return;
    }
    if open && !cancel {
        ui_state.new_song = Some(d);
    }
}

/// Make the song the dialog describes, and its first take.
fn make(ui_state: &mut PlenioUi, app: &mut SoundApp, d: &NewSong) {
    if ui_state.settings.stems_right_away != d.stems {
        ui_state.settings.stems_right_away = d.stems;
        ui_state.save_settings(app);
    }
    let cover = d.kind == SongKind::Cover;
    let mut params = json!({"kind": if cover { "cover" } else { "song" }, "fields": d.fields(), "stems_right_away": d.stems});
    if let Some(t) = d.source {
        if let Some((start, duration)) = excerpt(app, t) {
            params["fields"]["excerpt.enabled"] = json!(true);
            params["fields"]["excerpt.start_index"] = json!(start);
            params["fields"]["excerpt.duration"] = json!(duration);
        }
        params["source_track"] = json!(t.0);
        let name = if d.title.trim().is_empty() {
            app.engine.session().track(t).map(|t| format!("{} (Cover)", t.name)).unwrap_or_default()
        } else {
            d.title.trim().to_string()
        };
        params["title"] = json!(name);
    } else if !d.title.trim().is_empty() {
        params["title"] = json!(d.title.trim());
    }
    let Some(made) = run_or_say(app, "plenio.song.new", params) else { return };
    let Some(id) = made.get("song").and_then(Value::as_u64) else {
        say(app, "Plenio: the song was not made.");
        return;
    };
    let mut documents = serde_json::Map::new();
    if !cover && d.own_lyrics && !d.lyrics.trim().is_empty() {
        documents.insert("lyrics".into(), json!(d.lyrics));
    }
    if !cover && !d.title.trim().is_empty() {
        documents.insert("title".into(), json!(d.title.trim()));
    }
    if !documents.is_empty() && run_or_say(app, "plenio.song.set", json!({"song": id, "documents": documents})).is_none() {
        return;
    }
    ui_state.song = Some(id);
    ui_state.show_inspector = true;
    ui_state.generate(app, id, Mode::Auto);
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_song_sends_the_idea_as_what_the_lyrics_are_about_not_as_its_sound() {
        let mut d = NewSong::song(false);
        d.idea = "a lighthouse keeper's last night".into();
        let f = d.fields();
        assert_eq!(f.get("lyrics"), Some(&json!("a lighthouse keeper's last night")));
        assert!(f.get("description").is_none(), "the style's sound stays");
        assert_eq!(f.get("template"), Some(&json!(SONG_STYLE)));
        d.own_lyrics = true;
        assert!(d.fields().get("lyrics").is_none(), "own lyrics go as the lyrics document");
        d.vocals = "instrumental".into();
        let f = d.fields();
        assert!(f.get("language").is_none() && f.get("lyrics").is_none());
    }

    #[test]
    fn more_options_go_with_the_job_and_a_cover_keeps_its_own_fields() {
        let mut d = NewSong::cover(TrackId(3), true);
        d.extra.insert("creativity".into(), json!(40));
        d.title = "Garden (Jazz)".into();
        let f = d.fields();
        assert_eq!(f.get("creativity"), Some(&json!(40)));
        assert_eq!(f.get("harmony"), Some(&json!("keep original chords")));
        assert_eq!(f.get("title"), Some(&json!("Garden (Jazz)")));
        assert!(f.get("length").is_none(), "a cover keeps the recording's length");
        assert!(f.get("language").is_none(), "left empty: heard from the singing");
        d.vocals = "new lyrics".into();
        d.theme = "leaving home".into();
        assert_eq!(d.fields().get("theme"), Some(&json!("leaving home")));
    }

    #[test]
    fn a_style_sets_the_songs_shape() {
        let style = Style {
            id: "jazz/bebop-instrumental".into(),
            name: "Bebop".into(),
            group: "Jazz".into(),
            fields: [("vocals", "instrumental"), ("length", "long (about 4:30)")].into_iter().map(|(k, v)| (k.to_string(), v.to_string())).collect(),
        };
        let mut d = NewSong::song(false);
        d.take_style(&style);
        assert_eq!((d.style.as_str(), d.vocals.as_str(), d.length.as_str()), ("jazz/bebop-instrumental", "instrumental", "long (about 4:30)"));
        let mut c = NewSong::cover(TrackId(1), false);
        c.take_style(&style);
        assert_eq!(c.vocals, "original lyrics", "a cover's vocals are about its recording");
    }
}
