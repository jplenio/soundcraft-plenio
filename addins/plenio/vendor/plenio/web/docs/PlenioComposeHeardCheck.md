# Compose Misheard Check

The question about a **cover's original lyrics**: *Transcribe Lyrics* writes what the lyrics ASR heard in the source, and a word it misheard would be sung by the cover as heard. This node gives the writer the draft's sung lines, numbered, with the words the ASR heard with a probability below 0.5 in **[brackets]**, and the recording's name (the Cover Brief's title).

- **lyrics** - the draft *Transcribe Lyrics* made (its *lyrics* output).
- **report** (optional) - *Transcribe Lyrics*' report: it lists the heard words of every draft line with their probability, which marks the unsure ones.
- **brief** (optional) - the Cover Brief: only *original lyrics* are checked.
- **language** (optional) - the language *Transcribe Lyrics* heard.

Outputs: **prompt** for a writer (*Generate Text* or *Local LLM*) and **schema**, the JSON schema of the answer (Local LLM keeps to it exactly).

Anything but a Cover Brief with *original lyrics* - new lyrics, an instrumental, a Song Brief, no brief - and Chinese or Japanese lyrics give an empty prompt, and since *Apply Misheard Check* then asks for no answer, no writer runs. The block *Plenio · Fix Misheard Words* contains this node, the writer branches and *Apply Misheard Check*.
