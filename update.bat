@echo off
REM ============================================================
REM  update.bat - update the MiniMax H3 sampler comparison site
REM
REM  Double-click this after ComfyUI finishes rendering. It:
REM    1. scans the source folder for new <sampler>_*.mp4 clips,
REM    2. copies them into videos\  and generates posters,
REM    3. updates data.js (RENDERED) so the pages show them,
REM    4. commits everything, then asks if you want to push to
REM       GitHub (the site goes live ~1 min after a push).
REM ============================================================
setlocal enabledelayedexpansion
cd /d "%~dp0"

REM --- CONFIGURE -------------------------------------------------
REM  Folder where ComfyUI saves its renders. Default: the
REM  samplertest output folder sitting next to this site folder.
REM  Change SOURCE if your renders live somewhere else.
set "SOURCE=%~dp0.."
REM ----------------------------------------------------------------

echo.
echo  MiniMax H3 sampler eval - update
echo  source folder: %SOURCE%
echo.

where python >nul 2>nul
if errorlevel 1 (
    where py >nul 2>nul
    if errorlevel 1 (
        echo ERROR: Python not found on PATH.
        echo Install Python or add it to PATH, then try again.
        pause
        exit /b 1
    )
    set "PY=py -3"
) else (
    set "PY=python"
)

REM --- 1-3. copy clips, make posters, refresh data.js ------------
%PY% tools\sync_videos.py --source "%SOURCE%"
if errorlevel 1 (
    echo.
    echo ERROR: sync failed - see messages above.
    pause
    exit /b 1
)

REM --- 4. commit & push ------------------------------------------
git rev-parse --is-inside-work-tree >nul 2>nul
if errorlevel 1 (
    echo No git repo here - files were copied, but nothing was committed.
    pause
    exit /b 0
)

set "GIT_AUTHOR_NAME=LuisaCaotica"
set "GIT_AUTHOR_EMAIL=38731510+Luisacaotica@users.noreply.github.com"
set "GIT_COMMITTER_NAME=LuisaCaotica"
set "GIT_COMMITTER_EMAIL=38731510+Luisacaotica@users.noreply.github.com"

git add -A
git commit -m "Update sampler renders (%date% %time%)" >nul 2>nul
if not errorlevel 1 echo Committed the new renders.

choice /c YN /m "Push to GitHub now"
if errorlevel 2 goto :done

git push origin main
if errorlevel 1 (
    echo.
    echo Push failed - you may need to sign in to GitHub once
    echo (GitHub Desktop or the git credential manager will help).
) else (
    echo.
    echo Pushed! GitHub Pages rebuilds in about a minute.
    echo Live at: https://luisacaotica.github.io/minimax-h3-sampler-eval/
)
:done
pause
