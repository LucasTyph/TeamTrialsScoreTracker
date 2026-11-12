@echo off
rem Opens the Team Trials Score Tracker without a console window.
cd /d "%~dp0.."
start "" pythonw -m score_tracker
if errorlevel 1 (
    echo Couldn't start the app. Is Python installed and on your PATH?
    echo   Install dependencies:  pip install -r requirements.txt
    pause
)
