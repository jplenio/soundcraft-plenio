//! The studio: the add-in's ComfyUI instance and everything sent to it, run on background threads.
//! The UI sends [`Request`]s and reads [`Event`]s once a frame; nothing here blocks the UI.

use crate::client::{ApiError, Client, MAX_FILE_BYTES};
use crate::discover::{self, Install};
use crate::instance::{self, Instance, Layout};
use crate::song::{Cue, Job, Record, parse_srt};
use serde_json::{Value, json};
use std::path::PathBuf;
use std::sync::mpsc::{Receiver, RecvTimeoutError, Sender, channel};
use std::time::{Duration, Instant};

/// How long a starting ComfyUI may take before the add-in gives up (the first start loads every
/// custom node and imports PyTorch).
pub const START_TIMEOUT: Duration = Duration::from_secs(300);
/// How long one long-poll of a job waits on the server.
const WAIT_S: u32 = 30;
/// How often the worker looks whether its ComfyUI still runs while nothing is asked of it.
const HEALTH_CHECK: Duration = Duration::from_secs(2);

/// What the studio is doing.
#[derive(Debug, Clone, PartialEq)]
pub enum State {
    Stopped,
    Starting(String),
    Ready { port: u16, plenio: String, comfyui: String },
    Failed(String),
}

/// A request to the studio.
#[derive(Debug, Clone)]
pub enum Request {
    /// Find ComfyUI, install the add-in's package into its instance, start it and wait for it.
    Start {
        config_dir: PathBuf,
        comfyui: Option<PathBuf>,
    },
    /// Use an instance that already runs (tests, a studio on another port).
    Attach {
        port: u16,
    },
    Stop,
    /// `GET` a JSON answer, returned as [`Event::Answer`] with the tag.
    Get {
        tag: String,
        path: String,
    },
    /// `POST` JSON (Plenio's own routes, such as the lyrics check), answered like [`Request::Get`].
    Post {
        tag: String,
        path: String,
        body: Value,
    },
    /// Make a song: `POST /jobs`, follow the job, and when it succeeds download its files into `into`.
    Submit {
        tag: u64,
        body: Value,
        into: PathBuf,
    },
    Cancel {
        job: String,
    },
    /// Upload a cover's recording; answered with [`Event::Uploaded`].
    Upload {
        tag: u64,
        path: PathBuf,
    },
    /// Start the Plenio Player (when it does not run) on the studio's output; answered with
    /// [`Event::Player`].
    Player {
        config_dir: PathBuf,
        comfyui: Option<PathBuf>,
    },
    /// Download model files (`url`, target, expected bytes).
    DownloadModels {
        files: Vec<(String, PathBuf, u64)>,
    },
}

/// A finished take, its files on disk.
#[derive(Debug, Clone, PartialEq)]
pub struct Delivery {
    pub job: Job,
    /// The song as released (mastered).
    pub song: Option<PathBuf>,
    /// The unmastered take.
    pub original: Option<PathBuf>,
    pub record: Option<Record>,
    pub record_file: Option<PathBuf>,
    /// The lyrics' lines as sung, when the song has words.
    pub lines: Vec<Cue>,
}

/// What the studio reports.
#[derive(Debug, Clone)]
pub enum Event {
    State(State),
    Answer {
        tag: String,
        result: Result<Value, String>,
    },
    Job {
        tag: u64,
        job: Job,
    },
    Delivered {
        tag: u64,
        delivery: Box<Delivery>,
    },
    Uploaded {
        tag: u64,
        result: Result<String, String>,
    },
    /// The Plenio Player's address, or why it does not run.
    Player(Result<String, String>),
    ModelProgress {
        file: String,
        done: u64,
        total: u64,
    },
    ModelDone {
        file: String,
        result: Result<(), String>,
    },
    Failed {
        tag: Option<u64>,
        message: String,
    },
}

/// The handle the UI keeps.
pub struct Studio {
    tx: Sender<Request>,
    rx: Receiver<Event>,
}

impl Drop for Studio {
    /// Stop the instance when SoundCraft closes (it holds GPU memory); the add-in's package also
    /// ends it by itself when SoundCraft is gone (`SCP_PARENT_PID`).
    fn drop(&mut self) {
        let _ = self.tx.send(Request::Stop);
        let deadline = Instant::now() + Duration::from_secs(5);
        while Instant::now() < deadline {
            match self.rx.recv_timeout(Duration::from_millis(200)) {
                Ok(Event::State(State::Stopped)) | Err(std::sync::mpsc::RecvTimeoutError::Disconnected) => break,
                _ => {}
            }
        }
    }
}

