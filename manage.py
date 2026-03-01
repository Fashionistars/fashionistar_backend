#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import io
import os
import sys


# ── Windows UTF-8 fix ─────────────────────────────────────────────────────
# Windows terminals default to cp1252 which cannot encode Unicode characters
# (e.g. ✅ ❌ emojis) used in logger.info calls across the codebase.
# Reconfiguring stdout/stderr here is the single-point fix for every module.
# This is a no-op on Linux/Mac where streams are already UTF-8.
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(
        sys.stdout.buffer, encoding="utf-8", errors="replace"
    )
if sys.stderr.encoding and sys.stderr.encoding.lower() != "utf-8":
    sys.stderr = io.TextIOWrapper(
        sys.stderr.buffer, encoding="utf-8", errors="replace"
    )


def main():
    """Run administrative tasks."""
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()
