# Der Fork „SoundCraft with Plenio“

Dieser Fork wird dauerhaft eigenständig geführt und nimmt regelmäßig SoundCrafts Änderungen auf. Es gibt
keinen Weg zurück zu SoundCraft (Entscheidung des Eigentümers vom 2026-11-06, ersetzt die frühere
Entscheidung 9.2 „Seams upstream einreichen“).

## Aufbau

| | Wo | Was |
|---|---|---|
| Remote `upstream` | `github.com/storytold/soundcraft` | SoundCraft; nur lesen |
| Remote `origin` | `github.com/jplenio/soundcraft-plenio` | dieser Fork |
| Branch `plenio-addin` | Standard-Branch des Forks | SoundCraft plus Add-in: hier wird gearbeitet |
| Branch `main` | im Fork | reine Kopie von `upstream/main`, ohne eigene Commits |

`git diff main plenio-addin -- . ":(exclude)addins"` zeigt damit jederzeit genau, was der Fork an SoundCraft
ändert. Ein Commit mit Fork-eigenem Code gehört nie auf `main`.

## Was auf GitHub zu tun ist (einmalig)

1. **Fork anlegen:** `github.com/storytold/soundcraft` → **Fork** → Name `soundcraft-plenio`, Haken bei „Copy the
   `main` branch only“ lassen → **Create fork**.
   - Ein GitHub-Fork eines öffentlichen Repos ist immer öffentlich. Soll er privat sein: stattdessen unter
     **New repository** ein leeres privates Repo `soundcraft-plenio` anlegen (ohne README, Lizenz und .gitignore).
   - Bei einem anderen Namen oder Konto müssen `repo:` in `crates/ui-egui/src/lib.rs` (Update-Quelle), der Link in
     `crates/ui-egui/src/panels/about.rs` und der Klon-Befehl in `README.md` angepasst werden.
2. **Hochladen,** lokal in diesem Ordner:
   ```sh
   git remote add origin https://github.com/jplenio/soundcraft-plenio.git
   git push -u origin plenio-addin
   git push origin upstream/main:refs/heads/main
   ```
3. **Standard-Branch:** Repo → **Settings → General → Default branch** → `plenio-addin`.
4. **Actions aus lassen:** In einem Fork sind die Workflows zunächst aus; im Tab **Actions** nichts aktivieren. Sie
   rufen `storytold/craft-common-actions` mit Secrets auf, die der Fork nicht hat. Geprüft wird lokal mit
   `tools/test_all.ps1`. Die Workflow-Dateien bleiben unverändert im Repo, damit sie beim Merge nie stören.

**„Sync fork“ auf GitHub nicht für `plenio-addin` benutzen:** Es würde ungeprüft mergen. Für `main` ist es harmlos,
aber auch unnötig, weil das Skript `main` mitschiebt.

## Regelmäßig SoundCraft aufnehmen

```powershell
pwsh addins/plenio/tools/update_soundcraft.ps1 -Preview    # was käme, und gäbe es Konflikte? Ändert nichts
pwsh addins/plenio/tools/update_soundcraft.ps1 -Full -Push # mergen, alles prüfen, hochladen
```

Das Skript merged immer und rebased nie, denn die Historie des Forks ist veröffentlicht. Es entscheidet selbst, was
keine Entscheidung braucht:

- `README.md` bleibt die des Forks (`merge=ours`, eingetragen in `.git/info/attributes` dieses Klons).
- `Cargo.lock` wird die von SoundCraft, cargo trägt die Add-in-Crates wieder ein.
- ArtCraft-Marken, die SoundCraft neu mitbringt, fliegen wieder raus.
- Von Hand gelöste Konflikte merkt sich `git rerere` und wendet sie beim nächsten Mal selbst an.

`-Full` lässt zusätzlich SoundCrafts ganze Testsuite laufen. Bekannte Fehlschläge auf diesem Rechner sind nur drei
Tests von `soundcraft-cli` (`it`): Unter Windows läuft dort eine Verbindung in ein Timeout statt abgewiesen zu
werden, unabhängig vom Add-in.

### Wenn ein Konflikt stehen bleibt

Das Skript listet die Dateien und hält an. Es können nur Stellen aus der Tabelle unten sein, denn SoundCraft fasst
`addins/` nie an. Beide Seiten behalten, dann:

```powershell
git add <datei>; git commit --no-edit
pwsh addins/plenio/tools/update_soundcraft.ps1 -Continue -Full -Push
```

Abbrechen geht jederzeit mit `git merge --abort`. Nach einem fertigen Merge führt `git reset --hard ORIG_HEAD` zurück,
solange nichts hochgeladen ist.

