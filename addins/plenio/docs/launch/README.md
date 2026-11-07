# Launch plan for 0.1.0-alpha

What is ready, and the order to publish it in. Nothing here publishes by itself.

## Ready in the repository

| What | Where |
|---|---|
| Version `0.1.0-alpha` in the add-in's crates, the changelog | `addins/plenio/crates/*/Cargo.toml`, [`CHANGELOG.md`](../../CHANGELOG.md) |
| Licences and notices | [`NOTICE.md`](../../NOTICE.md), root `LICENSE-MIT`, `LICENSE-APACHE`, `NOTICE`, `ATTRIBUTION.md` |
| README of the fork and of the add-in, tutorial, developer guide | `README.md`, [`addins/plenio/README.md`](../../README.md), [`TUTORIAL.md`](../TUTORIAL.md), [`DEVELOPMENT.md`](../DEVELOPMENT.md) |
| The release's text | [`docs/release/plenio-v0.1.0-alpha.md`](../release/plenio-v0.1.0-alpha.md) |
| The texts for every channel | [`ANNOUNCEMENTS.md`](ANNOUNCEMENTS.md) |
| Logo, banner, social preview, screenshots, animations | [`docs/media/`](../media/) |

## Ready outside the repository

In the launch folder beside this repository (`../soundcraft-plenio-launch/`, not committed: the teaser's
music is a YuE2 song, CC BY-NC 4.0, which the repository's asset rules do not take):

| File | What |
|---|---|
| `release/soundcraft-plenio-0.1.0-alpha-windows-x64-portable.zip` | the Windows build (checked with `tools/smoke_package.ps1`) |
| `release/plenio-comes-to-soundcraft.mp4` | the teaser, 1920 x 1080, 72 s, -14 LUFS |
| `release/plenio-comes-to-soundcraft-vertical.mp4` | the teaser for Shorts, Reels and TikTok, 1080 x 1920 |
| `release/plenio-tutorial.mp4` | the tutorial as a video, 1920 x 1080, 1:52 |
| `release/SHA256SUMS.txt` | the checksums of the four |
| `tour/session/Plenio Demo.scraft` | the demo session the screenshots and the teaser come from (open it in SoundCraft) |
| `tour/shots/`, `tour/frames/` | every screenshot and frame of the tour |

Make them again: `examples/plenio_tour.rs`, then `tools/media/make_media.py`, `make_teaser.py` and
`make_tutorial.py`, and `tools/package_windows.ps1` ([DEVELOPMENT.md](../DEVELOPMENT.md#media)).

## Order

1. **Push** the branch and the tag:
   ```powershell
   git push origin plenio-addin
   git push origin plenio-v0.1.0-alpha
   ```
2. **Release:** GitHub › Releases › *Draft a new release* › tag `plenio-v0.1.0-alpha`, title
   `Plenio for SoundCraft 0.1.0-alpha`, the text of `docs/release/plenio-v0.1.0-alpha.md` (without its first
   comment), attach the five files of `release/`, tick **Set as a pre-release**, publish. The README's teaser link
   and the release text point at this release.
3. **Repository settings:** description, website and topics from `ANNOUNCEMENTS.md › GitHub`; the social
   preview image; Discussions on, if you want questions there rather than in issues.
4. **Video:** upload the teaser to YouTube (title and description in `ANNOUNCEMENTS.md`), the vertical one
   to Shorts, Instagram or TikTok.
5. **Posts:** Hacker News and Reddit on a weekday morning US time (they reward being there for the
   comments), then X, Bluesky, Mastodon, LinkedIn, Discord, KVR, the newsletter.

## Licence of the launch material

The texts, logo, banner and screenshots: as in [`NOTICE.md`](../../NOTICE.md). The teaser: its pictures
are the project's, its music is a YuE2 song, so the video as a whole is **CC BY-NC 4.0**: fine for
announcing a free project, not for paid advertising.
