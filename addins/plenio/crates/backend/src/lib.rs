//! The Plenio add-in's backend side: its settings, the ComfyUI instance it runs (with Plenio inside,
//! unchanged), the client of Plenio's Song API and the add-in's routes, and what it reads from
//! Plenio (jobs, release records, scores, timed lyrics).
//!
//! Network, processes and files run on the studio's own threads ([`studio::Studio`]); the UI only
//! sends requests and reads events.
#![deny(clippy::unwrap_used, clippy::expect_used, clippy::panic, clippy::unimplemented, clippy::todo, clippy::unreachable)]

pub mod client;
pub mod discover;
pub mod instance;
pub mod player;
pub mod settings;
pub mod song;
pub mod studio;

pub use settings::{Settings, SettingsError};
pub use studio::{Delivery, Event, Request, State, Studio};
