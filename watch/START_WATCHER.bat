@echo off
title Leylu board watcher (ntfy: leylu-watch-31)
cd /d "%~dp0"
rem Only one watcher at a time: stop any other copy before starting this one.
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name LIKE 'python%%'\" | Where-Object { $_.CommandLine -match 'board_watch_live' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"
rem The team key: FIVEU_API_KEY from the environment, else one line in watch\team_key.txt (gitignored, never commit it).
if not defined FIVEU_API_KEY if exist team_key.txt set /p FIVEU_API_KEY=<team_key.txt
if not defined NTFY_TOPIC set NTFY_TOPIC=leylu-watch-31
set WATCH_STATE=%~dp0watch_state.json
set PYTHONIOENCODING=utf-8
echo Leylu board watcher - alerts go to https://ntfy.sh/%NTFY_TOPIC%  (close this window to stop it)
echo.
rem uv's Python 3.12 (the script needs 3.10+, a system Python 3.8 can't run it); stdlib only, no project packages
uv run --no-project --python 3.12 python -u board_watch_live.py
echo.
echo The watcher stopped. Press any key to close.
pause >nul
