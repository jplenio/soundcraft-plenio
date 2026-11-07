//! The Song API's fields as the add-in shows them: friendly labels, an editor for each type, which
//! fields apply (a field's `when`), and the style templates whose values a field left empty takes.
//!
//! The studio describes all of it (`GET /plenio/api/v1/templates/{id}` and `GET /briefs`), so a
//! field a later Plenio adds shows up without a change here. The add-in keeps the last answers on
//! disk, so its dialogs are complete before the studio is ready.

use serde_json::{Value, json};
use std::collections::BTreeMap;
use std::hash::Hash;

/// The most styles taken from an answer (Plenio ships about 250).
const MAX_STYLES: usize = 2000;
/// The most suggestions kept per field.
const MAX_SUGGESTIONS: usize = 400;

/// A style template: a ready brief such as "Synth pop" (Plenio's `resources/templates`).
#[derive(Debug, Clone, PartialEq, Default)]
pub struct Style {
    pub id: String,
    pub name: String,
    pub group: String,
    /// What the style fills in: `description`, `genre`, `tempo`, `voice`, `length`, `vocals` …
    pub fields: BTreeMap<String, String>,
}

impl Style {
    pub fn field(&self, id: &str) -> Option<&str> {
        self.fields.get(id).map(String::as_str).filter(|v| !v.trim().is_empty())
    }

    /// `synth-pop · Dancefloor (120-130 BPM) · female vocal`
    pub fn summary(&self) -> String {
        ["genre", "tempo", "voice", "vocals"].iter().filter_map(|k| self.field(k)).filter(|v| *v != "sung").collect::<Vec<_>>().join(" · ")
    }
}

/// The style templates and, per field, every value they have (the suggestions of a field).
#[derive(Debug, Clone, Default, PartialEq)]
pub struct Styles {
    pub list: Vec<Style>,
    pub values: BTreeMap<String, Vec<String>>,
}

impl Styles {
    /// From the studio's `GET /plenio/api/v1/briefs` answer; whatever is not as expected is left out.
    pub fn parse(answer: &Value) -> Styles {
        let text = |v: &Value| v.as_str().map(str::to_string);
        let list = answer
            .get("briefs")
            .and_then(Value::as_array)
            .into_iter()
            .flatten()
            .take(MAX_STYLES)
            .filter_map(|b| {
                Some(Style {
                    id: text(b.get("id")?)?,
                    name: b.get("name").and_then(text).unwrap_or_default(),
                    group: b.get("group").and_then(text).unwrap_or_default(),
                    fields: b
                        .get("fields")
                        .and_then(Value::as_object)
                        .map(|m| m.iter().filter_map(|(k, v)| Some((k.clone(), text(v)?))).collect())
                        .unwrap_or_default(),
                })
            })
            .collect();
        let values = answer
            .get("values")
            .and_then(Value::as_object)
            .map(|m| {
                m.iter().map(|(k, v)| (k.clone(), v.as_array().into_iter().flatten().filter_map(text).take(MAX_SUGGESTIONS).collect())).collect()
            })
            .unwrap_or_default();
        Styles { list, values }
    }

    pub fn get(&self, id: &str) -> Option<&Style> {
        self.list.iter().find(|s| s.id == id)
    }

    /// Whether a style fills this field: then a song that leaves it empty takes the style's value.
    pub fn fills(&self, field: &str) -> bool {
        self.values.contains_key(field)
    }

    /// Every value the styles have for a field, for a list to pick from.
    pub fn suggestions(&self, field: &str) -> &[String] {
        self.values.get(field).map_or(&[], Vec::as_slice)
    }

    /// The styles whose name, group, genre or id hold every word of `filter`, in the studio's order.
    pub fn matching(&self, filter: &str) -> Vec<&Style> {
        let words: Vec<String> = filter.split_whitespace().map(str::to_lowercase).collect();
        self.list
            .iter()
            .filter(|s| {
                let hay = format!("{} {} {} {}", s.name, s.group, s.field("genre").unwrap_or_default(), s.id).to_lowercase();
                words.iter().all(|w| hay.contains(w.as_str()))
            })
            .collect()
    }
}