impl Studio {
    /// Start the studio's worker thread (it starts no ComfyUI until asked).
    pub fn spawn() -> Studio {
        let (tx, requests) = channel::<Request>();
        let (events, rx) = channel::<Event>();
        let spawned = std::thread::Builder::new()
            .name("plenio-studio".into())
            .spawn(move || Worker { events, instance: None, client: None, player: None, install: None }.run(requests));
        if let Err(e) = spawned {
            log::error!("Plenio studio thread not started: {e}");
        }
        Studio { tx, rx }
    }

    pub fn send(&self, request: Request) {
        if self.tx.send(request).is_err() {
            log::warn!("Plenio studio: the worker thread is gone");
        }
    }

    /// Every event since the last call, without waiting.
    pub fn poll(&self) -> Vec<Event> {
        self.rx.try_iter().take(1000).collect()
    }

    /// Wait for the next event (tests and tools; never on the UI thread).
    pub fn wait(&self, timeout: Duration) -> Option<Event> {
        self.rx.recv_timeout(timeout).ok()
    }
}

struct Worker {
    events: Sender<Event>,
    instance: Option<Instance>,
    client: Option<Client>,
    player: Option<crate::player::Player>,
    /// The ComfyUI the instance runs on.
    install: Option<Install>,
}

impl Worker {
    fn emit(&self, event: Event) {
        let _ = self.events.send(event);
    }

    fn run(mut self, requests: Receiver<Request>) {
        loop {
            match requests.recv_timeout(HEALTH_CHECK) {
                Ok(request) => self.handle(request),
                Err(RecvTimeoutError::Timeout) => {}
                Err(RecvTimeoutError::Disconnected) => break,
            }
            // A studio that ended by itself (out of memory, closed from outside) is reported, also
            // while nothing is asked of it.
            if let Some(instance) = &mut self.instance
                && let Some(how) = instance.ended()
            {
                self.instance = None;
                self.client = None;
                self.emit(Event::State(State::Failed(format!(
                    "ComfyUI ended ({how}); its log is comfyui.log in the add-in's folder. Start it again in Plenio › Studio and Models…"
                ))));
            }
        }
        self.stop();
    }

    fn handle(&mut self, request: Request) {
        match request {
            Request::Start { config_dir, comfyui } => self.start(&config_dir, comfyui.as_deref()),
            Request::Attach { port } => self.attach(port),
            Request::Stop => {
                self.stop();
                self.emit(Event::State(State::Stopped));
            }
            Request::Get { tag, path } => {
                let result = self.client().and_then(|c| c.get(&path).map_err(|e| e.to_string()));
                self.emit(Event::Answer { tag, result });
            }
            Request::Post { tag, path, body } => {
                let result = self.client().and_then(|c| c.post(&path, &body, None).map_err(|e| e.to_string()));
                self.emit(Event::Answer { tag, result });
            }
            Request::Submit { tag, body, into } => match self.client() {
                Ok(client) => {
                    let events = self.events.clone();
                    let _ = std::thread::Builder::new().name("plenio-job".into()).spawn(move || follow(&client, &events, tag, &body, &into));
                }
                Err(message) => self.emit(Event::Failed { tag: Some(tag), message }),
            },
            Request::Cancel { job } => {
                if let Ok(client) = self.client()
                    && let Err(e) = client.delete(&format!("/plenio/api/v1/jobs/{}", encode_segment(&job)))
                {
                    self.emit(Event::Failed { tag: None, message: e.to_string() });
                }
            }
            Request::Upload { tag, path } => {
                let result = self.client().and_then(|c| {
                    c.upload(&path)
                        .map_err(|e| e.to_string())
                        .and_then(|v| v.get("name").and_then(Value::as_str).map(str::to_string).ok_or_else(|| "the upload has no name".into()))
                });
                self.emit(Event::Uploaded { tag, result });
            }
            Request::Player { config_dir, comfyui } => {
                let answer = self.player(&config_dir, comfyui.as_deref());
                self.emit(Event::Player(answer));
            }
            Request::DownloadModels { files } => {
                let events = self.events.clone();
                let _ = std::thread::Builder::new().name("plenio-models".into()).spawn(move || download_models(&events, files));
            }
        }
    }

