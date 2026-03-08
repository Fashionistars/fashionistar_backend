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
import sys
from decouple import config
import dj_database_url
import cloudinary
import cloudinary.uploader
import cloudinary.api

# ── Environment loader ────────────────────────────────────────────────
env = Env()
env.read_env()

# ── Path resolution ───────────────────────────────────────────────────
# BASE_DIR → fashionistar_backend/  (root of the Django project)
BASE_DIR = Path(__file__).resolve().parent.parent.parent


# =============================================================================
# SECURITY
# =============================================================================
SECRET_KEY = env(
    "SECRET_KEY",
    default='django-insecure-b*tuoe%^o+=^35$0fufrm=oamh^(o0tabn39(7ni12(i-oup+4'
)

ALLOWED_HOSTS = env.list(
    "ALLOWED_HOSTS",
    default=["127.0.0.1", "localhost", "localhost:8000", "localhost:3001"]
)

CSRF_TRUSTED_ORIGINS = env.list(
    "CSRF_TRUSTED_ORIGINS",
    default=['http://localhost:3000', 'http://localhost:8000']
)

SECURE_CROSS_ORIGIN_OPENER_POLICY = 'same-origin-allow-popups'

# Admin URL (secret to prevent enumeration)
DJANGO_SECRET_ADMIN_URL = env("DJANGO_SECRET_ADMIN_URL", default="admin/")

# Site URL for email links, OTP callbacks, etc.
SITE_URL = env("SITE_URL", default="http://127.0.0.1:8000")


# =============================================================================
# INSTALLED APPS
# =============================================================================
INSTALLED_APPS = [
    # ── Admin UI ─────────────────────────────────────────────────────────────
    'jazzmin',
    'drf_yasg',
    'drf_spectacular',

    # ── Django Core ──────────────────────────────────────────────────────────
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',

    # Whitenoise MUST be before staticfiles
    'whitenoise.runserver_nostatic',
    'django.contrib.staticfiles',

    # ── Fashionistar New Architecture ────────────────────────────────────────
    'apps.common',
    'apps.authentication',

    # ── Legacy Apps (pending migration to apps/) ─────────────────────────────
    'admin_backend',
    'userauths',
    'store',
    'vendor',
    'customer',
    'addon',
    'api',
    'ShopCart',
    'checkout',
    'notification',
    'createOrder',
    'chat',
    'measurements',
    'Blog',
    'Homepage',
    'Paystack_Webhoook_Prod',
    'utilities',

    # ── Third Party ──────────────────────────────────────────────────────────
    'rest_framework',
    'rest_framework_simplejwt.token_blacklist',  # JWT logout blacklisting
    'corsheaders',
    'import_export',
    'anymail',
    'storages',
    'auditlog',
    'phone_verify',
    'channels',
    'django_filters',
    'phonenumber_field',
    'django_redis',
    'django_celery_beat',
    'cloudinary',
    'cloudinary_storage',
]


# =============================================================================
# MIDDLEWARE
# =============================================================================
MIDDLEWARE = [
    # ── Fashionistar Observability (must be FIRST) ───────────────────────────
    # Every subsequent middleware & view gets request.request_id + timing
    'apps.common.middleware.RequestIDMiddleware',
    'apps.common.middleware.RequestTimingMiddleware',
    # SIEM audit log: captures IP, UA, URL, method, role for all 7 roles
    'apps.common.middleware.SecurityAuditMiddleware',

    # ── Django Security & CORS ───────────────────────────────────────────────
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',     # serve static in prod
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'backend.urls'


# =============================================================================
# TEMPLATES
# =============================================================================
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'backend.wsgi.application'
ASGI_APPLICATION = 'backend.asgi.application'


# =============================================================================
# DATABASE
# =============================================================================
# Defaults to SQLite for local dev if DATABASE_URL not set in .env.
# Production uses PostgreSQL via DATABASE_URL.
DATABASES = {
    'default': dj_database_url.config(
        default=env("DATABASE_URL", default='sqlite:///db.sqlite3'),
        conn_max_age=600,
        ssl_require=False,
    )
}

# SQLite-specific options (ignored for PostgreSQL)
if 'sqlite' in DATABASES['default']['ENGINE']:
    DATABASES['default'].setdefault('OPTIONS', {})['timeout'] = 20


# =============================================================================
# AUTHENTICATION
# =============================================================================
AUTH_USER_MODEL = 'userauths.User'  # NOTE: Will migrate to authentication.UnifiedUser in Phase 3

AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',       # Legacy userauths
    'apps.authentication.backends.UnifiedUserBackend', # New UnifiedUser
]

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]


