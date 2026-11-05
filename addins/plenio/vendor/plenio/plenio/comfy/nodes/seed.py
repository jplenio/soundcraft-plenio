"""Seed: a seed with one plain switch - a new seed for every run, or the same one again (owner's request
2026-10-15, ``docs/design/subtitles-tags-seeds.md`` §4).

The browser draws the new seed **before** a run (``frontend/src/extension/seedNode.ts``), so the number shown
is always the one the last run used: switching to *same seed* keeps exactly the result just heard. ComfyUI's
own control (*control after generate*) changes the number after the run, so the number shown there belongs
to the next run. Headless, the prompt carries the number, as with every seed.
"""

from __future__ import annotations

from comfy_api.latest import io

SEED_MAX = 2**63 - 1
SEED_TOOLTIP = "The number behind this part's random choices: the same number gives the same result."
KEEP_TOOLTIP = (
    "🎲 new seed: every run draws a new number before it starts - something new each time. 🔒 same seed: every "
    "run uses this number again - the same result while you change other things."
)


class PlenioSeed(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="PlenioSeed",
            display_name="Seed",
            category="Plenio/Utilities",
            description=(
                "A seed with one switch: 🎲 a new seed for every run, or 🔒 the same seed again. The number shown "
                "is always the one the last run used - switch to 🔒 to keep what you just heard."
            ),
            inputs=[
                io.Int.Input(
                    "seed",
                    default=0,
                    min=0,
                    max=SEED_MAX,
                    # no ComfyUI control: the frontend adds one to every INT named seed unless told not to
                    control_after_generate=False,
                    tooltip=SEED_TOOLTIP,
                ),
                io.Boolean.Input(
                    "keep_seed",
                    display_name="each run",
                    default=False,
                    label_on="🔒 same seed",
                    label_off="🎲 new seed",
                    tooltip=KEEP_TOOLTIP,
                ),
            ],
            outputs=[io.Int.Output(display_name="seed", tooltip="The seed of this run.")],
        )

    @classmethod
    def execute(cls, seed: int, keep_seed: bool = False) -> io.NodeOutput:
        return io.NodeOutput(int(seed))
