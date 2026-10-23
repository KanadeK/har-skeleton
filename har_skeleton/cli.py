"""Offline CLI. Errors deliberately omit capture content and filesystem paths."""

import argparse
import json
import sys

from . import __version__
from .core import MAX_BYTES, MAX_ENTRIES, HarError, build_skeleton, load_har, write_new


def positive(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be positive")
    return number


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Export a text-free HAR performance skeleton offline."
    )
    parser.add_argument("--version", action="version", version=f"har-skeleton {__version__}")
    parser.add_argument("input", help="UTF-8 HAR capture")
    parser.add_argument("output", help="new output file; existing files are refused")
    parser.add_argument("--max-bytes", type=positive, default=MAX_BYTES)
    parser.add_argument("--max-entries", type=positive, default=MAX_ENTRIES)
    args = parser.parse_args(argv)
    try:
        skeleton, counts = build_skeleton(
            load_har(args.input, max_bytes=args.max_bytes), max_entries=args.max_entries
        )
        write_new(args.output, skeleton)
    except FileExistsError:
        print("error: output already exists; choose a new file", file=sys.stderr)
        return 2
    except HarError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except OSError:
        print(
            "error: cannot read input or create output; check paths and permissions",
            file=sys.stderr,
        )
        return 2
    print(json.dumps({"written": True, **counts}, sort_keys=True))
    return 0
