@echo off
cd /d "%~dp0.."
echo Starting Score Tracker...
echo The app will run in the background (system tray).
echo Close the console window to exit.
echo.

python main.py --tray
set EXIT_CODE=%ERRORLEVEL%

if not "%EXIT_CODE%"=="0" (
    echo.
    echo ERROR: The tray app failed to start ^(exit code %EXIT_CODE%^).
    echo.
    echo   - Install dependencies:  pip install -r requirements.txt
    echo   - Install Tesseract OCR:  https://github.com/UB-Mannheim/tesseract/wiki
    echo   - Check tray.log for details.
    echo.
    pause
)
