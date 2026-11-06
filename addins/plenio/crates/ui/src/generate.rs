//! Making takes: the next job from the song's plan, its files, and the take on the song's tracks.

use crate::{Pending, PlenioUi, say};
use serde_json::{Value, json};
use soundcraft_model::{ClipContent, TrackId};
use soundcraft_plenio_backend::song::ScoreInfo;
use soundcraft_plenio_backend::studio::job_body;
use soundcraft_plenio_backend::{Delivery, Request};
use soundcraft_plenio_project::{Mode, Project, Role, SongKind};
use soundcraft_ui_egui::SoundApp;
use std::path::PathBuf;

/// How the job id of a song brought in from its files starts.
const IMPORTED: &str = "imported: ";

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
            say(app, "Plenio: the studio is starting; the take follows when it is ready.");
            return;
        }
        let Ok(project) = Project::load(app.engine.session()) else {
            say(app, "Plenio: the song data of this session is not readable.");
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
                    say(app, format!("Plenio: reading your notes of {} into its score.", s.title));
                    self.studio.send(Request::Post {
                        tag: format!("score-import:{song}:{}", mode_key(mode)),
                        path: "/plenio/score/midi/import".into(),
                        body: json!({"data": soundcraft_model::b64::encode(&bytes), "chords": false}),
                    });
                }
                Err(e) => say(app, format!("Plenio: your notes could not be read: {e}")),
            }
            return;
        }
        self.submit(app, &project, song, mode);
    }

    /// Send the job for the song's plan, without further checks.
    pub fn submit(&mut self, app: &mut SoundApp, project: &Project, song: u64, mode: Mode) {
        let Some(s) = project.song(song) else { return };
        if self.jobs.values().any(|p| p.song == song) {
            say(app, format!("Plenio: a take of {} is being made already.", s.title));
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
        say(app, format!("Plenio: {} - {what}.", s.title));
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
            say(app, "Plenio: the cover has no recording track.");
            return;
        };
        let Some(path) = Self::source_file(app, track) else {
            say(app, "Plenio: the cover's recording track has no audio file on disk (save the session first, or import the recording).");
            return;
        };
        let tag = self.tag();
        self.uploads.insert(tag, song);
        say(app, "Plenio: sending the recording to the studio.");
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
            Err(e) => say(app, format!("Plenio: the recording was not sent: {e}")),
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
            say(app, "Plenio: the take came without audio.");
            return;
        };
        // A song brought in lies outside the studio, which reads only its own output.
        if d.job.id.starts_with(IMPORTED) && self.ready() {
            match self.copy_into_studio(std::path::Path::new(&audio), &format!("song-{}-{tag}", pending.song)) {
                Ok(copy) => {
                    files.insert("studio_song".into(), Value::String(copy));
                }
                Err(e) => log::warn!("Plenio: {e}"),
            }
        }
        let title = if record.title.is_empty() { d.job.title.clone() } else { record.title.clone() };
        let take = json!({
            "job": d.job.id, "title": title, "seeds": d.job.seeds, "fields": pending.fields, "documents": documents,
            "stars": record.stars, "seconds": seconds, "files": files, "sections": sections, "lines": lines,
            "bpm": info.as_ref().map(|i| i.bpm), "key": info.as_ref().map(|i| i.key.clone()).unwrap_or_default(),
            "warp": record.warp,
        });
        let meter = info.as_ref().map(|i| json!([i.meter.0, i.meter.1])).unwrap_or(Value::Null);
        let params = json!({"song": pending.song, "audio": audio, "take": take, "meter": meter, "anchors": record.anchors});
        let score = record.document("score");
        // What the add-in makes for a take lies beside the take; a song brought in may lie among others
        // in a folder that is not the add-in's.
        let folder = if d.job.id.starts_with(IMPORTED) {
            Some(self.takes_dir(app, pending.song, tag))
        } else {
            PathBuf::from(&audio).parent().map(PathBuf::from)
        };
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
        let tempo = serde_json::from_value::<soundcraft_plenio_project::BarMap>(params["take"]["bars"].clone())
            .ok()
            .filter(|b| b.usable())
            .map(|b| b.tempo_range());
        match app.run("plenio.take.add", params) {
            Ok(v) => {
                let how = match tempo {
                    Some((low, high)) => format!("the session's tempo follows its audio ({low:.1} to {high:.1} BPM)"),
                    None => "its bars could not be measured, so the session's tempo may run off its audio".to_string(),
                };
                say(app, format!("Plenio: take {} of {title} is on its tracks; {how}.", v["take"]));
            }
            Err(e) => say(app, format!("Plenio: the take could not be placed: {e}")),
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
                match std::fs::create_dir_all(&folder).and_then(|()| std::fs::write(&path, bytes)) {
                    Ok(()) => params["midi"] = json!(path.to_string_lossy()),
                    Err(e) => say(app, format!("Plenio: the score's notes were not saved: {e}")),
                }
            }
            Err(e) => say(app, format!("Plenio: the take comes without its notes: {e}")),
        }
        // Where every bar lies in the audio, which is the master: measured in the studio, from the take
        // itself and its score, near where Plenio's warp (or else its estimate) puts them.
        let take = &params["take"];
        if self.ready()
            && let (Some(file), Some(score)) = (take["files"]["studio_song"].as_str(), take["documents"]["score"].as_str())
        {
            let body = json!({"file": file, "score": score, "warp": take["warp"], "anchors": params["anchors"]});
            self.held.insert(tag, (params, folder));
            self.studio.send(Request::Post { tag: format!("beats:{tag}"), path: "/scp/v1/beats".into(), body });
            return;
        }
        Self::place(app, params);
    }

    /// The bars of a take arrived (or did not): place the take. Without them it lies on the warp's line.
    pub fn beats_found(&mut self, app: &mut SoundApp, tag: u64, result: Result<Value, String>) {
        let Some((mut params, _)) = self.held.remove(&tag) else { return };
        match result {
            Ok(answer) => {
                if params["take"]["warp"].is_null() {
                    params["take"]["warp"] = answer.get("warp").cloned().unwrap_or(Value::Null);
                }
                if let Some(bars) = answer.get("bars").filter(|b| b.is_object()) {
                    params["take"]["bars"] = bars.clone();
                    // The sections by their measures: not every measure of a song has the same length.
                    let score = params["take"]["documents"]["score"].as_str().and_then(ScoreInfo::parse);
                    let times: Vec<f64> = bars["score"].as_array().map(|a| a.iter().filter_map(Value::as_f64).collect()).unwrap_or_default();
                    if let Some(info) = score {
                        let at = |bar: u32| times.get(bar as usize).copied();
                        let sections: Vec<Value> = info
                            .sections
                            .iter()
                            .filter_map(|s| {
                                Some(json!({"name": s.name, "start": at(s.start_bar)?, "end": at(s.start_bar + s.bars).or(times.last().copied())?}))
                            })
                            .collect();
                        params["take"]["sections"] = Value::Array(sections);
                    }
                }
            }
            Err(e) => log::warn!("Plenio: the bars of this take were not measured: {e}"),
        }
        Self::place(app, params);
    }

    /// Plenio read the owner's notes into a score: make it the song's score, then the take.
    pub fn score_imported(&mut self, app: &mut SoundApp, song: u64, mode: Mode, result: Result<Value, String>) {
        let abc = match result {
            Ok(v) => v.get("abc").and_then(Value::as_str).map(str::to_string),
            Err(e) => {
                say(app, format!("Plenio: your notes could not be read: {e}"));
                return;
            }
        };
        let Some(abc) = abc.filter(|a| !a.trim().is_empty()) else {
            say(app, "Plenio: your notes gave no score.");
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
        let Some(s) = project.song(song) else { return };
        let Some(t) = s.takes.iter().find(|t| t.number == take) else { return };
        if !self.ready() {
            say(app, "Plenio: start the studio first (Plenio > Studio and Models).");
            return;
        }
        let key = if s.unmastered { "studio_original" } else { "studio_song" };
        let file = match t.files.get(key).or_else(|| t.files.get("studio_song")).cloned() {
            Some(file) => file,
            None if t.job.starts_with(IMPORTED) => match self.copy_to_studio(s, t) {
                Ok(file) => file,
                Err(e) => {
                    say(app, format!("Plenio: no stems: {e}"));
                    return;
                }
            },
            None => {
                say(app, "Plenio: this take is not in the studio any more; make a new take to split it.");
                return;
            }
        };
        say(app, format!("Plenio: splitting {} into stems.", t.label()));
        self.splitting.insert(song);
        self.studio.send(Request::Post { tag: format!("stems:{song}:{take}"), path: "/scp/v1/stems".into(), body: json!({"file": file}) });
    }

    /// A song brought in lies outside the studio, which reads only its own output: a copy for it.
    fn copy_to_studio(&self, song: &soundcraft_plenio_project::Song, take: &soundcraft_plenio_project::Take) -> Result<String, String> {
        let (first, second) = if song.unmastered { ("original", "song") } else { ("song", "original") };
        let from = PathBuf::from(take.files.get(first).or_else(|| take.files.get(second)).ok_or("the take has no audio file")?);
        self.copy_into_studio(&from, &format!("song-{}-take-{}", song.id, take.number))
    }

    /// A copy of a file in a folder of the studio's output.
    fn copy_into_studio(&self, from: &std::path::Path, folder: &str) -> Result<String, String> {
        let name = from.file_name().ok_or("the take has no audio file")?;
        let layout = soundcraft_plenio_backend::instance::Layout::new(&self.studio_root());
        let folder = layout.output().join("soundcraft-imported").join(folder);
        let to = folder.join(name);
        std::fs::create_dir_all(&folder).and_then(|()| std::fs::copy(from, &to)).map_err(|e| format!("{}: {e}", from.display()))?;
        Ok(to.to_string_lossy().into_owned())
    }

    /// The stems arrived: copy them beside the take and put them on the song's stem tracks.
    pub fn stems_done(&mut self, app: &mut SoundApp, song: u64, take: u32, result: Result<Value, String>) {
        self.splitting.remove(&song);
        let answer = match result {
            Ok(v) => v,
            Err(e) => {
                say(app, format!("Plenio: no stems: {e}"));
                return;
            }
        };
        let folder = Project::load(app.engine.session()).ok().and_then(|p| {
            let t = p.song(song)?.takes.iter().find(|t| t.number == take)?;
            let beside = if t.job.starts_with(IMPORTED) {
                self.takes_dir(app, song, u64::from(take))
            } else {
                PathBuf::from(t.files.get("song")?).parent()?.to_path_buf()
            };
            Some(beside.join("stems"))
        });
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
            Ok(_) => say(app, "Plenio: the stems are on their tracks; the mix track is muted while they play."),
            Err(e) => say(app, format!("Plenio: the stems could not be placed: {e}")),
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
            say(app, "Plenio: make a take first.");
            return;
        };
        let layout = soundcraft_plenio_backend::instance::Layout::new(&self.studio_root());
        let folder = soundcraft_plenio_backend::player::sent_folder(&layout);
        let title = format!("{} (SoundCraft mix)", if take.title.is_empty() { s.title.as_str() } else { take.title.as_str() });
        let stem = safe(&title);
        let audio = folder.join(format!("{stem}.flac"));
        if let Err(e) = std::fs::create_dir_all(&folder) {
            say(app, format!("Plenio: {}: {e}", folder.display()));
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
            say(app, format!("Plenio: the mix was not bounced: {e}"));
            return;
        }
        let from = rate.seconds(start);
        let lines: Vec<(f64, f64, String)> =
            take.lines.iter().map(|l| ((l.start - from).max(0.0), (l.end - from).max(0.0), l.text.clone())).collect();
        let srt_path = folder.join(format!("{stem} (lines).srt"));
        let srt = (!lines.is_empty() && std::fs::write(&srt_path, soundcraft_plenio_backend::player::srt(&lines)).is_ok()).then_some(srt_path);
        let record = take_record(take);
        let seconds = rate.seconds(end - start);
        match soundcraft_plenio_backend::player::write_sent_record(&record, &title, &audio, srt.as_deref(), seconds, take.audio_at - from) {
            Ok(_) => {
                say(app, format!("Plenio: {title} is in the Plenio Player."));
                self.open_player();
            }
            Err(e) => say(app, format!("Plenio: the song was not sent: {e}")),
        }
    }
}

