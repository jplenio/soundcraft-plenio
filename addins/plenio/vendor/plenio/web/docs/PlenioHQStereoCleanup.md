# HQ 1 · Stereo Cleanup

The first Audio HQ stage, before the EQ. It splits the song into **mid** (what both channels share: voice, kick, snare, bass) and **side** (the difference: width, room, and the unsteady stereo shimmer of AI renders at the edge of the image) and cleans only the side:

1. a zero-phase high-cut of the side above **side_highcut_hz**, blended in by *0.4 + 0.6 x side_cleanup*;
2. a spectral cleanup of the side above 2 kHz: where the side is no louder than its diffuse surroundings (a median over 21 bins and 5 frames), it is turned down - by at most 12 dB, smoothly;
3. **warmth**: a 2x oversampled, slightly asymmetric saturation above 400 Hz that adds 2nd and 3rd harmonics (at the standard 0.18 the 3rd harmonic of a -6 dBFS tone lies about 53 dB below it - density, not distortion).

The mid is never filtered. A mono input gets the warmth only. Same rate and length, no normalisation.

**preset** - *auto* picks the profile from the connected brief's genre (*standard* without a brief), or choose one:

| profile | for | side high-cut | side cleanup | warmth |
|---|---|---|---|---|
| *standard* | pop, hip-hop, soul, world | 10.5 kHz | 65 % | 0.18 |
| *gentle* | classical, jazz, folk | 11.5 kHz | 55 % | 0.14 |
| *strong* | rock, metal, punk | 9.5 kHz | 80 % | 0.25 |
| *wide* | electronic, dance, ambient | 14 kHz | 40 % | 0.12 |

*custom* shows the three fields. *standard* is the proposal of the listening test (2026-10-21); the other profiles are **provisional** until they have been listened to, and the summary says so.

**brief** (optional) - Song Brief or Cover Brief for *auto*: the genre's words first (*folk metal* is strong, *synth-pop* wide), then the template's family.

The summary and the report name the profile and why it was chosen, the settings, and how much the side changed above 10.5 kHz. In the templates the node is inside the **Plenio · Master** block (open it with the icon at the top right of the node); the user guide [Audio HQ](../../docs/user/concepts/audio-hq.md) covers the three stages.