Typischer Fall (beim ersten echten Merge am 2026-11-06 aufgetreten): SoundCraft ergänzt ein Feld von `Session`, und in
`crates/engine/src/dirty.rs` stehen die Felder beider Seiten in derselben Zeile. Lösung: beide Felder behalten.

## Warum Plenio von SoundCrafts Änderungen nicht betroffen ist

Alles vom Add-in liegt in `addins/plenio/`, und SoundCraft kennt diesen Ordner nicht. Die Kopie von Plenio in
`vendor/plenio` ist nur durch `tools/sync_plenio.py` zu ändern und wird gegen `VENDOR.sha256` geprüft. Bricht eine
SoundCraft-Änderung eine Schnittstelle, die das Add-in nutzt, schlägt das in `test_all.ps1` beim Merge an, nicht erst
bei der Benutzung.

## Was der Fork an SoundCraft ändert

| Datei | Änderung | Warum |
|---|---|---|
| `crates/model/src/session.rs`, `crates/engine/src/dirty.rs` | Feld `extensions` | Daten des Add-ins in der Session |
| `crates/engine/src/cmd.rs`, `cmd/extensions.rs` (neu) | `register_extension_commands` | Befehle des Add-ins |
| `crates/ui-egui/src/extension.rs` (neu), wenige Aufrufe in `lib.rs`, `app.rs`, `menus.rs`, `edit_window/tracks.rs` | `UiExtension` | Oberfläche des Add-ins |
| `apps/soundcraft/` | Feature `plenio`, zwei Zeilen in `main.rs` | schaltet das Add-in ein |
| `Cargo.toml`, `xtask/src/main.rs` | Workspace-Mitglieder, Layer aus dem Manifest | baut und prüft `addins/` |
| `docs/architecture.md`, `ATTRIBUTION.md` | Abschnitt „Extensions“, Zeile für `vendor/` | Doku und Herkunft |
| `crates/ui-egui/src/lib.rs` | `UPDATE_APP`: `repo` und `developer` | siehe unten: Updates |
| `crates/ui-egui/src/panels/about.rs` | Text und Links im About-Fenster | siehe unten: Marken |
| `README.md` | eigene Fassung | siehe unten: Marken |
| `docs/brand/` | Logos entfernt, `LICENSE-brand.txt` bleibt | siehe unten: Marken |

### Updates

Die App sucht beim Start nach neuen Releases. Unverändert hätte sie das offizielle SoundCraft-Release angeboten, und
ein Klick hätte die Plenio-Version durch eine Version ohne Add-in ersetzt. Deshalb zeigt `UPDATE_APP` auf die Releases
dieses Forks. Solange der Fork keine Releases hat, bleibt das still; **Help › Check for Updates** meldet dann nichts
Neues oder einen Fehler.

### ArtCraft-Marken

`docs/brand/LICENSE-brand.txt` schreibt vor: Wer eine veränderte Fassung veröffentlicht oder weitergibt, muss die
ArtCraft-Marken entfernen und darf sie nicht als ArtCraft-Produkt darstellen; im Klartext darf stehen, dass sie auf
SoundCraft vom ArtCraft-Team beruht. Die Ausnahme für Forks gilt nur für Forks, die Änderungen zurückschlagen sollen,
also nicht für diesen. Die Copyright-Zeilen in `LICENSE-MIT` und `NOTICE` müssen dagegen bleiben.

**Noch offen, bevor Installer oder fertige Programme verteilt werden** (für Klonen und Selberbauen nicht relevant):

- `packaging/windows/*` installiert nach `Programs\ArtCraft\SoundCraft`,
- `packaging/linux/flatpak/*` liest `xdg-data/ArtCraft/versions`,
- `.github/workflows/windows-arm64.yml` prüft diesen Installationsordner.

Das ist bewusst noch unverändert: Es wird erst gebraucht, wenn der Fork eigene Releases baut, und jede Änderung dort
wäre eine zusätzliche Stelle für Merge-Konflikte. Diese Einschätzung der Lizenztexte ist keine Rechtsberatung; bei
Zweifeln oder für eine Erlaubnis ist das ArtCraft-Team über getartcraft.com erreichbar.

## Was mit dem Repo öffentlich wird

Bei einem öffentlichen Fork: die Kopie von Plenio samt seinen Tests und Docs (1073 Dateien), dieser Plan mit den
lokalen Pfaden dieses Rechners, und die E-Mail-Adresse in den Commits (`git log`). Ist auf GitHub „Block command line
pushes that expose my email“ aktiv, lehnt GitHub den ersten Push ab.
