# backend/config/base.py
"""
FASHIONISTAR — Base Settings (All Environments)
================================================
Contains settings common to ALL environments (
    development, production, testing).
Environment-specific overrides live in development.py and production.py.

Architecture:
    base.py         ← You are here (common to all)
    development.py  ← imports base, overrides for local dev
    production.py   ← imports base, hardens for prod (Render/AWS)
    logging.py      ← logging configuration, imported by base
"""

from pathlib import Path
from datetime import timedelta
from environs import Env
import os
from decouple import config
import dj_database_url

# field-encryption-key for encrypted-model-fields in devops models
import base64
import hashlib

from backend.config.logging_config import build_logging_config

# ── Environment loader ────────────────────────────────────────────────
env = Env()
env_file_path = os.environ.get("ENV_FILE_PATH")
if env_file_path and os.path.exists(env_file_path):
    env.read_env(env_file_path)
else:
    env.read_env()


# ── Path resolution ───────────────────────────────────────────────────
# BASE_DIR → fashionistar_backend/  (root of the Django project)
BASE_DIR = Path(__file__).resolve().parent.parent.parent


def build_origin_list(*values) -> list[str]:
    origins: list[str] = []
    for value in values:
        if not value:
            continue

        normalized = str(value).strip().rstrip("/")
        if normalized and normalized not in origins:
            origins.append(normalized)

    return origins


def read_debug_flag(default: bool = False) -> bool:
    """
    Read DEBUG defensively.

    Some host shells export DEBUG with non-Django values such as "release",
    which breaks Env.bool() during import. We normalize common boolean strings
    and safely fall back for anything else so settings import never crashes.
    """
    raw_value = env("DEBUG", default=None)

    if raw_value is None:
        return default

    normalized = str(raw_value).strip().lower()

    if normalized in {"1", "true", "yes", "on"}:
        return True

    if normalized in {"0", "false", "no", "off"}:
        return False

    return default


FASHIONISTAR_COMPANY_WALLET_EMAIL_ADDRESS = env("FASHIONISTAR_COMPANY_WALLET_EMAIL_ADDRESS", default="fashionistarclothings@outlook.com")



# =============================================================================
# SECURITY
# =============================================================================
SECRET_KEY = env(
    "SECRET_KEY",
    default="django-insecure-b*tuoe%^o+=^35$0fufrm=oamh^(o0tabn39(7ni12(i-oup+4",
)

# field-encryption-key for encrypted-model-fields in devops models

raw_encryption_key = env("FIELD_ENCRYPTION_KEY", default=None)
if not raw_encryption_key:
    secret = SECRET_KEY.encode("utf-8")
    salt = b"fashionistar-field-encryption-salt-v1"
    dk = hashlib.pbkdf2_hmac("sha256", secret, salt, iterations=100_000)
    FIELD_ENCRYPTION_KEY = base64.urlsafe_b64encode(dk).decode("utf-8")
else:
    FIELD_ENCRYPTION_KEY = raw_encryption_key


# Base settings must always define DEBUG because this module is imported before
# environment-specific overrides. Development/production settings can still
# override DEBUG after import, but base.py needs a safe default for any values
# computed during import time.
DEBUG = read_debug_flag(default=False)

ALLOWED_HOSTS = env.list(
    "ALLOWED_HOSTS",
    default=[
        # WSGI dev server (Django runserver)
        "127.0.0.1",
        "localhost",
        # ASGI / Uvicorn / Daphne (port 8001)
        "localhost:8001",
        "127.0.0.1:8001",
        "0.0.0.0",
        # Local frontend
        "localhost:3000",
        "localhost:3001",
        "localhost:3002",
        # Windows machine hostname (Uvicorn binds to 0.0.0.0)
        "FASHIONISTAR",
        "fashionistar",
        # ngrok tunnel — required for Playwright E2E tests and manual QA via tunnel
        "hydrographically-tawdrier-hayley.ngrok-free.dev",
        "aeration-scabby-navy.ngrok-free.dev",
        ".ngrok-free.dev",  # wildcard for any future ngrok tunnel restarts
        ".ngrok.io",
    ],
)

FRONTEND_URL = env("FRONTEND_URL", default="http://localhost:3000")
BACKEND_URL = env("BACKEND_URL", default="http://localhost:8001")
FRONTEND_TUNNEL_URL = env(
    "FRONTEND_TUNNEL_URL", default="https://aeration-scabby-navy.ngrok-free.dev"
)
BACKEND_TUNNEL_URL = env(
    "BACKEND_TUNNEL_URL",
    default="https://hydrographically-tawdrier-hayley.ngrok-free.dev",
)

DEFAULT_FRONTEND_ORIGINS = build_origin_list(
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:3001",
    "http://127.0.0.1:3001",
    "http://localhost:3002",
    "http://127.0.0.1:3002",
    FRONTEND_URL,
    FRONTEND_TUNNEL_URL,
)

CSRF_TRUSTED_ORIGINS = env.list(
    "CSRF_TRUSTED_ORIGINS",
    default=DEFAULT_FRONTEND_ORIGINS,
)

SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin-allow-popups"

# Admin URL (secret to prevent enumeration)
DJANGO_SECRET_ADMIN_URL = env("DJANGO_SECRET_ADMIN_URL", default="admin/")


# =============================================================================
# INSTALLED APPS
# =============================================================================
INSTALLED_APPS = [
    # ── Backend core (AppConfig fixes Python 3.12+ logging QueueListener) ────
    "backend.apps.BackendConfig",
    # ── Admin UI ─────────────────────────────────────────────────────────────
    "jazzmin",
    "drf_yasg",
    "drf_spectacular",
    # ── Django Core ──────────────────────────────────────────────────────────
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    # Whitenoise MUST be before staticfiles
    "whitenoise.runserver_nostatic",
    "django.contrib.staticfiles",
    "django.contrib.postgres",          # SearchVectorField, GinIndex, full-text search
    # ── Fashionistar New Architecture ────────────────────────────────────────
    "apps.common",
    "apps.authentication",
    "apps.audit_logs",  # Enterprise audit log — AuditEventLog
    "apps.client",      # Phase 2: Client domain (profiles, addresses)
    "apps.vendor",      # Phase 2: Vendor domain (stores, setup, payouts)
    "apps.transactions",  # Financial ledger, commissions, disputes, audit trail
    "apps.wallet",        # Role wallets, escrow, PINs, company wallet
        "apps.payment",       # Paystack/provider intents and webhooks
        # ── Modular admin backend migrated into apps/ ───────────────────────────
        "apps.admin_backend",
        "apps.providers",     # Phase 7: Unified provider registry (Email, SMS, KYC circuit breaker)
        "apps.global_platform_settings",   # Phase 9: Global admin-configurable platform settings (standalone app)
        "apps.catalog",       # Canonical public commerce metadata facade
        "apps.product",       # Phase 4: Product catalogue, variants, inventory, reviews
        "apps.order",          # Phase 4: Order lifecycle, status machine, escrow trigger
        "apps.notification",   # Phase 4: In-app, email, push, SMS notification feed
        "apps.measurements",   # Phase 4: Body measurements, checkout gate for custom tailoring
        "apps.ai",             # Phase 6: AI Orchestration Engine — measurement, recommendation, analytics
        "apps.chat",           # Phase 5 (P1): Buyer-Vendor real-time messaging, offers, moderation
        "apps.support",        # Phase 5 (P2): Customer dispute & ticket management domain
        "apps.kyc",            # Phase 6: Identity verification (KYC) domain
        "apps.custom_order",   # Phase 7: Bespoke commission (Custom Order) domain
        "apps.search",         # Search domain (hybrid FTS + semantic)
        "apps.scheduler",      # Task scheduler and time-based runner
        "apps.devops",         # DevOps environment control and health monitoring
        "apps.chatbot",        # Chatbot system for customer / vendor style and support
        "apps.integrations",   # Unified third-party API integration and webhook manager
        "apps.app_standards",  # Standard abstract base models and orchestrator cores
        "apps.analytics",      # System and business metrics telemetry and alerting
        "apps.agent_tools",    # Agent developer tools (generation, progress, validation)
        # ── Third Party ──────────────────────────────────────────────────────────
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",  # JWT logout blacklisting
    "corsheaders",
    "import_export",
    "anymail",
    "storages",
    "auditlog",
    "phone_verify",
    "channels",
    "django_filters",
    "phonenumber_field",
    "django_redis",
    "django_celery_beat",
    "cloudinary",
    "cloudinary_storage",
    # ── Django Control Room ──────────────────────────────────────────────────
    "dj_control_room_base",
    "dj_redis_panel",
    "dj_cache_panel",
    "dj_urls_panel",
    "dj_celery_panel",
    "dj_signals_panel",
    "dj_control_room",
]


