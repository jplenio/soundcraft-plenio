# The fork "SoundCraft with Plenio"

This fork is kept on its own for good and takes in SoundCraft's changes regularly. Nothing goes back to SoundCraft
(the owner's decision of 2026-11-06, which replaces the earlier decision 9.2, "submit the seams upstream").

## Layout

| | Where | What |
|---|---|---|
| Remote `upstream` | `github.com/storytold/soundcraft` | SoundCraft; read only |
| Remote `origin` | `github.com/jplenio/soundcraft-plenio` | this fork |
| Branch `plenio-addin` | the fork's default branch | SoundCraft plus the add-in: the work happens here |
| Branch `main` | in the fork | a plain copy of `upstream/main`, with no commits of its own |

So `git diff main plenio-addin -- . ":(exclude)addins"` always shows exactly what the fork changes in SoundCraft. A
commit with the fork's own code never goes on `main`.

## What to do on GitHub (once)

Done on 2026-11-06: the repository `jplenio/soundcraft-plenio` exists, `plenio-addin` and `main` are uploaded.
The steps stay here for a second clone or another account.

1. **Create the fork:** `github.com/storytold/soundcraft` → **Fork** → name `soundcraft-plenio`, keep "Copy the `main`
   branch only" ticked → **Create fork**.
   - A GitHub fork of a public repository is always public. For a private one, create an empty private repository
     `soundcraft-plenio` under **New repository** instead (without README, licence or .gitignore).
   - With another name or account, change `repo:` in `crates/ui-egui/src/lib.rs` (the update source), the link in
     `crates/ui-egui/src/panels/about.rs` and the clone command in `README.md`.
2. **Upload,** locally in this folder:
   ```sh
   git remote add origin https://github.com/jplenio/soundcraft-plenio.git
   git push -u origin plenio-addin
   git push origin upstream/main:refs/heads/main
   ```
3. **Default branch:** repository → **Settings → General → Default branch** → `plenio-addin`.
4. **Leave Actions off:** in a fork the workflows start out off; enable nothing in the **Actions** tab. They call
   `storytold/craft-common-actions` with secrets the fork does not have. Checks run locally with `tools/test_all.ps1`.
   The workflow files stay in the repository unchanged, so that they never get in the way of a merge.

**Do not use "Sync fork" on GitHub for `plenio-addin`:** it would merge unchecked. For `main` it is harmless but also
needless, because the script moves `main` along.

## Taking in SoundCraft regularly

```powershell
pwsh addins/plenio/tools/update_soundcraft.ps1 -Preview    # what would come, and would it conflict? Changes nothing
pwsh addins/plenio/tools/update_soundcraft.ps1 -Full -Push # merge, check everything, upload
```

The script always merges and never rebases, because the fork's history is published. It decides by itself what needs
no decision:

- `README.md` stays the fork's (`merge=ours`, set in `.git/info/attributes` of this clone).
- `Cargo.lock` becomes SoundCraft's, and cargo adds the add-in's crates back.
- ArtCraft marks that SoundCraft newly brings in are removed again.
- `git rerere` remembers conflicts solved by hand and applies them itself the next time.

`-Full` also runs SoundCraft's whole test suite. On Windows it skips three tests of `soundcraft-cli` there: a
connection to a closed port times out instead of being refused. They fail here without the add-in too.

### When a conflict remains

The script lists the files and stops. They can only be places from the table below, because SoundCraft never touches
`addins/`. Keep both sides, then:

```powershell
git add <file>; git commit --no-edit
pwsh addins/plenio/tools/update_soundcraft.ps1 -Continue -Full -Push
```

`git merge --abort` cancels at any time. After a finished merge, `git reset --hard ORIG_HEAD` goes back, as long as
nothing has been uploaded.

A typical case (it happened in the first real merge, on 2026-11-06): SoundCraft changes the field list of `Session` in
`crates/engine/src/dirty.rs`, where the fork added `extensions`. The solution: take SoundCraft's change and keep
`extensions` in the list. If the field goes missing afterwards, the compiler says so.

## Why SoundCraft's changes do not affect Plenio

Everything of the add-in lies in `addins/plenio/`, and SoundCraft does not know that folder. The copy of Plenio in
`vendor/plenio` can only be changed by `tools/sync_plenio.py` and is checked against `VENDOR.sha256`. If a SoundCraft
change breaks an interface the add-in uses, `test_all.ps1` reports it at the merge, not only when the app is used.

## What the fork changes in SoundCraft

| File | Change | Why |
|---|---|---|
| `crates/model/src/session.rs`, `crates/engine/src/dirty.rs` | field `extensions` | the add-in's data in the session |
| `crates/engine/src/cmd.rs`, `cmd/extensions.rs` (new) | `register_extension_commands` | the add-in's commands |
| `crates/ui-egui/src/extension.rs` (new), a few calls in `lib.rs`, `app.rs`, `menus.rs`, `edit_window/tracks.rs` | `UiExtension` | the add-in's UI |
| `apps/soundcraft/` | feature `plenio`, two lines in `main.rs` | turns the add-in on |
| `apps/soundcraft/src/main.rs` | `open_filter`: the file dialog offers the extensions its caller names | otherwise "Import Plenio Song…" offers only audio |
| `Cargo.toml`, `xtask/src/main.rs` | workspace members, layers from the manifest | builds and checks `addins/` |
| `docs/architecture.md`, `ATTRIBUTION.md` | section "Extensions", a row for `vendor/` | docs and provenance |
| `crates/ui-egui/src/lib.rs` | `UPDATE_APP`: `repo` and `developer` | see Updates below |
| `crates/ui-egui/src/panels/about.rs` | text and links in the About window | see ArtCraft marks below |
| `README.md` | the fork's own version | see ArtCraft marks below |
| `docs/brand/` | logos removed, `LICENSE-brand.txt` stays | see ArtCraft marks below |

### Updates

The app looks for new releases when it starts. Left unchanged it would have offered the official SoundCraft release,
and one click would have replaced the Plenio version with one without the add-in. So `UPDATE_APP` points at this fork's
releases. As long as the fork has no releases this stays silent; **Help › Check for Updates** then reports nothing new
or an error.

### ArtCraft marks

`docs/brand/LICENSE-brand.txt` requires this: whoever publishes or distributes a modified version must remove the
ArtCraft marks and must not present it as an ArtCraft product; plain text may say that it is based on SoundCraft by
the ArtCraft team. The exception for forks only covers forks kept to propose changes back, so not this one. The
copyright lines in `LICENSE-MIT` and `NOTICE`, on the other hand, must stay.

**Still open before installers or finished programs are distributed** (not relevant for cloning and building yourself):

- `packaging/windows/*` installs to `Programs\ArtCraft\SoundCraft`,
- `packaging/linux/flatpak/*` reads `xdg-data/ArtCraft/versions`,
- `.github/workflows/windows-arm64.yml` checks that install folder.

This is deliberately still unchanged: it is only needed once the fork builds its own releases, and every change there
would be one more place for merge conflicts. This reading of the licence texts is not legal advice; for doubts or for
a permission, the ArtCraft team can be reached through getartcraft.com.

## Releases

The add-in has versions of its own (`addins/plenio/crates/*/Cargo.toml`, [CHANGELOG.md](../CHANGELOG.md)); the app
keeps SoundCraft's version, so that `Cargo.toml` never conflicts at a merge. A release is tagged
`plenio-v<version>` on `plenio-addin`, and its GitHub release is marked as a **pre-release** while the version has a
suffix (`-alpha`, `-beta`, `-rc.1`).

- `pwsh addins/plenio/tools/package_windows.ps1` builds the Windows zip (with `plenio-addin/` beside the program,
  where the add-in looks for its Python files) and `SHA256SUMS.txt` in `target/plenio-dist/`.
- SoundCraft's updater (Help › Check for Updates, `UPDATE_APP`) looks at this fork's releases, skips pre-releases, and
  reads only tags of the form `v<version>`. So the add-in's releases never offer themselves as an update of the app;
  an update path for the fork's own builds is open until the fork builds installers.
- The release's text and the launch plan: [release/](release/) and [launch/](launch/README.md).

## What becomes public with the repository

With a public fork: the copy of Plenio with its tests and docs (1073 files), the plan with the local paths of this
computer, and the email address in the commits (`git log`). If "Block command line pushes that expose my email" is on
at GitHub, GitHub rejects the first push.
