# Transcribe Lyrics

Transcribes the sung words of a recording with **Qwen3-ASR 1.7B** - **Qwen3-ForcedAligner 0.6B** gives every word its time - in a separate process, and places them into the **final score's sections** on the beat grid. The result is a *draft*: the Song Sheet decides what is used, and your corrections there always win.

- **audio** - the source recording (or a take, see the check below).
- **engine** - *Qwen3-ASR 1.7B* (default): it hears 30 languages; its aligner times words in English, German, French, Spanish, Italian, Portuguese, Russian, Chinese, Cantonese, Japanese and Korean. For any other language *faster-whisper large-v3* takes over by itself and the summary says so. *faster-whisper large-v3*: always Whisper (a workflow saved with it keeps it). Both run in a separate process; the models are fetched on first use (Qwen3: 4.1 + 1.8 GB, Whisper: 3.1 GB).
- **score** - the final score from *Song Sheet · Score*: its sections become the lyrics' tags. Edit a section name in the score and the draft follows. Copy, move or delete sections and the words follow their bars: a copied chorus gets the chorus words again, a deleted section's words are left out (reported). This needs a timeline from this version of *Transcribe Score*.
- **timeline** - from *Transcribe Score*: only the parts where somebody sings are transcribed, and words land in the bar where they are sung (a word sung just before a section starts - a pickup - belongs to the new section).
- **brief** - for an *original lyrics* Cover Brief its language (the source's) is used; otherwise the **language** widget (auto, a name or a code) names the language of the singing in this recording. For *new lyrics* the brief's language is that of the new text, so it is not used here.
- **device** (advanced) - auto uses the GPU and falls back to the CPU with a warning (Qwen3 then takes several times the audio length, Whisper about 0.6 x). On the GPU a four-minute song takes about half a minute; the two Qwen3 models run one after the other (about 4 GB of VRAM at a time).

Outputs: **lyrics** (the sectioned draft; in the check below the lyrics as heard), **transcript** (the plain text), **language** (detected or given) and the **report**.

What it leaves out, and says so in the report: words far from any sung note (inventions), and - with Whisper - very short, very unsure segments it is known to invent at the end of a passage ("Thank you.") and the sentences it learnt from subtitled video and writes into music wherever it stands ("Untertitelung des ZDF für funk, 2017", "Vielen Dank fürs Zuschauen", "Amara.org" ...), with a year on its own right after one.

**Reproducible:** every result is stored on disk under the source's hash, the sung regions, the model revision and the settings. A later run - also after a restart - gives the same draft without running the ASR again, so an edited lyrics document stays valid.

**Song Sheet editor:** the editor shows the words the ASR was unsure about (Qwen3: the confidence of the transcription's tokens, Whisper: its word probability) and what it left out, next to the draft.

**Sung-lyrics check:** connect a take to **audio** and the lyrics it was given to **expected_lyrics**. The node then reports the word error rate overall and per section and names sections that were not sung as written (a warning, not an error).

The model (3 GB, MIT licence) is fetched on first use; point `[asset_paths]` in the Plenio configuration at an existing folder to use a copy you already have.
