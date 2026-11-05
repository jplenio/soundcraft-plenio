#!/usr/bin/env sh
# Plenio Player: your Plenio songs in the browser - lyrics, sheet music and visuals in time with the music.
# Start it with this script (ComfyUI need not run). It uses the Python of the ComfyUI it is installed in
# (its .venv or venv), else python3. Stop it with Ctrl+C, or on the player's Settings page.
cd "$(dirname "$0")" || exit 1
for candidate in ../../.venv/bin/python ../../venv/bin/python; do
  if [ -x "$candidate" ]; then exec "$candidate" plenio_player.py "$@"; fi
done
exec python3 plenio_player.py "$@"
