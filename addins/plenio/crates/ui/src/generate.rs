//! Making takes: the next job from the song's plan, its files, and the take on the song's tracks.

use crate::{Pending, PlenioUi};
use serde_json::{Value, json};
use soundcraft_model::{ClipContent, TrackId};
use soundcraft_plenio_backend::song::ScoreInfo;
use soundcraft_plenio_backend::studio::job_body;
use soundcraft_plenio_backend::{Delivery, Request};
use soundcraft_plenio_project::{Mode, Project, Role, SongKind};
use soundcraft_ui_egui::SoundApp;
use std::path::PathBuf;

impl PlenioUi {
    /// Ask the studio for the next take of `song`.
    pub fn generate(&mut self, app: &mut SoundApp, song: u64, mode: Mode) {
        if !self.ready() {
            if !self.waiting.iter().any(|(s, _)| *s == song) {
                self.waiting.push((song, mode));
            }
            if !matches!(self.state, soundcraft_plenio_backend::State::Starting(_)) {
                self.start_studio();
            }
            app.engine.message("Plenio: the studio is starting; the take follows when it is ready.");
            return;
        }
        let Ok(project) = Project::load(app.engine.session()) else {
            app.engine.message("Plenio: the song data of this session is not readable.");
            return;
        };
        let Some(s) = project.song(song) else { return };
        if s.kind == SongKind::Cover && s.source.is_none() {
            self.upload_source(app, song);
            return;
        }
        // Notes changed on the score tracks: Plenio reads them back into the score first.
        if mode != Mode::Recompose
            && mode != Mode::Rewrite
            && let Some(file) = soundcraft_plenio_commands::notes_for_plenio(app.engine.session(), s)
        {
            match file {
                Ok(bytes) => {
                    app.engine.message(format!("Plenio: reading your notes of {} into its score.", s.title));
                    self.studio.send(Request::Post {
                        tag: format!("score-import:{song}:{}", mode_key(mode)),
                        path: "/plenio/score/midi/import".into(),
                        body: json!({"data": soundcraft_model::b64::encode(&bytes), "chords": false}),
                    });
                }
                Err(e) => app.engine.message(format!("Plenio: your notes could not be read: {e}")),
            }
            return;
        }
        self.submit(app, &project, song, mode);
    }

    /// Send the job for the song's plan, without further checks.
    pub fn submit(&mut self, app: &mut SoundApp, project: &Project, song: u64, mode: Mode) {
        let Some(s) = project.song(song) else { return };
        if self.jobs.values().any(|p| p.song == song) {
            app.engine.message(format!("Plenio: a take of {} is being made already.", s.title));
            return;
        }
        let plan = s.plan(mode);
        let fields: serde_json::Map<String, Value> = plan.fields.clone().into_iter().collect();
        let documents: serde_json::Map<String, Value> = plan.documents.iter().map(|(k, v)| (k.clone(), Value::String(v.clone()))).collect();
        let seeds: serde_json::Map<String, Value> = plan.seeds.iter().map(|(k, v)| (k.clone(), json!(v))).collect();
        let body = job_body(&s.template, &Value::Object(fields), &Value::Object(documents), &Value::Object(seeds));
        let tag = self.tag();
        let into = self.takes_dir(app, song, tag);
        app.engine.message(format!("Plenio: {} - {}.", s.title, plan.what.label()));
        self.jobs.insert(tag, Pending { song, what: plan.what, fields: plan.fields, job: None });
        self.studio.send(Request::Submit { tag, body, into });
    }

