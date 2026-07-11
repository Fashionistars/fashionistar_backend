#!/usr/bin/env python3
"""Validate that every .py file is plain UTF-8 and has no BOM/UTF-16 encoding.

This catches files like the old `scratch/old_product_views.py` which was saved
as UTF-16 LE with BOM and broke the Codacy security scan.

Usage:
    python scripts/validate_utf8.py
    python scripts/validate_utf8.py --path /path/to/repo

Exit codes:
    0 - all Python files are valid UTF-8 without BOM
    1 - one or more files are malformed
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Directories that should not be scanned
SKIP_DIRS = {
    ".git",
    ".venv",
    ".env",
    ".uv-cache",
    ".cache",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".egg-info",
    "build",
    "dist",
    "node_modules",
}

# Byte markers that indicate BOMs
UTF8_BOM = b"\xef\xbb\xbf"
UTF16_LE_BOM = b"\xff\xfe"
UTF16_BE_BOM = b"\xfe\xff"


def should_skip(path: Path) -> bool:
    """Return True if the directory should be skipped."""
    return any(part in SKIP_DIRS for part in path.parts)


def validate_file(file_path: Path) -> list[str]:
    """Return a list of error messages for the file, or empty if valid."""
    errors: list[str] = []
    raw = file_path.read_bytes()

    # 1. Reject UTF-16 BOMs
    if raw.startswith(UTF16_LE_BOM):
        errors.append(f"{file_path}: UTF-16 LE BOM detected")
    elif raw.startswith(UTF16_BE_BOM):
        errors.append(f"{file_path}: UTF-16 BE BOM detected")
    elif raw.startswith(UTF8_BOM):
        errors.append(f"{file_path}: UTF-8 BOM detected")

    # 2. Reject null bytes
    if b"\x00" in raw:
        errors.append(f"{file_path}: contains null bytes")

    # 3. Validate strict UTF-8 decode
    if not errors:
        try:
            raw.decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            errors.append(f"{file_path}: {exc}")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate UTF-8 encoding for all .py files in a tree."
    )
    parser.add_argument(
        "--path",
        type=Path,
        default=Path.cwd(),
        help="Root directory to scan (default: current directory)",
    )
    parser.add_argument(
        "--skip",
        type=str,
        action="append",
        default=[],
        help="Additional directory names to skip (can be given multiple times)",
    )
    args = parser.parse_args()

    skip_dirs = SKIP_DIRS | set(args.skip)
    root: Path = args.path.resolve()

    all_errors: list[str] = []
    for py_path in root.rglob("*.py"):
        if should_skip(py_path):
            continue
        all_errors.extend(validate_file(py_path))

    if all_errors:
        print("Invalid encoding detected in the following files:", file=sys.stderr)
        for error in all_errors:
            print(f"  - {error}", file=sys.stderr)
        return 1

    print(f"Validated {len(list(root.rglob('*.py')))} Python files in {root}")
    print("All .py files are valid UTF-8 without BOM.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
