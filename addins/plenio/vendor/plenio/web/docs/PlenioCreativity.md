# Creativity

Turns a creativity value - **0 steady, 50 the reference, 100 experimental** - into the sampling of one stage.
The slider you move is on **Song Brief** and **Cover Brief**; this node sits inside the template blocks and
hands the brief's value on to the native nodes' fields.

- **stage** - which values it gives:
  - *writer* - the temperature of Write Song's first draft (0.6 at 0, **0.8 at 50**, 1.0 at 100). The repair
    rounds keep their own.
  - *arrangement* - the temperature of a creative mode's plan in Arrange (0.55, **0.7**, 0.9). The re-ask keeps
    its own.
  - *plan* - YuE2's score (YuE2 Plan): temperature, top-p and top-k (0.55 / 0.85 / 20, **0.7 / 0.9 / 30**,
    0.92 / 0.95 / 50) - how freely YuE2 picks notes, chords and rhythms.
  - *take* - YuE2's performance (YuE2 Render and Takes): temperature, top-p and top-k (0.9 / 0.92 / 60,
    **1.0 / 0.95 / 100**, 1.1 / 0.97 / 150) - how freely YuE2 sings and plays the score.
- **creativity** - the value, when no brief is connected.
- **brief** (optional) - a connected brief's creativity is used instead.

Between 0, 50 and 100 the values move in a straight line. **At 50 they are exactly the values of before**
(YuE2's native defaults), so nothing changes until the slider moves. The ends stay moderate: more creativity
means more surprises and also more misses - try a few seeds. The repetition penalties are not changed.

Outputs: **temperature**, **top_p**, **top_k** (the writer and the arrangement use the temperature only).