# =============================================================================
# MIDDLEWARE
# =============================================================================
#
# ASGI-FIRST ORDERING STRATEGY — <30ms latency design
# ======================================================
# Django processes middleware in order on REQUEST (top-down) and in REVERSE
# order on RESPONSE (bottom-up). Under Uvicorn/Daphne ASGI:
#
#   ──────────────────────────────────────────────────────────────────────
#   RULE 1: Middleware with async def __acall__ runs natively in the asyncio
#           event loop — ZERO thread switching overhead.
#   RULE 2: Sync middleware (no __acall__) forces Django ASGI to spin up a
#           thread from the sync thread pool for EACH request — adds ~0.5ms
#           per sync middleware crossing under load.
#   RULE 3: Custom async middleware MUST come BEFORE Django core sync
#           middleware so ASGI requests reach Ninja views without first being
#           routed through the sync thread pool.
#   RULE 4: SecurityMiddleware is kept in its standard position (after our
#           async layer). Moving it before CorsMiddleware breaks preflight
#           CORS headers on OPTIONS requests. The OWASP headers it adds are
#           critical enough to accept one sync crossing.
#   RULE 5: WhiteNoiseMiddleware must be immediately after SecurityMiddleware
#           (serves /static/ with no-op for API paths).
#
# RATIONALE:
#   For Django-Ninja async views under Uvicorn:
#     - Request hits RequestIDMiddleware (async, 0ms overhead)
#     - Timing starts, CORS validated (async)
#     - Audit context injected (ContextVar, async)
#     - Idempotency key checked (Redis SETNX via Lua, async)
#     - Django ASGI adapter then handles the view WITHOUT sync crossing
#     - Ninja's async router dispatches to aget_* selectors (pure async)
#   Total ASGI overhead before hitting a Ninja view: ~1-2ms at 100k RPS.
#
MIDDLEWARE = [
    # ══ TIER 1: Fashionistar Async Middleware (async __acall__ ✓) ══════════════
    # These middleware run natively in the asyncio event loop under Uvicorn.
    # No thread switching — pure coroutine overhead only.
    #
    # 1. Request ID injection (async __acall__ ✓)
    #    Injects X-Request-ID UUID into every request FIRST so all downstream
    #    middleware and views have access to the correlation ID for logging.
    "apps.common.middleware.RequestIDMiddleware",
    #
    # 2. Request timing (async __acall__ ✓)
    #    Starts the high-resolution timer immediately after Request ID is set.
    #    Writes X-Response-Time header on every response (used by Datadog APM).
    "apps.common.middleware.RequestTimingMiddleware",
    #
    # 3. CORS (django-cors-headers implements async ASGI __acall__ ✓)
    #    Must come BEFORE Django's SessionMiddleware — CORS preflight returns
    #    early (200/204) before session is evaluated. Placed here so preflight
    #    short-circuits ALL downstream middleware at zero cost.
    "corsheaders.middleware.CorsMiddleware",
    #
    # 4. Security audit (async __acall__ ✓)
    #    Captures IP, User-Agent, method, URL, role for SIEM logs.
    #    Pure CPU: no I/O, no Redis. Must run AFTER RequestIDMiddleware
    #    (needs request.request_id) and BEFORE AuditContextMiddleware
    #    (AuditContext reads from request.security_audit_data).
    "apps.common.middleware.SecurityAuditMiddleware",
    #
    # 5. Audit context — ContextVar-based (async __acall__ ✓)
    #    Binds IP/UA/actor into a ContextVar for AuditService.log() calls.
    #    MUST remain AFTER SecurityAuditMiddleware (depends on request.request_id)
    #    and BEFORE IdempotencyMiddleware (idempotency task inherits audit ctx).
    "apps.audit_logs.middleware.AuditContextMiddleware",
    #
    # 6. Idempotency — Redis Lua SETNX (async __acall__ ✓)
    #    Exactly-once POST semantics. Checks X-Idempotency-Key in Redis via
    #    Lua EVALSHA atomic script (prevents race under 100k RPS).
    #    Returns cached 2xx or 409 for duplicate requests BEFORE any view runs.
    #    Placed BEFORE Django’s session+auth middleware: replayed responses
    #    must not re-authenticate or re-run business logic.
    "apps.authentication.middleware.idempotency.IdempotencyMiddleware",
    #
    # ══ TIER 2: Django Core Middleware (sync, ASGI adapter wraps each) ═════════
    # These are Django’s built-in sync middleware. Under Uvicorn ASGI they are
    # wrapped by Django’s SyncToAsync shim — each adds one thread-pool crossing
    # for sync requests. Ninja async views bypass most of them via short-circuit.
    #
    # 7. Django SecurityMiddleware (sync — must stay in position per Django docs)
    #    Adds HSTS, SSL redirect, MIME sniff protection, XSS filter headers.
    #    OWASP A05 / A02. Do NOT move this above CorsMiddleware — it breaks
    #    HTTPS redirect on preflight OPTIONS requests.
    "django.middleware.security.SecurityMiddleware",
    # Whitenoise Middleware - serves static files in production.
    # Should be placed right after the security middleware.
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "apps.chatbot.middleware.rate_limiting.ChatbotRateLimitMiddleware",
    "apps.chatbot.middleware.rate_limiting.ChatbotSecurityMiddleware",
]

ROOT_URLCONF = "backend.urls"


# =============================================================================
# TEMPLATES
# =============================================================================
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "backend.wsgi.application"
ASGI_APPLICATION = "backend.asgi.application"


# =============================================================================
# DATABASE
# =============================================================================
# Defaults to SQLite for local dev if DATABASE_URL not set in .env.
# Production uses PostgreSQL via DATABASE_URL.
DATABASES = {
    "default": dj_database_url.config(
        default=env("DATABASE_URL", default="sqlite:///db.sqlite3"),
        conn_max_age=600,
        ssl_require=False,
    )
}
DATABASES["default"]["DISABLE_SERVER_SIDE_CURSORS"] = True

# PostgreSQL connection resilience.
# Managed poolers (Neon, pgBouncer) silently close idle connections, which
# surfaces as "SSL connection has been closed unexpectedly" on the next query
# when Django reuses a stale persistent connection (conn_max_age > 0).
# CONN_HEALTH_CHECKS makes Django validate a pooled connection at the start of
# each request and transparently reconnect if the server dropped it. TCP
# keepalives keep the socket alive across the pooler between requests.
if "postgresql" in DATABASES["default"]["ENGINE"]:
    DATABASES["default"]["CONN_HEALTH_CHECKS"] = True
    _pg_options = DATABASES["default"].setdefault("OPTIONS", {})
    _pg_options.setdefault("keepalives", 1)
    _pg_options.setdefault("keepalives_idle", 30)
    _pg_options.setdefault("keepalives_interval", 10)
    _pg_options.setdefault("keepalives_count", 5)

# SQLite-specific options (ignored for PostgreSQL)
if "sqlite" in DATABASES["default"]["ENGINE"]:
    DATABASES["default"].setdefault("OPTIONS", {})["timeout"] = 20


# =============================================================================
# AUTHENTICATION
# =============================================================================
# ─────────────────────────────────────────────────────────────────────────────
# AUTH_USER_MODEL Migration — Phase 3 (March 2026)
# UnifiedUser is now the SINGLE source of truth for all authentication.
# Legacy `userauths.User` remains in the codebase for reference ONLY.
# All Django auth machinery (admin, JWT, permissions, groups) now uses
# `authentication.UnifiedUser` exclusively.
# ─────────────────────────────────────────────────────────────────────────────
AUTH_USER_MODEL = "authentication.UnifiedUser"

AUTHENTICATION_BACKENDS = [
    # UnifiedUserBackend handles email + phone + Google OAuth
    "apps.authentication.backends.UnifiedUserBackend",
    # SoftDeleteAwareModelBackend — catches SoftDeletedUserError from
    # get_by_natural_key() so Django admin login shows a form validation
    # error instead of a 500 crash. Drop-in replacement for ModelBackend.
    "apps.authentication.backends.SoftDeleteAwareModelBackend",
]

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
    "django.contrib.auth.hashers.BCryptSHA256PasswordHasher",
    "django.contrib.auth.hashers.ScryptPasswordHasher",
]

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 8},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]


# =============================================================================
# INTERNATIONALISATION
# =============================================================================
LANGUAGE_CODE = "en-us"
# Consider 'Africa/Lagos' if that's your primary timezone for consistency with Celery
TIME_ZONE = "Africa/Lagos"  # Can be 'Africa/Lagos' or 'UTC'
USE_I18N = True
USE_TZ = True


# =============================================================================
# STATIC & MEDIA FILES
# =============================================================================
STATIC_URL = "/static/"
STATIC_ROOT = os.path.join(BASE_DIR, "staticfiles")
STATICFILES_DIRS = [os.path.join(BASE_DIR, "static")]

MEDIA_URL = "/media/"
MEDIA_ROOT = os.path.join(BASE_DIR, "media")


# Cloudinary Configuration — SDK-level only (NOT used as Django storage backend)
# The media storage backend is FileSystemStorage. Cloudinary is used via
# apps.common.utils.cloudinary — direct uploads from client using presigned tokens.
CLOUDINARY_STORAGE = {
    "CLOUD_NAME": env("CLOUDINARY_CLOUD_NAME", default="your_cloud_name"),
    "API_KEY": env("CLOUDINARY_API_KEY", default="your_api_key"),
    "API_SECRET": env("CLOUDINARY_API_SECRET", default="your_api_secret"),
    "SECURE": True,  # Always HTTPS
}

# Webhook callback URL for Cloudinary upload/eager notifications.
# Must be a publicly-reachable HTTPS URL (e.g. ngrok in dev).
# Set BACKEND_URL in .env to the public base (e.g. https://your-ngrok.ngrok-free.dev)
CLOUDINARY_NOTIFICATION_URL = env(
    "CLOUDINARY_NOTIFICATION_URL",
    default="",
)