/// A style's name and group for a style id, also before the studio described the styles:
/// `electronic/synth-pop-vocal` gives `Synth pop vocal · Electronic`.
pub fn style_title(styles: &Styles, id: &str) -> String {
    if let Some(s) = styles.get(id) {
        return if s.group.is_empty() { s.name.clone() } else { format!("{} · {}", s.name, s.group) };
    }
    let (group, name) = id.split_once('/').unwrap_or(("", id));
    let tidy = |s: &str| {
        let s = s.replace('-', " ");
        let mut c = s.chars();
        c.next().map(|f| f.to_uppercase().collect::<String>() + c.as_str()).unwrap_or_default()
    };
    if group.is_empty() { tidy(name) } else { format!("{} · {}", tidy(name), tidy(group)) }
}

/// A field's id.
pub fn id(field: &Value) -> &str {
    field.get("id").and_then(Value::as_str).unwrap_or_default()
}

/// A friendlier name than the node input a field comes from.
pub fn label(field: &Value) -> String {
    let named = match id(field) {
        "description" => "Sound",
        "lyrics" => "What it is about",
        "lyrics_from" => "Lyrics",
        "theme" => "Theme",
        "voice" => "Voice",
        "lead_instrument" => "Lead instrument",
        "genre_closeness" => "Genre closeness",
        "song_flow_closeness" => "Closeness to the original",
        "lyrics_closeness" => "Closeness of the new lyrics",
        "lines_under_singing" => "Instrument line under the singing",
        "lyrics_fidelity" => "Lyrics fidelity",
        "original_notes" => "Notes of the original",
        "phrasing_reference" => "Phrasing like the original",
        "finish.hq_mastering" => "HQ mastering",
        "finish.cover_art" => "Cover art",
        "writer.model" => "Writer model",
        _ => "",
    };
    if !named.is_empty() {
        return named.to_string();
    }
    let raw = field.get("label").and_then(Value::as_str).filter(|l| !l.is_empty()).unwrap_or_else(|| id(field)).replace('_', " ");
    let mut c = raw.chars();
    c.next().map(|f| f.to_uppercase().collect::<String>() + c.as_str()).unwrap_or_default()
}

/// The field's description, for its tooltip.
pub fn description(field: &Value) -> Option<&str> {
    field.get("description").and_then(Value::as_str).filter(|d| !d.is_empty())
}

/// Whether a field can be changed here at all: not fixed by the API, not a file to upload.
pub fn editable(field: &Value) -> bool {
    !field.get("fixed").and_then(Value::as_bool).unwrap_or(false) && field.get("type").and_then(Value::as_str) != Some("upload")
}

/// Whether a field applies, given the values of the fields it depends on (its `when`): a voice does
/// not apply to an instrumental. `value_of` gives a field's value as it would be sent.
pub fn applies(field: &Value, value_of: impl Fn(&str) -> Option<String>) -> bool {
    let Some(when) = field.get("when").and_then(Value::as_object) else { return true };
    when.iter().all(|(other, allowed)| {
        let Some(value) = value_of(other) else { return true };
        allowed.as_array().is_none_or(|a| a.iter().filter_map(Value::as_str).any(|v| v.eq_ignore_ascii_case(&value)))
    })
}

/// A value as the text a choice or a hint shows.
pub fn as_text(v: &Value) -> Option<String> {
    match v {
        Value::Null => None,
        Value::String(s) => Some(s.clone()),
        other => Some(other.to_string()),
    }
}

/// What one editor shows, and what it may return.
pub struct Edit<'a> {
    /// The value the owner set; `None`: not set, the style's or the template's value applies.
    pub current: Option<&'a Value>,
    /// What applies when nothing is set (the style's value, else the template's default).
    pub fallback: Option<String>,
    /// Values to pick from for a text field.
    pub suggestions: &'a [String],
    /// The editor's width.
    pub width: f32,
}

