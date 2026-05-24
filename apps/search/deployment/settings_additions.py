"""
تنظیمات اضافی برای search
Additional Settings for search
"""

# اضافه کردن به INSTALLED_APPS
INSTALLED_APPS += [
    'search',
]

# Rate limiting (نمونه)
RATE_LIMIT_SEARCH = {
    'api_calls': '200/minute',
}

# Logging برای search
LOGGING.setdefault('loggers', {})
LOGGING['loggers'].setdefault('search', {
    'handlers': ['console'],
    'level': 'INFO',
    'propagate': False,
})

