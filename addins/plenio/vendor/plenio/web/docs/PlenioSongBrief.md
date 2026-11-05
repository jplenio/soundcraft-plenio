# Song Brief

The intent of a new song. It is the only place where the *work mode*, *sung or instrumental* and the *length* are chosen.

- **mode** - how the runs of this workflow behave:
  - *new song every run* - every run writes and renders a **different song** from this brief (a new *series variation*: the writer is asked for its own title, story, images and hook, with its own draft and plan seeds). Song Sheets set to *as the brief says* do not stop; a sheet set to *stop for review* stops every new song, and the run after *Approve* renders that song before the next one is written. Set the batch count next to **Run** (App mode: *Number of runs*) to make a whole series with one click.
  - *one song, stop to review* - the brief stays the same, so its song is written once: Song Sheets set to *as the brief says* stop until you **Approve** the documents, and later runs are new takes of the approved song.
- **template** - a starting point from the template library. Text fields you leave empty are taken from the template; selecting a template never overwrites what you typed.
- **description, genre, mood, tempo** - what the song is and how it sounds. Sent to the writing model.
- **length** - from *very short (about 1:00)* in half-minute steps to *about 5:00*, and *very long (about 6:00)*; *standard (about 3:00)* is the default. Guides the song form and how much the writer writes (YuE2's plan follows the amount of lyrics) and sets the render ceiling without a score (MiniMax Music 3 renders at most 6:00). A free-form value such as *2-3 minutes* (from older workflows) takes the nearest option, with a note.
- **vocals** - *sung* (language, voice character, lyrics theme) or *instrumental* (the instrument plays the lead melody, or accompaniment only; optional lead instrument).
- **key, meter** - optional musical constraints (the DAW template's empty score takes both; also in App mode).
- **arrangement (experimental)** - the creative mode (creative modes can give unexpected results: try them, listen, keep what you like). *off* (default): the music model plans melody, chords and instruments by itself. A creative mode adds its hints to the writing prompt and, in *YuE2 Song*, lets the writer model plan every section of YuE2's score (chords, the instrument line, energy; *Plenio · Arrange*). Plenio writes the notes and checks them; a plan it cannot use leaves the score as it was, and *Song Sheet · Score* says so. The line under the brief says what the chosen mode does; the shipped modes:
  - *standard* - genre-typical: calm verses, fuller choruses, the last chorus the strongest.
  - *sterile* - clean, sparse and steady: plain chords, long notes or silence, low even energy.
  - *unplugged* - intimate and acoustic: guitar or piano, fingerpicked broken chords, soft pads.
  - *varied* - every section sounds different: the instrument line changes, contrasting energy.
  - *call and response* - the instruments answer the melody in the gaps between its phrases.
  - *signature motif* - one short figure opens the song, returns in every chorus and closes it.
  - *hypnotic* - a steady repeating pattern over few chords, changing little by little.
  - *breakdown* - full sections with a breakdown in the middle, then a big final section.
  - *dramatic* - one long arc from a quiet start to a big climax in the final chorus.
  - *many instruments* - a full ensemble: lines in every section, riffs, countermelodies, a solo.
  - *jazz colours* - seventh chords, passing chords, a mellow countermelody and a solo.
  - *fantasy* - colourful chords, unusual lines, a returning motif, a touch of film music.
  - *key change* - standard with the final chorus lifted a half or whole step (the only mode that changes the key).
  - your own file in `user/plenio/arrangement` (its description is shown the same way).
- **lines under the singing (experimental)** - creative modes only: off (default), the instrument line plays where the voice rests (fills and answers, as in YuE2's own scores); on, it also sounds under the singing - calm, below the voice, never a minor second against it.
- **genre closeness** (creative modes; *off* ignores it) - how close the song stays to its genre: 100 strictly typical, 70 typical with personal touches (default), 40 free within the genre, 0 borrow from any style. It shapes the style words and the section plan.
- **creativity** - one slider from **0 steady** to **100 experimental**; **50 is the reference**: exactly as before (a workflow saved before the slider existed keeps 50). Away from 40-60 the writer gets rules for the style and the lyrics - plain, regular and typical at the low end; more specific instruments, contrast, fresher images at the high end, and at 81-100 one unexpected but fitting colour. The writer's draft (and a creative mode's plan) gets a lower or higher temperature, and in the templates YuE2's plan and takes are sampled more steadily or more freely. More surprises also bring more misses: try a few seeds. MiniMax Music 3 follows the slider in its writing only.
- **lyrics fidelity** - how closely the song sings its lyrics: **standard** renders one take; **high - best of 2 takes** renders a second take (the next seed) and keeps the one that sings more of the lyrics as written, as the lyrics ASR hears it (*Best Take* in the render section); **highest - best of 3 takes** adds a third take when neither sang 95 % of the words. Higher fidelity makes the generation take longer - up to about twice or three times. Instrumentals take one take. A workflow saved before the option keeps *standard*.

Outputs: the brief, a readable summary, a render headroom for the length, whether the song is instrumental, and the *song seed* - added to the draft and plan seeds: a new value for every song of a series (kept while it waits for review), 0 for one song. Then every field as its own output - *template, genre, mood, tempo, length, vocals, language, voice, theme, key, meter, arrangement* (text), *genre closeness* and *creativity* (numbers) and *lines under the singing* (on/off) - with the brief's final values (a field left empty gives the template's), for example for a tag field of Export Release, which also reads them all through its *brief* input as variables (`{genre}`, `{mood}` ...). The *creativity* output feeds the YuE2 blocks of the templates (YuE2 Plan, YuE2 Render). The node's summary shows the mode, the creativity and, in *new song every run*, the variation of the current run.
