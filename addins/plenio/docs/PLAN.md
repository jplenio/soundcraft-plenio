# Plenio-Add-in für SoundCraft – Plan und Fortschritt

| | |
|---|---|
| **Ziel** | Plenio (YuE2 · Song, YuE2 · Cover, Plenio Player – **ohne MiniMax**) als Add-in in SoundCraft, nahtlos integriert |
| **Branch** | `plenio-addin` (Remote `upstream` = `storytold/soundcraft`) |
| **Plenio-Quelle** | `D:\Daten2\Deepseek\ComfyUI-MiniMax\Plenio-Music-Production-System` (Version 1.5.0) – **wird nie verändert**, Code wird kopiert |
| **Plan erstellt** | 2026-11-05 |
| **Zuletzt aktualisiert** | 2026-11-06 |
| **Stand** | Phase 0–5 erledigt und live durch die UI geprüft (Song, Noten, Stems, Cover, Player); Phase 6 großteils, offene Punkte im Abschnitt „Stand 2026-11-05 abends“; eigener Fork vorbereitet, Repo auf GitHub steht noch aus ([FORK.md](FORK.md)) |

Legende: `[x]` erledigt · `[ ]` offen · `[~]` begonnen / teilweise · 💡 Hinweis

---

## Fortschritt auf einen Blick

| Phase | Inhalt | Status |
|---|---|---|
| A | Analyse, Konzept, Entscheidungen | ✅ erledigt |
| 0 | Fundament: Git, Seams S1–S6, Crate-Skelett, Plenio-Menü, Aktivieren-Schalter | ✅ erledigt |
| 1 | Backend: Plenio-Kopie, Wrapper, ComfyUI-Supervisor, Modelle (Song-API statt eigener Stage-API) | ✅ erledigt |
| 2 | MVP „YuE2 Song“ | ✅ erledigt |
| 3 | Noten und Stems | ✅ erledigt (Browser-Score-Editor offen) |
| 4 | YuE2 Cover | ✅ erledigt (live geprüft) |
| 5 | Player und Release | ✅ erledigt („In SoundCraft öffnen“ offen) |
| 6 | Härtung, Update-Probelauf, Doku | 🔶 großteils |

---

## Checkliste

### Phase A – Analyse, Konzept, Entscheidungen

- [x] `CLAUDE.md` / `AGENTS.md` gelesen, SoundCraft-Architektur analysiert
  💡 `plan/STATUS.md` und `plan/execution-plan.md` existieren lokal nicht (`plan/` ist gitignored und fehlt auf diesem Rechner).
- [x] Plenio analysiert (Song-API, Routen, Subgraphs, Player, Modellkatalog, Standalone-Konzept)
- [x] Plan erstellt und vom Owner freigegeben (2026-11-05)
- [x] Entscheidung 9.1: **eigene, vom Add-in verwaltete ComfyUI-Instanz** (eigener Basisordner, vorhandene Modelle werden mitbenutzt)
- [x] Entscheidung 9.2: ~~Seams dürfen upstream~~ → **kein Upstream, eigener Fork** (geändert 2026-11-06, siehe [FORK.md](FORK.md))
- [x] Entscheidung 9.3: **`origin` → `upstream` umbenannt, Arbeit auf Branch `plenio-addin`**
- [x] Zusatzvorgabe: **Plenio-Projekt nicht verändern**, sinnvollen Code nach SoundCraft kopieren
- [x] Plan als Markdown gespeichert (diese Datei)

### Phase 0 – Fundament

- [x] Git: `origin` in `upstream` umbenannt, Branch `plenio-addin` von `73eeb69` angelegt
  💡 Der GitHub-Fork `jplenio/soundcraft-plenio` als `origin` muss der Owner noch anlegen (Schritte in [FORK.md](FORK.md)); bis dahin ist alles nur lokal.
- [x] Rust-Toolchain installiert: rustup mit stable 1.99.1 (`x86_64-pc-windows-msvc` + `wasm32-unknown-unknown`, clippy, rustfmt) unter `D:\Rust`
  💡 `CARGO_HOME=D:\Rust\cargo`, `RUSTUP_HOME=D:\Rust\rustup` als Benutzervariablen; `D:\Rust\cargo\bin` steht im Benutzer-PATH (neue Shells). rustup-init per SHA-256 geprüft. MSVC kommt aus Visual Studio 2022.
- [x] Baseline auf unverändertem Stand `73eeb69` (eigener Worktree, eigenes Target-Verzeichnis)
  💡 fmt, clippy, Doctests, assets, layers und wasm grün. **3 Tests scheitern schon vorher** auf diesem Rechner: `soundcraft-cli` `it::behaviour::app_port_comes_from_the_flag_then_the_environment`, `it::behaviour::app_takes_an_empty_port_variable_as_unset`, `it::run::app_reports_a_refused_connection_and_checks_arguments_first`. Ursache: Unter Windows läuft der Verbindungsaufbau zu einem geschlossenen Port in einen Timeout statt sofort abgelehnt zu werden („connection timed out“ statt „refused“). Nicht vom Add-in verursacht. `cargo xtask ci` bricht deshalb hier beim Schritt `test` ab; die übrigen Schritte wurden einzeln ausgeführt.
- [x] **S1** `crates/model/src/session.rs`: `extensions: BTreeMap<String, Arc<str>>` mit `extension()`, `set_extension()`, Schlüsselregel und Deckeln (64 Einträge, 16 MiB je Eintrag, 64 MiB gesamt), in `sanitize` beim Laden begrenzt; `crates/engine/src/dirty.rs` berücksichtigt das Feld beim Gespeichert-Status. 3 Tests.
  💡 `Arc<str>` statt `String`, damit Undo-Schnappschüsse den Text nicht kopieren.
- [x] **S2** `crates/engine/src/cmd/extensions.rs` (neu): `register_extension_commands`, `refused_extension_commands`, `extension_command_id_ok`; in `cmd.rs` nur 3 Zeilen (Modul, `pub use`, `close_into` am Ende von `command_specs()`). Eigene Test-Binary `crates/engine/tests/extension_commands.rs` (Registrierung, Undo, `enabled`, Kollision mit SoundCraft-IDs, späte Registrierung abgelehnt) + 1 Unit-Test.
  💡 Bewusst kleiner Diff: die Liste der SoundCraft-Module in `command_specs()` blieb unverändert, das erleichtert spätere Rebases. Eine ID, die SoundCraft schon hat, wird beim Aufbau ausgelassen und gemeldet.