# Upload presets — configure these in your Cloudinary Dashboard
# (Settings → Upload → Upload presets → Add upload preset)
CLOUDINARY_UPLOAD_PRESET_AVATAR = env(
    "CLOUDINARY_UPLOAD_PRESET_AVATAR", default="fashionistar_avatars"
)
CLOUDINARY_UPLOAD_PRESET_PRODUCT = env(
    "CLOUDINARY_UPLOAD_PRESET_PRODUCT", default="fashionistar_products"
)
CLOUDINARY_UPLOAD_PRESET_MEASURE = env(
    "CLOUDINARY_UPLOAD_PRESET_MEASURE", default="fashionistar_measurements"
)
CLOUDINARY_UPLOAD_PRESET_VIDEO = env(
    "CLOUDINARY_UPLOAD_PRESET_VIDEO", default="fashionistar_videos"
)

# Presigned upload token TTL in seconds (cached in Redis).
# Must be ≤ 3600 (Cloudinary 1-hour max). We use 3300 (55 min) for safety.
CLOUDINARY_SIGNATURE_TTL = int(env("CLOUDINARY_SIGNATURE_TTL", default=3300))


CLOUDINARY_ADMIN_ASYNC = True   # Enable async Celery path (production)
#CLOUDINARY_ADMIN_ASYNC = False  # Sync inline path (dev default)

# =============================================================================
# AI & EXTERNAL INTEGRATIONS
# =============================================================================

# ── Ollama Self-Hosted LLM Configuration ──────────────────────────────────────
OLLAMA_ENABLED = env.bool("OLLAMA_ENABLED", default=True)
OLLAMA_HOST = env("OLLAMA_HOST", default="http://localhost:11434")
OLLAMA_MODEL = env("OLLAMA_MODEL", default="llama3.2:3b")
OLLAMA_EMBED_MODEL = env("OLLAMA_EMBED_MODEL", default="nomic-embed-text")

# ── OpenAI & Self-Hosted compatibility Configuration ──────────────────────────
OPENAI_API_KEY = env("OPENAI_API_KEY", default="")
OPENAI_API_BASE_URL = env("OPENAI_API_BASE_URL", default="http://localhost:11434/v1")
OPENAI_DEFAULT_MODEL = env("OPENAI_DEFAULT_MODEL", default="llama3.2:3b")
OPENAI_MAX_TOKENS = env.int("OPENAI_MAX_TOKENS", default=2000)
OPENAI_TEMPERATURE = env.float("OPENAI_TEMPERATURE", default=0.7)

# ── OpenRouter & Groq Integration Configurations ──────────────────────────────
OPENROUTER_API_KEY = env("OPENROUTER_API_KEY", default="")
OPENROUTER_BASE_URL = env("OPENROUTER_BASE_URL", default="https://openrouter.ai/api/v1")
GROQ_API_KEY = env("GROQ_API_KEY", default="")

# ── Termii SMS Integration Configuration ──────────────────────────────────────
TERMII_API_KEY = env("TERMII_API_KEY", default="")
TERMII_SENDER_ID = env("TERMII_SENDER_ID", default="Fashionistar")

# ── Kudi SMS Integration Configuration ──────────────────────────────────────
KUDI_API_KEY = env("KUDI_API_KEY", default="")
KUDI_SENDER_ID = env("KUDI_SENDER_ID", default="fashionistar")

# ── Integrations Settings ────────────────────────────────────────────────────
INTEGRATION_ENVIRONMENT = env("INTEGRATION_ENVIRONMENT", default="production")
CREDENTIAL_ENCRYPTION_KEY = env("CREDENTIAL_ENCRYPTION_KEY", default="bxc5%hug9u6twumy*utz#y=wcz!bs@4j")





STORAGES = {
    "default": {
        "BACKEND": "cloudinary_storage.storage.MediaCloudinaryStorage",
    },
    "staticfiles": {
        # Overridden in production.py to CompressedManifestStaticFilesStorage
        # Whitenoise for static files in production, default for dev.
        "BACKEND": (
            "whitenoise.storage.CompressedManifestStaticFilesStorage"
            if not DEBUG
            else "django.contrib.staticfiles.storage.StaticFilesStorage"
        ),
    },
}

WHITENOISE_MANIFEST_STRICT = False

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# =============================================================================
# CACHING (Redis)
# =============================================================================

def _sanitize_redis_url(url: str) -> str:
    if not url or not url.startswith("rediss://"):
        return url
    if "ssl_cert_reqs" not in url:
        separator = "&" if "?" in url else "?"
        url = f"{url}{separator}ssl_cert_reqs=none"
    return url



def change_redis_db(url: str, db_num: int) -> str:
    """Updates the Redis database index (e.g. /0 to /1) while keeping query params."""
    if not url:
        return url
    parts = url.split("?", 1)
    base_part = parts[0]
    query_part = f"?{parts[1]}" if len(parts) > 1 else ""
    
    scheme_separator = "://"
    if scheme_separator in base_part:
        scheme, remainder = base_part.split(scheme_separator, 1)
        if "/" in remainder:
            host_port, db = remainder.rsplit("/", 1)
            new_remainder = f"{host_port}/{db_num}"
        else:
            new_remainder = f"{remainder}/{db_num}"
        base_part = f"{scheme}{scheme_separator}{new_remainder}"
    return f"{base_part}{query_part}"


# Single-source normalized Redis base URL (default DB 0)
_RAW_REDIS_URL = env("REDIS_URL", default="redis://127.0.0.1:6379/0")
REDIS_URL = _sanitize_redis_url(_RAW_REDIS_URL)


# Configure Django's CACHES
# - 'default': Redis (sessions, throttling, app-level caching)
# - 'schema':  LocMemCache — OpenAPI/Swagger schema caching (drf-yasg)
#              Uses in-process memory so Redis unavailability NEVER causes
#              a 500 on GET / (the Swagger UI homepage).
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": REDIS_URL,
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
            # Silently return None on cache misses when Redis is unreachable.
            # Prevents Redis outages from propagating as 500 errors to users.
            "IGNORE_EXCEPTIONS": True,
            "CONNECTION_POOL_KWARGS": {
                # Default pool is 10 connections — exhausted under load.
                # 50 connections prevents pool-wait latency spikes.
                "max_connections": 50,
                "decode_responses": False,  # bytes mode for maximum speed
            },
            # CRITICAL: Without timeouts, a Redis hiccup causes 30-second
            # hangs. 500ms fail-fast is the industry standard for low-latency
            # APIs (Netflix, Stripe, Shopify all use ≤500ms Redis timeouts).
            "SOCKET_TIMEOUT": 0.5,  # seconds — receive timeout
            "SOCKET_CONNECT_TIMEOUT": 0.5,  # seconds — connection timeout
        },
    },
    # ── Schema cache: LocMemCache (no Redis dependency) ──────────────────
    # Used by drf-yasg schema_view via cache_page('schema') decorator.
    # Falls back to per-process memory — always available regardless of
    # whether Redis is running.
    "schema": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "fashionistar-schema-cache",
    },
    # ── Idempotency cache: Redis DB 1 (dedicated namespace) ──────────────
    # Stores X-Idempotency-Key responses for exactly-once POST semantics.
    # Separate from 'default' (DB 0) to allow per-alias override in tests
    # without affecting session/throttle caches.
    # In tests: overridden to LocMemCache via @override_settings(CACHES=...).
    "idempotency": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": change_redis_db(REDIS_URL, 1),
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
            "IGNORE_EXCEPTIONS": True,
            "SOCKET_TIMEOUT": 1.0,
            "SOCKET_CONNECT_TIMEOUT": 1.0,
        },
        "TIMEOUT": 60 * 60 * 24,  # 24h default TTL for idempotency responses
    },
}


# =============================================================================
# CHANNELS (WebSocket / Real-time)
# =============================================================================
#
# Resilience strategy:
#   • socket_connect_timeout — fail-fast when Redis is unreachable.
#     Without this, channels_redis hangs for ≥30s (TCP SYN timeout) blocking
#     the asyncio event loop and cascading into uvicorn worker exhaustion.
#   • socket_timeout — fail-fast on stalled reads/writes after a connection
#     is established (e.g. Redis GC pause, network brownout).
#   • capacity / group_expiry — bound memory and avoid stale group entries
#     after client disconnects that don't cleanly unsubscribe.
#
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [
                {
                    "address": REDIS_URL,
                    # Fail-fast timeouts (seconds) — critical for Cloud Run + VPC Redis.
                    # A missing/misconfigured REDIS_URL would otherwise stall all WS
                    # connects for the full TCP timeout (~30s) blocking uvicorn workers.
                    "socket_connect_timeout": 2,
                    "socket_timeout": 30,
                }
            ],
            # Per-channel message buffer capacity (default: 100).
            # 500 handles bursts of real-time events without dropping messages.
            "capacity": 500,
            # Group membership expiry in seconds (default: 86400 = 24h).
            # 3600 (1h) prevents ghost group entries from stale connections.
            "group_expiry": 3600,
            # Symmetric encryption off for internal VPC traffic — avoids the
            # ~0.5ms per-message overhead on high-throughput notification streams.
            # Enable when channels_redis version supports it and inter-node
            # traffic crosses a public network segment.
            # "symmetric_encryption_keys": [],
        },
    },
}


