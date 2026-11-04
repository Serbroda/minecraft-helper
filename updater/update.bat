@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if not errorlevel 1 (
    py -3 "%~dp0update.py" %*
) else (
    python "%~dp0update.py" %*
)
set "result=%errorlevel%"
echo.
pause
exit /b %result%