- [x] **S3** `crates/ui-egui/src/extension.rs` (neu): Trait `UiExtension` mit `logic`, `menu_bar`, `windows`, `track_header`, `lane` (mit `Lane::x_of`/`sample_at`), `track_context_menu`; `SoundApp::add_extension`/`extensions()`. Aufrufstellen: je 1 Zeile in `app.rs` (2×), `menus.rs`, `edit_window/tracks.rs` (3×), Feld in `lib.rs`. Ein Hook, der panickt, stoppt nur dieses Add-in (`catch_unwind`, Log und Statusmeldung). 2 Tests.
  💡 Dock-Panel (`Panel::Extension`), Einstellungen und Datei-Drop sind noch nicht drin: sie kommen additiv, wenn Phase 2 sie braucht (Default-Methoden brechen nichts).
- [x] **S4** `apps/soundcraft`: Feature `plenio` (im Branch Standard), `register_commands()` direkt nach dem Logger, `add_extension(...)` nach den Prefs (Einstellungsordner nur, wenn Prefs aktiv sind).
  💡 `cargo clippy -p soundcraft --no-default-features` ist grün: SoundCraft baut weiterhin ohne Add-in.
- [x] **S5** `Cargo.toml`: Members `addins/*/crates/*`; `xtask layers` liest für Crates außerhalb der Tabelle `[package.metadata.soundcraft] layer = N` aus dem Manifest.
  💡 Allgemein statt Plenio-spezifischer `LAYERS`-Einträge: so bleibt die Änderung upstream-tauglich. Dokumentiert in `docs/architecture.md › Extensions` (mit Revisionseintrag).
- [x] **S6** `ATTRIBUTION.md`: Verzeichnis-Zeile für `addins/plenio/vendor/` (Template-Vorschaubilder, App-Icons des Players; Apache-2.0)
- [x] Crate-Gerüst `addins/plenio/crates/{project,backend,commands,ui}` mit `[lints] workspace = true`, crate-weiten `#![deny(...)]`-Attributen und Layer im Manifest (2/4/4/6)
  💡 `project`: Songs und Spur-Rollen in `Session.extensions["plenio"]` (begrenzt, verwaiste Rollen fallen weg, neuere Versionen werden abgelehnt). `backend`: Einstellungen in `<Einstellungsordner>/Plenio/settings.json`, atomar geschrieben. `commands`: `plenio.status` und die Aktivierungsprüfung `when_activated`. `ui`: Menü und Fenster. 12 Tests.
- [x] Menü „Plenio“ sichtbar, „Activate Plenio Add-in…“ mit Fenster (nennt die eigene ComfyUI-Instanz, die Modelle und die CC-BY-NC-Lizenz); aktiviert: „New Song…“, „New Cover from Selection…“, „Open Plenio Player“ (noch ausgegraut), „Deactivate“, „About“
  💡 Offscreen geprüft mit `cargo run -p soundcraft-plenio-ui --example plenio_shot -- <Ordner>` (drei PNGs: Menü, Aktivierung, Menü aktiviert). Die Oberfläche ist englisch wie SoundCraft und Plenio; Deutsch wäre eine spätere Lokalisierung.
- [x] Gates: fmt, clippy `--workspace --all-targets -D warnings`, Tests, Doctests, assets, layers, wasm grün, abgesehen von den 3 Baseline-Fehlern oben. Commits pro Thema auf `plenio-addin` (lokal, nicht gepusht).
- [ ] Offen für später: `soundcraft-cli` (headless/MCP) registriert die `plenio.*`-Commands noch nicht. Im laufenden Desktop-Programm laufen Control-Channel und `soundcraft-cli mcp --connect` über dessen Registry und sollten sie daher erreichen; geprüft ist das noch nicht (das GUI-Programm wurde bisher nicht gestartet, nur offscreen gerendert).

### Phase 1 – Backend

- [x] `tools/sync_plenio.py`: feste Kopierliste, `vendor/VENDOR.toml` (Quelle, Commit, Version, Datum, Anzahl), `vendor/VENDOR.sha256`, Änderungsbericht (`--dry-run`), Hash-Check gegen Handänderungen (`--check`)
  💡 Liest nur Git-Blobs des Commits (`ls-tree` + `cat-file`): nicht committete Änderungen in Plenio werden nie kopiert, jeder Sync eines Commits ergibt dieselben Dateien, das Plenio-Repo wird nicht verändert. `vendor/.gitattributes` hält LF-Zeilenenden wie Plenio (dessen Tests vergleichen byte-genau; SoundCraft arbeitet hier mit `core.autocrlf=true`).
- [x] Erste Kopie nach `addins/plenio/vendor/plenio/`: Plenio 1.5.0 @ `f26972890377`, 1027 Dateien, ca. 18 MB
  💡 Kopiert: `plenio/`, `resources/`, `frontend/`, `tests/`, `tools/` (ohne `tools/tutorials/`), `subgraphs/` und `example_workflows/` ohne MiniMax, `locales/`, Lizenz-/Readme-Dateien, `pyproject.toml`, `requirements.txt`, Player-Starter. Nicht kopiert: `web/` (gebaute ComfyUI-Frontend-Erweiterung), `docs/`, `assets/` (Branding), `tools/tutorials/` (Sprecheraufnahme und Showcase-Bilder ungeklärter Herkunft, für Tests nicht nötig). MiniMax-Modelle stehen noch im kopierten `models.toml`; der Wrapper filtert sie zur Laufzeit.
- [x] Python-Wrapper `backend/soundcraft_plenio/`: eigener `comfy_entrypoint` = Plenios Extension unverändert + `/scp/v1`
  💡 Plenio hat keine eigenen MiniMax-Nodes (MiniMax ist eine Engine-Wahl in Templates); es reicht, MiniMax-Templates, -Subgraphs und -Modelle wegzulassen. Ein Wächter beendet die Instanz, wenn SoundCraft weg ist (`SCP_PARENT_PID`).
- [x] ~~Stage-API~~ → **Plenios Song-API direkt** (`/plenio/api/v1/jobs`, `?wait`, `DELETE`, `templates`, `briefs`, `uploads`, `from-record`); `/scp/v1` nur für Info, Modelle (ohne MiniMax) und Stems
  💡 Anhalten nach Lyrics/Noten („Bei Lyrics/Noten anhalten“) gibt es damit nicht als Zwischenstopp; Lyrics und Noten lassen sich nach jedem Take ändern und neu generieren.