# =============================================================================
# REST FRAMEWORK — Enterprise Configuration
# =============================================================================
REST_FRAMEWORK = {
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    # ── Permissions ────────────────────────────────────────────────────────
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    # ── Authentication ─────────────────────────────────────────────────────
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
        "rest_framework.authentication.TokenAuthentication",
        "rest_framework.authentication.SessionAuthentication",
        "rest_framework.authentication.BasicAuthentication",
    ),
    # ── Rendering — Fashionistar standard envelope ─────────────────────────
    # FashionistarRenderer wraps every response in {success, message, data}.
    # BrowsableAPIRenderer kept for local development (removed in production).
    "DEFAULT_RENDERER_CLASSES": [
        "apps.common.renderers.FashionistarRenderer",
        "rest_framework.renderers.BrowsableAPIRenderer",
    ],
    # ── Parsers ────────────────────────────────────────────────────────────
    "DEFAULT_PARSER_CLASSES": [
        "rest_framework.parsers.JSONParser",
        "rest_framework.parsers.FormParser",
        "rest_framework.parsers.MultiPartParser",
    ],
    # ── Rate Limiting (Fashionistar tiered throttle classes) ───────────────
    # Burst + sustained throttles applied per request.
    # Override individual rates via THROTTLE_RATES dict in this file.
    "DEFAULT_THROTTLE_CLASSES": [
        "apps.common.throttling.AnonBurstThrottle",
        "apps.common.throttling.AnonSustainedThrottle",
        "apps.common.throttling.UserBurstThrottle",
        "apps.common.throttling.UserSustainedThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        # Mapped by scope in apps.common.throttling
        "anon_burst": "30/minute",
        "anon_day": "500/day",
        "user_burst": "120/minute",
        "user_day": "5000/day",
        "auth": "5/minute",
        "otp": "3/minute",
        "upload": "20/hour",
        "vendor": "200/minute",
        "client_chatbot": "60/minute",
        "vendor_chatbot": "100/minute",
    },
    # ── Pagination — Fashionistar standard envelope ─────────────────────────
    "DEFAULT_PAGINATION_CLASS": "apps.common.pagination.DefaultPagination",
    "PAGE_SIZE": 20,
    # ── Exception Handler — unified DRF + Django errors ────────────────────
    "EXCEPTION_HANDLER": "apps.common.exceptions.custom_exception_handler",
}


# =============================================================================
# SIMPLE JWT
# =============================================================================
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(hours=1),  # 1 hour for security
    "REFRESH_TOKEN_LIFETIME": timedelta(days=30),  # 30 days (not 50!)
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
    "ALGORITHM": "HS256",
    "VERIFYING_KEY": None,
    "AUDIENCE": None,
    "ISSUER": None,
    "JWK_URL": None,
    "LEEWAY": 0,
    "AUTH_HEADER_TYPES": ("Bearer",),
    "AUTH_HEADER_NAME": "HTTP_AUTHORIZATION",
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
    "USER_AUTHENTICATION_RULE": "rest_framework_simplejwt.authentication.default_user_authentication_rule",
    "AUTH_TOKEN_CLASSES": ("rest_framework_simplejwt.tokens.AccessToken",),
    "TOKEN_TYPE_CLAIM": "token_type",
    "TOKEN_USER_CLASS": "rest_framework_simplejwt.models.TokenUser",
    "JTI_CLAIM": "jti",
    "SLIDING_TOKEN_REFRESH_EXP_CLAIM": "refresh_exp",
    "SLIDING_TOKEN_LIFETIME": timedelta(minutes=5),
    "SLIDING_TOKEN_REFRESH_LIFETIME": timedelta(days=1),
}


# =============================================================================
# API DOCUMENTATION
# =============================================================================
SPECTACULAR_SETTINGS = {
    "TITLE": "Fashionistar API",
    "DESCRIPTION": (
        "Nigeria's Premier AI-Powered Fashion E-Commerce Platform API.\n\n"
        "**v1 (DRF/Sync):** Standard REST endpoints, WSGI-safe, Celery-backed.\n"
        "**v1 (Ninja/Async):** High-concurrency async endpoints, ASGI-native.\n\n"
        "**Authentication:** Bearer JWT (SimpleJWT). Get tokens via `/api/v1/auth/login/`.\n"
        "**Register first:** `POST /api/v1/auth/register/` → verify OTP → login."
    ),
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
    "SORT_OPERATIONS": True,
    # ── Security ────────────────────────────────────────────────────────────
    "SECURITY": [{"BearerAuth": []}],
    "SECURITY_DEFINITIONS": {
        "BearerAuth": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": "Enter your JWT access token prefixed with Bearer",
        },
    },
    # ── Schema Generation Robustness ────────────────────────────────────────
    # ENUM_GENERATE_CHOICE_DESCRIPTION prevents crashes on complex enum types
    "ENUM_GENERATE_CHOICE_DESCRIPTION": False,
    # Suppress non-fatal warnings from legacy app URL patterns
    "DISABLE_ERRORS_AND_WARNINGS": True,
    # Don't fail on warnings (legacy app URL collisions)
    "FAIL_ON_WARN": False,
    # Auto-handle operationId collisions (pluralise duplicates automatically)
    "OPERATION_ID": None,
    "SERVERS": [
        {"url": "http://127.0.0.1:8001", "description": "Development (ASGI/Uvicorn)"},
    ],
    # ── Filter: Only expose /api/v1/auth/ in schema ──────────────────────
}

SWAGGER_SETTINGS = {
    "DEFAULT_INFO": "backend.urls.api_info",
    "USE_SESSION_AUTH": True,
    "relative_paths": False,
    "DISPLAY_OPERATION_ID": False,
    "SECURITY_DEFINITIONS": {
        "Bearer": {"type": "apiKey", "name": "Authorization", "in": "header"},
    },
}


# =============================================================================
# CORS
# =============================================================================
CORS_ALLOW_ALL_ORIGINS = False
CORS_ALLOWED_ORIGINS = env.list(
    "CORS_ALLOWED_ORIGINS",
    default=DEFAULT_FRONTEND_ORIGINS,
)
if "*" in CORS_ALLOWED_ORIGINS:
    CORS_ALLOW_ALL_ORIGINS = True
    CORS_ALLOWED_ORIGINS = []

CORS_ALLOW_HEADERS = [
    "accept",
    "accept-encoding",
    "authorization",
    "content-type",
    "content-disposition",
    # ── Idempotency key — required for exactly-once POST semantics ──
    "x-idempotency-key",
    # ── Anonymous session identity — required for guest cart & wishlist reads ──
    # Without this header the CORS preflight (OPTIONS) returns 403 and the
    # Ninja async endpoints cannot identify anonymous shoppers.
    "x-fashionistar-session-key",
    # ── Wave B3 Audit Context Headers — client device/geo enrichment ───────
    # These headers are injected by fashionista_frontend/src/lib/api/axiosInstance.ts
    # (buildAuditHeadersSync) on every authenticated and anonymous request.
    # Without explicit CORS whitelist, the browser preflight BLOCKS the request.
    "x-device-id",           # UUID v4 — cross-session device correlation
    "x-client-timezone",     # IANA timezone — more accurate than IP-based geo
    "x-client-locale",       # navigator.language — fraud locale detection
    "x-client-platform",     # navigator.userAgentData.platform — UA enrichment
    "x-client-geo-lat",      # GPS latitude (optional — geolocation permission)
    "x-client-geo-lng",      # GPS longitude (optional)
    "x-client-geo-accuracy", # GPS accuracy in metres (optional)
    "dnt",
    "origin",
    "user-agent",
    "x-csrftoken",
    "x-requested-with",
    "access-control-allow-origin",
    "ngrok-skip-browser-warning",  # Allow frontend dev to bypass ngrok warning page
]

CORS_ALLOW_METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS")

# Required for HttpOnly refresh-token cookie to be sent on cross-origin requests.
# Without this the browser strips the cookie from every CORS preflight.
CORS_ALLOW_CREDENTIALS = True

# Refresh-token HttpOnly cookie name + lifetime (used by LoginView / VerifyOTPView).
# Name is intentionally generic to reduce attacker reconnaissance.
REFRESH_TOKEN_COOKIE_NAME    = "fashionistar_rt"
REFRESH_TOKEN_COOKIE_MAX_AGE = 60 * 60 * 24 * 30   # 30 days — mirrors SIMPLE_JWT lifetime


# =============================================================================
# PAYSTACK
# =============================================================================
PAYSTACK_TEST_KEY = env("PAYSTACK_TEST_KEY", default="sk_test_placeholder")
PAYSTACK_SECRET_KEY = env("PAYSTACK_SECRET_KEY", default="sk_test_placeholder")


# =============================================================================
# PHONE NUMBERS
# =============================================================================
PHONENUMBER_DB_FORMAT = "INTERNATIONAL"
PHONENUMBER_DEFAULT_REGION = "NG"
PHONENUMBER_DEFAULT_FORMAT = "INTERNATIONAL"

TWILIO_ACCOUNT_SID = config("TWILIO_ACCOUNT_SID", default="AC_PLACEHOLDER_SID")
TWILIO_AUTH_TOKEN = config("TWILIO_AUTH_TOKEN", default="PLACEHOLDER_AUTH_TOKEN")
TWILIO_PHONE_NUMBER = config("TWILIO_PHONE_NUMBER", default="+15005550006")

