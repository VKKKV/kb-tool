#!/usr/bin/env python3
"""Compatibility entry point for the former ctf-tool WeChat tidy script.

Use ``kb tidy-wechat`` for new invocations.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from kb.migrations import load_coverage, tidy_wechat


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("articles", type=Path)
    parser.add_argument("year")
    parser.add_argument("coverage", type=Path)
    args = parser.parse_args()
    processed, changed, errors = tidy_wechat(
        args.articles, args.year, load_coverage(args.coverage)
    )
    for path, error in errors:
        print(f"{path}: {error}")
    print(f"processed={processed} changed={changed} errors={len(errors)}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