# =============================================================================
# INTERNATIONALISATION
# =============================================================================
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Africa/Lagos'
USE_I18N = True
USE_TZ = True


# =============================================================================
# STATIC & MEDIA FILES
# =============================================================================
STATIC_URL = '/static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')
STATICFILES_DIRS = [os.path.join(BASE_DIR, 'static')]

MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

CLOUDINARY_STORAGE = {
    "CLOUD_NAME": env("CLOUDINARY_CLOUD_NAME", default="your_cloud_name"),
    "API_KEY": env("CLOUDINARY_API_KEY", default="your_api_key"),
    "API_SECRET": env("CLOUDINARY_API_SECRET", default="your_api_secret"),
}

STORAGES = {
    "default": {
        "BACKEND": "cloudinary_storage.storage.MediaCloudinaryStorage",
    },
    "staticfiles": {
        # Overridden in production.py to CompressedManifestStaticFilesStorage
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


# =============================================================================
# CACHING (Redis)
# =============================================================================
CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': env("REDIS_URL", default="redis://127.0.0.1:6379/0"),
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
            'IGNORE_EXCEPTIONS': True,   # Redis outage ≠ 500 error
            'CONNECTION_POOL_KWARGS': {
                'max_connections': 50,
                'decode_responses': False,
            },
            'SOCKET_TIMEOUT': 0.5,
            'SOCKET_CONNECT_TIMEOUT': 0.5,
        },
    },
    # LocMemCache for OpenAPI schema (no Redis dependency)
    'schema': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'fashionistar-schema-cache',
    },
}


# =============================================================================
# CHANNELS (WebSocket / Real-time)
# =============================================================================
CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels_redis.core.RedisChannelLayer',
        'CONFIG': {
            'hosts': [env("REDIS_URL", default='redis://127.0.0.1:6379/0')],
        },
    },
}


# =============================================================================
# REST FRAMEWORK — Enterprise Configuration
# =============================================================================
REST_FRAMEWORK = {
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',

    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),

    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
        'rest_framework.authentication.TokenAuthentication',
        'rest_framework.authentication.SessionAuthentication',
        'rest_framework.authentication.BasicAuthentication',
    ),

    'DEFAULT_RENDERER_CLASSES': [
        'apps.common.renderers.FashionistarRenderer',
        'rest_framework.renderers.BrowsableAPIRenderer',
    ],

    'DEFAULT_PARSER_CLASSES': [
        'rest_framework.parsers.JSONParser',
        'rest_framework.parsers.FormParser',
        'rest_framework.parsers.MultiPartParser',
    ],

    'DEFAULT_THROTTLE_CLASSES': [
        'apps.common.throttling.AnonBurstThrottle',
        'apps.common.throttling.AnonSustainedThrottle',
        'apps.common.throttling.UserBurstThrottle',
        'apps.common.throttling.UserSustainedThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon_burst':  '30/minute',
        'anon_day':    '500/day',
        'user_burst':  '120/minute',
        'user_day':    '5000/day',
        'auth':        '5/minute',
        'otp':         '3/minute',
        'upload':      '20/hour',
        'vendor':      '200/minute',
    },

    'DEFAULT_PAGINATION_CLASS': 'apps.common.pagination.DefaultPagination',
    'PAGE_SIZE': 20,

    'EXCEPTION_HANDLER': 'apps.common.exceptions.custom_exception_handler',
}


