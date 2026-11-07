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
| `web/` | 720p copies of the three videos (8.9 to 11.3 MB): small enough for Discord's 10 MB and for a player in the release's text |

## On YouTube

| Video | Link |
|---|---|
| The teaser | https://youtu.be/NRKGa-Vvr_k |
| The tutorial | https://youtu.be/QFgfxBdV52c |
| The playlist, for every video to come | https://www.youtube.com/playlist?list=PLJfLcDGpXv1s |

They are linked from the fork's README, the add-in's README, the tutorial, the release's text and the
announcements. A new video joins the playlist, whose link stays. YouTube cannot swap a video's file, so a
video made again gets a new link: put it in the old one's place in the playlist, and change its link in
those files.
| `tour/session/Plenio Demo.scraft` | the demo session the screenshots and the teaser come from (open it in SoundCraft) |
| `tour/shots/`, `tour/frames/` | every screenshot and frame of the tour |

Make them again: `examples/plenio_tour.rs`, then `tools/media/make_media.py`, `make_teaser.py` and
`make_tutorial.py`, and `tools/package_windows.ps1` ([DEVELOPMENT.md](../DEVELOPMENT.md#media)). The 720p
copies are two-pass H.264 at 900 kbit/s (the tutorial at 700) with AAC at 128 kbit/s, scaled to 1280 x 720
(the vertical one to 720 x 1280), `-movflags +faststart`.

## Order

1. **Push** the branch and the tag:
   ```powershell
   git push origin plenio-addin
   git push origin plenio-v0.1.0-alpha
   ```
2. **Release:** GitHub › Releases › *Draft a new release* › tag `plenio-v0.1.0-alpha`, title
   `Plenio for SoundCraft 0.1.0-alpha`, the text of `docs/release/plenio-v0.1.0-alpha.md` (without its first
   comment), attach the five files of `release/`, tick **Set as a pre-release**, publish. The README's
   download link and the tutorial point at this release. For a player at the top of the text, drag
   `web/plenio-comes-to-soundcraft-720p.mp4` onto an empty line after its first paragraph: GitHub plays videos
   of up to 10 MB in place.
   ✅ Published on 2026-11-07, before the videos were on YouTube: in its text (*Edit release*), replace the
   line that starts with `▶ **Teaser:**` by the line with the two YouTube links from
   `docs/release/plenio-v0.1.0-alpha.md`.
3. **Repository settings:** description, website and topics from `ANNOUNCEMENTS.md › GitHub`; the social
   preview image; Discussions on, if you want questions there rather than in issues. ✅ All but the topics,
   which GitHub still showed empty on 2026-11-07: each topic has to turn into a chip before *Save changes*;
   if pasting the list does not split it, type them one by one, each followed by a space.
4. **Video:** ✅ the teaser and the tutorial are on YouTube ([above](#on-youtube)); their descriptions in
   `ANNOUNCEMENTS.md` now link each other and the playlist. Still open: the vertical teaser on Shorts,
   Instagram or TikTok.
5. **Posts:** Hacker News and Reddit on a weekday morning US time (they reward being there for the
   comments), then X, Bluesky, Mastodon, LinkedIn, Discord, KVR, the newsletter.

## Licence of the launch material

The texts, logo, banner and screenshots: as in [`NOTICE.md`](../../NOTICE.md). The teaser: its pictures
are the project's, its music is a YuE2 song, so the video as a whole is **CC BY-NC 4.0**: fine for
announcing a free project, not for paid advertising.
