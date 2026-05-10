# backend/config/__init__.py
"""
Fashionistar Settings Package
==============================

Usage — set DJANGO_SETTINGS_MODULE to select an environment:

  Development (default):
    DJANGO_SETTINGS_MODULE=backend.config.development

  Production:
    DJANGO_SETTINGS_MODULE=backend.config.production

  OR keep using the original settings.py (unchanged):
    DJANGO_SETTINGS_MODULE=backend.settings

Files in this package:
  base.py         — Common settings for ALL environments
  development.py  — Local dev (DEBUG=True, console email)
  production.py   — Production (HTTPS, HSTS, hardened)
"""