/// A take's release record: its file, or what the take's FLAC carries.
pub(crate) fn take_record(take: &soundcraft_plenio_project::Take) -> Value {
    let from_file = || std::fs::read_to_string(take.files.get("record")?).ok().and_then(|t| serde_json::from_str::<Value>(&t).ok());
    let from_flac = || soundcraft_plenio_backend::release::read_project(std::path::Path::new(take.files.get("song")?)).ok().flatten();
    from_file().or_else(from_flac).unwrap_or(Value::Null)
}

impl PlenioUi {
    /// Bring a Plenio song into the session as a song of its own that can be made again, from any of
    /// its files: its FLAC (which carries the record) or its `.plenio.json` (a release, a party song).
    /// Plenio's `/from-record` gives the request that made it (template, fields, seeds) and the studio
    /// the notes, so the song waits for a studio that is not ready yet; the files give the take.
    pub fn import_record(&mut self, app: &mut SoundApp, path: PathBuf) {
        let found = match soundcraft_plenio_backend::release::find_song(&path) {
            Ok(found) => found,
            Err(e) => {
                let name = path.file_name().map(|n| n.to_string_lossy().into_owned()).unwrap_or_default();
                say(app, format!("Plenio: {name}: {e}"));
                return;
            }
        };
        let title = soundcraft_plenio_backend::song::Record::parse(&found.record).title;
        let tag = self.tag();
        self.imports.insert(tag, (path, found));
        if self.ready() {
            say(app, format!("Plenio: bringing in {title}."));
            self.ask_from_record(tag);
        } else if self.auto_start {
            self.waiting_imports.push(tag);
            if !matches!(self.state, soundcraft_plenio_backend::State::Starting(_)) {
                self.start_studio();
            }
            say(app, format!("Plenio: {title} comes in when the studio is ready."));
        } else {
            self.imported(app, tag, Err("the studio is not running".into()));
        }
    }

