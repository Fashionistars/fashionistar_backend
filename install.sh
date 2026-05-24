#!/bin/bash
# ============================================================
# FASHIONISTAR AI — Resilient Package Installer
# Mirrors requirements.txt (20 sections) in batch order
# Installs packages in small batches to survive network drops
# Usage: source venv/Scripts/activate && bash install.sh
# ============================================================

set -e
PIP="python -m pip install --timeout 120 --retries 10"

echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║   FASHIONISTAR AI — Resilient Batch Installer           ║"
echo "║   Django 6.0.2 | Python 3.14+ | 14 Batches             ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Batch 1: Core Framework (Section 1)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo "📦 [1/14] Core Framework..."
$PIP Django==6.0.2 djangorestframework django-ninja adrf \
  && echo "✅ Batch 1 done" \
  || echo "❌ Batch 1 failed — retry manually"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Batch 2: Environment & Configuration + Database (Sections 2-3)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo "📦 [2/14] Environment, Config & Database..."
$PIP django-environ environs python-decouple \
     psycopg2-binary dj-database-url \
  && echo "✅ Batch 2 done" \
  || echo "❌ Batch 2 failed"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Batch 3: Authentication & Security (Section 4)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo "📦 [3/14] Authentication & Security..."
$PIP djangorestframework-simplejwt PyJWT cryptography pycryptodome \
     django-encrypted-model-fields django-ratelimit fido2 \
     google-auth google-auth-oauthlib google-auth-httplib2 \
     django-axes django-csp \
  && echo "✅ Batch 3 done" \
  || echo "❌ Batch 3 failed"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Batch 4: Caching & Redis (Section 5)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo "📦 [4/14] Caching & Redis..."
$PIP django-redis redis hiredis \
  && echo "✅ Batch 4 done" \
  || echo "❌ Batch 4 failed"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Batch 5: Background Tasks (Section 6)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo "📦 [5/14] Background Tasks..."
$PIP celery django-celery-beat flower \
  && echo "✅ Batch 5 done" \
  || echo "❌ Batch 5 failed"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Batch 6: ASGI/WSGI Servers + Channels (Sections 7-8)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo "📦 [6/14] ASGI/WSGI Servers & Channels..."
$PIP uvicorn daphne gunicorn \
     channels channels-redis \
  && echo "✅ Batch 6 done" \
  || echo "❌ Batch 6 failed"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Batch 7: CORS, Middleware & Storage (Sections 9-10)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo "📦 [7/14] CORS, Middleware & Storage..."
$PIP django-cors-headers whitenoise \
     django-storages django-cloudinary-storage cloudinary pillow \
  && echo "✅ Batch 7 done" \
  || echo "❌ Batch 7 failed"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Batch 8: Phone, SMS & Email (Sections 11-12)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo "📦 [8/14] Phone, SMS & Email..."
$PIP "django-phonenumber-field[phonenumbers]" phonenumbers twilio django-phone-verify \
     django-anymail django-zoho-zeptomail email-validator \
  && echo "✅ Batch 8 done" \
  || echo "❌ Batch 8 failed"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Batch 9: API Documentation (Section 13)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo "📦 [9/14] API Documentation..."
$PIP drf-spectacular drf-yasg \
  && echo "✅ Batch 9 done" \
  || echo "❌ Batch 9 failed"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Batch 10: Admin & Audit (Section 14)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo "📦 [10/14] Admin & Audit..."
$PIP django-jazzmin django-import-export \
  && echo "✅ Batch 10 done" \
  || echo "❌ Batch 10 failed"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Batch 11: Logging, Monitoring & Observability (Section 15)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo "📦 [11/14] Logging, Monitoring & Observability (Enterprise)..."
$PIP drf-api-logger prometheus_client \
     "sentry-sdk[django]" django-silk django-health-check django-structlog \
  && echo "✅ Batch 11 done" \
  || echo "❌ Batch 11 failed"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Batch 12: Data, Validation, HTTP & Networking (Sections 16-17)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo "📦 [12/14] Data, Validation, HTTP & Networking..."
$PIP pydantic django-filter marshmallow tablib \
     requests httpx aiohttp aiohttp-retry \
     certifi charset-normalizer idna urllib3 \
  && echo "✅ Batch 12 done" \
  || echo "❌ Batch 12 failed"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Batch 13: Payments, Utilities & Async Internals (Sections 18-20)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo "📦 [13/14] Payments, Utilities & Async Internals..."
$PIP stripe rave-python \
     asgiref attrs click colorama humanize jsonschema packaging \
     python-dateutil pytz PyYAML setuptools shortuuid six sqlparse \
     typing_extensions tzdata uritemplate uuid6 wrapt \
     aiohappyeyeballs aiosignal async-timeout frozenlist multidict propcache yarl \
  && echo "✅ Batch 13 done" \
  || echo "❌ Batch 13 failed"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Batch 14: 🔒 Django Version Pin (SAFETY NET)
# Some packages (channels, celery-beat, etc.) may pull an older
# Django during resolution. This final step FORCES 6.0.2 back.
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo ""
echo "🔒 [14/14] Pinning Django==6.0.2 (safety net)..."
$PIP Django==6.0.2 \
  && echo "✅ Django 6.0.2 pinned successfully" \
  || echo "❌ Django pin failed — run manually: pip install Django==6.0.2"


# ━━━━ Verification ━━━━
echo ""
DJANGO_VER=$(python -c "import django; print(django.VERSION)" 2>/dev/null || echo "IMPORT FAILED")
echo "🔎 Installed Django version: $DJANGO_VER"

echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║  ✅  Installation complete!                             ║"
echo "║  Run:  make dev    (to start the server)                ║"
echo "║  Or:   python manage.py runserver 0.0.0.0:8001          ║"
echo "╚══════════════════════════════════════════════════════════╝"
