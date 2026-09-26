#!/usr/bin/env python3
"""Compatibility entry point for the former ctf-tool link migration script.

Use ``kb convert-links`` for new invocations.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from kb.migrations import convert_links, load_mapping


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mapping", type=Path)
    parser.add_argument("index", type=Path)
    args = parser.parse_args()
    converted, missing = convert_links(args.index, load_mapping(args.mapping))
    print(f"converted={converted} missing={missing}")
    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