/// Edit one field. Returns the new value once the owner is done with it (a click, the end of a drag,
/// leaving a text field), only when it differs: `Value::Null` hands the field back to the style or
/// the template (a text field emptied).
pub fn editor(ui: &mut egui::Ui, salt: impl Hash + std::fmt::Debug, field: &Value, edit: &Edit<'_>) -> Option<Value> {
    let key = egui::Id::unique(salt);
    let default = field.get("default").cloned().unwrap_or(Value::Null);
    let shown = || edit.current.cloned().or_else(|| edit.fallback.clone().map(Value::String)).unwrap_or_else(|| default.clone());
    match field.get("type").and_then(Value::as_str).unwrap_or("string") {
        "choice" => {
            let options: Vec<String> = field.get("choices").and_then(Value::as_array).into_iter().flatten().filter_map(as_text).collect();
            let before = as_text(&shown()).unwrap_or_default();
            let mut value = before.clone();
            craft_ui::ComboBox::from_id_salt(key).width(edit.width).selected_text(value.clone()).show_ui(ui, |ui| {
                for c in &options {
                    ui.selectable_value(&mut value, c.clone(), c);
                }
            });
            (value != before).then_some(Value::String(value))
        }
        "boolean" => {
            let before = shown().as_bool().unwrap_or(false);
            let mut on = before;
            ui.checkbox(&mut on, "");
            (on != before).then_some(Value::Bool(on))
        }
        "integer" => {
            let before = shown().as_i64().or_else(|| shown().as_f64().map(|f| f.round() as i64)).unwrap_or(0);
            let min = field.get("minimum").and_then(Value::as_f64).map(|m| m as i64);
            let max = field.get("maximum").and_then(Value::as_f64).map(|m| m as i64);
            let mut n = ui.data(|d| d.get_temp::<i64>(key)).unwrap_or(before);
            let response = match (min, max) {
                (Some(lo), Some(hi)) if hi > lo && hi - lo <= 1000 => ui.add(egui::Slider::new(&mut n, lo..=hi)),
                _ => ui.add(egui::DragValue::new(&mut n).range(min.unwrap_or(i64::MIN / 2)..=max.unwrap_or(i64::MAX / 2))),
            };
            staged(ui, key, &response, n, before).map(|n| json!(n))
        }
        "number" => {
            let before = shown().as_f64().unwrap_or(0.0);
            let lo = field.get("minimum").and_then(Value::as_f64).filter(|v| v.is_finite() && v.abs() < 1e12).unwrap_or(-1e9);
            let hi = field.get("maximum").and_then(Value::as_f64).filter(|v| v.is_finite() && v.abs() < 1e12).unwrap_or(1e9);
            let step = field.get("step").and_then(Value::as_f64).filter(|v| v.is_finite() && *v > 0.0).unwrap_or(0.01);
            let mut x = ui.data(|d| d.get_temp::<f64>(key)).unwrap_or(before);
            let response = ui.add(egui::DragValue::new(&mut x).range(lo..=hi.max(lo)).speed(step));
            staged(ui, key, &response, x, before).filter(|x| x.is_finite()).map(|x| json!(x))
        }
        kind => {
            let multiline = kind == "text";
            let before = edit.current.and_then(as_text).unwrap_or_default();
            let mut text = ui.data(|d| d.get_temp::<String>(key)).unwrap_or_else(|| before.clone());
            let hint = edit.fallback.clone().or_else(|| as_text(&default)).unwrap_or_default();
            let response = ui
                .horizontal(|ui| {
                    let box_width = if edit.suggestions.is_empty() { edit.width } else { (edit.width - 28.0).max(60.0) };
                    let text_edit =
                        if multiline { egui::TextEdit::multiline(&mut text).desired_rows(2) } else { egui::TextEdit::singleline(&mut text) };
                    let mut response = ui.add(text_edit.hint_text(hint).desired_width(box_width));
                    if !edit.suggestions.is_empty() {
                        ui.menu_button("…", |ui| {
                            egui::ScrollArea::vertical().max_height(260.0).show(ui, |ui| {
                                for s in edit.suggestions {
                                    if ui.button(s).clicked() {
                                        text = s.clone();
                                        response.mark_changed();
                                        ui.close();
                                    }
                                }
                            });
                        })
                        .response
                        .on_hover_text("Pick a value the styles use");
                    }
                    response
                })
                .inner;
            // A pick from the list is done at once; typing is done when the field is left.
            if response.changed() && !response.has_focus() {
                ui.data_mut(|d| d.remove::<String>(key));
                return finish_text(&text, &before);
            }
            if response.has_focus() {
                ui.data_mut(|d| d.insert_temp(key, text));
                return None;
            }
            ui.data_mut(|d| d.remove::<String>(key));
            finish_text(&text, &before)
        }
    }
}

/// A text field's end: an emptied field goes back to the style, an unchanged one stays.
fn finish_text(text: &str, before: &str) -> Option<Value> {
    let text = text.trim();
    if text == before.trim() {
        None
    } else if text.is_empty() {
        Some(Value::Null)
    } else {
        Some(Value::String(text.to_string()))
    }
}

