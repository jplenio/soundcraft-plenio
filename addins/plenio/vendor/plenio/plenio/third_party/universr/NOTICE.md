# UniverSR (vendored inference code)

Upstream: https://github.com/woongzip1/UniverSR (MIT, see LICENSE in this folder)
Pinned commit: `d8636623fe0c0704296239c1d3d3c5b911ecb2e0`
Retrieved: 2026-09-27
Paper: *UniverSR: Unified and Versatile Audio Super-Resolution via Vocoder-Free Flow
Matching* (ICASSP 2026), arXiv 2510.00771; weights: https://huggingface.co/woongzip1/universr-audio
(CC BY 4.0).

Vendored for Plenio's Refine (48 kHz) stage; loaded only when a super-resolution model is
loaded (`plenio/comfy/universr.py`), never at import time.

## Files

| Path | Upstream path | SHA-256 of the vendored file |
|---|---|---|
| `LICENSE` | `LICENSE` | `2e5bef1a3c216f25239d7dce7ca31d4c9e3199da9bd2be250e3a8475b6bde99b` |
| `inference.py` | `universr/inference.py` | `745510e5c1cd4682c5b128f535ef163f620b94a1868b48bd1a53f685ff529ab5` |
| `models/__init__.py` | `universr/models/__init__.py` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `models/unet.py` | `universr/models/unet.py` | `75bb3baa9a33cc0dbe690b9a8624b4025f77f034fcc0ba15d44f85e1c666b3d0` |
| `flow/__init__.py` | `universr/flow/__init__.py` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `flow/path.py` | `universr/flow/path.py` | `1fd0d744a67e0ba3a05b54c8ec5b3e3f2bf22d18afb9983f7817e616389f3ca5` |
| `flow/solver.py` | `universr/flow/solver.py` | `09cd769a068f279f98526588a0d3eb5d7e89d7b2a589252a4eaa0c26624927ee` |
| `utils/__init__.py` | `universr/utils/__init__.py` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `utils/spectral_ops.py` | `universr/utils/spectral_ops.py` | `3060a88de283e2b1df0f298ce9822bea33cfb07b5e27adb93f81f9f6fc320003` |
| `audio_config.yaml` | `config.yaml` of the weights repo | `2e035dacc833368319f9d5ba1a34e5efd343faf749008d433e309f3c65f4dac9` |

## Deliberate changes to the upstream files

Only the import statements below were rewritten (the package is vendored under a different
name), and three loaders Plenio never calls were taken out; every other byte is upstream:

- `universr/inference.py: 'from universr.models.unet import' -> 'from .models.unet import'`
- `universr/inference.py: 'from universr.flow.path import' -> 'from .flow.path import'`
- `universr/inference.py: 'from universr.flow.solver import' -> 'from .flow.solver import'`
- `universr/inference.py: 'from universr.utils.spectral_ops import' -> 'from .utils.spectral_ops import'`
- `universr/flow/solver.py: 'from universr.models.unet import' -> 'from ..models.unet import'`
- `universr/inference.py`: `UniverSR.from_pretrained` (it downloaded `config.yaml` and the weights from
  Hugging Face) and `UniverSR.from_local` (it read a training checkpoint with
  `torch.load(..., weights_only=False)`, which unpickles code) taken out, with the imports of `os`, `yaml`
  and `huggingface_hub` they alone used (Plenio 1.4.0)
- `universr/flow/path.py`: `get_path` (it imported the module a config's `class_path` names) taken out,
  with `import importlib` (Plenio 1.4.0)

The weights come through ComfyUI's model management (`plenio/comfy/universr.py` reads them with
`weights_only=True` and builds the model, the transform and the path itself); the vendored code downloads
nothing. `universr/flow/solver.py` imports `torchdiffeq`
and `tqdm`: ComfyUI ships both, and `_compat.py` next to this file installs a vendored
fixed-step stand-in when `torchdiffeq` is missing (the adapter reports which one ran).
`universr/utils/utils.py` (librosa/box/matplotlib helpers) and the training code are not vendored.
