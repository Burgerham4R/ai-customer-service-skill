#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""技术栈检测 CLI。

用法：
    python scripts/detect-stack.py /path/to/user/project
    python scripts/detect-stack.py /path/to/user/project --json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))

from scripts.lib import stack_detector as sd


def main() -> None:
    parser = argparse.ArgumentParser(description="技术栈检测 CLI")
    parser.add_argument("project", type=Path, help="目标项目根目录")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if not args.project.exists():
        raise SystemExit(f"path not found: {args.project}")
    res = sd.detect(args.project)
    if args.json:
        print(json.dumps(res.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(f"primary    : {res.primary}")
        print(f"candidates : {', '.join(res.candidates) or '-'}")
        print(f"signals    : {', '.join(res.signals) or '-'}")


if __name__ == "__main__":
    main()
