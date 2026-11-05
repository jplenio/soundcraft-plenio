# Best Take · lyrics fidelity

Applies the brief's **lyrics fidelity**: a music model does not always sing its lyrics - it leaves a line out, repeats one, sings other words. This node keeps the take that sings most of them.

- **take** - the first take (from the render block; in the cover template from *Check Vocals*).
- **lyrics** - the final lyrics of the Song Sheet: what the takes should sing.
- **brief** - Song Brief or Cover Brief: its *lyrics fidelity*. Without a brief, for an instrumental or for lyrics without sung lines, the first take passes.
- **second**, **third** - the render block's retakes (the take seed + 1 and + 2). They are lazy: they render only when this node asks for them.

The levels:

- **standard** - the first take, nothing more.
- **high - best of 2 takes** - the second take is rendered, both are heard, and the one that sings more of the lyrics as written is kept.
- **highest - best of 3 takes** - as high, and a third take when neither of the two sang **95 %** of the words.

Each take is heard by the lyrics ASR (Qwen3-ASR, the hearing Export Release uses; it is kept in its cache) and scored like the release record's *as sung*: the share of the lyrics' words heard as written. In 37 sung YuE2 takes measured in October 2026 a single take sang 89 % in the median and one in six less than 75 %; two takes make that rare.

**Higher fidelity makes the generation take longer**: every further take costs a render and a hearing - up to about twice (high) or three times (highest) the time.

Outputs: **audio** (the kept take, on to the Master block) and **report** (each take's share and the one kept - in the release record). The summary says the same.
