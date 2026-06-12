@echo off
setlocal EnableExtensions EnableDelayedExpansion
title Tunnel Digital Twin - local launcher

REM ===========================================================================
REM  Tunnel Digital Twin - run the Streamlit dashboard locally (offline).
REM
REM  The dashboard is also deployed on Streamlit Community Cloud; this script
REM  runs the SAME app.py on your own machine with no dependency on the cloud.
REM
REM  First run: creates an isolated Python environment and installs the
REM  dependencies from requirements.txt. Later runs reuse it and start fast.
REM
REM  Why pure batch (no PowerShell .ps1)? This project lives on a Google
REM  Shared Drive, which stamps synced files with a "Mark of the Web". On a
REM  managed/Enterprise machine that blocks unsigned .ps1 scripts even with
REM  -ExecutionPolicy Bypass. A .cmd is not subject to that, so it just runs.
REM
REM  Usage:
REM    run_local.cmd            Set up if needed, then launch on port 8501.
REM    run_local.cmd 8600       Launch on a custom port.
REM    run_local.cmd clean      Delete the environment and rebuild from scratch.
REM    run_local.cmd clean 8600 Rebuild, then launch on a custom port.
REM ===========================================================================

REM --- locations -------------------------------------------------------------
set "PROJECT=%~dp0"
if "%PROJECT:~-1%"=="\" set "PROJECT=%PROJECT:~0,-1%"

REM Keep the venv OFF the synced drive (sync churn) AND out of AppData (the
REM Microsoft Store build of Python redirects venvs created under AppData
REM into its sandbox). The profile root satisfies both. Override with the
REM TUNNEL_DT_VENV environment variable.
set "VENV=%USERPROFILE%\.tunnel-dt2026-venv"
if defined TUNNEL_DT_VENV set "VENV=%TUNNEL_DT_VENV%"
set "VPY=%VENV%\Scripts\python.exe"
set "REQ=%PROJECT%\requirements.txt"
set "APP=%PROJECT%\app.py"
set "MARKER=%VENV%\.requirements.sha256"
set "PORT=8501"

REM --- arguments: "clean" rebuilds; a number sets the port -------------------
for %%A in (%*) do (
  set "ARG=%%~A"
  if /I "!ARG!"=="clean" (
    echo Removing existing environment for a clean rebuild...
    if exist "%VENV%" rmdir /S /Q "%VENV%"
  ) else (
    echo !ARG!| findstr /R "^[1-9][0-9]*$" >nul && set "PORT=!ARG!"
  )
)

echo.
echo === Tunnel Digital Twin - local launcher ===
echo Project : %PROJECT%
echo Env     : %VENV%
echo Port    : %PORT%
echo.

if not exist "%REQ%" ( echo ERROR: requirements.txt not found at "%REQ%". & goto :fail )
if not exist "%APP%" ( echo ERROR: app.py not found at "%APP%". & goto :fail )

REM --- find a base Python (only needed to create the venv) -------------------
set "BASEPY="
where py >nul 2>&1 && set "BASEPY=py -3"
if not defined BASEPY ( where python  >nul 2>&1 && set "BASEPY=python" )
if not defined BASEPY ( where python3 >nul 2>&1 && set "BASEPY=python3" )
if not defined BASEPY (
  echo ERROR: No Python interpreter found.
  echo Install Python 3.11+ from https://www.python.org/ or the Microsoft Store.
  goto :fail
)

REM --- create the virtual environment if missing -----------------------------
if not exist "%VPY%" (
  echo Creating virtual environment with: %BASEPY%
  %BASEPY% -m venv "%VENV%"
)
if not exist "%VPY%" (
  echo ERROR: Failed to create the virtual environment at "%VENV%".
  goto :fail
)

REM --- (re)install dependencies only when requirements.txt changed -----------
set "REQHASH="
for /f "skip=1 delims=" %%H in ('certutil -hashfile "%REQ%" SHA256 2^>nul') do if not defined REQHASH set "REQHASH=%%H"
set "REQHASH=%REQHASH: =%"

set "HAVEHASH="
if exist "%MARKER%" set /p HAVEHASH=<"%MARKER%"

if /I not "%REQHASH%"=="%HAVEHASH%" (
  echo Installing dependencies ^(first run or requirements.txt changed^)...
  "%VPY%" -m pip install --upgrade pip
  "%VPY%" -m pip install -r "%REQ%"
  if errorlevel 1 (
    echo ERROR: dependency installation failed - see the pip output above.
    goto :fail
  )
  >"%MARKER%" echo %REQHASH%
  echo Dependencies installed.
) else (
  echo Dependencies already up to date - skipping install.
)

REM --- launch ----------------------------------------------------------------
echo.
echo Starting Streamlit on http://localhost:%PORT%
echo A browser tab should open automatically. Close this window or press
echo Ctrl+C here to stop the server.
echo.

cd /d "%PROJECT%"
"%VPY%" -m streamlit run "%APP%" --server.port %PORT% --server.headless false --browser.gatherUsageStats false --server.fileWatcherType none
goto :end

:fail
echo.
echo Launch aborted.

:end
echo.
pause
