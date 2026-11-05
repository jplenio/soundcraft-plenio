# Parse Song Draft

Reads the writing model's answer and extracts title, style, lyrics and artwork prompt. Models do not always follow the layout, so the parser accepts labelled blocks (`TITLE:`), headings and unlabelled answers.

**The title:** the writer proposes ten titles after the lyrics (`TITLES:`); Parse Song Draft picks one at random - seeded by the answer, so the same answer gives the same title - and passes over titles a song in `output/plenio` has already (or this ComfyUI picked since it started), while others are left. An answer with one `TITLE:` keeps it; a title fixed by the brief (a cover named after its recording) always wins.

Connect **text** to the writer's answer (*Generate Text* or *Local LLM*) and **request** to *Compose Writing Prompt*'s request: the answer is checked against what was asked. Outputs: **title**, **style**, **lyrics** and **artwork_prompt** - the drafts for the Song Sheets - and the **report**.

It enforces the format deterministically and **reports every change**: one-line style, `[Tag]` sections, repeat marks written out, stage directions removed, and for instrumentals: tags only and no vocal or language descriptors. The report lists the changes and the engine's checks on the draft.

If the answer has no recognisable style and lyrics, the node stops and shows the beginning of the answer.
