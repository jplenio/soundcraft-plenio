//! Drawing on the song's tracks: the song folder's header shows the take and its state, its lane
//! the song's sections in time.

use crate::PlenioUi;
use egui::{Align2, Color32, FontId, Rect, Stroke, pos2, vec2};
use soundcraft_model::TrackId;
use soundcraft_plenio_project::{Project, Role, Song};
use soundcraft_ui_egui::SoundApp;
use soundcraft_ui_egui::extension::Lane;

/// The song a folder track is the head of.
fn song_of(app: &SoundApp, track: TrackId) -> Option<Song> {
    let project = Project::load(app.engine.session()).ok()?;
    let (song, role) = project.role_of(track)?;
    (role == Role::Song).then(|| song.clone())
}

/// `Plenio · Take 2 · 4 stars (of 3) · changed: lyrics` or `Plenio · composing 43 %`.
pub fn badge(ui_state: &PlenioUi, song: &Song) -> String {
    if let Some(p) = ui_state.jobs.values().find(|p| p.song == song.id) {
        let stage = p.job.as_ref().map(|j| j.stage.clone()).filter(|s| !s.is_empty()).unwrap_or_else(|| "starting".into());
        let percent = p.job.as_ref().and_then(|j| j.progress).map(|f| format!(" {:.0} %", f * 100.0)).unwrap_or_default();
        return format!("Plenio · {stage}{percent}");
    }
    if ui_state.waiting.iter().any(|(s, _, _)| *s == song.id) {
        return "Plenio · waiting for the studio".into();
    }
    let take = match (song.active_take(), song.takes.len()) {
        (Some(t), n) => format!("{} (of {n})", t.label()),
        (None, _) => "no take yet".into(),
    };
    let changes = song.changes();
    if changes.is_empty() { format!("Plenio · {take}") } else { format!("Plenio · {take} · changed: {}", changes.join(", ")) }
}

pub fn header(ui_state: &mut PlenioUi, app: &mut SoundApp, ui: &mut egui::Ui, track: TrackId, head: Rect) {
    let Some(song) = song_of(app, track) else { return };
    let text = badge(ui_state, &song);
    let font = FontId::proportional(10.0);
    let at = pos2(head.min.x + 10.0, head.max.y - 4.0);
    let color = if song.changes().is_empty() { ui.visuals().weak_text_color() } else { ui.visuals().warn_fg_color };
    let galley = ui.painter().layout_no_wrap(text.clone(), font.clone(), color);
    let width = galley.size().x.min(head.width() - 14.0);
    let back = Rect::from_min_size(pos2(at.x - 2.0, at.y - galley.size().y - 1.0), vec2(width + 4.0, galley.size().y + 2.0));
    let painter = ui.painter().with_clip_rect(head);
    painter.rect_filled(back, 3.0, ui.visuals().extreme_bg_color.gamma_multiply(0.85));
    painter.text(at, Align2::LEFT_BOTTOM, text, font, color);
}

/// The section's colour: one hue per kind of section, so verses and choruses tell apart.
fn section_color(name: &str) -> Color32 {
    let n = name.to_ascii_lowercase();
    let (r, g, b) = if n.contains("chorus") || n.contains("hook") {
        (214, 96, 120)
    } else if n.contains("verse") {
        (86, 140, 214)
    } else if n.contains("bridge") {
        (170, 120, 214)
    } else if n.contains("intro") || n.contains("outro") {
        (110, 170, 140)
    } else {
        (196, 160, 80)
    };
    Color32::from_rgba_unmultiplied(r, g, b, 150)
}

pub fn lane(_ui_state: &mut PlenioUi, app: &mut SoundApp, painter: &egui::Painter, lane: &Lane<'_>) {
    let Some(song) = song_of(app, lane.track) else { return };
    let Some(take) = song.active_take() else {
        painter.text(
            lane.rect.left_center() + vec2(8.0, 0.0),
            Align2::LEFT_CENTER,
            "Plenio song - no take yet",
            FontId::proportional(12.0),
            Color32::GRAY,
        );
        return;
    };
    let rate = lane.session().sample_rate;
    let band = Rect::from_min_max(
        pos2(lane.rect.min.x, lane.rect.min.y + 2.0),
        pos2(lane.rect.max.x, lane.rect.min.y + 20.0f32.min(lane.rect.height() - 2.0)),
    );
    for s in &take.sections {
        let (a, b) = (rate.samples(s.start), rate.samples(s.end));
        if b < lane.view.start || a > lane.view.end {
            continue;
        }
        let r = Rect::from_min_max(pos2(lane.x_of(a), band.min.y), pos2(lane.x_of(b), band.max.y));
        let r = r.intersect(lane.rect);
        if r.width() < 1.0 {
            continue;
        }
        painter.rect_filled(r, 3.0, section_color(&s.name));
        painter.rect_stroke(r, 3.0, Stroke::new(1.0, Color32::from_black_alpha(90)), egui::StrokeKind::Inside);
        if r.width() > 24.0 {
            painter.with_clip_rect(r).text(
                r.left_center() + vec2(4.0, 0.0),
                Align2::LEFT_CENTER,
                &s.name,
                FontId::proportional(11.0),
                Color32::WHITE,
            );
        }
    }
}
