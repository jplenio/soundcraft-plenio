@echo off
rem Plenio Player: your Plenio songs in the browser - lyrics, sheet music and visuals in time with the music.
rem Double-click to start it (ComfyUI need not run). It finds the Python of the ComfyUI it is installed in:
rem the portable build's python_embeded, or the .venv of a manual or Desktop install; else "python".
rem Stop it with Ctrl+C in this window, or on the player's Settings page.
setlocal
cd /d "%~dp0"
set "PLENIO_PY="
if exist "..\..\..\python_embeded\python.exe" set "PLENIO_PY=..\..\..\python_embeded\python.exe"
if not defined PLENIO_PY if exist "..\..\.venv\Scripts\python.exe" set "PLENIO_PY=..\..\.venv\Scripts\python.exe"
if not defined PLENIO_PY if exist "..\..\venv\Scripts\python.exe" set "PLENIO_PY=..\..\venv\Scripts\python.exe"
if not defined PLENIO_PY set "PLENIO_PY=python"
"%PLENIO_PY%" plenio_player.py %*
if errorlevel 1 pause
endlocal
