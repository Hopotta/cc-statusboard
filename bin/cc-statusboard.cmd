@echo off
REM cc-statusboard CLI launcher (Windows).
REM Generates statusboard.json + serves the frontend on http://localhost:3456.
REM
REM Usage:
REM   cc-statusboard                REM one-shot generate, then serve
REM   cc-statusboard --watch        REM also watch JSONL files
REM   cc-statusboard --port 4000    REM override port
REM   cc-statusboard --no-open      REM don't open the browser
REM   cc-statusboard --dev          REM use Vite dev server (with HMR)

setlocal
set "SCRIPT_DIR=%~dp0"
set "PROJECT_ROOT=%SCRIPT_DIR%.."

pushd "%PROJECT_ROOT%"
python "%PROJECT_ROOT%\collector\serve_statusboard.py" %*
set "EC=%ERRORLEVEL%"
popd
exit /b %EC%