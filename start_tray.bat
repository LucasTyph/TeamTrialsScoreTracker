@echo off
cd /d "%~dp0"
echo Starting Score Tracker...
echo The app will run in the background (system tray).
echo Close the console window to exit.
echo.
python main.py --tray
if errorlevel 1 (
    echo.
    echo ERROR: The tray app failed to start.
    echo Check tray.log for details.
    pause
)
