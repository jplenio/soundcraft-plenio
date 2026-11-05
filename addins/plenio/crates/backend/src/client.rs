//! A small, blocking HTTP client for the add-in's ComfyUI instance: Plenio's Song API
//! (`/plenio/api/v1`), Plenio's own routes (`/plenio/…`) and the add-in's (`/scp/v1`).
//!
//! It blocks, so it runs on the add-in's worker threads only, never on the UI or audio thread.
//! Every answer is hostile input: bounded in size and parsed without trust.

use serde_json::Value;
use std::io::Read;
use std::path::Path;
use std::time::Duration;

/// The largest JSON answer read (the OpenAPI document and the template fields are the biggest).
pub const MAX_JSON_BYTES: u64 = 64 * 1024 * 1024;
/// The largest file downloaded from a job (a song as WAV, a long FLAC with the project inside).
pub const MAX_FILE_BYTES: u64 = 4 * 1024 * 1024 * 1024;
/// The largest recording uploaded for a cover (the Song API's own limit).
pub const MAX_UPLOAD_BYTES: u64 = 200 * 1024 * 1024;

#[derive(Debug, thiserror::Error)]
pub enum ApiError {
    #[error("the Plenio studio does not answer: {0}")]
    Network(String),
    #[error("{message}")]
    Api { status: u16, code: String, message: String, hint: String },
    #[error("unexpected answer from the Plenio studio: {0}")]
    Format(String),
    #[error("{0}")]
    File(String),
}

impl ApiError {
    /// The API's error code (`invalid_value`, `not_found` …), if the API answered with one.
    pub fn code(&self) -> Option<&str> {
        match self {
            ApiError::Api { code, .. } => Some(code),
            _ => None,
        }
    }
}

/// The client of one instance.
#[derive(Clone)]
pub struct Client {
    base: String,
    agent: ureq::Agent,
}

impl Client {
    /// The instance on this computer's `port`.
    pub fn local(port: u16) -> Self {
        Self::new(&format!("http://127.0.0.1:{port}"))
    }

    pub fn new(base: &str) -> Self {
        // Long-polls wait up to 60 s on the server; uploads and downloads can take longer.
        let config = ureq::Agent::config_builder().http_status_as_error(false).timeout_global(Some(Duration::from_secs(600))).build();
        Client { base: base.trim_end_matches('/').to_string(), agent: config.into() }
    }

    pub fn base(&self) -> &str {
        &self.base
    }

    fn url(&self, path: &str) -> String {
        if path.starts_with("http://") || path.starts_with("https://") { path.to_string() } else { format!("{}{path}", self.base) }
    }

    fn answer(mut response: ureq::http::Response<ureq::Body>) -> Result<Value, ApiError> {
        let status = response.status().as_u16();
        let text = response.body_mut().with_config().limit(MAX_JSON_BYTES).read_to_string().map_err(|e| ApiError::Network(e.to_string()))?;
        let value: Value =
            if text.trim().is_empty() { Value::Null } else { serde_json::from_str(&text).map_err(|e| ApiError::Format(e.to_string()))? };
        if (200..300).contains(&status) {
            return Ok(value);
        }
        let error = value.get("error");
        let field = |k: &str| error.and_then(|e| e.get(k)).and_then(Value::as_str).unwrap_or_default().to_string();
        let message = Some(field("message")).filter(|m| !m.is_empty()).unwrap_or_else(|| format!("HTTP {status}"));
        Err(ApiError::Api { status, code: field("code"), message, hint: field("hint") })
    }

    /// `GET` a JSON answer.
    pub fn get(&self, path: &str) -> Result<Value, ApiError> {
        let response = self.agent.get(&self.url(path)).call().map_err(|e| ApiError::Network(e.to_string()))?;
        Self::answer(response)
    }

    /// Whether the instance answers at all, within a short time.
    pub fn alive(&self) -> bool {
        let quick: ureq::Agent =
            ureq::Agent::config_builder().http_status_as_error(false).timeout_global(Some(Duration::from_secs(3))).build().into();
        quick.get(&self.url("/scp/v1")).call().is_ok_and(|r| r.status().is_success())
    }

    /// `POST` JSON; `idempotency` makes a repeated request return the first job (Song API).
    pub fn post(&self, path: &str, body: &Value, idempotency: Option<&str>) -> Result<Value, ApiError> {
        let mut request = self.agent.post(&self.url(path)).header("Content-Type", "application/json");
        if let Some(key) = idempotency {
            request = request.header("Idempotency-Key", key);
        }
        let response = request.send(body.to_string()).map_err(|e| ApiError::Network(e.to_string()))?;
        Self::answer(response)
    }

    /// `DELETE` (cancel a job).
    pub fn delete(&self, path: &str) -> Result<Value, ApiError> {
        let response = self.agent.delete(&self.url(path)).call().map_err(|e| ApiError::Network(e.to_string()))?;
        Self::answer(response)
    }

    /// Upload a recording for a cover (`POST /plenio/api/v1/uploads`); the answer's `name` goes
    /// into the field `source.audio`.
    pub fn upload(&self, file: &Path) -> Result<Value, ApiError> {
        let size = std::fs::metadata(file).map_err(|e| ApiError::File(format!("{}: {e}", file.display())))?.len();
        if size > MAX_UPLOAD_BYTES {
            return Err(ApiError::File(format!("{} is over {} MB, the most a cover takes", file.display(), MAX_UPLOAD_BYTES / 1024 / 1024)));
        }
        let name = file.file_name().map(|n| n.to_string_lossy().into_owned()).unwrap_or_else(|| "recording.wav".into());
        let bytes = std::fs::read(file).map_err(|e| ApiError::File(format!("{}: {e}", file.display())))?;
        let url = format!("{}?name={}", self.url("/plenio/api/v1/uploads"), encode(&name));
        let response =
            self.agent.post(&url).header("Content-Type", content_type(&name)).send(&bytes[..]).map_err(|e| ApiError::Network(e.to_string()))?;
        Self::answer(response)
    }