- [x] ComfyUI-Supervisor: findet ComfyUI über Plenios `comfyui-start.json`, eigene Instanz mit `--base-directory`, `--models-directory` des Owners, freiem Port, Log; Stopp beim Schließen
  💡 ComfyUI 0.43.0 unter `D:\Daten2\ComfyUI`, Modelle unter `F:\ComfyUI\models`. Live: bereit nach etwa 10 s. Leerlauf-Stopp noch nicht (Stop-Knopf im Studio-Fenster).
- [x] Modellmanager (`/scp/v1/models` + Downloads in Rust mit Fortschritt, Fortsetzen und Größenprüfung; CC-BY-NC-Modelle erst nach Lizenzbestätigung)
  💡 Systemcheck über `/plenio/system` (Plenios Route) möglich, im UI noch nicht angezeigt.
- [x] ~~Golden-Test gegen eine Stage-Kette~~ entfällt: die Songs entstehen mit Plenios eigenem Template über die Song-API, also identisch zur Plenio-Nutzung
  💡 Echte Läufe: 61-s-Instrumental (133 s), gesungener Song „Heavy in My Pocket“ (93,7 s, durch die SoundCraft-UI, 238 s).
- [x] Kopierte Plenio-Testsuite gegen die Kopie: `tools/test_all.ps1 -Plenio <Checkout>` (pytest aus Plenios `.devdeps`, nur lesend)

### Phase 2 – MVP „YuE2 Song“

- [x] Dialog „Plenio › Neuer Song…“ (250 Genre-Templates mit Suche, Idee oder eigene Lyrics, Länge, Gesang)
- [x] Song-Ordner (Routing-Folder) mit Lyrics-, Noten- und Mix-Spur; Rollen in `Session.extensions`
- [x] Lyrics-Spur: ein Clip je gesungener Zeile (aus Plenios `(lines).srt`), sonst je Abschnitt; Prüfung mit Plenios Regeln (`/plenio/lyrics/analyze`)
  💡 Token-Budget und Silben zeigt Plenios Prüfung als Hinweise; eine eigene Budget-Anzeige gibt es nicht. Take-Wahl im Inspector (nicht im Spurkopf).
- [x] Lyrics-Editor-Panel (Abschnitts-Tags als Buttons, Silben, Budget, Status auto/bearbeitet/manuell, Diff zum letzten Take)
- [x] Inspector mit dynamischem Formular aus `/templates/{id}`
- [x] Generieren → Take als Playlist; Take-Wahl im Header schaltet alle Spuren gleichzeitig
- [x] Veraltet-Anzeige („● Lyrics geändert → Noten + Take“), Seeds sperren/würfeln
- [x] Jobs im Hintergrund mit Fortschritt und Abbrechen; jede Übernahme ist ein Undo-Schritt
- [ ] ~~Schalter „Bei Lyrics/Noten anhalten“~~ (die Song-API v1 hält nicht an; siehe Phase 1)

### Phase 3 – Noten und Stems

- [x] Score ↔ MIDI (Melodie, Akkorde, Begleitlinie) über `/plenio/score/midi/export|import`; stumme Instrument-Spuren mit Synth zum Vorhören
- [x] DAW-Pfad: bearbeitete Noten → zurück an Plenio (Conductor-Track mit Layout und unveränderte Spuren byte-genau) → YuE2 singt genau diese Noten
- [x] Tempo, Takt und Tonart aus dem Score (erster Take einer sonst leeren Session); Abschnitte als farbige Blöcke in der Song-Lane
  💡 Memory Locations werden nicht angelegt (mehrere Songs in einer Session würden sich mischen).
- [x] Stems (Vocals, Drums, Bass, Other, Rest) mit Plenios BS-RoFormer über `/scp/v1/stems`, als Spuren mit Take-Playlists; Mix-Spur stumm, solange ein Take mit Stems spielt
  💡 Live: 61-s-Take in 21,7 s. Stems als MIDI noch nicht.
- [ ] Browser-Score-Editor (kopiertes Vue-Frontend mit SoundCraft-Adapter im Overlay), Änderungen fließen in die Session zurück

### Phase 4 – YuE2 Cover

- [x] „New Cover from Selected Track…“ und im Kontextmenü; Edit-Auswahl = Ausschnitt (`excerpt.start_index/duration`); Upload über `/plenio/api/v1/uploads`
- [x] Analyse macht Plenios Cover-Template (SheetSage2, Qwen3-ASR); der Take bringt Tempo, Noten und Lyrics des Covers mit
  💡 Die gehörten Lyrics des Originals und die gesungene Tonhöhe zeigt das Add-in nicht getrennt an (die Song-API liefert sie nicht als eigenes Ergebnis).
- [x] Alle Cover-Felder der Song-API im Inspector-Formular (Modi, Harmonie, Closeness, original notes); Fit Lyrics macht Plenio im Template
- [x] A/B gegen das Original: die Aufnahme liegt im Cover-Ordner und wird beim ersten Cover-Take stummgeschaltet (zum Vergleich einschalten)
- [x] Cover live durch die UI (`examples/plenio_cover_e2e.rs`): Aufnahme importiert → New Cover from Selected Track → Upload nach 23 s → Cover-Take nach 309 s (54,6 s, mit Lyrics und Noten)

### Phase 5 – Player und Release

- [x] Player-Sidecar: kopierter Player, eigener Zustandsordner und Port, Bibliothek = Ausgabe der Instanz; Party-Songs gehen an die Instanz (`studio.json`)
- [x] „Send the mix to the Plenio Player“: `file.bounce_mix` (FLAC 24 bit) + Record aus dem des Takes (Dokumente, Lyrics-Timing als `(lines).srt`)
  💡 Ohne Plenio-Mastering und ohne PDF; der Mix ist SoundCraft's.
- [ ] Rückweg „In SoundCraft öffnen“ (Overlay statt „Open in ComfyUI“, über den Control-Channel)
- [x] „Import Plenio Song…“: `.plenio.json` + Audio daneben → Song mit Feldern und Seeds aus `/from-record`, Take mit Lyrics und Noten (auch Party-Songs aus der Player-Bibliothek)

### Phase 6 – Härtung

- [x] Parität: Songs entstehen mit Plenios eigenen Templates über die Song-API, also mit allem, was die Templates tun (Best Take, Check Vocals, LoRAs, Creativity, Creative Modes, Master, Cover-Art, Export); im Formular stehen alle Felder der Song-API. Plenios Unit-Tests gegen die Kopie: **1980 bestanden, 1 übersprungen, 0 fehlgeschlagen**.
  💡 Nicht über die API erreichbar und daher offen: Zwischenstopps zum Prüfen (Review-Modus), LoRA-Auswahl (kein Feld der Song-API v1).
