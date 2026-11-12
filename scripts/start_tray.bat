@echo off
cd /d "%~dp0.."
echo Starting Score Tracker...
echo The app opens a window and an icon in the system tray.
echo Closing the window keeps it running in the tray; use the tray menu to exit.
echo.

python -m score_tracker --app
set EXIT_CODE=%ERRORLEVEL%

if not "%EXIT_CODE%"=="0" (
    echo.
    echo ERROR: The app failed to start ^(exit code %EXIT_CODE%^).
    echo.
    echo   - Install dependencies:  pip install -r requirements.txt
    echo   - Install Tesseract OCR:  https://github.com/UB-Mannheim/tesseract/wiki
    echo.
    pause
)
