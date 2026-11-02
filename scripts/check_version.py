#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
version = tomllib.loads((ROOT / "pyproject.toml").read_text("utf-8"))["project"]["version"]

parser = argparse.ArgumentParser()
parser.add_argument("--tag", default=os.environ.get("GITHUB_REF_NAME"))
args = parser.parse_args()
print(version)
if args.tag and args.tag != f"v{version}":
    print(f"release tag {args.tag!r} does not match project version v{version}", file=sys.stderr)
    raise SystemExit(1)