- [x] Property-Tests mit feindlichen Eingaben: Job, Record, Score, SRT (`backend/tests/hostile.rs`), MIDI-Splicing (`commands/tests/hostile_midi.rs`); Pfadschutz der Stems-Route live geprüft
- [x] Update-Probelauf SoundCraft: erster echter Merge am 2026-11-06 (5 Commits von `upstream/main`, 1 Konflikt in `crates/engine/src/dirty.rs`), Skript in Wegwerf-Klonen mit erfundenem Upstream geprobt (README, Logos, `Cargo.lock`, zweiter Merge ohne Handarbeit)
- [x] Update-Probelauf Plenio: Plenio-Sync mehrfach ohne Handarbeit (Kopie um `docs/api`, `docs/design/data`, `docs/user/models.md`, `web/docs` erweitert).
- [x] ~~Seams upstream einreichen~~: entfällt, der Owner führt einen eigenen Fork (2026-11-06). Branch `extension-api` gelöscht; seine Commits sind in `plenio-addin` enthalten.
- [x] Fork vorbereitet: eigene `README.md`, ArtCraft-Marken entfernt (ihre Lizenz verlangt das), Update-Quelle der App auf den Fork, `tools/update_soundcraft.ps1` neu (merged statt rebased), [FORK.md](FORK.md)
  💡 Offen beim Owner: Repo auf GitHub anlegen und hochladen. Offen vor eigenen Installern: `packaging/` nennt noch den Ordner `ArtCraft`.
- [x] Benutzer- und Entwicklerdoku: `addins/plenio/README.md`, `docs/architecture.md › Extensions`

---

## 1. Kernentscheidungen

1. **Die Generierung bleibt, wo sie heute funktioniert:** ComfyUI mit dem kopierten Plenio-Code läuft als eigener Hintergrundprozess. YuE2, SheetSage2, ASR und Stems brauchen PyTorch und ComfyUIs Kernel. Plenios eigenes Konzept (`docs/design/standalone-app-concept.md`) schätzt 30–46 Wochen, bis eine Rust-Inferenz so klingt wie heute.
2. **SoundCraft bekommt ein natives Rust-Add-in** für Oberfläche, Spuren, Takes und Steuerung. Ein Absturz in Python oder CUDA kann SoundCraft nicht mitreißen („Never crash“).
3. **Der ganze Add-in-Code liegt in `addins/plenio/`.** SoundCraft bekommt nur 6 kleine, allgemeine Erweiterungspunkte („Seams“), weil es heute kein Add-in-System hat:
   - Die Command-Registry ist ein statisches `OnceLock` (`crates/engine/src/cmd.rs`).
   - Das Menü wird aus dem Katalog gebaut (`crates/ui-egui/src/menus.rs`, `tree()`).
   - Die Docking-Panels sind ein festes Enum (`crates/ui-egui/src/docking.rs`, `Panel`).
   - `Session` hat kein Erweiterungsfeld; fremde Daten gingen beim nächsten Speichern verloren.
4. **Plenio wird kopiert, nicht verändert.** Ein Sync-Skript kopiert 1:1 nach `addins/plenio/vendor/`; alle Anpassungen liegen außerhalb der Kopie (Wrapper, Overlays).

## 2. Architektur

```
┌──────────────────── SoundCraft (Rust, ein Prozess) ─────────────────────┐
│ Upstream-Crates (unverändert)  ◄─ 6 Seams ─►  addins/plenio/crates/*    │
│ model · engine · mix · ui-egui               project · backend ·        │
│                                              commands · ui              │
└──────────────────────────────┬──────────────────────────────────────────┘
          HTTP 127.0.0.1 (JSON, Long-Poll); Prozesse vom Add-in gestartet und überwacht
        ┌──────────────────────┴─────────────────────┐
        ▼                                            ▼
ComfyUI (eigene Instanz, headless)          Plenio Player (Kopie, Python stdlib)
 └ custom_nodes/soundcraft-plenio            127.0.0.1:8765…
    ├ soundcraft_plenio/  Wrapper: Stage-API /scp/v1, Modellmanager
    └ vendor/plenio/      1:1-Kopie (core, comfy, player, workers, third_party …)
```

## 3. Trennung und Update-Fähigkeit

### 3.1 Verzeichnisse

```
addins/plenio/
├─ docs/PLAN.md                 diese Datei
├─ crates/
│  ├─ project/   Datenmodell: Songs, Spur-Rollen, Dokumente, Seeds, Takes (reine Daten)
│  ├─ backend/   HTTP-Client (ureq), Jobs, Prozess-Supervisor, Modelle
│  ├─ commands/  Engine-Commands plenio.* (laufen über Engine::execute → Undo gratis)
│  └─ ui/        egui: Inspector, Lyrics-Editor, Lanes, Take-Wahl, Aktivierungs-Assistent
├─ backend/soundcraft_plenio/   eigener ComfyUI-Entry-Point + Stage-API (Python, neu)
├─ vendor/plenio/               1:1-Kopie + VENDOR.toml (Commit, Version, Datei-Hashes)
├─ frontend/overlay/            ersetzt beim Build z. B. shared/comfy.ts durch einen SoundCraft-Adapter
└─ tools/  sync_plenio.py · update_soundcraft.ps1 · test_all.ps1
```

### 3.2 Die einzigen Änderungen an SoundCraft (allgemein, nichts Plenio-Spezifisches)

| # | Wo | Was | Umfang |
|---|---|---|---|
| S1 | `crates/model/src/session.rs` | `extensions: BTreeMap<String, String>` (serde default, leer nicht gespeichert, Größe in `sanitize` gedeckelt). Add-in-Daten sind damit Teil der Session: Undo, Autosave, Crash-Recovery und Bundles funktionieren ohne Zusatzarbeit. | ~30 Z. |
| S2 | `crates/engine/src/cmd.rs` | `register_extension_commands(Vec<CommandSpec>)`, eingebunden in `command_specs()`/`find_command`. `plenio.*` landet automatisch auch in CLI, MCP und Control-Channel. | ~30 Z. |
| S3 | `crates/ui-egui/src/extension.rs` (neu) + 5–6 Aufrufstellen | Trait `UiExtension`: Menü, Track-Header, Lane-Zeichnen, Dock-Panel (`Panel::Extension`), Frame-Update, Kontextmenü, Einstellungen, Datei-Drop | ~200–250 Z. |
| S4 | `apps/soundcraft` | Cargo-Feature `plenio` plus 3 Zeilen Registrierung in `main.rs` | ~10 Z. |
| S5 | `Cargo.toml` + `xtask` | Workspace-Members `addins/*/crates/*` und Einträge in `LAYERS` (sonst schlägt `cargo xtask layers` fehl) | ~10 Z. |
| S6 | `ATTRIBUTION.md` | eine Verzeichnis-Zeile für `addins/plenio/vendor/` (`xtask assets` akzeptiert Verzeichnis-Zeilen) | 1–3 Z. |

