#!/usr/bin/env python3
from __future__ import annotations
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory() as tmp:
    venv = Path(tmp) / "venv"
    subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True)
    python = venv / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    wheels = sorted((ROOT / "dist").glob("*.whl"))
    if not wheels: raise SystemExit("no wheel in dist/")
    subprocess.run([str(python), "-m", "pip", "install", str(wheels[-1])], check=True)
    subprocess.run([str(python), "-c", "import bundle_repo; assert bundle_repo.VERSION == 1"], check=True)
    executable = venv / ("Scripts/bundle-repo.exe" if sys.platform == "win32" else "bin/bundle-repo")
    subprocess.run([str(executable), "--help"], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
