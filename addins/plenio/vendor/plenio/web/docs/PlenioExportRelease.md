# Export Release

Writes the finished song into the ComfyUI output folder with a **release record** next to it.

**Formats** - *flac* (24-bit, lossless; default), *mp3* (VBR V0, LAME), *wav* (32-bit float: never clips, but holds only a few tags and no cover). Tick one or more.

**tags**

- *title only* - the title from the Song Sheet (or the copied title).
- *tags* - artist, album, date, track, genre, comment (preset to *Powered by Plenio Music Production System / ComfyUI*; change or clear it), album artist, composer and **lyrics** (FLAC: the `LYRICS` comment, MP3: an ID3 `USLT` frame; WAV has no place for it). Every field takes text with **variables** (below) - or connect any text output to it: drag a link onto the field, for example from a field output of the Song Brief or from a writer's answer. A connected text wins over the typed one.
- *copy from loaded file* - copies tags and the embedded cover from the file loaded by the workflow's **Load Audio** node (as in *4 · Enhance & Master*); the workflow must contain exactly one Load Audio node. The *title* input and the *cover* input win over copied values.

**cover** - an image input (for example from a cover-art block): cropped square, saved as `<name>.jpg` next to the audio and embedded into the FLAC and MP3 files - the mastered ones and the `(original).flac` - whichever *tags* option is chosen (*title only*, *tags* or *copy from loaded file*). A copied cover (*copy from loaded file*) is embedded the same way; the *cover* input wins over it. WAV has no place for a cover: it keeps the `.jpg` only. No extra package is needed. MP3 tags are ID3v2.3, which Windows Explorer, Windows Media Player and most players read (ffmpeg's default 2.4 is not shown there).

**Variables** - tag fields and the *naming* pattern take `{name}` variables:

| Group | Variables |
|---|---|
| song | `{title}`, `{lyrics}` (plain lines, a blank line between sections), `{style}`, `{artwork_prompt}`, `{duration}` (m:ss), `{bpm}` and `{score_key}` (from the score, YuE2) |
| brief | `{description}`, `{template}`, `{mode}`, `{genre}`, `{mood}`, `{tempo}`, `{length}`, `{vocals}`, `{language}`, `{voice}`, `{theme}`, `{melody}`, `{lead_instrument}`, `{key}`, `{meter}`, `{arrangement}`, `{genre_closeness}`, `{lines_under_singing}`; a cover's `{harmony}`, `{song_flow_closeness}`, `{lyrics_closeness}` - from the **brief** input |
| run | `{date}` (2026-10-15), `{year}`, `{time}` (HHMMSS), `{seed}` = `{take_seed}`, `{draft_seed}`, `{arrangement_seed}` (the seed nodes of those titles) |
| models | `{model}` (YuE2, MiniMax Music 3), `{writer}` (the writer model) |
| Plenio | `{plenio_version}` |
| tags | `{artist}`, `{album}`, `{album_artist}`, `{composer}`, `{track}` - in the file name and the other tag fields |

`[ ... ]` around text with a variable shows it only when every variable inside has a value: `[Mood: {mood} · ]` vanishes for an empty mood; brackets without a variable stay text. `{{` and `}}` are literal braces. A variable without a value gives an empty text. A typed name that is no variable stops the run when it is queued - before anything renders - with the list of names; in connected text it stays as written (generated text may hold braces of its own) and the summary notes it. Example comment: `Genre: {genre}[, mood: {mood}][, sung in {language}]`.

**brief** - optional: the Song Brief or Cover Brief, for the brief's variables. The templates connect it.

**original** - optional: also writes this audio (for example the unmastered take) as `<name> (original).flac`.

**Naming** - *naming* pattern with the variables above (`{date} {title}` by default; `{artist} - {title}`, `{genre}/{title}` ...); `/` makes sub-folders (a value's own slashes do not); *collision* decides what happens when a file exists (number, overwrite, error). All files of one export share one name: with *number* the whole set becomes `<name> (2)` when any of its files - audio, original, cover or record - already exists, so an earlier export is never overwritten. Since 1.1.0 *number* also numbers the **title** when another song of the export folder has it (the second cover of *Yesterday* is *Yesterday (2)* - in its tags, its record and its file name), so every song can be told apart in a player; the export's summary says so.

**sheet music** - *off*, *PDF (A4)* or *PDF (Letter)*: also saves the score's sheet music as `<name>.pdf` next to the audio - both voices, chord symbols, section names and the **lyrics under the notes**, with the title, exactly as the Song Sheet's *Export notation… > PDF* draws it (lyrics lines placed by hand included: the export reads them from the workflow the run was queued with). The notation is drawn by the browser: the export reserves the name, an open ComfyUI page draws the PDF right after the export - whichever workflow it shows - and Plenio saves it; the node's summary then says *saved* (when its workflow is open), a message says so, and the record lists the file. When no page was open (queued over the API, the tab closed or reloaded), the next ComfyUI page that opens or comes back to the front draws the PDFs still waiting - for up to 24 hours, while ComfyUI runs; until then the record says *drawn by the browser after the export*. Needs a score: MiniMax Music 3 and runs without planning have none (noted). The YuE2 templates save it on A4.

**Stems** - when the report of a *Stem Mixer* comes into one of the *reports* inputs (as in every template), the strips marked *save* there are written next to the song, into the folder `<name>-stems` (`My Song-stems/drums.flac`, a batch `drums take 1.flac` ...), as 24-bit FLAC tagged with the song's tags and the title `<title> (<stem>)`; a saved **bass** and **vocals** also as MIDI notes (`bass.mid`, `vocals.mid`, at the song's tempo; experimental - see [Stems](../../docs/user/concepts/stems.md#the-bass-and-the-vocals-as-midi)). The folder takes part in *collision* like the other files, and the record lists every stem file.

**sheet music size** - how large the music is drawn: *standard* (default) about 3 bars a line - about 4 pages for a song of 3-4 minutes; *smaller* about 3-4 bars a line (3 pages), *compact* about 4 (2-3 pages), *large* 1-2 bars a line (about 13 pages, the biggest notes). The text shrinks less than the notes. The same sizes as *Export notation…* in the Song Sheet.

**lyrics subtitles (SRT)** (on by default) - writes the lyrics as subtitles next to the song, with times measured by listening:

- `<name> (lines).srt` - one subtitle per lyrics line, from where its first word is sung to where its last ends;
- `<name> (notes).srt` - the same lines painted on note by note: a new subtitle at every syllable (YuE2: on its note of the score) or word (MiniMax), each showing the line up to what is being sung.
- `<name> (sung).srt` - what the take really sings, as heard (a music model may repeat a line, make one up or leave one out): laid out like the lyrics where the take sings them, the words they do not have in lines of their own. The release record keeps it too, with how far the take follows its lyrics; the summary says it per take, and the Plenio Player follows either version.

The lyrics ASR listens to the exported song - Qwen3-ASR 1.7B hears the words and Qwen3-ForcedAligner 0.6B times them (Apache-2.0, 4.1 + 1.8 GB, fetched on first use; faster-whisper large-v3, MIT, 3.1 GB, for a language the aligner does not know); its results are cached. It hears the song in pieces of at most 20 seconds, each with a little of its neighbours - over a whole song the aligner loses its place. Its words are matched to the final lyrics (Chinese and Japanese character by character) and, with a score, the score is fitted to them, so every syllable gets its note's time. Whisper's times start early and are corrected - measured on 48 YuE2 songs against the aligner: half the words within 0.16 s, 82 % within 0.5 s. A YuE2 render is shifted against its score (1.7 s in the median song), so the score's times alone are not used. Without lyrics (*Enhance & Master*) the subtitles are the words as heard; an instrumental gets none. Offline without the model, or when the ASR fails, the export goes on without subtitles and says why - in its summary and in the release record, where the Plenio Player reads it. When Qwen3-ASR cannot run here (a transformers older than 5.5) and faster-whisper is installed, faster-whisper hears the song instead. No styling tags (YouTube and video editors read SRT markup differently): the files work everywhere. A batch writes one pair per take.

**Release record** (`<name>.plenio.json`) - the documents with their hashes, the executed graph and the workflow it was queued with (secrets redacted), all connected reports, every written file with size and SHA-256 (the stems with their folder), the delivered audio's loudness (LUFS, true peak, loudness range), the tags, the licences of the models used, and whether lyrics subtitles were asked for and made (and why not).

With *sheet music* on the record also says which PDF belongs to the export, its paper and size, and whether it was saved.

**project in FLAC** (on by default) - also writes the release record into the song's FLAC files, compressed, in a metadata block players skip (a FLAC *APPLICATION* block, id `PLNO`): the FLAC alone is then enough to continue the song. The record lists such a FLAC with the size and SHA-256 it has without the record (`"project": "embedded"`), and every FLAC with `audio_md5`, the MD5 of its decoded audio. Turn it off for files you share without their making-of; ComfyUI's `--disable-metadata` turns it off too.

**song page (HTML)** (on by default) - also writes `<name>.html`: the song on one page to open in any browser, without internet - the cover and the song to play, the lyrics with their sections and the style and prompts, each with a copy button, every field of the brief, how it was made (the model files, the LoRAs, the seeds), the sound and its mastering, the score as ABC and links to every file beside it. The Plenio Player shows the same page for every song, also for one exported before.

**Continue the song later**: *File > Continue a Plenio song…* lists the records of the output folder and opens a record or a song's FLAC from anywhere; dropping a record onto ComfyUI, or the song's FLAC onto the empty canvas, works too. The song opens in the workflow it was made with, its title, style, lyrics and score kept in the Song Sheets (*manual*) - new takes with another take seed, or edits from there.

**▶ Open in the Plenio Player** - the button on the node opens the song it exported last in the Plenio Player: its page, with the lyrics that light up as they are sung and the sheet music following the music. The player is a program of its own; when none runs, ComfyUI starts it (it keeps running when ComfyUI stops; stop it on its Settings page). *Plenio Player* beside *Run* and the *Plenio* menu open it too. From a song's page in the player, *Open in ComfyUI* brings the song back here.

Samples above full scale are clipped in FLAC and MP3; the node warns. MP3 holds at most 48 kHz: hi-res audio (88.2/96/192 kHz) is converted for the MP3 only (to 44.1 or 48 kHz); FLAC and WAV keep the rate, and the node notes the conversion. Audio with NaN or infinite samples is refused. Put **Loudness & Dynamics** before the export.