**Regel für den Add-in-Code:** Er ändert SoundCraft nur über dessen eigene Command-IDs (z. B. `track.new`, `track.playlist_new`, `track.playlist_select`, `track.move_to_folder`, `event.tempo`, `event.add_key_change`, `file.import_midi`). `session_mut()` nutzt er nur für die eigenen Erweiterungsdaten. Ändert sich die API, zeigt das ein Compile-Fehler in `addins/`.

### 3.3 SoundCraft-Updates einspielen

- Remote `upstream` = `storytold/soundcraft`; Branch `plenio` / `plenio-addin` = `upstream/main` + Seam-Commit + `addins/`.
- `tools/update_soundcraft.ps1`: fetch, **merge** (der Fork ist veröffentlicht, also kein Rebase), `README.md` bleibt, `Cargo.lock` neu auflösen, ArtCraft-Marken raus, dann `tools/test_all.ps1`. Konflikte sind nur an den in [FORK.md](FORK.md) gelisteten Stellen möglich; Lösungen merkt sich `git rerere`.

### 3.4 Plenio-Updates übernehmen

- `tools/sync_plenio.py --from D:\…\Plenio-Music-Production-System` kopiert eine feste Liste 1:1: `plenio/`, `resources/`, die YuE2-Subgraphs, die Templates 0/1/2/4/5, `frontend/src`, `tests/` sowie LICENSE/NOTICE/THIRD_PARTY.
- Es schreibt `VENDOR.toml`, berichtet geänderte Dateien und führt Plenios Tests und die Wrapper-Tests aus. Ein Hash-Check verhindert Handänderungen an `vendor/`.
- **MiniMax:** keine Templates, Subgraphs oder Modelle von MiniMax, nichts in der Oberfläche; der Wrapper registriert die MiniMax-Nodes nicht. MiniMax ist in `plenio/core` verwoben (`engines/__init__.py`, `brief.py`, `writing.py`); diese Dateien werden als inaktiver Code mitkopiert, weil Entfernen die Kopie verändern würde.

## 4. Bedienkonzept

### 4.1 Ein Plenio-Song im Edit-Fenster

```
▼ ✦ Nachtfahrt (Plenio-Song)   Take ◀ 3/5 ▶ ★★★★☆   ● Lyrics geändert   [⟳ Generieren ▾]
  │Intro│ Verse 1 │Pre│ Chorus │ Verse 2 │ Chorus │Bridge│ Chorus │Outro│  ← Song-Form
  ├ Lyrics       [verse] Regen auf dem Asphalt … │ [chorus] Wir fahren …
  ├ Melodie      MIDI, mit SoundCraft-Instrument vorhörbar
  ├ Akkorde      MIDI
  ├ Begleitlinie MIDI
  ├ Song (Mix)   Audio, Takes als Playlists
  └ (optional) Vocals · Drums · Bass · Other · Rest   ← Stems, Summe = Take
 Audio 1 · MIDI 1 · Instrument …   ← eigene Spuren, überall, auch im Ordner
```

| Spur | Technisch | Was das Add-in ergänzt |
|---|---|---|
| **Song** | Routing-Folder: summiert alle Kinder (Effekte auf den ganzen Song) | Header mit Status, Take-Wahl, Generieren; Lane mit den Abschnitten; Inspector mit allen YuE2-Parametern |
| **Lyrics** | stumme MIDI-Spur, ein Clip je Abschnitt | Lane zeigt Text statt Noten; YuE2-Regeln live (Abschnitts-Tags, eigene Tags, Silben, Token-Budget 24 576 über Plenios Tokenizer); nach dem Rendern Wörter an der gesungenen Stelle |
| **Noten** | MIDI-Spuren mit eingebautem Instrument | Projektion von Plenios Score (ABC bleibt Hauptquelle); Bearbeitung → „bearbeitet“ → YuE2 singt genau diese Noten (Pfad „YuE2 · DAW“) |
| **Ergebnis** | normale Audiospuren | Effekte, Schnitte, Fades, Automation wie immer; Takes = Playlists; Comping mit den vorhandenen Playlist-Lanes |
| **Cover-Quelle** | normale Audiospur mit dem Original | Analysequelle; A/B über Solo/Mute |

Tempo-Map und Tonart kommen aus dem Score, sodass eigene MIDI-Spuren sofort im Raster liegen. Abschnitte werden als Memory Locations angelegt (Navigation, Loop pro Abschnitt).

### 4.2 Takes

- Jede Generierung ist ein **Take** über alle Spuren des Songs: Playlists gleichen Namens auf Lyrics-, Noten- und Audiospuren („Take 4 · neue Lyrics ★4“).
- Ein Take friert Lyrics, Noten, Parameter und Seeds ein. Wählst du Take 2, siehst du dessen Lyrics und Noten und kannst von dort weiterarbeiten.
- Alte Takes bleiben mit deinen Bearbeitungen erhalten; Aufräumen mit `track.playlist_delete_unused`.
- Jede übernommene Generierung ist **ein Undo-Schritt**.

### 4.3 Ändern und neu generieren

| Du änderst … | Plenio macht neu … | Ergebnis |
|---|---|---|
| Seed, Anzahl Takes, LoRA, Lyrics-Fidelity | nur rendern | neuer Take |
| Noten (MIDI oder Score-Editor) | rendern mit deinem Score | neuer Take, singt exakt deine Noten |
| Lyrics | neu komponieren, dann rendern (neue Worte brauchen neue Noten); beim Cover alternativ auf die Melodie einpassen (Fit Lyrics) | neue Noten und neuer Take |
| Stil, Tempo, Tonart, Länge | neu planen, dann rendern | dto. |
| Brief oder Idee | neu schreiben, planen, rendern | dto. |

