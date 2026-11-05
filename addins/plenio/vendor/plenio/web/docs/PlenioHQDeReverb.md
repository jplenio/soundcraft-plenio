# HQ 3 · De-Reverb

*Experimental.* The third Audio HQ stage, before the EQ - **bypassed in the templates** (select it inside the Master block and press **Ctrl+B** to use it). Two things above 600 Hz, every channel on its own:

1. **dereverb** - a late-envelope subtraction: a delayed, smoothed copy of the spectrum stands for the short metallic room after syllables and hits; where it is strong against the direct sound, the spectrum is turned down (by at most 10 dB, full strength from 3.1 kHz up);
2. **phase_lock** - above 2 kHz the phase of every point is pulled towards the magnitude-weighted phase of its neighbours (rising to at most 47 % from 4.6 kHz up). Steady tones stay as they are.

Same rate and length, no normalisation.

**What it does, measured (2026-10-21, YuE2 takes, standard):** -3 to -4 dB above 3.2 kHz, with attacks and tails lowered alike - so it acts more like a gentle high cut than like a room remover; on a test song without any reverb it takes off as much. In the listening test it sounded dull, which is why it is bypassed.

**preset** - *auto* picks the profile from the connected brief's genre (*standard* without a brief), or choose one:

| profile | for | de-reverb | phase lock |
|---|---|---|---|
| *standard* | pop, hip-hop, soul, world | 45 % | 55 % |
| *gentle* | classical, jazz, folk | 25 % | 30 % |
| *strong* | rock, metal, punk | 65 % | 70 % |
| *wide* | electronic, dance, ambient | 30 % | 40 % |

*custom* shows the two fields. All profiles are **provisional**. **brief** (optional) - for *auto*, as in HQ 1.

The user guide [Audio HQ](../../docs/user/concepts/audio-hq.md) covers the three stages.
