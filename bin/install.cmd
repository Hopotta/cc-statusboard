@echo off
REM One-time Windows setup. Safe to run from any current directory.
setlocal
set "SCRIPT_DIR=%~dp0"
set "PROJECT_ROOT=%SCRIPT_DIR%.."

python "%PROJECT_ROOT%\collector\install.py"
exit /b %ERRORLEVEL%
