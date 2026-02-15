#!/bin/bash
# ============================================================
# FASHIONISTAR AI — Resilient Package Installer
# Installs packages in small batches to survive network drops
# Usage: source venv/Scripts/activate && bash install.sh
# ============================================================

set -e
PIP="python -m pip install --timeout 120 --retries 10"

echo "🚀 Starting batch installation..."
echo ""

# Batch 1: Core Framework
echo "📦 [1/10] Core Framework..."
$PIP Django==6.0.2 djangorestframework django-ninja && echo "✅ Batch 1 done" || echo "❌ Batch 1 failed — retry: $PIP Django==6.0.2 djangorestframework django-ninja"

# Batch 2: API Docs + Auth
echo "📦 [2/10] API Docs & Authentication..."
$PIP drf-spectacular drf-yasg djangorestframework-simplejwt PyJWT && echo "✅ Batch 2 done" || echo "❌ Batch 2 failed"

# Batch 3: Security
echo "📦 [3/10] Security..."
$PIP cryptography pycryptodome django-encrypted-model-fields django-ratelimit fido2 && echo "✅ Batch 3 done" || echo "❌ Batch 3 failed"

# Batch 4: Database & Cache
echo "📦 [4/10] Database & Cache..."
$PIP psycopg2-binary dj-database-url django-redis redis hiredis && echo "✅ Batch 4 done" || echo "❌ Batch 4 failed"

# Batch 5: Background Tasks
echo "📦 [5/10] Background Tasks..."
$PIP celery django-celery-beat flower && echo "✅ Batch 5 done" || echo "❌ Batch 5 failed"

# Batch 6: ASGI & Middleware
echo "📦 [6/10] ASGI Servers & Middleware..."
$PIP uvicorn daphne gunicorn django-cors-headers whitenoise && echo "✅ Batch 6 done" || echo "❌ Batch 6 failed"

# Batch 7: Storage & Media
echo "📦 [7/10] Storage & Media..."
$PIP django-storages django-cloudinary-storage cloudinary boto3 pillow && echo "✅ Batch 7 done" || echo "❌ Batch 7 failed"

# Batch 8: Phone, SMS & Email
echo "📦 [8/10] Phone, SMS & Email..."
$PIP "django-phonenumber-field[phonenumbers]" phonenumbers twilio django-phone-verify django-anymail django-zoho-zeptomail email-validator && echo "✅ Batch 8 done" || echo "❌ Batch 8 failed"

# Batch 9: Admin, Config & Data
echo "📦 [9/10] Admin, Config & Data..."
$PIP django-environ django-jazzmin django-import-export django-auditlog pydantic django-filter marshmallow tablib && echo "✅ Batch 9 done" || echo "❌ Batch 9 failed"

# Batch 10: HTTP, Channels, Monitoring, Utils, Payments
echo "📦 [10/10] HTTP, Channels, Monitoring, Utils & Payments..."
$PIP requests httpx aiohttp aiohttp-retry channels drf-api-logger prometheus_client colorama humanize python-dateutil pytz PyYAML setuptools shortuuid sqlparse typing_extensions tzdata uuid6 stripe rave-python && echo "✅ Batch 10 done" || echo "❌ Batch 10 failed"

echo ""
echo "============================================"
echo "✅ Installation complete!"
echo "Run: make dev  (to start the server)"
echo "============================================"
