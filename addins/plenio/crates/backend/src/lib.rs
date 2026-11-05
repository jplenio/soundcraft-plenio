//! The Plenio add-in's backend side: its settings now; the ComfyUI instance it runs, the client of
//! the stage API and the model downloads come with the next milestone (see `addins/plenio/docs/PLAN.md`).
//!
//! Nothing here runs on the UI or audio thread for long: reading and writing the small settings
//! file is the only file access, and it is bounded.
#![deny(clippy::unwrap_used, clippy::expect_used, clippy::panic, clippy::unimplemented, clippy::todo, clippy::unreachable)]

pub mod settings;

pub use settings::{Settings, SettingsError};