    fn client(&self) -> Result<Client, String> {
        self.client.clone().ok_or_else(|| "the Plenio studio is not running (start it in Plenio › Studio and Models…)".into())
    }

    fn attach(&mut self, port: u16) {
        let client = Client::local(port);
        match info(&client) {
            Ok((plenio, comfyui)) => {
                self.client = Some(client);
                self.emit(Event::State(State::Ready { port, plenio, comfyui }));
            }
            Err(e) => self.emit(Event::State(State::Failed(e))),
        }
    }

    fn start(&mut self, config_dir: &std::path::Path, chosen: Option<&std::path::Path>) {
        if self.client.as_ref().is_some_and(Client::alive) {
            return;
        }
        self.stop();
        self.emit(Event::State(State::Starting("looking for ComfyUI".into())));
        let Some(install) = discover::find(chosen) else {
            self.emit(Event::State(State::Failed(
                "no ComfyUI found: install ComfyUI 0.37 or newer, or choose its folder in Plenio › Studio and Models…".into(),
            )));
            return;
        };
        match self.launch(&install, &Layout::new(config_dir)) {
            Ok((port, plenio, comfyui)) => self.emit(Event::State(State::Ready { port, plenio, comfyui })),
            Err(message) => {
                self.stop();
                self.emit(Event::State(State::Failed(message)));
            }
        }
    }

    /// Start the player when it does not run, and wait until it answers.
    fn player(&mut self, config_dir: &std::path::Path, chosen: Option<&std::path::Path>) -> Result<String, String> {
        if let Some(p) = &mut self.player
            && !p.ended()
        {
            return Ok(crate::player::url(p.port));
        }
        let install = match &self.install {
            Some(i) => i.clone(),
            None => discover::find(chosen).ok_or("no ComfyUI found for the Plenio Player's Python")?,
        };
        let layout = Layout::new(config_dir);
        let source = instance::source_dir().map_err(|e| e.to_string())?;
        instance::install_package(&source, &layout).map_err(|e| e.to_string())?;
        let port = instance::free_port().map_err(|e| e.to_string())?;
        let studio_port = self.instance.as_ref().map(|i| i.port);
        let player = crate::player::Player::start(&install, &layout, studio_port, port).map_err(|e| e.to_string())?;
        self.player = Some(player);
        let probe: ureq::Agent = ureq::Agent::config_builder().timeout_global(Some(Duration::from_secs(3))).build().into();
        let started = Instant::now();
        while started.elapsed() < Duration::from_secs(90) {
            if self.player.as_mut().is_some_and(crate::player::Player::ended) {
                self.player = None;
                return Err(format!("the Plenio Player ended while starting; its log: {}", layout.root.join("player.log").display()));
            }
            let answer = probe.get(&format!("http://127.0.0.1:{port}/api/info")).call().ok().and_then(|mut r| r.body_mut().read_to_string().ok());
            if answer.is_some_and(|a| a.contains("plenio-player")) {
                return Ok(crate::player::url(port));
            }
            std::thread::sleep(Duration::from_millis(500));
        }
        Err("the Plenio Player did not answer within 90 s".into())
    }

    fn launch(&mut self, install: &Install, layout: &Layout) -> Result<(u16, String, String), String> {
        self.install = Some(install.clone());
        self.emit(Event::State(State::Starting("installing the add-in into its ComfyUI".into())));
        let source = instance::source_dir().map_err(|e| e.to_string())?;
        instance::install_package(&source, layout).map_err(|e| e.to_string())?;
        let port = instance::free_port().map_err(|e| e.to_string())?;
        self.emit(Event::State(State::Starting(format!("starting ComfyUI {} on port {port}", install.version.as_deref().unwrap_or("")))));
        let instance = Instance::start(install, layout, port).map_err(|e| e.to_string())?;
        self.instance = Some(instance);
        let client = Client::local(port);
        let started = Instant::now();
        while started.elapsed() < START_TIMEOUT {
            if let Some(instance) = &mut self.instance
                && let Some(how) = instance.ended()
            {
                return Err(format!("ComfyUI ended while starting ({how}); its log: {}", layout.log().display()));
            }
            if client.alive() {
                let (plenio, comfyui) = info(&client)?;
                self.client = Some(client);
                return Ok((port, plenio, comfyui));
            }
            std::thread::sleep(Duration::from_millis(500));
        }
        Err(format!("ComfyUI did not answer within {} s; its log: {}", START_TIMEOUT.as_secs(), layout.log().display()))
    }

