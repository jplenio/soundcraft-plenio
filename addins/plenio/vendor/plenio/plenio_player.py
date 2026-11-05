"""Start the Plenio Player from the package folder, without ComfyUI:

    python plenio_player.py [--folder <folder with Plenio songs>] [--port 8765]

(any Python 3.10+, for example ComfyUI's own). Without --folder it plays ComfyUI's output folder.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

if __name__ == "__main__":
    from plenio.player.__main__ import main

    sys.exit(main())
