"""Fixture subprocess: print lines and exit with a chosen code."""

from __future__ import annotations

import argparse
import sys


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--exit-code", type=int, default=0)
    parser.add_argument("lines", nargs="*", default=["hello"])
    args = parser.parse_args()
    for line in args.lines:
        print(line, flush=True)
    raise SystemExit(args.exit_code)


if __name__ == "__main__":
    main()