# =============================================================================
# SIMPLE JWT
# =============================================================================
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(hours=1),     # 1 hour for security
    'REFRESH_TOKEN_LIFETIME': timedelta(days=30),    # 30 days (not 50!)
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'UPDATE_LAST_LOGIN': True,
    'ALGORITHM': 'HS256',
    'VERIFYING_KEY': None,
    'AUDIENCE': None,
    'ISSUER': None,
    'JWK_URL': None,
    'LEEWAY': 0,
    'AUTH_HEADER_TYPES': ('Bearer',),
    'AUTH_HEADER_NAME': 'HTTP_AUTHORIZATION',
    'USER_ID_FIELD': 'id',
    'USER_ID_CLAIM': 'user_id',
    'USER_AUTHENTICATION_RULE': 'rest_framework_simplejwt.authentication.default_user_authentication_rule',
    'AUTH_TOKEN_CLASSES': ('rest_framework_simplejwt.tokens.AccessToken',),
    'TOKEN_TYPE_CLAIM': 'token_type',
    'TOKEN_USER_CLASS': 'rest_framework_simplejwt.models.TokenUser',
    'JTI_CLAIM': 'jti',
    'SLIDING_TOKEN_REFRESH_EXP_CLAIM': 'refresh_exp',
    'SLIDING_TOKEN_LIFETIME': timedelta(minutes=5),
    'SLIDING_TOKEN_REFRESH_LIFETIME': timedelta(days=1),
}


# =============================================================================
# API DOCUMENTATION
# =============================================================================
SPECTACULAR_SETTINGS = {
    'TITLE': 'Fashionistar API',
    'DESCRIPTION': (
        'Nigeria\'s Premier AI-Powered Fashion E-Commerce Platform API.\n\n'
        '**V1 (DRF/Sync):** Standard REST endpoints, WSGI-safe.\n'
        '**V2 (Ninja/Async):** High-concurrency async endpoints, ASGI-native.'
    ),
    'VERSION': '2.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
    'COMPONENT_SPLIT_REQUEST': True,
    'SECURITY': [{'Bearer': []}],
    'SECURITY_DEFINITIONS': {
        'Bearer': {
            'type': 'http',
            'scheme': 'bearer',
            'bearerFormat': 'JWT',
        },
    },
}

