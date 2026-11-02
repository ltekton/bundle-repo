#!/usr/bin/env python3
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
for name in ["dist", "build", ".pytest_cache", ".ruff_cache", ".pyrefly", "htmlcov", ".coverage"]:
    path = ROOT / name
    if path.is_dir(): shutil.rmtree(path)
    elif path.exists(): path.unlink()
for path in ROOT.rglob("__pycache__"):
    shutil.rmtree(path)
