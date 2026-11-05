# YuE2 LoRAs

Up to four **LoRAs for YuE2**, each with its strength. It stands under the music model in the YuE2 templates (*MUSIC MODEL*); with every slot on *none* YuE2 runs as loaded - the run is the one it was without the node.

**What a LoRA changes** - YuE2 has two halves. Its **planner** (the CLIP output: it writes the score and the music's tokens) decides the structure, melody and genre; its **acoustic model** (the MODEL output) renders the sound. A LoRA trained on the planner (often called *AR*) shapes the plan, one trained on the acoustic model (*NAR*) the timbre. The node reads which half a file is for from its weights and applies it there - one strength per LoRA is enough, and a file with both halves patches both.

**Files** - put them into `models/loras` (or a folder of `extra_model_paths.yaml`). Two layouts are read:

- **ComfyUI's** (`text_encoders.model.layers.N.self_attn.qkv_proj.lora_up.weight` ...; often named `*_comfyui.safetensors`) - what ComfyUI's own LoRA loader reads as well;
- **the original one** of m-a-p's YuE2 code (`model.layers.N.self_attn.q_proj.lora_A`, the acoustic half as `nar_self_attn` / `nar_mlp`) - separate q, k, v and gate, up projections, which ComfyUI's YuE2 has fused. The node joins them exactly; ComfyUI's loader would skip them. Its strength is read as trained (alpha = rank) unless an `adapter_config.json` or `<name>.json` with `rank` and `alpha` lies beside the file.

**strength** - 1 as trained, 0 off, negative to push away from it. A plan LoRA often sounds best near 0.5, a sound LoRA near 1 - its model card says. Far above the trained strength it sounds broken; two LoRAs on one half add up.

**Nothing breaks the run** - a LoRA that does not fit is left out and named in the node's summary, the others apply: a file of another model (an image LoRA, a LoRA of YuE 1), a file that cannot be read, weights of another shape than YuE2's, values that are not numbers. The summary says per LoRA how many weights went to the plan and to the sound.

**int8 or bf16** - the node applies a LoRA to either checkpoint (tested on the default `yue2_3b_int8_convrot`). LoRAs are trained on `yue2_3b_bf16`; on the int8 checkpoint one may act a little differently - its card says what it was made for.

**The record** - Export Release keeps the LoRAs and their strengths in the release record (the workflow), and the song's page names them. A song made from the Plenio Player - a new take, a party song - uses the template as it ships, without LoRAs.

**Licences** - a LoRA has its own licence and its own training data: read its card before you share what you make with it. Plenio does not vouch for a LoRA's quality.