    /// Ask Plenio for the request that made a song being brought in.
    pub fn ask_from_record(&self, tag: u64) {
        if let Some((_, found)) = self.imports.get(&tag) {
            self.studio.send(Request::Post {
                tag: format!("from-record:{tag}"),
                path: "/plenio/api/v1/from-record".into(),
                body: found.record.clone(),
            });
        }
    }

    /// Plenio's answer to `/from-record` (or none): make the song and put the record's take on it.
    pub fn imported(&mut self, app: &mut SoundApp, tag: u64, request: Result<Value, String>) {
        let Some((path, found)) = self.imports.remove(&tag) else { return };
        let without = request.as_ref().err().cloned();
        let request = request.unwrap_or(Value::Null);
        let record = soundcraft_plenio_backend::song::Record::parse(&found.record);
        let template = request.get("template").and_then(Value::as_str).unwrap_or("yue2-song").to_string();
        if template != "yue2-song" && template != "yue2-cover" {
            say(app, format!("Plenio: this song was made with {template}, which the add-in does not make (no MiniMax)."));
            return;
        }
        if found.audio.is_none() && found.original.is_none() {
            let name = path.file_name().map(|n| n.to_string_lossy().into_owned()).unwrap_or_default();
            say(app, format!("Plenio: no audio beside {name}."));
            return;
        }
        let fields = request.get("fields").cloned().unwrap_or_else(|| json!({}));
        let kind = if template == "yue2-cover" { "cover" } else { "song" };
        let made = app.run("plenio.song.new", json!({"kind": kind, "template": template, "title": record.title, "fields": fields}));
        let song = match made {
            Ok(v) => v.get("song").and_then(Value::as_u64),
            Err(e) => {
                say(app, format!("Plenio: {e}"));
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
            id: format!("{IMPORTED}{}", path.display()),
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
        let title = record.title.clone();
        let delivery =
            Delivery { job, song: found.audio, original: found.original, record: Some(record), record_file: found.record_file, lines: found.lines };
        self.song = Some(song);
        self.show_inspector = true;
        self.deliver(app, tag, delivery);
        if let Some(why) = without {
            let what = if self.ready() { "its fields" } else { "its notes and its fields" };
            say(app, format!("Plenio: {title} came in without {what} ({why}); import it again when the studio runs."));
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
