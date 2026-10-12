"""
build_exe.py — Build FedExFlagger.exe using PyInstaller.

Run from the project root:
    python build/build_exe.py

Output: dist/FedExFlagger.exe (single self-contained executable)

The EXE includes all Python code, dependencies, and Flask templates/static files.
Playwright's Chromium browser is downloaded separately on first launch (~130 MB).
"""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC  = ROOT / "src"
DIST = ROOT / "dist"
SPEC = ROOT / "build" / "FedExFlagger.spec"


def build():
    print("=" * 56)
    print("  Building FedExFlagger.exe")
    print("=" * 56)

    # Ensure PyInstaller is installed
    try:
        import PyInstaller
        print(f"  PyInstaller {PyInstaller.__version__} found [OK]")
    except ImportError:
        print("  Installing PyInstaller...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller==6.1.0"])

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--onefile",
        "--windowed",                      # No console window
        "--name", "FedExFlagger",
        "--distpath", str(DIST),
        "--workpath", str(ROOT / "pyinstaller-build"),
        "--specpath", str(ROOT / "build"),
        # Add Python source path
        "--paths", str(SRC),
        # Include Flask templates and static files
        "--add-data", f"{SRC / 'flagger' / 'dashboard' / 'templates'}{os.pathsep}flagger/dashboard/templates",
        "--add-data", f"{SRC / 'flagger' / 'dashboard' / 'static'}{os.pathsep}flagger/dashboard/static",
        # Hidden imports Flask/Jinja2 don't always auto-detect
        "--hidden-import", "flask",
        "--hidden-import", "jinja2",
        "--hidden-import", "werkzeug",
        "--hidden-import", "pystray",
        "--hidden-import", "PIL",
        "--hidden-import", "plyer",
        "--hidden-import", "plyer.platforms.win.notification",
        # Entry point
        str(SRC / "flagger" / "main.py"),
    ]

    # Add icon if it exists
    icon_path = ROOT / "assets" / "icon.ico"
    if icon_path.exists():
        cmd += ["--icon", str(icon_path)]

    print("\n  Running PyInstaller...\n")
    result = subprocess.run(cmd, cwd=str(ROOT))

    if result.returncode == 0:
        exe = DIST / "FedExFlagger.exe"
        size_mb = exe.stat().st_size / 1_048_576 if exe.exists() else 0
        print(f"\n{'=' * 56}")
        print("  Build successful!")
        print(f"  Output: {exe}")
        print(f"  Size:   {size_mb:.1f} MB")
        print(f"{'=' * 56}")
    else:
        print(f"\n  Build failed (exit code {result.returncode})")
        sys.exit(1)


if __name__ == "__main__":
    build()