PHONE_VERIFICATION = {
    "BACKEND": "phone_verify.backends.twilio.TwilioBackend",
    "OPTIONS": {
        "SID": env("TWILIO_ACCOUNT_SID", default="fake"),
        "SECRET": env("TWILIO_AUTH_TOKEN", default="fake"),
        "FROM": env("TWILIO_PHONE_NUMBER", default="+14755292729"),
    },
    "TOKEN_LENGTH": 6,
    "MESSAGE": "Fashionistar verification code: {security_code}",
    "APP_NAME": "Fashionistar",
    "SECURITY_CODE_EXPIRATION_TIME": 300,  # 5 minutes
    "VERIFY_SECURITY_CODE_ONLY_ONCE": True,
}


# =============================================================================
# EMAIL
# =============================================================================
# Priority:
#   1. Resend API (if RESEND_API_KEY set)          → anymail.backends.resend
#   2. Gmail SMTP (if EMAIL_HOST_PASSWORD set)     → smtp.EmailBackend
#   3. Console (fallback, safe for dev/test)       → console.EmailBackend
#
# HF Spaces BLOCKS port 587/465 (SMTP is unreliable on containers).
# Resend API (HTTP-based) works reliably on HF Spaces with no port restrictions.
# =============================================================================

DEFAULT_FROM_EMAIL = config("DEFAULT_FROM_EMAIL", default="noreply@fashionistar.net")
SERVER_EMAIL       = config("DEFAULT_FROM_EMAIL", default="noreply@fashionistar.net")

# Gmail SMTP (fallback when Resend not configured)
EMAIL_HOST          = "smtp.gmail.com"
EMAIL_HOST_USER     = config("EMAIL_HOST_USER",     default="fashionistar.home.beauty@gmail.com")
EMAIL_HOST_PASSWORD = config("EMAIL_HOST_PASSWORD", default="")
EMAIL_PORT          = 465
EMAIL_USE_TLS       = False
EMAIL_USE_SSL       = True

# Resend API key (set this to enable Resend backend — preferred for HF Spaces)
_RESEND_API_KEY   = env("RESEND_API_KEY",   default="")
_MAILGUN_API_KEY  = env("MAILGUN_API_KEY",  default="")

# Auto-select best available email backend
if _RESEND_API_KEY:
    # ✅ Best: Resend API (HTTP, no port restrictions, 3,000 emails/mo free)
    EMAIL_BACKEND = "anymail.backends.resend.EmailBackend"
    ANYMAIL = {
        "RESEND_API_KEY": _RESEND_API_KEY,
    }
elif _MAILGUN_API_KEY:
    # ✅ Fallback: Mailgun (HTTP API, also works on HF Spaces)
    EMAIL_BACKEND = "anymail.backends.mailgun.EmailBackend"
    ANYMAIL = {
        "MAILGUN_API_KEY":      _MAILGUN_API_KEY,
        "MAILGUN_SENDER_DOMAIN": env("MAILGUN_DOMAIN", default=""),
    }
else:
    # ⚠️  Fallback: SMTP (may fail on HF Spaces; works in local dev)
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    ANYMAIL = {}

# Zoho ZeptoMail (optional — used by DatabaseConfiguredEmailBackend)
ZOHO_ZEPTOMAIL_API_KEY_TOKEN = env("ZOHO_ZEPTOMAIL_API_KEY_TOKEN", default="")
ZOHO_ZEPTOMAIL_HOSTED_REGION = env(
    "ZOHO_ZEPTOMAIL_HOSTED_REGION", default="zeptomail.zoho.com"
)

# =============================================================================
# AI / LLM ENGINE — Multi-Provider Settings
# =============================================================================
# Priority waterfall (see apps/ai/engines/llm_engine.py get_llm_engine()):
#   1. SambaNova  — Llama-4 Maverick/Scout on RDU chips. ~4000 tok/s. Free $5 credit.
#   2. Cerebras   — Llama-3.3-70B on WSE-3 chips. ~2000 tok/s. 1M tokens/day free.
#   3. Groq       — Llama-3.3-70B on LPU chips.   ~300  tok/s. 14,400 req/day free.
#   4. Ollama     — Local self-hosted (dev only).   CPU/GPU. Zero cost, no rate limit.
# =============================================================================

# SambaNova Cloud (Fastest for large models: Llama-4 Maverick)
# Get key: https://cloud.sambanova.ai/apis
SAMBANOVA_API_KEY = env("SAMBANOVA_API_KEY", default="")
SAMBANOVA_MODEL   = env("SAMBANOVA_MODEL",   default="Meta-Llama-3.3-70B-Instruct")
SAMBANOVA_ENABLED = bool(SAMBANOVA_API_KEY)

# Cerebras Cloud (Highest token throughput: 2000+ tok/s, 1M tok/day free)
# Get key: https://cloud.cerebras.ai/
CEREBRAS_API_KEY = env("CEREBRAS_API_KEY", default="")
CEREBRAS_MODEL   = env("CEREBRAS_MODEL",   default="llama-3.3-70b")
CEREBRAS_ENABLED = bool(CEREBRAS_API_KEY)

# Groq Cloud (Ultra-low latency: <200ms, 14,400 req/day free)
# Get key: https://console.groq.com/keys
GROQ_API_KEY = env("GROQ_API_KEY", default="")
GROQ_MODEL   = env("GROQ_MODEL",   default="llama-3.3-70b-versatile")
GROQ_ENABLED = bool(GROQ_API_KEY)

# Ollama (local dev, self-hosted — fallback of last resort)
OLLAMA_HOST       = env("OLLAMA_HOST",       default="http://localhost:11434")
OLLAMA_MODEL      = env("OLLAMA_MODEL",      default="llama3.2:3b")
OLLAMA_EMBED_MODEL = env("OLLAMA_EMBED_MODEL", default="nomic-embed-text")
OLLAMA_ENABLED    = env.bool("OLLAMA_ENABLED", default=True)

# =============================================================================
# MEASUREMENT ENGINE — Quality & Versioning Settings
# =============================================================================
# Rec 7 — Confidence Threshold
#   Minimum MediaPipe pose confidence to accept a body scan as valid.
#   Results below this threshold return HTTP 422 with a user-friendly message.
#   Tune between 0.55 (permissive) and 0.80 (strict) based on observed quality.
MEASUREMENT_MIN_CONFIDENCE = env.float("MEASUREMENT_MIN_CONFIDENCE", default=0.65)

# Rec 6 — AI Engine Version Tracking
#   Stored on each MeasurementProfile row for:
#     - A/B testing between engine versions
#     - Easy invalidation when the pose model is upgraded
#     - Production quality auditing over time
#   Format: "<major>.<minor>.<patch>-<provider>" e.g. "3.0.0-zerogpu"
AI_ENGINE_VERSION = env("AI_ENGINE_VERSION", default="3.0.0-zerogpu")


# =============================================================================
# CELERY — Base Settings (Broker / Serialiser / Reliability Flags)
# =============================================================================
# Queue definitions, task routes, and beat schedule live in backend/celery.py
# (the Celery application module). Only the environment-driven connection
# settings and Django-namespace flags are configured here.
#
# Architecture Pattern:
#   backend/celery.py   ← Queue topology, task routes, beat schedule  ← YOU
#   backend/config/base.py ← Broker URL, serialiser, reliability flags ← THIS FILE

REDIS_URL = _sanitize_redis_url(env("REDIS_URL", default="redis://127.0.0.1:6379/1"))

CELERY_BROKER_URL = _sanitize_redis_url(env("CELERY_BROKER_URL", default=REDIS_URL))
CELERY_RESULT_BACKEND = _sanitize_redis_url(env("CELERY_RESULT_BACKEND", default=REDIS_URL))

if CELERY_BROKER_URL.startswith("rediss://"):
    CELERY_BROKER_USE_SSL = {
        "ssl_cert_reqs": "none"
    }

if CELERY_RESULT_BACKEND.startswith("rediss://"):
    CELERY_REDIS_BACKEND_USE_SSL = {
        "ssl_cert_reqs": "none"
    }

# Fast-fail for local Redis; use longer timeouts for cloud/TLS Redis (Aiven on HF Spaces)
# The TLS handshake from HF cross-region can take 2–5s, so we give a generous window.
_celery_is_cloud_redis = (
    CELERY_BROKER_URL.startswith("rediss://") and "aivencloud.com" in CELERY_BROKER_URL
)
CELERY_BROKER_TRANSPORT_OPTIONS = {
    "socket_connect_timeout": 10 if _celery_is_cloud_redis else 2,
    "socket_timeout": 30 if _celery_is_cloud_redis else 2,
    "socket_keepalive": True,
}
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True

CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TIMEZONE = "UTC"
CELERY_ENABLE_UTC = True
CELERY_WORKER_HIJACK_ROOT_LOGGER = False

# ── Reliability flags ─────────────────────────────────────────────────────
CELERY_WORKER_MAX_TASKS_PER_CHILD = (
    1000  # evict workers after 1K tasks for memory hygiene
)
CELERY_WORKER_PREFETCH_MULTIPLIER = 1  # one task at a time for fairness
CELERY_TASK_ACKS_LATE = True  # ack AFTER completion — guarantees at-least-once delivery
CELERY_TASK_REJECT_ON_WORKER_LOST = True  # requeue task if worker dies mid-execution
CELERY_TASK_IGNORE_RESULT = True  # no result storage overhead
CELERY_TASK_TRACK_STARTED = True  # track when tasks start (for monitoring)
CELERY_TASK_TIME_LIMIT = 300  # 5-min hard kill
CELERY_TASK_SOFT_TIME_LIMIT = 240  # 4-min SoftTimeLimitExceeded warning
CELERY_WORKER_SEND_TASK_EVENTS = True  # enable Flower monitoring
CELERY_TASK_SEND_SENT_EVENT = True  # track when tasks are sent

