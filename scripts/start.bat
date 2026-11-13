@echo off
rem Opens the Team Trials Score Tracker without a console window.
rem Uses the built .exe if there is one (python scripts\build_exe.py), else Python.
cd /d "%~dp0.."
if exist "dist\TeamTrialsScoreTracker\TeamTrialsScoreTracker.exe" (
    start "" "dist\TeamTrialsScoreTracker\TeamTrialsScoreTracker.exe"
    exit /b
)
start "" pythonw -m score_tracker
if errorlevel 1 (
    echo Couldn't start the app. Is Python installed and on your PATH?
    echo   Install dependencies:  pip install -r requirements.txt
    pause
)