SWAGGER_SETTINGS = {
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
# Overridden per-environment in development.py / production.py
CORS_ALLOW_ALL_ORIGINS = True   # Dev default — MUST be False in production


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

TWILIO_ACCOUNT_SID = config('TWILIO_ACCOUNT_SID', default='AC_PLACEHOLDER_SID')
TWILIO_AUTH_TOKEN = config('TWILIO_AUTH_TOKEN', default='PLACEHOLDER_AUTH_TOKEN')
TWILIO_PHONE_NUMBER = config('TWILIO_PHONE_NUMBER', default='+15005550006')

PHONE_VERIFICATION = {
    'BACKEND': 'phone_verify.backends.twilio.TwilioBackend',
    'OPTIONS': {
        'SID': env('TWILIO_ACCOUNT_SID', default='fake'),
        'SECRET': env('TWILIO_AUTH_TOKEN', default='fake'),
        'FROM': env('TWILIO_PHONE_NUMBER', default='+14755292729'),
    },
    'TOKEN_LENGTH': 6,
    'MESSAGE': 'Fashionistar verification code: {security_code}',
    'APP_NAME': 'Fashionistar',
    'SECURITY_CODE_EXPIRATION_TIME': 300,  # 5 minutes
    'VERIFY_SECURITY_CODE_ONLY_ONCE': True,
}


# =============================================================================
# EMAIL
# =============================================================================
# NOTE: Override EMAIL_BACKEND in development.py (console) or production.py (SMTP/Mailgun)
DEFAULT_FROM_EMAIL = config('DEFAULT_FROM_EMAIL', default='noreply@fashionistar.net')
SERVER_EMAIL = config('DEFAULT_FROM_EMAIL', default='noreply@fashionistar.net')

# Gmail SMTP (used in production or via DatabaseConfiguredEmailBackend)
EMAIL_HOST = 'smtp.gmail.com'
EMAIL_HOST_USER = config('EMAIL_HOST_USER', default='fashionistar.home.beauty@gmail.com')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD', default='')
EMAIL_PORT = 465
EMAIL_USE_TLS = False
EMAIL_USE_SSL = True

# Anymail (Mailgun)
ANYMAIL = {
    "MAILGUN_API_KEY": env("MAILGUN_API_KEY", default=""),
    "MAILGUN_SENDER_DOMAIN": env("MAILGUN_DOMAIN", default=""),
}

# Zoho ZeptoMail
ZOHO_ZEPTOMAIL_API_KEY_TOKEN = env('ZOHO_ZEPTOMAIL_API_KEY_TOKEN', default='')
ZOHO_ZEPTOMAIL_HOSTED_REGION = env('ZOHO_ZEPTOMAIL_HOSTED_REGION', default='zeptomail.zoho.com')


# =============================================================================
# CELERY — Enterprise Configuration
# =============================================================================
REDIS_URL = env("REDIS_URL", default="redis://127.0.0.1:6379/1")

CELERY_BROKER_URL = env('CELERY_BROKER_URL', default=REDIS_URL)
CELERY_RESULT_BACKEND = env('CELERY_RESULT_BACKEND', default=REDIS_URL)

# Fast-fail: 1s timeouts so dead Redis fails immediately, not after 60s
CELERY_BROKER_TRANSPORT_OPTIONS = {
    'socket_connect_timeout': 1,
    'socket_timeout': 1,
    'socket_keepalive': True,
}
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = False

CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TIMEZONE = 'UTC'
CELERY_ENABLE_UTC = True

CELERY_WORKER_MAX_TASKS_PER_CHILD = 200
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_REJECT_ON_WORKER_LOST = True
CELERY_TASK_IGNORE_RESULT = True

CELERY_BEAT_SCHEDULE = {
    "keep-render-service-awake": {
        "task": "keep_service_awake",
        "schedule": 300.0,
    },
}


# =============================================================================
# JAZZMIN Admin UI
# =============================================================================
JAZZMIN_SETTINGS = {
    "user_avatar": "avatar",
    "usermodel_field_mappings": {
        "userauths.User": "avatar",
    },
    "site_title": "Fashionistar Admin",
    "site_header": "Fashionistar",
    "site_brand": "AI Fashion Marketplace",
    "site_icon": "images/favicon.ico",
    "site_logo": "images/logos/logo.png",
    "welcome_sign": "Welcome to Fashionistar Admin",
    "copyright": "© 2026 Fashionistar Ltd.",
    "topmenu_links": [
        {"name": "Dashboard", "url": "admin:index", "permissions": ["auth.view_user"]},
        {"model": "auth.User"},
    ],
    "show_sidebar": True,
    "navigation_expanded": True,
    "order_with_respect_to": [
        "store", "store.product", "store.cartorder", "store.cartorderitem",
        "store.cart", "store.category", "store.brand", "store.productfaq",
        "store.review", "store.Coupon", "store.DeliveryCouriers",
        "userauths", "userauths.user", "userauths.profile",
    ],
    "icons": {
        "admin.LogEntry": "fas fa-file",
        "auth": "fas fa-users-cog",
        "auth.user": "fas fa-user",
        "userauths.User": "fas fa-user",
        "userauths.Profile": "fas fa-address-card",
        "store.Product": "fas fa-th",
        "store.CartOrder": "fas fa-shopping-cart",
        "store.Cart": "fas fa-cart-plus",
        "store.CartOrderItem": "fas fa-shopping-basket",
        "store.Brand": "fas fa-check-circle",
        "store.productfaq": "fas fa-question",
        "store.Review": "fas fa-star fa-beat",
        "store.Category": "fas fa-tag",
        "store.Coupon": "fas fa-percentage",
        "store.DeliveryCouriers": "fas fa-truck",
        "store.Address": "fas fa-location-arrow",
    },
    "default_icon_parents": "fas fa-chevron-circle-right",
    "default_icon_children": "fas fa-arrow-circle-right",
    "related_modal_active": False,
    "custom_js": None,
    "show_ui_builder": False,
    "changeform_format": "horizontal_tabs",
    "changeform_format_overrides": {
        "auth.user": "collapsible",
        "auth.group": "vertical_tabs",
        "authentication.unifieduser": "vertical_tabs",
    },
}

JAZZMIN_UI_TWEAKS = {
    "navbar_small_text": False,
    "footer_small_text": False,
    "body_small_text": True,
    "brand_small_text": False,
    "brand_colour": "navbar-dark",
    "accent": "accent-olive",
    "navbar": "navbar-dark",
    "no_navbar_border": False,
    "navbar_fixed": False,
    "layout_boxed": False,
    "footer_fixed": False,
    "sidebar_fixed": False,
    "sidebar": "sidebar-dark-info",
    "sidebar_nav_small_text": False,
    "sidebar_disable_expand": False,
    "sidebar_nav_child_indent": False,
    "sidebar_nav_compact_style": False,
    "sidebar_nav_legacy_style": False,
    "sidebar_nav_flat_style": False,
    "theme": "cyborg",
    "dark_mode_theme": "cyborg",
    "button_classes": {
        "primary": "btn-primary",
        "secondary": "btn-secondary",
        "info": "btn-info",
        "warning": "btn-warning",
        "danger": "btn-danger",
        "success": "btn-success",
    },
}


# =============================================================================
# LOGGING — imported from logging.py at app startup via apps.common.apps
# =============================================================================
# Async QueueHandler + QueueListener configured in apps/common/apps.py
# This dict provides the synchronous fallback (used by Django check, runserver)
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '[{levelname}] {asctime} {module} PID:{process} TID:{thread} — {message}',
            'style': '{',
        },
        'simple': {
            'format': '[{levelname}] {message}',
            'style': '{',
        },
        'json': {
            '()': 'logging.Formatter',
            'format': '{"level":"%(levelname)s","time":"%(asctime)s","module":"%(module)s","msg":"%(message)s"}',
        },
    },
    'filters': {
        'require_debug_false': {
            '()': 'django.utils.log.RequireDebugFalse',
        },
        'require_debug_true': {
            '()': 'django.utils.log.RequireDebugTrue',
        },
    },
    'handlers': {
        'console': {
            'level': 'DEBUG',
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
            'stream': sys.stdout,
        },
        'file': {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': os.path.join(BASE_DIR, 'logs', 'application.log'),
            'maxBytes': 10 * 1024 * 1024,  # 10MB
            'backupCount': 5,
            'formatter': 'verbose',
            'encoding': 'utf-8',
        },
        'webhook_file': {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': os.path.join(BASE_DIR, 'logs', 'webhook.log'),
            'maxBytes': 5 * 1024 * 1024,   # 5MB
            'backupCount': 3,
            'formatter': 'verbose',
            'encoding': 'utf-8',
        },
        'mail_admins': {
            'level': 'ERROR',
            'class': 'django.utils.log.AdminEmailHandler',
            'formatter': 'verbose',
            'filters': ['require_debug_false'],
        },
    },
    'loggers': {
        'django': {
            'handlers': ['console', 'file'],
            'level': 'INFO',
            'propagate': True,
        },
        'application': {
            'handlers': ['console', 'file'],
            'level': 'DEBUG',
            'propagate': False,
        },
        'security': {
            'handlers': ['console', 'file'],
            'level': 'INFO',
            'propagate': False,
        },
        'webhook': {
            'handlers': ['console', 'webhook_file'],
            'level': 'INFO',
            'propagate': False,
        },
        'paystack': {
            'handlers': ['console', 'file'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}
