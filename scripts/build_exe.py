"""Build TeamTrialsScoreTracker.exe with PyInstaller.

    python scripts/build_exe.py              # build dist/TeamTrialsScoreTracker/
    python scripts/build_exe.py --shortcut   # also add Desktop and Start menu shortcuts

The result is a folder (faster to start than a single-file .exe, which
unpacks itself on every launch). Run it from where it's built: an .exe
inside this checkout uses the checkout's data/ folder, like running from
source. Tesseract stays a separate install.

Needs: pip install -e ".[build]"
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NAME = "TeamTrialsScoreTracker"
EXE = ROOT / "dist" / NAME / f"{NAME}.exe"

# Big optional packages pandas and Pillow can pull in but the app never uses
EXCLUDES = ["tkinter", "matplotlib", "IPython", "jupyter", "notebook", "scipy", "pytest",
            "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.Qt3DCore",
            "PySide6.QtQuick", "PySide6.QtQml", "PySide6.QtMultimedia", "PySide6.QtPdf"]


def build():
    sep = ";" if os.name == "nt" else ":"
    cmd = [
        sys.executable, "-m", "PyInstaller", str(ROOT / "main.py"),
        "--name", NAME, "--windowed", "--onedir", "--noconfirm", "--clean",
        "--icon", str(ROOT / "score_tracker" / "assets" / "icon.png"),
        "--add-data", f"{ROOT / 'score_tracker' / 'assets'}{sep}score_tracker/assets",
        "--distpath", str(ROOT / "dist"), "--workpath", str(ROOT / "build"), "--specpath", str(ROOT / "build"),
    ]
    for module in EXCLUDES:
        cmd += ["--exclude-module", module]
    subprocess.run(cmd, check=True, cwd=ROOT)
    print(f"\nBuilt {EXE}")


def shortcut():
    """Desktop and Start menu shortcuts to the .exe (Windows)."""
    script = f"""
$shell = New-Object -ComObject WScript.Shell
foreach ($dir in @([Environment]::GetFolderPath('Desktop'), [Environment]::GetFolderPath('Programs'))) {{
    $link = $shell.CreateShortcut((Join-Path $dir 'Team Trials Score Tracker.lnk'))
    $link.TargetPath = '{EXE}'
    $link.WorkingDirectory = '{EXE.parent}'
    $link.IconLocation = '{EXE},0'
    $link.Save()
    Write-Output "Shortcut: $dir"
}}
"""
    subprocess.run(["powershell", "-NoProfile", "-Command", script], check=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--shortcut", action="store_true", help="add Desktop and Start menu shortcuts")
    parser.add_argument("--no-build", action="store_true", help="only make the shortcuts")
    args = parser.parse_args()
    if not args.no_build:
        build()
    if args.shortcut:
        shortcut()