- Von Hand bearbeitete Dokumente bleiben unangetastet (auto, bearbeitet, manuell).
- Seeds (draft, plan, arrangement, take) lassen sich sperren oder neu würfeln.
- Der Song-Header zeigt, was veraltet ist („● Lyrics geändert → Noten + Take“).
- Generieren-Menü: „Neuer Take“, „Neu komponieren“, „Lyrics neu schreiben“, „×4 Takes, Best Take wählen“.
- Jobs laufen im Hintergrund; Transport spielt weiter; Fortschritt und Abbrechen im Header und im Jobs-Panel.

### 4.4 Neuer Song

- **Plenio › Neuer Song…**: Genre aus 250 Templates (Suche), Idee oder eigene Lyrics, Länge, Gesang, „Erstellen“.
- Die Spuren erscheinen sofort und füllen sich nacheinander: Lyrics, Noten, Take.
- Schalter **„Bei Lyrics/Noten anhalten“** entspricht Plenios Modus „one song, stop to review“.

### 4.5 Cover

- Rechtsklick auf Audiospur oder Auswahl → **„Plenio-Cover daraus…“**; die Edit-Auswahl wird zum Ausschnitt (`excerpt`).
- Analyse füllt Tempo und Beat-Grid (SheetSage2), Noten-Spuren mit dem Original, Lyrics-Spur mit den gehörten Worten (unsichere markiert), optional die gesungene Tonhöhe.
- Wählbar: instrumental, original lyrics, new lyrics, Harmonie, song flow closeness, lyrics closeness, original notes. Danach wie beim Song.

### 4.6 Notation

1. **Nativ:** Noten-Spuren im MIDI- und Score-Editor von SoundCraft (Notation, MusicXML, Print Score). Später Lyrics unter den Melodienoten.
2. **Volle Parität ab Tag 1:** **„Im Plenio-Score-Editor öffnen“** startet den kopierten Vue-Editor im Browser (Overlay-Adapter statt ComfyUI): Akkord-Lane, Bar-Inspector, Arrangieren, MIDI-Keyboard, PDF. Änderungen fließen in die Session zurück.

### 4.7 Stems

- „In Stems aufteilen“ legt Vocals, Drums, Bass, Other, Rest an; optional automatisch für jeden Take.
- Optional Stems als MIDI (z. B. Bassline mit eigenem Instrument ersetzen).
- Standard bleibt eine Mix-Spur (Plenio stuft Stems als experimentell ein).

### 4.8 Player

- **Plenio › An Player senden:** Bounce des Song-Ordners (mit deinen Effekten), dann kopierter Export-Release-Schritt (FLAC/MP3, Tags, Lyrics-Timing auf dem Vocal-Stem, PDF, `.plenio.json`) in die Player-Bibliothek; Plenio-Mastering (-14 LUFS) optional.
- **Player öffnen** startet den kopierten Player mit eigenem Zustandsordner. „Open in ComfyUI“ wird per Overlay zu „In SoundCraft öffnen“ (Control-Channel).
- Party-Songs funktionieren weiter; „In SoundCraft übernehmen“ macht daraus einen regenerierbaren Plenio-Song, ebenso eine hineingezogene Plenio-FLAC.

### 4.9 Aktivieren und Modelle automatisch laden

**Plenio › Add-in aktivieren…** öffnet einen Assistenten:

1. **Systemcheck** (kopierter `system.py`): GPU, VRAM → Empfehlung int8 (4 GB) oder bf16 (7,8 GB, ab 24 GB VRAM).
2. **ComfyUI finden:** über Plenios `comfyui-start.json` und `extra_model_paths.yaml`, sonst Download von ComfyUI portable anbieten. Eigene headless Instanz mit eigenem Basisordner; vorhandene ComfyUI- und Plenio-Installationen bleiben unberührt, vorhandene Modelle werden mitbenutzt.
3. **Modelle** über den kopierten Katalog (`models.toml` ohne MiniMax) und Downloader (fortsetzbar, SHA-256), Fortschritt in SoundCraft:
   - Profil „Song“: YuE2, Instrumental-LoRA, Writer, UniverSR.
   - Profil „Cover“ beim ersten Cover: SheetSage2 (1,4 GB), Qwen3-ASR + Aligner (3,8 + 1,7 GB), BS-RoFormer (0,5 GB).
   - FLUX.2 Klein (Cover-Art) optional.
   - **Lizenz CC BY-NC 4.0 (nicht kommerziell) von YuE2 und SheetSage2 wird vor dem Download angezeigt und muss bestätigt werden.**
4. **Testlauf:** kurzer Instrumental-Take.

Deaktivieren blendet die Oberfläche aus und beendet die Prozesse; die Session bleibt voll nutzbar (alles Erzeugte ist normales Audio und MIDI).

## 5. Backend: kopierter Code plus Wrapper

Die Song-API v1 läuft immer komplett durch (keine Review-Stopps), ihre Ergebnisrollen enthalten keine Stems. Der Wrapper bietet daher eine **Stage-API `/scp/v1`**. Jede Stufe ist ein ComfyUI-Lauf aus den kopierten Subgraphs, der Workflow wird auf den Ziel-Node gekürzt; ComfyUI hält Modelle und unveränderte Zwischenergebnisse im Cache.

| Endpunkt | Basis (kopiert) |
|---|---|
| `draft`: Brief → Titel, Stil, Lyrics | Subgraph *Write Song*, `core.writing` |
| `lyrics/check`: live prüfen | Routen `lyrics/analyze`, `sheet/resolve` |
| `plan`: Score, Abschnitte, BPM, Tonart, MIDI | *YuE2 Plan*, Song Form, `score/midi` |
| `score/from-midi`, `to-midi`, `musicxml` | `score/midi/*`, `musicxml/*` |
| `render`: Takes, Best Take, Qualität, gesungenes Timing | *YuE2 Render/Takes*, Subtitles |
| `stems` | *Stems* |
| `cover/analyze`, `cover/fit` | *Transcribe Score*, Lyrics-ASR, Sung Pitch, Fit Lyrics |
| `release` | Export Release, *Master* |
| `system`, `models` | `system.py`, `assets/fetch.py` |
| `jobs/{id}?wait`, `DELETE` | Job-Mechanik der Song-API |

Die Parameterformulare baut das Rust-UI **dynamisch aus `/templates/{id}`**; neue Plenio-Felder erscheinen ohne Rust-Änderung.

## 6. Qualität mindestens wie heute