    fn stop(&mut self) {
        self.client = None;
        if let Some(mut instance) = self.instance.take() {
            instance.stop();
        }
        if let Some(mut player) = self.player.take() {
            player.stop();
        }
    }
}

fn info(client: &Client) -> Result<(String, String), String> {
    let v = client.get("/scp/v1").map_err(|e| e.to_string())?;
    if v.get("addin").and_then(Value::as_str) != Some("soundcraft-plenio") {
        return Err("the ComfyUI on that port does not run the SoundCraft Plenio add-in".into());
    }
    let s = |k: &str| v.get(k).and_then(Value::as_str).unwrap_or_default().to_string();
    Ok((s("plenio"), s("comfyui")))
}

fn encode_segment(s: &str) -> String {
    s.chars().filter(|c| c.is_ascii_alphanumeric() || *c == '-').collect()
}

/// Submit a job, follow it to its end and download what the add-in needs.
fn follow(client: &Client, events: &Sender<Event>, tag: u64, body: &Value, into: &std::path::Path) {
    let fail = |message: String| {
        let _ = events.send(Event::Failed { tag: Some(tag), message });
    };
    let key = format!("soundcraft-{}-{tag}", std::process::id());
    let mut job = match client.post("/plenio/api/v1/jobs", body, Some(&key)).map(|v| Job::parse(&v)) {
        Ok(Some(job)) => job,
        Ok(None) => return fail("the Song API answered without a job".into()),
        Err(e) => return fail(describe(&e)),
    };
    let _ = events.send(Event::Job { tag, job: job.clone() });
    let mut errors = 0;
    while !job.status.finished() {
        match client.get(&format!("/plenio/api/v1/jobs/{}?wait={WAIT_S}", encode_segment(&job.id))).map(|v| Job::parse(&v)) {
            Ok(Some(next)) => {
                errors = 0;
                if next != job {
                    let _ = events.send(Event::Job { tag, job: next.clone() });
                }
                job = next;
            }
            Ok(None) => return fail("the Song API answered without a job".into()),
            Err(e) => {
                errors += 1;
                if errors > 5 {
                    return fail(describe(&e));
                }
                std::thread::sleep(Duration::from_secs(2));
            }
        }
    }
    if job.status != crate::song::JobStatus::Succeeded {
        let message = if job.error.is_empty() {
            format!("the take was {}", if matches!(job.status, crate::song::JobStatus::Cancelled) { "cancelled" } else { "not made" })
        } else {
            job.error.clone()
        };
        return fail(message);
    }
    match deliver(client, &job, into) {
        Ok(delivery) => {
            let _ = events.send(Event::Delivered { tag, delivery: Box::new(delivery) });
        }
        Err(e) => fail(e),
    }
}

fn describe(e: &ApiError) -> String {
    match e {
        ApiError::Api { message, hint, .. } if !hint.is_empty() => format!("{message} ({hint})"),
        other => other.to_string(),
    }
}

/// A file name safe on every platform, from a name the API gave.
fn safe_name(name: &str) -> String {
    let cleaned: String = name.chars().map(|c| if c.is_control() || "<>:\"/\\|?*".contains(c) { '_' } else { c }).take(160).collect();
    let trimmed = cleaned.trim_matches(|c: char| c == '.' || c.is_whitespace()).to_string();
    if trimmed.is_empty() { "take".into() } else { trimmed }
}

