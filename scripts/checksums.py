#!/usr/bin/env python3
from __future__ import annotations

import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
dist = ROOT / "dist"
artifacts = sorted(path for path in dist.iterdir() if path.is_file() and path.name != "SHA256SUMS")
if not artifacts:
    raise SystemExit("no distribution artifacts found")
lines = []
for path in artifacts:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    lines.append(f"{digest}  {path.name}")
(dist / "SHA256SUMS").write_text("\n".join(lines) + "\n", encoding="ascii")