- Gleicher Code, gleiche ComfyUI-Nodes, gleiche Subgraphs.
- **Golden-Test:** Template 1 bzw. 2 im Original gegen die Stage-Kette, gleiche Seeds und Dokumente; Vergleich von Dokument-Hashes und Audio.
- Plenios Testsuite läuft nach jedem Sync gegen die Kopie.
- Paritäts-Checkliste aus Plenios Funktionsinventar (siehe Phase 6).

## 7. SoundCraft-Regeln

- Jedes Add-in-Crate: `[lints] workspace = true` und `#![deny(clippy::unwrap_used, clippy::expect_used, clippy::panic, clippy::unimplemented, clippy::todo, clippy::unreachable)]`; kein `unsafe`.
- Backend-Antworten sind feindliche Eingaben: Größen deckeln, `get()` statt Index, gecheckte Arithmetik.
- HTTP nie auf UI- oder Audio-Thread; Ergebnisse per Channel, im Frame-Hook per `execute` angewendet.
- Add-in nur nativ; Web/WASM-Build bleibt unberührt.
- CI bleibt unverändert; Python-Tests lokal über `tools/test_all.ps1`.
- `addins/plenio` unter Apache-2.0 mit NOTICE (passt zu MIT OR Apache-2.0). ComfyUI (GPL) wird nie kopiert oder gebündelt, nur als externer Prozess gestartet.
- Jedes gebündelte Asset (auch in `vendor/`) braucht eine Zeile in `ATTRIBUTION.md` (S6).

## 8. Phasen und Aufwand (grobe Schätzung in Agent-Stunden)

| Phase | Inhalt | Abnahme | h |
|---|---|---|---|
| 0 Fundament | Git, Seams S1–S6 mit Tests, leere Crates, Plenio-Menü, Aktivieren-Schalter | `cargo xtask ci` grün | 10–15 |
| 1 Backend | Sync-Skript, Wrapper mit `draft`/`plan`/`render`, ComfyUI-Supervisor, Systemcheck, Modell-Downloads | Golden-Test Song identisch | 25–40 |
| 2 MVP Song | Dialog, Ordner und Spuren, Lyrics-Spur und Editor, Inspector, Takes als Playlists, Veraltet-Anzeige, Jobs, Undo | erster Song komplett in SoundCraft | 35–55 |
| 3 Noten und Stems | Score↔MIDI, DAW-Pfad, Tempo/Tonart, Memory Locations, Stems, Browser-Editor-Adapter | Noten editieren, YuE2 singt sie | 30–45 |
| 4 Cover | Cover aus Spur/Auswahl, Analyse, drei Vocal-Modi, Fit Lyrics, A/B | Golden-Test Cover | 20–30 |
| 5 Player | Player-Sidecar, „An Player senden“, Rückweg, FLAC übernehmen | Song im Player mit Lyrics und Noten | 12–20 |
| 6 Härtung | Paritäts-Checkliste, Fuzzing, Update-Probelauf, Doku | beide Updates ohne Handarbeit | 15–25 |

Bis zum MVP grob 70–110 h, insgesamt etwa 150–230 h.

## 9. Risiken

- **Score-Rundweg ABC ↔ MIDI** kann Details verlieren; der Browser-Editor fängt das ab.
- **Eigene ComfyUI-Instanz:** `--base-directory` in Phase 1 prüfen. Laufen deine ComfyUI und die Add-in-Instanz gleichzeitig, konkurrieren sie um die GPU; die Add-in-Instanz entlädt nach Leerlauf ihre Modelle oder stoppt.
- **Comping über Takes** klappt gut bei gleichem Score (gleiches Tempo, gleiche Form), bei neuem Score eingeschränkt.

## 10. Entscheidungen (alle getroffen am 2026-11-05)

| # | Frage | Entscheidung |
|---|---|---|
| 9.1 | Eigene ComfyUI-Instanz oder bestehende? | **Eigene Instanz** |
| 9.2 | Seams upstream einreichen? | ~~Ja, erlaubt~~ → **Nein: eigener Fork mit regelmäßigem Merge** (2026-11-06) |
| 9.3 | `origin` → `upstream`, Branch `plenio-addin`? | **Ja, erlaubt** – erledigt |
| – | Plenio-Projekt ändern? | **Nein** – Code wird nach SoundCraft kopiert |

## 11. Fundstellen für die Umsetzung (geprüft 2026-11-05)

**SoundCraft**

- Command-Registry: `crates/engine/src/cmd.rs` – `command_specs()` (statisches `OnceLock`), `find_command`, Makro `cmd!`; `CommandSpec`-Felder sind `pub` (`&'static str`, Funktionszeiger).
- Engine-API: `crates/engine/src/lib.rs` – `session()`, `session_mut()` (pub), `execute()`, `execute_merged()`.
- Session: `crates/model/src/session.rs` – `Session` (ohne Erweiterungsfeld), `from_json` parst ohne `Value`-Baum, unbekannte Schlüssel werden ignoriert; `EditState.flags`/`values` (von Score Setup genutzt).
- Track/Playlist/Clip: `crates/model/src/track.rs`, `crates/model/src/clip.rs` (`ClipContent::Audio|Midi|Video`).
- Playlist-Lanes mit Comping: `crates/ui-egui/src/edit_window/tracks.rs` (`playlist_lanes`).
- Menü: `crates/ui-egui/src/menus.rs` (`tree()`, `UI_COMMANDS`, `menu_bar`).
- Docking: `crates/ui-egui/src/docking.rs` (`Panel`-Enum).
- App-Einstieg: `apps/soundcraft/src/main.rs` (`SoundApp::new(engine, player, services())`).
- Notation: `crates/engine/src/score.rs`, `crates/ui-egui/src/panels/score_editor.rs`.
- Wiederverwendbare Commands: `track.playlist_new`, `track.playlist_select`, `track.playlist_duplicate`, `track.playlist_delete_unused`, `track.move_to_folder`, `track.rename`, `track.color`, `track.comments`, `event.tempo`, `event.add_key_change`, `file.import_midi`, `clip.rename`, `clip.color`.
- Layer-Prüfung: `xtask/src/main.rs` (`LAYERS`); Asset-Prüfung: `assets()` (Verzeichnis-Zeilen decken ganze Bäume ab).
- Schon in `Cargo.lock`: `ureq 3.5.0`, `sha2 0.10.9`, `zip 9.1.3`.

**Plenio**