# CELERY_BROKER_TRANSPORT_OPTIONS = {
#     "visibility_timeout": 3600,         # 1hr task visibility
#     "socket_timeout": 30,               # network read timeout
#     "socket_connect_timeout": 30,       # initial connection timeout
#     "retry_on_timeout": True,
#     "max_connections": 20,              # limit connections
#     'socket_keepalive': True,
#     "ssl_cert_reqs": None, # Important for rediss schemes if not using full cert validation
# }


# Beat Scheduler (if you use periodic tasks)
# If using `django_celery_beat`, schedule via Admin UI, not hardcoded here.


CELERY_BEAT_SCHEDULE = {
    # ── Keep Render.com service awake (free-tier cold-start prevention) ────────
    "keep-render-service-awake": {
        "task": "keep_service_awake",  # matches @shared_task name
        "schedule": 60.0,  # every 1 minute
    },

    # ── NDPR/PCI-DSS Compliance: Audit log retention enforcement ──────────────
    # Deletes non-compliance AuditEventLog rows whose per-row retention_days
    # has elapsed. Compliance rows (is_compliance=True) are NEVER touched.
    # Runs daily at 02:00 UTC (04:00 WAT / Africa/Lagos) when load is minimal.
    "audit-log-cleanup": {
        "task": "audit_log_cleanup",
        "schedule": 86400.0,          # every 24 hours
        "options": {
            "expires": 3600,          # drop if worker is unavailable for 1h
            "queue": "celery",        # default queue
        },
    },
}




#                       =========================
# ----------------------CELERY CONFIGURATION ENDS HERE ------------------------------
#                       =========================


# =============================================================================
# AI ENGINE CONFIGURATION  (apps/ai — Phase 6)
# =============================================================================

# ── Ollama (Local LLM — self-hosted, no cloud cost) ───────────────────────────
# Production: set OLLAMA_BASE_URL to your VPS/server URL
# Local dev:  "http://localhost:11434" (default Ollama port)
OLLAMA_BASE_URL = env("OLLAMA_BASE_URL", default="http://localhost:11434")
OLLAMA_DEFAULT_MODEL = env("OLLAMA_DEFAULT_MODEL", default="llama3.2:3b")
OLLAMA_EMBED_MODEL  = env("OLLAMA_EMBED_MODEL",  default="nomic-embed-text")
OLLAMA_TIMEOUT_SECONDS = int(env("OLLAMA_TIMEOUT_SECONDS", default="30"))
OLLAMA_REQUEST_TIMEOUT = int(env("OLLAMA_REQUEST_TIMEOUT", default="120"))

# ── FashionSigLIP Recommendation Engine ───────────────────────────────────────
# Model: marqo/marqo-FashionSigLIP (from HuggingFace — apache 2.0 license)
# Embedding dimension: 512 (ViT-B-16 variant) or 768 (ViT-L-14 variant)
FASHION_CLIP_MODEL   = env("FASHION_CLIP_MODEL",   default="hf-hub:Marqo/marqo-fashionSigLIP")
FASHION_CLIP_PRETRAINED = env("FASHION_CLIP_PRETRAINED", default="")  # Empty = from HF hub
FASHION_CLIP_EMBEDDING_DIM = int(env("FASHION_CLIP_EMBEDDING_DIM", default="512"))

# ── pgvector (PostgreSQL vector extension) ────────────────────────────────────
# Enable pgvector for HNSW approximate nearest-neighbour search
# Requires: pip install django-pgvector
# DB migration: CREATE EXTENSION IF NOT EXISTS vector;
PGVECTOR_ENABLED = True
PGVECTOR_EMBEDDING_DIM = FASHION_CLIP_EMBEDDING_DIM   # Must match embedding model

# ── Measurement AI Engine ─────────────────────────────────────────────────────
# Minimum landmark visibility score to accept a pose as valid
AI_MEASUREMENT_MIN_VISIBILITY  = float(env("AI_MEASUREMENT_MIN_VISIBILITY", default="0.6"))
# Tolerance (±cm) for size-fit filtering in recommendations
AI_SIZE_FIT_TOLERANCE_CM       = float(env("AI_SIZE_FIT_TOLERANCE_CM", default="5.0"))

# ── AI Analytics ──────────────────────────────────────────────────────────────
# Max report cache TTL in seconds (default: 24 hours)
AI_ANALYTICS_CACHE_TTL = int(env("AI_ANALYTICS_CACHE_TTL", default="86400"))
# Recommendation cache TTL (default: 1 hour)
AI_RECOMMENDATION_CACHE_TTL = int(env("AI_RECOMMENDATION_CACHE_TTL", default="3600"))


