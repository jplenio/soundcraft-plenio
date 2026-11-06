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
        let what = if s.kind == SongKind::Cover && plan.what == soundcraft_plenio_project::What::NewSong {
            "read the recording, then write and render the cover"
        } else {
            plan.what.label()
        };
        app.engine.message(format!("Plenio: {} - {what}.", s.title));
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
                        json!({"name": s.name, "start": start, "end": start + f64::from(s.bars) * bar})
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
        // The take as the studio keeps it, for the stems (the studio reads only its own output).
        let studio_file = |f: Option<&soundcraft_plenio_backend::song::JobFile>| {
            f.filter(|_| !d.job.folder.is_empty()).map(|f| PathBuf::from(&d.job.folder).join(&f.name).to_string_lossy().into_owned())
        };
        if let Some(p) = studio_file(d.job.file("")) {
            files.insert("studio_song".into(), Value::String(p));
        }
        if let Some(p) = studio_file(d.job.file("original")) {
            files.insert("studio_original".into(), Value::String(p));
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
            "warp": record.warp,
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
        // No measurement (a song without words has nothing to measure by): Plenio's estimate from the
        // music, as its Player makes it.
        let take = &params["take"];
        if take["warp"].is_null()
            && self.ready()
            && let (Some(file), Some(score)) = (take["files"]["studio_song"].as_str(), take["documents"]["score"].as_str())
        {
            let body = json!({"file": file, "score": score});
            self.held.insert(tag, (params, folder));
            self.studio.send(Request::Post { tag: format!("align:{tag}"), path: "/scp/v1/align".into(), body });
            return;
        }
        Self::place(app, params);
    }

    /// Plenio's estimate of where the score sits in a take arrived (or did not): place the take.
    pub fn aligned(&mut self, app: &mut SoundApp, tag: u64, result: Result<Value, String>) {
        let Some((mut params, _)) = self.held.remove(&tag) else { return };
        match result.map(|v| v.get("warp").cloned().unwrap_or(Value::Null)) {
            Ok(warp) if !warp.is_null() => params["take"]["warp"] = warp,
            Ok(_) => app.engine.message("Plenio: the music of this take does not tell where its score sits; the notes lie as written."),
            Err(e) => app.engine.message(format!("Plenio: where the score sits in this take was not found ({e}); the notes lie as written.")),
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

impl PlenioUi {
    /// Split a take into stems in the studio (Plenio's separation), then put them on stem tracks.
    pub fn split_stems(&mut self, app: &mut SoundApp, song: u64, take: u32) {
        let Ok(project) = Project::load(app.engine.session()) else { return };
        let Some(t) = project.song(song).and_then(|s| s.takes.iter().find(|t| t.number == take)) else { return };
        let key = if project.song(song).is_some_and(|s| s.unmastered) { "studio_original" } else { "studio_song" };
        let Some(file) = t.files.get(key).or_else(|| t.files.get("studio_song")).cloned() else {
            app.engine.message("Plenio: this take is not in the studio any more; make a new take to split it.");
            return;
        };
        if !self.ready() {
            app.engine.message("Plenio: start the studio first (Plenio > Studio and Models).");
            return;
        }
        app.engine.message(format!("Plenio: splitting {} into stems.", t.label()));
        self.splitting.insert(song);
        self.studio.send(Request::Post { tag: format!("stems:{song}:{take}"), path: "/scp/v1/stems".into(), body: json!({"file": file}) });
    }

    /// The stems arrived: copy them beside the take and put them on the song's stem tracks.
    pub fn stems_done(&mut self, app: &mut SoundApp, song: u64, take: u32, result: Result<Value, String>) {
        self.splitting.remove(&song);
        let answer = match result {
            Ok(v) => v,
            Err(e) => {
                app.engine.message(format!("Plenio: no stems: {e}"));
                return;
            }
        };
        let folder = Project::load(app.engine.session())
            .ok()
            .and_then(|p| p.song(song)?.takes.iter().find(|t| t.number == take)?.files.get("song").cloned())
            .and_then(|f| PathBuf::from(f).parent().map(|p| p.join("stems")));
        let mut stems = Vec::new();
        for name in answer.get("order").and_then(Value::as_array).into_iter().flatten().filter_map(Value::as_str) {
            let Some(from) = answer.get("stems").and_then(|s| s.get(name)).and_then(Value::as_str) else { continue };
            let from = PathBuf::from(from);
            let path = match &folder {
                Some(dir) => {
                    let to = dir.join(format!("{name}.flac"));
                    match std::fs::create_dir_all(dir).and_then(|()| std::fs::copy(&from, &to)) {
                        Ok(_) => to,
                        Err(_) => from,
                    }
                }
                None => from,
            };
            stems.push(json!([name, path.to_string_lossy()]));
        }
        match app.run("plenio.stems.add", json!({"song": song, "take": take, "stems": stems})) {
            Ok(_) => app.engine.message("Plenio: the stems are on their tracks; the mix track is muted while they play."),
            Err(e) => app.engine.message(format!("Plenio: the stems could not be placed: {e}")),
        }
    }
}

impl PlenioUi {
    pub fn open_player(&self) {
        self.studio.send(Request::Player { config_dir: self.studio_root(), comfyui: self.settings.comfyui.clone() });
    }

    /// Bounce the session's mix (with the owner's effects) and send it to the Plenio Player with the
    /// take's lyrics, score and story: a release record made from the take's.
    pub fn send_to_player(&mut self, app: &mut SoundApp, song: u64) {
        let Ok(project) = Project::load(app.engine.session()) else { return };
        let Some(s) = project.song(song) else { return };
        let Some(take) = s.active_take() else {
            app.engine.message("Plenio: make a take first.");
            return;
        };
        let layout = soundcraft_plenio_backend::instance::Layout::new(&self.studio_root());
        let folder = soundcraft_plenio_backend::player::sent_folder(&layout);
        let title = format!("{} (SoundCraft mix)", if take.title.is_empty() { s.title.as_str() } else { take.title.as_str() });
        let stem = safe(&title);
        let audio = folder.join(format!("{stem}.flac"));
        if let Err(e) = std::fs::create_dir_all(&folder) {
            app.engine.message(format!("Plenio: {}: {e}", folder.display()));
            return;
        }
        let session = app.engine.session();
        let rate = session.sample_rate;
        let end = session.content_end().max(rate.samples(take.audio_at + take.seconds)).max(1);
        // The mix starts where the session's sound starts: no silence before a take that was moved to
        // meet its score.
        let start = session.tracks.iter().filter(|t| !t.mixer.mute).flat_map(|t| t.clips()).map(|c| c.start).min().unwrap_or(0).clamp(0, end - 1);
        if let Err(e) =
            app.run("file.bounce_mix", json!({"path": audio.to_string_lossy(), "format": "flac", "bit_depth": 24, "start": start, "end": end}))
        {
            app.engine.message(format!("Plenio: the mix was not bounced: {e}"));
            return;
        }
        let from = rate.seconds(start);
        let lines: Vec<(f64, f64, String)> =
            take.lines.iter().map(|l| ((l.start - from).max(0.0), (l.end - from).max(0.0), l.text.clone())).collect();
        let srt_path = folder.join(format!("{stem} (lines).srt"));
        let srt = (!lines.is_empty() && std::fs::write(&srt_path, soundcraft_plenio_backend::player::srt(&lines)).is_ok()).then_some(srt_path);
        let record = take
            .files
            .get("record")
            .and_then(|p| std::fs::read_to_string(p).ok())
            .and_then(|t| serde_json::from_str::<Value>(&t).ok())
            .unwrap_or(Value::Null);
        let seconds = rate.seconds(end - start);
        match soundcraft_plenio_backend::player::write_sent_record(&record, &title, &audio, srt.as_deref(), seconds, take.audio_at - from) {
            Ok(_) => {
                app.engine.message(format!("Plenio: {title} is in the Plenio Player."));
                self.open_player();
            }
            Err(e) => app.engine.message(format!("Plenio: the song was not sent: {e}")),
        }
    }
}

/// The largest release record read.
const MAX_RECORD_BYTES: u64 = 32 * 1024 * 1024;

impl PlenioUi {
    /// Bring a Plenio song (its `.plenio.json` and the files beside it: a release, a party song) into
    /// the session as a song of its own that can be made again: Plenio's `/from-record` gives the
    /// request that made it (template, fields, seeds), the files give the take.
    pub fn import_record(&mut self, app: &mut SoundApp, path: PathBuf) {
        let text = match std::fs::metadata(&path) {
            Ok(m) if m.len() <= MAX_RECORD_BYTES => std::fs::read_to_string(&path).map_err(|e| e.to_string()),
            Ok(_) => Err("the record is too large".into()),
            Err(e) => Err(e.to_string()),
        };
        let record = match text.and_then(|t| serde_json::from_str::<Value>(&t).map_err(|e| e.to_string())) {
            Ok(v) if v.get("schema").and_then(Value::as_str).is_some_and(|s| s.starts_with("plenio.record/")) => v,
            Ok(_) => {
                app.engine.message("Plenio: that file is not a Plenio release record.");
                return;
            }
            Err(e) => {
                app.engine.message(format!("Plenio: {}: {e}", path.display()));
                return;
            }
        };
        let tag = self.tag();
        self.imports.insert(tag, (path, record.clone()));
        if self.ready() {
            self.studio.send(Request::Post { tag: format!("from-record:{tag}"), path: "/plenio/api/v1/from-record".into(), body: record });
        } else {
            // Without the studio: the documents and the take, the brief's fields come later.
            self.imported(app, tag, Err("the studio is not running".into()));
        }
    }

    /// Plenio's answer to `/from-record` (or none): make the song and put the record's take on it.
    pub fn imported(&mut self, app: &mut SoundApp, tag: u64, request: Result<Value, String>) {
        let Some((path, record_json)) = self.imports.remove(&tag) else { return };
        let request = request.unwrap_or_else(|e| {
            log::info!("Plenio: importing without /from-record: {e}");
            Value::Null
        });
        let record = soundcraft_plenio_backend::song::Record::parse(&record_json);
        let template = request.get("template").and_then(Value::as_str).unwrap_or("yue2-song").to_string();
        if template != "yue2-song" && template != "yue2-cover" {
            app.engine.message(format!("Plenio: this song was made with {template}, which the add-in does not make (no MiniMax)."));
            return;
        }
        let folder = path.parent().map(PathBuf::from).unwrap_or_default();
        let stem = path.file_name().map(|n| n.to_string_lossy().trim_end_matches(".plenio.json").to_string()).unwrap_or_default();
        let audio = ["flac", "wav", "mp3"].iter().map(|ext| folder.join(format!("{stem}.{ext}"))).find(|p| p.is_file());
        let Some(audio) = audio else {
            app.engine.message(format!("Plenio: no audio beside {}", path.display()));
            return;
        };
        let original = Some(folder.join(format!("{stem} (original).flac"))).filter(|p| p.is_file());
        let lines = std::fs::read_to_string(folder.join(format!("{stem} (lines).srt")))
            .map(|t| soundcraft_plenio_backend::song::parse_srt(&t))
            .unwrap_or_default();
        let fields = request.get("fields").cloned().unwrap_or_else(|| json!({}));
        let kind = if template == "yue2-cover" { "cover" } else { "song" };
        let made = app.run("plenio.song.new", json!({"kind": kind, "template": template, "title": record.title, "fields": fields}));
        let song = match made {
            Ok(v) => v.get("song").and_then(Value::as_u64),
            Err(e) => {
                app.engine.message(format!("Plenio: {e}"));
                return;
            }
        };
        let Some(song) = song else { return };
        // A cover's recording: the name it had in the studio, when that studio still has it.
        if let Some(source) = request.get("fields").and_then(|f| f.get("source.audio")).and_then(Value::as_str) {
            let _ = app.run("plenio.song.set", json!({"song": song, "source": source}));
        }
        let seeds: std::collections::BTreeMap<String, u64> = request
            .get("seeds")
            .and_then(Value::as_object)
            .map(|m| m.iter().filter_map(|(k, v)| Some((k.clone(), v.as_u64()?))).collect())
            .unwrap_or_default();
        let job = soundcraft_plenio_backend::song::Job {
            id: format!("imported: {}", path.display()),
            status: soundcraft_plenio_backend::song::JobStatus::Succeeded,
            queue_position: None,
            stage: String::new(),
            progress: None,
            seeds,
            title: record.title.clone(),
            seconds: record.seconds,
            folder: String::new(),
            files: Vec::new(),
            error: String::new(),
            warnings: Vec::new(),
        };
        let fields_map = fields.as_object().map(|m| m.iter().map(|(k, v)| (k.clone(), v.clone())).collect()).unwrap_or_default();
        let tag = self.tag();
        self.jobs.insert(tag, Pending { song, what: soundcraft_plenio_project::What::NewTake, fields: fields_map, job: None });
        let delivery = Delivery { job, song: Some(audio), original, record: Some(record), record_file: Some(path), lines };
        self.song = Some(song);
        self.show_inspector = true;
        self.deliver(app, tag, delivery);
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