fn deliver(client: &Client, job: &Job, into: &std::path::Path) -> Result<Delivery, String> {
    let fetch = |file: &crate::song::JobFile| -> Result<PathBuf, String> {
        let dest = into.join(safe_name(&file.name));
        client.download(&file.url, &dest, MAX_FILE_BYTES).map_err(|e| e.to_string())?;
        Ok(dest)
    };
    let song = job.file("").map(fetch).transpose()?;
    let original = job.file("original").map(fetch).transpose()?;
    let record_file = job.file("record").map(fetch).transpose()?;
    let record = record_file
        .as_ref()
        .and_then(|p| std::fs::read_to_string(p).ok())
        .and_then(|t| serde_json::from_str::<Value>(&t).ok())
        .map(|v| Record::parse(&v));
    let lines = match job.line_subtitles() {
        Some(f) => fetch(f).ok().and_then(|p| std::fs::read_to_string(p).ok()).map(|t| parse_srt(&t)).unwrap_or_default(),
        None => Vec::new(),
    };
    Ok(Delivery { job: job.clone(), song, original, record, record_file, lines })
}

fn download_models(events: &Sender<Event>, files: Vec<(String, PathBuf, u64)>) {
    let client = Client::new("https://huggingface.co");
    for (url, target, bytes) in files {
        let file = target.file_name().map(|n| n.to_string_lossy().into_owned()).unwrap_or_default();
        if !(url.starts_with("https://huggingface.co/") || url.starts_with("https://github.com/")) {
            let _ = events.send(Event::ModelDone { file, result: Err(format!("not a download address the catalogue may use: {url}")) });
            continue;
        }
        let mut last = Instant::now();
        let mut progress = |done: u64, total: u64| {
            if last.elapsed() > Duration::from_millis(250) {
                last = Instant::now();
                let _ = events.send(Event::ModelProgress { file: file.clone(), done, total });
            }
            true
        };
        let result = client.download_model(&url, &target, bytes, &mut progress).map_err(|e| e.to_string());
        let _ = events.send(Event::ModelDone { file, result });
    }
}