/// A value being dragged stays in egui's memory until the owner lets go: then it is returned once,
/// when it differs from where it started. (A click or a typed number is done at once.)
fn staged<T: Clone + PartialEq + Send + Sync + 'static>(ui: &egui::Ui, key: egui::Id, response: &egui::Response, value: T, before: T) -> Option<T> {
    if response.dragged() {
        ui.data_mut(|d| d.insert_temp(key, value));
        return None;
    }
    ui.data_mut(|d| d.remove::<T>(key));
    (value != before).then_some(value)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn styles() -> Styles {
        Styles::parse(&json!({
            "briefs": [
                {"id": "electronic/synth-pop-vocal", "name": "Synth pop", "group": "Electronic",
                 "fields": {"genre": "synth-pop", "tempo": "Dancefloor (120-130 BPM)", "voice": "female vocal", "vocals": "sung"}},
                {"id": "jazz/bebop-instrumental", "name": "Bebop", "group": "Jazz", "fields": {"genre": "bebop", "vocals": "instrumental"}},
                {"name": "no id: left out"}
            ],
            "values": {"tempo": ["Dancefloor (120-130 BPM)", "Slow (40-70 BPM)"], "genre": ["bebop", "synth-pop"]}
        }))
    }

    #[test]
    fn styles_come_from_the_studio_answer() {
        let s = styles();
        assert_eq!(s.list.len(), 2);
        assert_eq!(s.get("jazz/bebop-instrumental").map(|x| x.name.as_str()), Some("Bebop"));
        assert_eq!(s.get("electronic/synth-pop-vocal").map(Style::summary).as_deref(), Some("synth-pop · Dancefloor (120-130 BPM) · female vocal"));
        assert_eq!(s.suggestions("tempo").len(), 2);
        assert!(s.fills("genre") && !s.fills("creativity"));
        assert!(Styles::parse(&json!("not an answer")).list.is_empty());
    }

    #[test]
    fn a_filter_needs_every_word_in_name_group_genre_or_id() {
        let s = styles();
        assert_eq!(s.matching("").len(), 2);
        assert_eq!(s.matching("JAZZ").len(), 1);
        assert_eq!(s.matching("synth electronic").len(), 1);
        assert!(s.matching("synth jazz").is_empty());
    }

    #[test]
    fn a_style_without_a_description_still_has_a_title() {
        let s = styles();
        assert_eq!(style_title(&s, "electronic/synth-pop-vocal"), "Synth pop · Electronic");
        assert_eq!(style_title(&Styles::default(), "pop/singer-songwriter-acoustic-vocal"), "Singer songwriter acoustic vocal · Pop");
        assert_eq!(style_title(&Styles::default(), "none"), "None");
    }

    #[test]
    fn a_field_applies_only_for_the_values_it_hangs_on() {
        let voice = json!({"id": "voice", "type": "string", "when": {"vocals": ["sung", "sparse vocals"]}});
        assert!(applies(&voice, |_| Some("sung".into())));
        assert!(applies(&voice, |_| Some("Sparse Vocals".into())));
        assert!(!applies(&voice, |_| Some("instrumental".into())));
        assert!(applies(&voice, |_| None), "an unknown value hides nothing");
        assert!(applies(&json!({"id": "genre"}), |_| Some("instrumental".into())));
    }

    #[test]
    fn labels_are_friendly_and_fixed_or_upload_fields_are_not_edited() {
        assert_eq!(label(&json!({"id": "description", "label": "description"})), "Sound");
        assert_eq!(label(&json!({"id": "writer.model", "label": "model"})), "Writer model");
        assert_eq!(label(&json!({"id": "genre", "label": "genre"})), "Genre");
        assert_eq!(label(&json!({"id": "some_new_field"})), "Some new field");
        assert!(!editable(&json!({"id": "mode", "fixed": true})));
        assert!(!editable(&json!({"id": "source.audio", "type": "upload"})));
        assert!(editable(&json!({"id": "genre", "type": "string"})));
    }

    #[test]
    fn a_text_field_emptied_goes_back_to_the_style() {
        assert_eq!(finish_text("  ", "jazz"), Some(Value::Null));
        assert_eq!(finish_text("jazz ", "jazz"), None);
        assert_eq!(finish_text("bebop", "jazz"), Some(json!("bebop")));
        assert_eq!(finish_text("", ""), None);
    }
}
