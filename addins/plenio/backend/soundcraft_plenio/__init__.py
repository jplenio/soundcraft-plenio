"""ComfyUI custom node package of SoundCraft's Plenio add-in.

SoundCraft installs this folder into the ComfyUI instance it runs for the add-in, with Plenio's code
beside it in ``plenio_vendor`` (an unchanged copy of ``addins/plenio/vendor/plenio``). It loads Plenio
as it is - its nodes, its routes and its Song API (``/plenio/api/v1``) - and adds the few routes
SoundCraft needs beyond them (``/scp/v1``, see ``routes.py``).
"""

# ComfyUI imports this file as a package; a test run imports the modules on their own.
if __package__:
    from .entry import comfy_entrypoint

    __all__ = ["comfy_entrypoint"]
