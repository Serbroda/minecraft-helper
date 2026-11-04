@echo off
setlocal
cd /d "%~dp0"
where git >nul 2>nul
if errorlevel 1 goto no_git
git -C "%~dp0." rev-parse --is-inside-work-tree >nul 2>nul
if errorlevel 1 goto no_repo
echo Aktualisiere Updater und Konfiguration ...
git -C "%~dp0." pull --ff-only
if errorlevel 1 (
    echo Fehler: git pull fehlgeschlagen. Updater wird nicht gestartet.
    set "result=1"
    goto finish
)
goto run

:no_git
echo Hinweis: Git nicht installiert; starte ohne git pull.
goto run

:no_repo
echo Hinweis: Kein Git-Repository; starte ohne git pull.

:run
where py >nul 2>nul
if not errorlevel 1 (
    py -3 "%~dp0update.py" %*
) else (
    python "%~dp0update.py" %*
)
set "result=%errorlevel%"
:finish
echo.
pause
exit /b %result%