# =============================================================================
# JAZZMIN Admin UI
# =============================================================================
JAZZMIN_SETTINGS = {
    "user_avatar": "avatar",
    "usermodel_field_mappings": {
        "userauths.User": "avatar",
    },
    "site_title": "FASHIONISTAR GLOBAL ADMIN",
    "site_header": "FASHIONISTAR GLOBAL ADMIN",
    "site_brand": "FASHIONISTAR GLOBAL ADMIN",
    "site_icon": "images/favicon.ico",
    "site_logo": "images/logos/logo.png",
    "welcome_sign": "Welcome to FASHIONISTAR Global Admin",
    "copyright": "© 2026 Fashionistar Ltd.",
    "topmenu_links": [
        {"name": "Dashboard", "url": "admin:index", "permissions": ["auth.view_user"]},
        {
            "name": "CORE COMMERCE",
            "url": "admin:product_product_changelist",
            "permissions": ["product.view_product"],
        },
        {
            "name": "FINANCIALS",
            "url": "admin:transactions_transaction_changelist",
            "permissions": ["transactions.view_transaction"],
        },
        {
            "name": "OPERATIONS",
            "url": "admin:order_order_changelist",
            "permissions": ["order.view_order"],
        },
        {
            "name": "USER MANAGEMENT",
            "url": "admin:authentication_unifieduser_changelist",
            "permissions": ["authentication.view_unifieduser"],
        },
        {
            "name": "AUDIT & PLATFORM",
            "url": "admin:audit_logs_auditeventlog_changelist",
            "permissions": ["audit_logs.view_auditeventlog"],
        },
        {"model": "authentication.UnifiedUser"},
    ],
    "show_sidebar": True,
    "navigation_expanded": True,
    # ── Sidebar app/model ordering ──────────────────────────────────────────
    "order_with_respect_to": [
        # Identity & Access
        "authentication",
        "authentication.unifieduser",
        "authentication.loginevent",
        "authentication.usersession",
        "authentication.biometriccredential",
        # Vendor
        "vendor",
        "vendor.vendorprofile",
        "vendor.vendorsetupstate",
        "vendor.vendorpayoutprofile",
        # Catalog
        "catalog",
        "catalog.category",
        "catalog.brand",
        "catalog.collections",
        "catalog.blogpost",
        "catalog.blogmedia",
        # Product
        "product",
        "product.product",
        "product.productvariant",
        "product.productgallerymedia",
        "product.productspecification",
        "product.productfaq",
        "product.productreview",
        "product.ProductSizeAndMeasurementGuide",
        "product.productcolor",
        "product.producttag",
        "product.productfabric",
        "product.productcertification",
        "product.productshippingprofile",
        "product.coupon",
        "product.deliverycourier",
        "product.productcommissionsnapshot",
        "product.productpricehistory",
        "product.productinventorylog",
        "product.productwishlist",
        "product.productviewlog",
        # Orders
        "order",
        "order.order",
        "order.cartorderitem",
        "order.orderstatushistory",
        "order.orderidempotencyrecord",
        "order.orderpaymentrecord",
        "order.ordercommercialtransitionlog",
        # Custom Orders
        "custom_order",
        "custom_order.customorder",
        "custom_order.customordermilestone",
        # KYC
        "kyc",
        "kyc.kycsubmission",
        "kyc.kycdocument",
        # Wallet & Finance
        "wallet",
        "wallet.wallet",
        "wallet.wallethold",
        "wallet.currency",
        # Transactions
        "transactions",
        "transactions.transaction",
        # Payment
        "payment",
        "payment.paymentintent",
        "payment.paymentprovider",
        "payment.paymentproviderlog",
        "payment.paymentwebhookevent",
        "payment.paystacktransferrecipient",
        # Measurements
        "measurements",
        "measurements.measurementprofile",
        # Notifications
        "notification",
        "notification.notification",
        "notification.notificationtemplate",
        "notification.notificationpreference",
        # Chat
        "chat",
        "chat.conversation",
        "chat.message",
        "chat.messagemedia",
        "chat.chatoffer",
        "chat.moderationflag",
        "chat.chatescalation",
        # Support
        "support",
        "support.supportticket",
        "support.ticketmessage",
        "support.ticketescalation",
        # Audit
        "audit_logs",
        "audit_logs.auditeventlog",
        # Django Control Room
        "dj_control_room",
        # Django internals
        "auth",
    ],
    # ── Per-model sidebar icons ─────────────────────────────────────────────
    "icons": {
        # Django internals
        "admin.LogEntry":                          "fas fa-history",
        "auth":                                    "fas fa-shield-alt",
        "auth.user":                               "fas fa-user-shield",
        "auth.group":                              "fas fa-users-cog",
        # Authentication
        "authentication":                          "fas fa-fingerprint",
        "authentication.unifieduser":              "fas fa-user-circle",
        "authentication.loginevent":               "fas fa-sign-in-alt",
        "authentication.usersession":              "fas fa-laptop",
        "authentication.biometriccredential":      "fas fa-id-badge",
        # Vendor
        "vendor":                                  "fas fa-store",
        "vendor.vendorprofile":                    "fas fa-store-alt",
        "vendor.vendorsetupstate":                 "fas fa-tasks",
        "vendor.vendorpayoutprofile":              "fas fa-university",
        # Catalog
        "catalog":                                 "fas fa-layer-group",
        "catalog.category":                        "fas fa-tag",
        "catalog.brand":                           "fas fa-certificate",
        "catalog.collections":                    "fas fa-palette",
        "catalog.blogpost":                       "fas fa-blog",
        "catalog.blogmedia":                      "fas fa-photo-video",
        # Product
        "product":                                 "fas fa-box-open",
        "product.product":                         "fas fa-tshirt",
        "product.productvariant":                  "fas fa-sitemap",
        "product.productgallerymedia":             "fas fa-images",
        "product.productreview":                   "fas fa-star",
        "product.ProductSizeAndMeasurementGuide":                     "fas fa-ruler-horizontal",
        "product.productcolor":                    "fas fa-paint-brush",
        "product.producttag":                      "fas fa-tags",
        "product.productfabric":                   "fas fa-scroll",
        "product.productmeasurementguide":         "fas fa-drafting-compass",
        "product.productcertification":            "fas fa-award",
        "product.productshippingprofile":          "fas fa-shipping-fast",
        "product.coupon":                          "fas fa-percent",
        "product.deliverycourier":                 "fas fa-truck",
        "product.productcommissionsnapshot":       "fas fa-file-invoice-dollar",
        "product.productpricehistory":             "fas fa-chart-line",
        "product.productinventorylog":             "fas fa-warehouse",
        "product.productwishlist":                 "fas fa-heart",
        "product.productviewlog":                  "fas fa-eye",
        "product.productspecification":            "fas fa-list-alt",
        "product.productfaq":                      "fas fa-question-circle",
        # Orders
        "order":                                   "fas fa-shopping-cart",
        "order.order":                             "fas fa-receipt",
        "order.cartorderitem":                     "fas fa-shopping-basket",
        "order.orderstatushistory":                "fas fa-stream",
        "order.orderidempotencyrecord":            "fas fa-fingerprint",
        "order.orderpaymentrecord":                "fas fa-money-check-alt",
        "order.ordercommercialtransitionlog":      "fas fa-random",
        # Custom Orders
        "custom_order":                            "fas fa-magic",
        "custom_order.customorder":                "fas fa-pencil-ruler",
        "custom_order.customordermilestone":       "fas fa-percentage",
        # KYC
        "kyc":                                     "fas fa-id-card",
        "kyc.kycsubmission":                       "fas fa-user-check",
        "kyc.kycdocument":                         "fas fa-file-alt",
        # Wallet
        "wallet":                                  "fas fa-wallet",
        "wallet.wallet":                           "fas fa-money-bill-wave",
        "wallet.wallethold":                       "fas fa-lock",
        "wallet.currency":                         "fas fa-coins",
        # Transactions
        "transactions":                            "fas fa-exchange-alt",
        "transactions.transaction":                "fas fa-random",
        "transactions.transactiondispute":         "fas fa-gavel",
        "transactions.transactionfee":             "fas fa-calculator",
        "transactions.transactionlog":             "fas fa-history",
        "transactions.transactionidempotencykey":  "fas fa-key",
        "transactions.commissionrule":             "fas fa-percent",
        "transactions.companyrevenueentry":        "fas fa-landmark",
        # Payment
        "payment":                                 "fas fa-credit-card",
        "payment.paymentintent":                   "fas fa-hand-holding-usd",
        "payment.paymentprovider":                 "fas fa-plug",
        "payment.paymentproviderlog":              "fas fa-stream",
        "payment.paymentwebhookevent":             "fas fa-satellite-dish",
        "payment.paystacktransferrecipient":       "fas fa-university",
        # Measurements
        "measurements":                            "fas fa-ruler-vertical",
        "measurements.measurementprofile":         "fas fa-ruler-combined",
        # Notifications
        "notification":                            "fas fa-bell",
        "notification.notification":               "fas fa-bell",
        "notification.notificationtemplate":       "fas fa-file-alt",
        "notification.notificationpreference":     "fas fa-sliders-h",
        # Chat
        "chat":                                    "fas fa-comments",
        "chat.conversation":                       "fas fa-comment-dots",
        "chat.message":                            "fas fa-comment",
        "chat.messagemedia":                       "fas fa-photo-video",
        "chat.chatoffer":                          "fas fa-file-invoice-dollar",
        "chat.moderationflag":                     "fas fa-flag",
        "chat.chatescalation":                     "fas fa-level-up-alt",
        # Support
        "support":                                 "fas fa-headset",
        "support.supportticket":                   "fas fa-ticket-alt",
        "support.ticketmessage":                   "fas fa-comments",
        "support.ticketescalation":                "fas fa-level-up-alt",
        # Audit
        "audit_logs":                              "fas fa-clipboard-list",
        "audit_logs.auditeventlog":                "fas fa-search",
        # Client
        "client":                                  "fas fa-user",
        "client.clientprofile":                    "fas fa-user-circle",
        "client.clientaddress":                    "fas fa-map-marker-alt",
        # Django Control Room
        "dj_control_room":                         "fas fa-tools",
        "dj_control_room.cachepanel":              "fas fa-database",
        "dj_control_room.celerypanel":             "fas fa-tasks",
        "dj_control_room.redispanel":              "fas fa-server",
        "dj_control_room.signalspanel":            "fas fa-broadcast-tower",
        "dj_control_room.urlspanel":               "fas fa-link",
    },
    "default_icon_parents":  "fas fa-chevron-circle-right",
    "default_icon_children": "fas fa-circle",
    "related_modal_active":  False,
    "custom_js":             "js/admin_dashboard.js",
    "custom_css":            "css/custom_admin.css",
    "show_ui_builder":       False,
    "changeform_format":     "horizontal_tabs",
    "changeform_format_overrides": {
        "auth.user":                   "collapsible",
        "auth.group":                  "vertical_tabs",
        "authentication.unifieduser":  "vertical_tabs",
        "vendor.vendorprofile":        "horizontal_tabs",
        "product.product":             "horizontal_tabs",
        "kyc.kycsubmission":           "horizontal_tabs",
        "order.order":                 "horizontal_tabs",
    },
    # Global top-bar search across most-used models
    "search_model": [
        "authentication.UnifiedUser",
        "product.Product",
        "order.Order",
        "vendor.VendorProfile",
        "kyc.KycSubmission",
    ],
}

JAZZMIN_UI_TWEAKS = {
    # ── Typography & density ─────────────────────────────────────────────────
    "navbar_small_text":           False,
    "footer_small_text":           False,
    "body_small_text":             True,
    "brand_small_text":            False,
    # ── Light theme colours (switched from dark cyborg) ──────────────────────
    "brand_colour":                "navbar-light",          # was navbar-dark
    "accent":                      "accent-warning",
    "navbar":                      "navbar-light",
    "no_navbar_border":            True,
    "navbar_fixed":                True,
    "layout_boxed":                False,
    "footer_fixed":                False,
    "sidebar_fixed":               True,
    "sidebar":                     "sidebar-light-warning",
    # ── Sidebar nav style ────────────────────────────────────────────────────
    "sidebar_nav_small_text":      False,
    "sidebar_disable_expand":      False,
    "sidebar_nav_child_indent":    True,
    "sidebar_nav_compact_style":   False,
    "sidebar_nav_legacy_style":    False,
    "sidebar_nav_flat_style":      False,
    # ── Theme (LIGHT) ────────────────────────────────────────────────────────
    "theme":                       "flatly",   # was "cyborg" (dark) → now light
    "dark_mode_theme":             "flatly",
    "default_theme_mode":          "light",    # was "auto"
    # ── Button classes ────────────────────────────────────────────────────────
    "button_classes": {
        "primary":   "btn-primary",
        "secondary": "btn-secondary",
        "info":      "btn-info",
        "warning":   "btn-warning",
        "danger":    "btn-danger",
        "success":   "btn-success",
    },
    # ── User menu ─────────────────────────────────────────────────────────────
    "user_avatar": "avatar",
    "usermenu_links": [
        {
            "name": "My Profile",
            "url": "admin:authentication_unifieduser_changelist",
            "icon": "fas fa-user-circle",
        },
        {
            "name": "Logout",
            "url": "admin:logout",
            "icon": "fas fa-sign-out-alt",
        },
    ],
}


