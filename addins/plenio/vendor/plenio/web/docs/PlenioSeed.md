# Seed

A seed decides the random choices of one part of the song - the writer's draft, the arrangement, the take.
The same seed with the same inputs gives the same result; another seed gives something new. This node makes
that one switch:

- **each run: 🎲 new seed** - every run draws a new number **before** it starts: something new every time
  (a new take, a new draft). Each run of a batch (the count next to **Run**) gets its own.
- **each run: 🔒 same seed** - every run uses the number again: that part stays the same, so you can change
  other things (a new take of the same lyrics, another mix of the same take).

**The number shown is always the one the last run used.** Liked what you just heard? Switch to 🔒 - the
number that made it stays. (ComfyUI's own *control after generate* changes the number *after* a run, so the
number it shows belongs to the next run; this node does not.)

- **seed** - the number; type one to go back to an earlier result (the release record of a song lists its
  seeds).
- **🎲 new seed now** - draws one new number at once, for example to try another variant while 🔒 is on.
- The node is **amber** while it draws a new seed for every run and **blue** while it keeps the seed; the
  line under the switch says what that means for its part.

A seed connected from another node is left alone. Over the API the prompt carries the number, as with every
seed: drawing a new one is the browser's job.

In the templates: **Take seed** 🎲 (every run a new take), **Draft seed** 🔒 (title, style and lyrics stay;
in *new song every run* the brief gives every song its own draft anyway), **Arrangement seed** 🔒 (the arrangement stays).
