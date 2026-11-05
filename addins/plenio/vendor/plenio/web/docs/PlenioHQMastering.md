# HQ Mastering & Cover Art

Two switches at the top of every template, drawn as cards with an icon so that you see at once what is on - in the graph and in App mode. Click a card to switch it. Under them, in the same first group, the template's *Writer model* (the song templates).

**✨ HQ Mastering** (**off** by default in the song templates, **on** in *4 · Enhance & Master* since 2026-10-24) - the switch for the highest mastering quality:

- **on** - *HQ 2 · Regenerate Highs* runs inside **Plenio · Master**: the UniverSR model generates new highs above 8.2 kHz. It can **clearly reduce AI shimmer and artifacts**, but the song takes **about twice as long** - about 1.5 s per second of music on an RTX 5060 Ti (a song of 1:37 took 280 s with it, about 130 s without). UniverSR (229 MB) goes into `models/audio_sr`; ComfyUI offers the download when a template opens, and the System Check lists it.
- **off** - the mastering runs without UniverSR: *HQ 1 · Stereo Cleanup*, the EQ and the loudness as always. The model is not loaded and not even needed - *HQ 2* says *off* in its badge, and the song passes it unchanged.

It is wired into the Master block only (in *4 · Enhance & Master* into HQ 2 directly): switching it runs the **mastering** again, not the song - ComfyUI reuses the render and everything before it. The output **hq_mastering** goes into the Master block's *HQ mastering* input (or HQ 2's).

**🖼 Cover Art** (**on** by default) - paints the song's cover from the sheet's artwork prompt (FLUX.2 Klein 4B); Export Release embeds it in the FLAC and MP3 files and saves it as `.jpg`. Off, the template's three cover nodes (*Cover Art*, *Cover seed*, *Cover preview*) are bypassed: no image model loads. The card shows what those nodes do - a cover bypassed by hand (Ctrl+B) shows as off too. Templates without a cover (*4 · Enhance & Master*) show only the HQ card.

The user guide [Audio HQ](../../docs/user/concepts/audio-hq.md) covers the mastering stages.
