# Apply Misheard Check

Corrects **misheard words in a cover's original lyrics**, before the render. The writer model names the words it is sure were misheard, each with the word that was most likely sung. A correction is taken only when

- the writer is **sure enough**: 80 % for a word the ASR was unsure of (bracketed), 90 % for one it heard clearly,
- the new word **sounds like** the one heard - their letters, and their consonants alone, compared (at least 0.6); a word that fits better but sounds otherwise is a rewrite, not a correction,
- it has **as many syllables** - the melody's notes stay,
- and it puts no word twice in a row where the line had none.

Only what a correction changes counts: *I'm not the only* -> *We're not the only* is judged as *I'm* -> *We're* (and refused: it does not sound alike). Measured with Gemma 4 E4B on 20 songs, the corrections taken were misheard words (*Zingway* -> *Sing way*, *in'cause* -> *because*, *willing* -> *feeling*); the unsure words it is not sure of stay as heard - and stay marked in the Song Sheet.

- **lyrics** - the draft *Transcribe Lyrics* made.
- **answer** - the writer's answer (asked only for a cover's original lyrics).
- **report**, **brief**, **language** (optional) - as in *Compose Misheard Check*.

Outputs: **lyrics**, the draft with the corrections, and a **report** of what was corrected and why not the rest. *Song Sheet · Text* lists every correction beside the word heard (*Corrected as misheard*); your edits always win. Lyrics that are not a cover's original lyrics, and Chinese or Japanese lyrics, pass unchanged. In the cover template the block *Fix Misheard Words* sits in *4 · LYRICS*, after *Transcribe Lyrics*, and uses the template's writer model.