    /// Download a job's file (its `url`) to `dest`, through a temporary file, at most `max` bytes.
    pub fn download(&self, url: &str, dest: &Path, max: u64) -> Result<u64, ApiError> {
        let mut response = self.agent.get(&self.url(url)).call().map_err(|e| ApiError::Network(e.to_string()))?;
        let status = response.status().as_u16();
        if !(200..300).contains(&status) {
            return Err(ApiError::Api { status, code: String::new(), message: format!("{url}: HTTP {status}"), hint: String::new() });
        }
        if let Some(parent) = dest.parent() {
            std::fs::create_dir_all(parent).map_err(|e| ApiError::File(format!("{}: {e}", parent.display())))?;
        }
        let part = dest.with_extension("part");
        let mut out = std::fs::File::create(&part).map_err(|e| ApiError::File(format!("{}: {e}", part.display())))?;
        let mut reader = response.body_mut().with_config().limit(max).reader();
        let copied = std::io::copy(&mut reader, &mut out).map_err(|e| ApiError::Network(e.to_string()));
        drop(out);
        let copied = match copied {
            Ok(n) => n,
            Err(e) => {
                let _ = std::fs::remove_file(&part);
                return Err(e);
            }
        };
        std::fs::rename(&part, dest).map_err(|e| ApiError::File(format!("{}: {e}", dest.display())))?;
        Ok(copied)
    }

    /// Download a model file from its catalogue URL to `dest`, resuming a `.part` file left by an
    /// earlier try; `progress(done, total)` is called as it goes. Checks the size the catalogue names.
    pub fn download_model(&self, url: &str, dest: &Path, expected: u64, progress: &mut dyn FnMut(u64, u64) -> bool) -> Result<(), ApiError> {
        let part = dest.with_extension(format!("{}.part", dest.extension().and_then(|e| e.to_str()).unwrap_or("bin")));
        if let Some(parent) = dest.parent() {
            std::fs::create_dir_all(parent).map_err(|e| ApiError::File(format!("{}: {e}", parent.display())))?;
        }
        let have = std::fs::metadata(&part).map(|m| m.len()).unwrap_or(0);
        let mut request = self.agent.get(url);
        if have > 0 {
            request = request.header("Range", &format!("bytes={have}-"));
        }
        let mut response = request.call().map_err(|e| ApiError::Network(e.to_string()))?;
        let status = response.status().as_u16();
        let resumed = status == 206;
        if !(200..300).contains(&status) {
            return Err(ApiError::Api { status, code: String::new(), message: format!("{url}: HTTP {status}"), hint: String::new() });
        }
        let mut out = std::fs::OpenOptions::new()
            .create(true)
            .append(resumed)
            .write(true)
            .truncate(!resumed)
            .open(&part)
            .map_err(|e| ApiError::File(format!("{}: {e}", part.display())))?;
        let mut done = if resumed { have } else { 0 };
        let total = if expected > 0 { expected } else { u64::MAX };
        let mut reader = response.body_mut().with_config().limit(total.saturating_sub(done).saturating_add(1)).reader();
        let mut buffer = vec![0u8; 1 << 20];
        loop {
            let n = reader.read(&mut buffer).map_err(|e| ApiError::Network(e.to_string()))?;
            if n == 0 {
                break;
            }
            std::io::Write::write_all(&mut out, buffer.get(..n).unwrap_or_default())
                .map_err(|e| ApiError::File(format!("{}: {e}", part.display())))?;
            done = done.saturating_add(n as u64);
            if !progress(done, expected) {
                return Err(ApiError::File("download cancelled".into()));
            }
        }
        drop(out);
        if expected > 0 && done != expected {
            return Err(ApiError::File(format!("{}: got {done} bytes, the catalogue says {expected}", dest.display())));
        }
        std::fs::rename(&part, dest).map_err(|e| ApiError::File(format!("{}: {e}", dest.display())))
    }
}

/// Percent-encode a query value.
fn encode(text: &str) -> String {
    let mut out = String::new();
    for b in text.bytes() {
        if b.is_ascii_alphanumeric() || matches!(b, b'-' | b'_' | b'.' | b'~') {
            out.push(char::from(b));
        } else {
            out.push_str(&format!("%{b:02X}"));
        }
    }
    out
}

fn content_type(name: &str) -> &'static str {
    match name.rsplit('.').next().map(str::to_ascii_lowercase).as_deref() {
        Some("mp3") => "audio/mpeg",
        Some("flac") => "audio/flac",
        Some("ogg" | "opus") => "audio/ogg",
        Some("m4a" | "aac") => "audio/mp4",
        Some("aif" | "aiff") => "audio/aiff",
        _ => "audio/wav",
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn names_are_encoded_for_the_query() {
        assert_eq!(encode("My Song (1).mp3"), "My%20Song%20%281%29.mp3");
        assert_eq!(encode("ä"), "%C3%A4");
    }

    #[test]
    fn a_closed_port_is_a_network_error_not_a_panic() {
        let port = crate::instance::free_port().unwrap();
        let client = Client::local(port);
        assert!(!client.alive());
        assert!(matches!(client.get("/plenio/api/v1"), Err(ApiError::Network(_))));
    }
}
