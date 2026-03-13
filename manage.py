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
    # ── Settings Module Resolution ─────────────────────────────────────────
    # Priority order (highest → lowest):
    #   1. DJANGO_SETTINGS_MODULE already set in shell/CI env — wins outright.
    #   2. WORKING_ENVIRONMENT from .env → auto-maps to config submodule.
    #   3. Fallback: backend.config.development (NEVER legacy backend.settings)
    #
    # WORKING_ENVIRONMENT values:
    #   development → backend.config.development
    #   staging     → backend.config.production   (prod settings on staging host)
    #   testing     → backend.config.test
    #   production  → backend.config.production
    _env_map = {
        'development': 'backend.config.development',
        'staging':     'backend.config.production',
        'testing':     'backend.config.test',
        'production':  'backend.config.production',
    }
    # If DJANGO_SETTINGS_MODULE is already set (by CI, Makefile, or shell),
    # leave it alone — it takes the highest priority.
    if not os.environ.get('DJANGO_SETTINGS_MODULE'):
        _working_env = os.environ.get('WORKING_ENVIRONMENT', 'development').lower()
        _settings_module = _env_map.get(
            _working_env,
            'backend.config.development',   # Safe fallback (NEVER legacy settings)
        )
        os.environ['DJANGO_SETTINGS_MODULE'] = _settings_module
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