- Song-API: `plenio/comfy/song_api.py`, `plenio/core/song_api.py`, Doku `docs/api/README.md` (v1.3; keine Review-Stopps).
- Routen für Editor und Werkzeuge: `plenio/comfy/routes.py` (`ROUTES`: score analyze/transform, midi import/export, musicxml, lyrics analyze, sheet resolve, templates, brief fields, presets, eq, export sheet-music, records, player open).
- Einstieg: `plenio/comfy/extension.py` (`PlenioExtension.on_load`), Node-Liste `plenio/comfy/nodes/__init__.py` (`NODES`).
- Subgraphs: `subgraphs/` (Write Song, YuE2 Plan, YuE2 Render, YuE2 Takes, Stems, Transcribe Score, Fix Misheard Words, Master, Arrange, Cover Art, Refine).
- Modelle: `resources/models.toml`, Downloader `plenio/core/assets/fetch.py`.
- ComfyUI starten: `plenio/player/studio.py` (Python finden, Argumente, Log, Leerlauf-Stopp, `comfyui-start.json`), Player-Start: `plenio/player/launch.py`.
- Stems: `plenio/comfy/nodes/stems.py` (Separate Stems, Stem Mixer, Stems als MIDI).
- Release-Record: `resources/schemas/record-1.schema.json`.

## Stand 2026-11-05 abends (Fortsetzungspunkt)

- [x] **Entscheidung:** Generierung läuft direkt über Plenios **Song-API** (`/plenio/api/v1`: jobs, templates, briefs, uploads), nicht über eine eigene Stage-API. Der Wrapper `addins/plenio/backend/soundcraft_plenio` lädt Plenio unverändert und ergänzt nur `/scp/v1` (Info, Modelle ohne MiniMax) und einen Eltern-Wächter (`SCP_PARENT_PID`).
- [x] Phase 1: Studio (`crates/backend`: discover, instance, client, song, studio). Eigene Instanz mit `--base-directory`, Modellen aus `F:\ComfyUI\models`, `PLENIO_PLAYER_STATE` im Add-in-Ordner. Live geprüft: Start und Stopp in 10 s, echter Job (61-s-Instrumental in 133 s).
- [x] Phase 2: `plenio.song.new/set/forget`, `plenio.take.add/select`; Plan-Regeln (neue Worte → neue Noten); UI mit Menü, New-Song-Dialog (250 Templates), Inspector (Takes, Generate/More, Lyrics-Editor mit YuE2-Tags und Prüfung über `/plenio/lyrics/analyze`, Brief-Formular dynamisch aus `/templates`, Seeds), Spurkopf-Plakette, Abschnitte in der Song-Lane, Studio- und Modellfenster mit Downloads.
- [x] Phase 3 (Teil): Score als Plenio-MIDI auf stummen Notenspuren (Melody, Instrument Line, Chords); bearbeitete Noten werden mit Plenios Conductor-Track byte-genau zurückgeschickt (`/plenio/score/midi/import`) und gesungen. Stems noch offen.
- [x] End-to-End durch die SoundCraft-UI (`cargo run -p soundcraft-plenio-ui --example plenio_e2e -- <Ordner>`): Aktivieren → New Song → Take nach 241 s („The Heavy Air“, 94,8 s, 8 gesungene Zeilen, 4 Abschnitte, 74 BPM) → Noten auf Melody/Instrument Line/Chords → Stems über den Inspector in 21 s (Vocals, Drums, Bass, Other, Rest; Song-Spur stumm) → Mix an den Player gesendet, Player gestartet
- [ ] Offen: Browser-Score-Editor (Plenios Vue-Editor mit SoundCraft-Adapter), „In SoundCraft öffnen“ aus dem Player, Zwischenstopps (Review) und LoRAs (nicht in Song-API v1), Leerlauf-Stopp des Studios, Inspector als Dock-Panel, `soundcraft-cli` (headless/MCP) mit `plenio.*`
- 💡 egui_kittest bricht bei fehlenden Glyphen ab, das Programm zeigt dann nur Ersatzkästchen: keine Symbole wie ✦ ★ ● ▾ ✓ in UI-Texten.

## Änderungsprotokoll

| Datum | Änderung |
|---|---|
| 2026-11-05 | Plan erstellt, Entscheidungen 9.1–9.3 eingetragen; Git eingerichtet (`upstream`, Branch `plenio-addin`); fehlende Rust-Toolchain notiert |
| 2026-11-05 | Rust 1.99.1 installiert; Baseline gemessen (3 Windows-Fehler in `soundcraft-cli`, schon vor dem Add-in); Phase 0 erledigt: Seams S1–S6, vier Add-in-Crates, Plenio-Menü und Aktivierung, Offscreen-Screenshots geprüft; Phase 1 begonnen: Sync-Skript und erste Kopie von Plenio 1.5.0 |
| 2026-11-05 | Phase 1–3 und 5: Studio, Song-API-Anbindung, Songs/Takes/Noten/Stems, Player, Import; Plenios Unit-Tests gegen die Kopie: 1980 bestanden, 1 übersprungen; End-to-End durch die UI; Branch `extension-api` mit den Seams |
| 2026-11-06 | Phase 4 live: Cover durch die UI (309 s), Original beim ersten Cover-Take stumm |
| 2026-11-06 | Rückmeldungen des Owners: (1) Inspector in der Höhe veränderbar, Lyrics wachsen mit. (2) Audio, Lyrics und Noten liegen zusammen: Plenios gemessener Warp aus dem Release-Record (`timing[0].warp`, ohne Worte Schätzung über `POST /scp/v1/align`); erster Score-Takt auf einem Taktstrich, Audio dagegen versetzt; Stems und Player folgen. Gemessen an „A Winter Shroud“: gesungene Zeilen gegen Noten im Median 0,05 s statt 1,3 s; live an „Sentences in the Shower“ (Warp 1,009/−1,71): Median 0,07 s, schlechteste Zeile 0,38 s. Plenios `follow()`-Pfad war gegen das Gehörte schlechter als die Gerade (Median 0,12 s), daher die Gerade. (3) MIDI-Clips des ersten Takes wurden mit dem alten Session-Tempo vermessen (120 statt 84 BPM: Ende bei 70 %) und nur bis zur letzten Note der eigenen Spur: Tempo zuerst, jeder Clip bis zum Score-Ende. Daten geprüft: Score, MIDI und SoundCrafts Leser haben dieselben 143/240/280 Noten. (4) Eigener Fork statt Upstream-PR, siehe [FORK.md](FORK.md); erster echter Merge von `upstream/main` (5 Commits, 1 Konflikt in `dirty.rs`), Skript zusätzlich in Wegwerf-Klonen geprobt |