    /// Where a take's files go: beside the session when it is saved, else in the add-in's folder.
    fn takes_dir(&self, app: &SoundApp, song: u64, tag: u64) -> PathBuf {
        let stamp = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).map_or(0, |d| d.as_secs());
        let base = match &app.engine.session().folder {
            Some(folder) => folder.join("Plenio"),
            None => self.studio_root().join("Plenio").join("takes").join(safe(&app.engine.session().name)),
        };
        base.join(format!("song-{song}")).join(format!("{stamp}-{tag}"))
    }

    /// Cancel the take being made of `song`.
    pub fn cancel(&mut self, song: u64) {
        let ids: Vec<String> = self.jobs.values().filter(|p| p.song == song).filter_map(|p| p.job.as_ref().map(|j| j.id.clone())).collect();
        for job in ids {
            self.studio.send(Request::Cancel { job });
        }
        self.waiting.retain(|(s, _)| *s != song);
    }

    /// A cover's recording: the audio file under the first clip of its source track.
    fn source_file(app: &SoundApp, track: TrackId) -> Option<PathBuf> {
        let s = app.engine.session();
        let clip = s.track(track)?.clips().first()?.clone();
        let ClipContent::Audio { source, .. } = clip.content else { return None };
        let path = s.sources.iter().find(|x| x.id == source)?.path.clone();
        let path = PathBuf::from(path);
        let path = if path.is_relative() { s.folder.as_ref().map_or(path.clone(), |f| f.join(&path)) } else { path };
        path.is_file().then_some(path)
    }

    fn upload_source(&mut self, app: &mut SoundApp, song: u64) {
        let Ok(project) = Project::load(app.engine.session()) else { return };
        let Some(track) = project.song(song).and_then(|s| s.track(Role::Source)) else {
            app.engine.message("Plenio: the cover has no recording track.");
            return;
        };
        let Some(path) = Self::source_file(app, track) else {
            app.engine.message("Plenio: the cover's recording track has no audio file on disk (save the session first, or import the recording).");
            return;
        };
        let tag = self.tag();
        self.uploads.insert(tag, song);
        app.engine.message("Plenio: sending the recording to the studio.");
        self.studio.send(Request::Upload { tag, path });
    }

    pub fn uploaded(&mut self, app: &mut SoundApp, tag: u64, result: Result<String, String>) {
        let Some(song) = self.uploads.remove(&tag) else { return };
        match result {
            Ok(name) => {
                if app.run("plenio.song.set", json!({"song": song, "source": name})).is_ok() {
                    self.generate(app, song, Mode::Auto);
                }
            }
            Err(e) => app.engine.message(format!("Plenio: the recording was not sent: {e}")),
        }
    }

    /// A take arrived: put it on the song's tracks.
    pub fn deliver(&mut self, app: &mut SoundApp, tag: u64, d: Delivery) {
        let Some(pending) = self.jobs.remove(&tag) else { return };
        let record = d.record.clone().unwrap_or_default();
        let info = ScoreInfo::parse(record.document("score"));
        let seconds = if record.seconds > 0.0 { record.seconds } else { d.job.seconds };
        let sections: Vec<Value> = info
            .as_ref()
            .map(|i| {
                let bar = i.bar_seconds();
                i.sections
                    .iter()
                    .map(|s| {
                        let start = f64::from(s.start_bar) * bar;
                        let end = (start + f64::from(s.bars) * bar).min(if seconds > 0.0 { seconds } else { f64::MAX });
                        json!({"name": s.name, "start": start, "end": end.max(start)})
                    })
                    .collect()
            })
            .unwrap_or_default();
        let lines: Vec<Value> = d.lines.iter().map(|c| json!({"start": c.start, "end": c.end, "text": c.text})).collect();
        let documents: serde_json::Map<String, Value> = record.documents.iter().map(|(k, v)| (k.clone(), Value::String(v.text.clone()))).collect();
        let path = |p: &Option<PathBuf>| p.as_ref().map(|p| p.to_string_lossy().into_owned());
        let mut files = serde_json::Map::new();
        for (role, p) in [("song", path(&d.song)), ("original", path(&d.original)), ("record", path(&d.record_file))] {
            if let Some(p) = p {
                files.insert(role.into(), Value::String(p));
            }
        }
        let unmastered = Project::load(app.engine.session()).ok().and_then(|p| p.song(pending.song).map(|s| s.unmastered)).unwrap_or(false);
        let audio = if unmastered { path(&d.original).or(path(&d.song)) } else { path(&d.song).or(path(&d.original)) };
        let Some(audio) = audio else {
            app.engine.message("Plenio: the take came without audio.");
            return;
        };
        let title = if record.title.is_empty() { d.job.title.clone() } else { record.title.clone() };
        let take = json!({
            "job": d.job.id, "title": title, "seeds": d.job.seeds, "fields": pending.fields, "documents": documents,
            "stars": record.stars, "seconds": seconds, "files": files, "sections": sections, "lines": lines,
            "bpm": info.as_ref().map(|i| i.bpm), "key": info.as_ref().map(|i| i.key.clone()).unwrap_or_default(),
        });
        let meter = info.as_ref().map(|i| json!([i.meter.0, i.meter.1])).unwrap_or(Value::Null);
        let params = json!({"song": pending.song, "audio": audio, "take": take, "meter": meter});
        let score = record.document("score");
        let folder = PathBuf::from(&audio).parent().map(PathBuf::from);
        if !score.trim().is_empty()
            && self.ready()
            && let Some(folder) = folder
        {
            // The score's notes come as Plenio's MIDI file; the take is placed when it is here.
            self.held.insert(tag, (params, folder));
            self.studio.send(Request::Post {
                tag: format!("midi:{tag}"),
                path: "/plenio/score/midi/export".into(),
                body: json!({"abc": score, "title": title}),
            });
            return;
        }
        Self::place(app, params);
    }

    fn place(app: &mut SoundApp, params: Value) {
        let title = params["take"]["title"].as_str().unwrap_or_default().to_string();
        match app.run("plenio.take.add", params) {
            Ok(v) => app.engine.message(format!("Plenio: take {} of {title} is on its tracks.", v["take"])),
            Err(e) => app.engine.message(format!("Plenio: the take could not be placed: {e}")),
        }
    }

    /// Plenio's MIDI file of a take's score arrived (or did not): place the take with it.
    pub fn score_midi(&mut self, app: &mut SoundApp, tag: u64, result: Result<Value, String>) {
        let Some((mut params, folder)) = self.held.remove(&tag) else { return };
        let bytes = result.and_then(|v| {
            v.get("data").and_then(Value::as_str).and_then(soundcraft_model::b64::decode).ok_or_else(|| "the MIDI file came empty".to_string())
        });
        match bytes {
            Ok(bytes) => {
                let path = folder.join("score.mid");
                match std::fs::write(&path, bytes) {
                    Ok(()) => params["midi"] = json!(path.to_string_lossy()),
                    Err(e) => app.engine.message(format!("Plenio: the score's notes were not saved: {e}")),
                }
            }
            Err(e) => app.engine.message(format!("Plenio: the take comes without its notes: {e}")),
        }
        Self::place(app, params);
    }

    /// Plenio read the owner's notes into a score: make it the song's score, then the take.
    pub fn score_imported(&mut self, app: &mut SoundApp, song: u64, mode: Mode, result: Result<Value, String>) {
        let abc = match result {
            Ok(v) => v.get("abc").and_then(Value::as_str).map(str::to_string),
            Err(e) => {
                app.engine.message(format!("Plenio: your notes could not be read: {e}"));
                return;
            }
        };
        let Some(abc) = abc.filter(|a| !a.trim().is_empty()) else {
            app.engine.message("Plenio: your notes gave no score.");
            return;
        };
        if app.run("plenio.song.set", json!({"song": song, "documents": {"score": abc}})).is_err() {
            return;
        }
        if let Ok(project) = Project::load(app.engine.session()) {
            self.submit(app, &project, song, mode);
        }
    }
}

pub fn mode_key(mode: Mode) -> &'static str {
    match mode {
        Mode::Auto => "auto",
        Mode::NewTake => "take",
        Mode::Recompose => "recompose",
        Mode::Rewrite => "rewrite",
    }
}

pub fn mode_from(key: &str) -> Mode {
    match key {
        "take" => Mode::NewTake,
        "recompose" => Mode::Recompose,
        "rewrite" => Mode::Rewrite,
        _ => Mode::Auto,
    }
}

/// A folder name from a session name.
fn safe(name: &str) -> String {
    let s: String = name.chars().map(|c| if c.is_alphanumeric() || c == '-' || c == ' ' { c } else { '_' }).take(80).collect();
    let s = s.trim().to_string();
    if s.is_empty() { "Untitled".into() } else { s }
}