/// The job request for a song: what the add-in always asks of a release (FLAC, no MP3, the record,
/// the timed lyrics) and who asks. Each take gets a release folder of its own (`take` names it):
/// in a shared folder Plenio numbers a title that is already there, and the second take of a song
/// would come back as "Title (2)".
pub fn job_body(template: &str, fields: &Value, documents: &Value, seeds: &Value, take: &str) -> Value {
    let take: String = take.chars().filter(|c| c.is_ascii_alphanumeric() || *c == '-').take(64).collect();
    let folder = if take.is_empty() { "plenio/soundcraft".to_string() } else { format!("plenio/soundcraft/{take}") };
    json!({
        "template": template,
        "fields": fields,
        "documents": documents,
        "seeds": seeds,
        "release": {"folder": folder, "flac": true, "mp3": false, "song_page": false, "lyrics_srt": true},
        "client": {"name": "SoundCraft"},
        "strict": false,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn every_take_has_a_release_folder_of_its_own() {
        let a = job_body("yue2-song", &json!({}), &json!({}), &json!({}), "20261107-0812-3");
        let b = job_body("yue2-song", &json!({}), &json!({}), &json!({}), "20261107-0812-4");
        assert_eq!(a["release"]["folder"], "plenio/soundcraft/20261107-0812-3");
        assert_ne!(a["release"]["folder"], b["release"]["folder"]);
        // Nothing of a name leaves the studio's output folder.
        assert_eq!(job_body("yue2-song", &json!({}), &json!({}), &json!({}), "../../x")["release"]["folder"], "plenio/soundcraft/x");
        assert_eq!(job_body("yue2-song", &json!({}), &json!({}), &json!({}), "")["release"]["folder"], "plenio/soundcraft");
    }

    #[test]
    fn names_from_the_api_are_made_safe() {
        assert_eq!(safe_name("2026-11-05 Night Drive.flac"), "2026-11-05 Night Drive.flac");
        assert_eq!(safe_name("../../evil:name?.flac"), "_.._evil_name_.flac");
        assert_eq!(safe_name("..."), "take");
        assert_eq!(encode_segment("4f6c-../x"), "4f6c-x");
    }

    #[test]
    fn a_request_without_a_studio_is_answered_not_lost() {
        let studio = Studio::spawn();
        studio.send(Request::Get { tag: "t".into(), path: "/plenio/api/v1".into() });
        match studio.wait(Duration::from_secs(10)) {
            Some(Event::Answer { tag, result: Err(message) }) => {
                assert_eq!(tag, "t");
                assert!(message.contains("not running"));
            }
            other => panic!("{other:?}"),
        }
    }

    /// The whole start: find ComfyUI, install the package into a fresh settings folder, start the
    /// instance, see it answer, stop it. `SCP_TEST_START=1 cargo test -p soundcraft-plenio-backend -- --ignored`.
    #[test]
    #[ignore = "starts ComfyUI (SCP_TEST_START=1)"]
    fn the_studio_starts_its_own_comfyui_and_stops_it() {
        if std::env::var("SCP_TEST_START").is_err() {
            return;
        }
        let config = std::env::temp_dir().join(format!("scp-studio-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&config);
        let studio = Studio::spawn();
        studio.send(Request::Start { config_dir: config.clone(), comfyui: None });
        let ready = loop {
            match studio.wait(START_TIMEOUT) {
                Some(Event::State(State::Starting(step))) => eprintln!("starting: {step}"),
                Some(Event::State(state)) => break state,
                other => panic!("{other:?}"),
            }
        };
        let State::Ready { port, plenio, comfyui } = ready else { panic!("{ready:?}") };
        eprintln!("ready on {port}: Plenio {plenio}, ComfyUI {comfyui}");
        // The studio runs the copy that was synced last (sync_plenio.py records its version).
        let record = std::fs::read_to_string(concat!(env!("CARGO_MANIFEST_DIR"), "/../../vendor/VENDOR.toml")).unwrap();
        let synced = record.lines().find_map(|l| l.strip_prefix("version = \"")?.strip_suffix('"'));
        assert_eq!(Some(plenio.as_str()), synced);
        studio.send(Request::Get { tag: "api".into(), path: "/plenio/api/v1".into() });
        match studio.wait(Duration::from_secs(30)) {
            Some(Event::Answer { result: Ok(v), .. }) => assert_eq!(v["api"], "plenio-song-api"),
            other => panic!("{other:?}"),
        }
        // Plenio's state went to the add-in's folder, not to the owner's Plenio Player.
        assert!(Layout::new(&config).player_state().join("comfyui-start.json").is_file());
        studio.send(Request::Stop);
        assert!(matches!(studio.wait(Duration::from_secs(30)), Some(Event::State(State::Stopped))));
        assert!(!Client::local(port).alive());
        let _ = std::fs::remove_dir_all(&config);
    }

    /// The Plenio Player starts on the studio's output and stops with the studio.
    /// `SCP_TEST_START=1 cargo test -p soundcraft-plenio-backend -- --ignored`.
    #[test]
    #[ignore = "starts the Plenio Player (SCP_TEST_START=1)"]
    fn the_player_starts_on_its_own_state_and_stops() {
        if std::env::var("SCP_TEST_START").is_err() {
            return;
        }
        let config = std::env::temp_dir().join(format!("scp-player-start-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&config);
        let studio = Studio::spawn();
        studio.send(Request::Player { config_dir: config.clone(), comfyui: None });
        let url = match studio.wait(Duration::from_secs(120)) {
            Some(Event::Player(Ok(url))) => url,
            other => panic!("{other:?}"),
        };
        eprintln!("player at {url}");
        let info = Client::new(url.trim_end_matches('/')).get("/api/info").unwrap();
        assert_eq!(info["app"], "plenio-player");
        assert!(info["state"].as_str().is_some_and(|s| s.contains("player-state")), "{info}");
        studio.send(Request::Stop);
        assert!(matches!(studio.wait(Duration::from_secs(30)), Some(Event::State(State::Stopped))));
        let _ = std::fs::remove_dir_all(&config);
    }

    /// End to end against a running add-in instance: `SCP_TEST_PORT=8291 cargo test -p soundcraft-plenio-backend -- --ignored`.
    #[test]
    #[ignore = "needs a running Plenio studio (SCP_TEST_PORT)"]
    fn a_running_studio_answers() {
        let Some(port) = std::env::var("SCP_TEST_PORT").ok().and_then(|p| p.parse().ok()) else { return };
        let studio = Studio::spawn();
        studio.send(Request::Attach { port });
        assert!(matches!(studio.wait(Duration::from_secs(10)), Some(Event::State(State::Ready { .. }))));
        studio.send(Request::Get { tag: "fields".into(), path: "/plenio/api/v1/templates/yue2-song".into() });
        match studio.wait(Duration::from_secs(30)) {
            Some(Event::Answer { result: Ok(v), .. }) => assert!(v["fields"].as_array().is_some_and(|f| !f.is_empty())),
            other => panic!("{other:?}"),
        }
    }
}