# =============================================================================
# LOGGING — Enterprise Per-App Rotating File Logging
# =============================================================================
# Delegates to build_logging_config() in backend/config/logging_config.py.
# Each app/domain writes to its own RotatingFileHandler log file:
#
#   logs/apps/authentication/auth.log   ← apps.authentication.*
#   logs/apps/common/common.log         ← apps.common.*
#   logs/apps/store/store.log           ← store, ShopCart, checkout, createOrder
#   logs/apps/customer/customer.log     ← customer, measurements
#   logs/apps/vendor/vendor.log         ← vendor
#   logs/apps/payments/payments.log     ← Paystack_Webhoook_Prod, apps.payments
#   logs/apps/notifications/notify.log  ← notification, Blog
#   logs/apps/chat/chat.log             ← chat
#   logs/apps/admin/admin.log           ← admin_backend, userauths, utilities
#   logs/system/security.log            ← security, django.security
#   logs/system/webhook.log             ← webhook
#   logs/system/paystack.log            ← paystack
#   logs/system/permissions.log         ← permissions
#   logs/system/celery.log              ← celery, celery.task, celery.worker
#   logs/system/django.log              ← django.*
#   logs/system/application.log         ← catchall 'application' logger (legacy)
#
# Rotation: 10 MB per app file (10 backups), 20 MB for system files (20 backups)
# Production: use_json=True emits structured JSON for Datadog / ELK / Loki.
# See: backend/config/logging_config.py for full documentation.


# LOGGING is computed in base so Django and Celery can boot even when this
# module is imported directly. Environment-specific settings still rebuild the
# final LOGGING dict with their own debug/production preferences.
_debug_mode = DEBUG

LOGGING = build_logging_config(
    debug=_debug_mode,
    use_json=False,  # Overridden to True in production.py
    mail_admins=False,  # Overridden to True in production.py
)

# =============================================================================
# LOGGING CONFIGURATION HOOK
# =============================================================================
# PROBLEM (Python 3.12+ + Django 4.2+):
#   Django's default LOGGING_CONFIG = 'logging.config.dictConfig' is called
#   by Django's setup() machinery. In Python 3.12+, dictConfig() automatically
#   wraps ALL handlers in a QueueHandler (async) for thread safety. This means
#   handlers are NOT directly attached to loggers — they're in a background
#   queue listener. Under Uvicorn/ASGI, this async routing drops INFO-level
#   log records from middleware (apps.common.middleware) before they reach
#   stdout, causing 2xx success requests to appear invisible in the terminal
#   while 4xx errors (which also trigger django.request WARNING level) do show.
#
# FIX:
#   Set LOGGING_CONFIG = None to prevent Django from calling dictConfig() via
#   the auto-wrapping pipeline. Then call dictConfig() DIRECTLY ourselves with
#   the same LOGGING dict. This attaches handlers DIRECTLY to each logger
#   (synchronous, no queue), ensuring every log record — including INFO-level
#   success request lines — reaches stdout reliably on ALL server types.
#
# RESULT:
#   - Django dev server:   ALL requests logged (was already OK)
#   - Uvicorn ASGI server: ALL requests logged (2xx + 4xx + 5xx) ← FIX
#   - Daphne ASGI server:  ALL requests logged (2xx + 4xx + 5xx) ← FIX
#   - Celery worker:       Email task output appears in worker terminal ← FIX
#
# HOW (Django official pattern):
#   Django calls LOGGING_CONFIG(LOGGING) during django.setup() — AFTER all
#   apps load and env is stable. By setting LOGGING_CONFIG to our own callable,
#   we call logging.config.dictConfig() at the right time (post-setup), ensuring
#   all file handlers can create log directories and attach properly.
#   See: https://docs.djangoproject.com/en/4.2/topics/logging/#custom-logging-configuration


def _apply_logging_config(config):
    """
    Custom LOGGING_CONFIG callable — called by Django during setup().
    Applies our logging config via dictConfig() at the correct time,
    after all apps load, ensuring handlers attach directly to loggers.

    Phase 5 addition: also initializes structlog immediately after dictConfig
    so both standard Python logging AND structlog share the same log level
    settings from the start.
    """
    import logging.config as _lc

    _lc.dictConfig(config)

    # Initialize structlog with the same debug flag used by build_logging_config
    try:
        from backend.config.logging_config import configure_structlog
        configure_structlog(debug=_debug_mode)
    except Exception:
        pass  # structlog not installed — no-op, stdlib logging still works


# Django reads LOGGING_CONFIG as a dotted string path and calls it with LOGGING
# dict during django.setup(). We point it to _apply_logging_config() which:
#   1. Calls logging.config.dictConfig(config) directly (no QueueHandler wrapping)
#   2. Immediately calls configure_structlog() for ASGI-safe JSON logging
# This is the Phase 5 activation point for structlog across the entire stack.
LOGGING_CONFIG = "backend.config.base._apply_logging_config"


# =============================================================================
# STRUCTLOG CONFIGURATION REFERENCE
# =============================================================================
# Full structlog config is in backend/config/logging_config.py::configure_structlog()
# and is activated by _apply_logging_config() above on every Django startup.
#
# Datadog-compatible JSON output (production, DEBUG=False):
#   {
#     "event":         "User registered",          ← log message
#     "level":         "info",
#     "logger":        "apps.authentication",
#     "timestamp":     "2026-05-30T05:00:00+01:00",
#     "request_id":    "req-uuid-...",             ← from RequestIDMiddleware
#     "user_id":       "user-uuid-...",            ← bound via bind_contextvars()
#     "dd.trace_id":   "1234567890",               ← Datadog APM correlation
#     "dd.span_id":    "9876543210",               ← Datadog APM correlation
#     "otel.trace_id": "00000000...",              ← OpenTelemetry (alternative)
#   }
#
# Usage in application code:
#   import structlog
#   logger = structlog.get_logger(__name__)
#   logger.info("User registered", user_id=str(user.pk), email=user.email)
#
#   # Bind request-scoped context (async-safe ContextVar):
#   structlog.contextvars.bind_contextvars(
#       request_id=request.request_id,
#       user_id=str(request.user.pk),
#   )
#   structlog.contextvars.clear_contextvars()  # call in middleware __acall__ finally
#
STRUCTLOG_CONFIG = {
    "processors": [
        "structlog.contextvars.merge_contextvars",   # ASGI-safe ContextVar context
        "structlog.stdlib.add_log_level",
        "structlog.stdlib.add_logger_name",
        "structlog.processors.TimeStamper",          # fmt='iso'
        "backend.config.logging_config._inject_trace_context",  # Datadog/OTel IDs
        "structlog.stdlib.PositionalArgumentsFormatter",
        "structlog.processors.StackInfoRenderer",
        "structlog.processors.format_exc_info",
        "structlog.processors.UnicodeDecoder",
        "structlog.processors.JSONRenderer",         # prod: machine-readable JSON
    ],
    "renderer_dev": "structlog.dev.ConsoleRenderer",  # dev: colored terminal output
    "level": "DEBUG" if DEBUG else "INFO",
    "cache_logger_on_first_use": True,               # thread-safe perf optimization
}


# ==============================================================================
# OWASP SECURITY HEADERS — Enterprise Production Hardening
# ==============================================================================
# These headers are enforced by Django's SecurityMiddleware (already in MIDDLEWARE).
# Defends against XSS, clickjacking, MIME sniffing, and protocol downgrade attacks.
#
# OWASP References:
#   A05:2021 – Security Misconfiguration
#   A02:2021 – Cryptographic Failures (HSTS enforces HTTPS-only transport)

# ── XSS Protection (legacy IE header, kept for compatibility) ──────────────
SECURE_BROWSER_XSS_FILTER = True

# ── MIME Sniffing Prevention (X-Content-Type-Options: nosniff) ─────────────
SECURE_CONTENT_TYPE_NOSNIFF = True

# ── Clickjacking Protection (X-Frame-Options: DENY) ────────────────────────
# DENY prevents ALL framing. Admin uses SAMEORIGIN if needed via Jazzmin.
X_FRAME_OPTIONS = "DENY"

# ── HSTS — HTTP Strict Transport Security ──────────────────────────────────
# Forces browsers to use HTTPS exclusively for 1 year (31536000 seconds).
# ONLY enabled in production (DEBUG=False) — avoids breaking local HTTP.
SECURE_HSTS_SECONDS = 0 if DEBUG else 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = not DEBUG  # Applies to *.fashionistar.io in prod
SECURE_HSTS_PRELOAD = not DEBUG  # Enables HSTS preload list eligibility

# ── SSL Redirect — production only ─────────────────────────────────────────
# Redirects HTTP → HTTPS. Disabled locally to allow plain HTTP dev server.
SECURE_SSL_REDIRECT = not DEBUG

# ── Session Cookie Security ─────────────────────────────────────────────────
SESSION_COOKIE_SECURE = not DEBUG  # Only transmitted over HTTPS
SESSION_COOKIE_HTTPONLY = True  # Not accessible via JavaScript (XSS protection)
SESSION_COOKIE_SAMESITE = "Lax"  # CSRF protection for cross-site requests

# ── CSRF Cookie Security ────────────────────────────────────────────────────
CSRF_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = "Lax"

# ── Referrer Policy ─────────────────────────────────────────────────────────
# Limits referrer information sent to third parties (privacy + security)
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"

# ==============================================================================
# END OF OWASP SECURITY HEADERS
# ==============================================================================

# =============================================================================
# DJANGO CONTROL ROOM CONFIGURATION
# =============================================================================
# Redis Panel settings: cursor-based pagination for large Redis datasets
DJ_REDIS_PANEL_SETTINGS = {
    "PAGINATION_METHOD": "CURSOR_PAGINATED_SCAN",
}

# Signals Panel settings: enable receiver source code viewing
DJ_SIGNALS_PANEL_SETTINGS = {
    "SHOW_SOURCE": True,
}

