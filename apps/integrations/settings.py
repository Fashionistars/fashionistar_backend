"""
تنظیمات اپلیکیشن integrations
"""
from django.conf import settings

# تنظیمات پیش‌فرض برای integrations
INTEGRATIONS_DEFAULTS = {
    # محیط پیش‌فرض برای credentials
    'INTEGRATION_ENVIRONMENT': 'production',
    
    # تنظیمات Kavenegar
    'KAVENEGAR_API_KEY': '',
    'KAVENEGAR_SENDER': '10004346',
    'KAVENEGAR_OTP_TEMPLATE': 'verify',
    'KAVENEGAR_APPOINTMENT_TEMPLATE': 'appointment-reminder',
    
    # تنظیمات OpenAI
    'OPENAI_API_KEY': '',
    'OPENAI_DEFAULT_MODEL': 'gpt-4',
    'OPENAI_MAX_TOKENS': 2000,
    'OPENAI_TEMPERATURE': 0.7,
    
    # تنظیمات TalkBot
    'TALKBOT_API_KEY': '',
    'TALKBOT_BASE_URL': 'https://api.talkbot.ir/v1',
    
    # تنظیمات Webhook
    'WEBHOOK_SECRET': '',
    'WEBHOOK_TIMEOUT': 30,
    'WEBHOOK_MAX_RETRIES': 3,
    'WEBHOOK_RETRY_DELAY': 60,  # ثانیه
    
    # تنظیمات Rate Limiting
    'RATE_LIMIT_CACHE_PREFIX': 'rate_limit',
    'RATE_LIMIT_DEFAULT_WINDOW': 3600,  # 1 ساعت
    'RATE_LIMIT_DEFAULT_MAX_REQUESTS': 100,
    
    # تنظیمات File Storage
    'ALLOWED_FILE_EXTENSIONS': [
        'jpg', 'jpeg', 'png', 'pdf', 'doc', 'docx',
        'mp3', 'wav', 'm4a', 'ogg'  # برای فایل‌های صوتی
    ],
    'MAX_FILE_SIZE': 10 * 1024 * 1024,  # 10MB
    'MAX_AUDIO_FILE_SIZE': 25 * 1024 * 1024,  # 25MB برای فایل‌های صوتی
    
    # تنظیمات لاگ
    'LOG_RETENTION_DAYS': 30,  # نگهداری لاگ‌ها به روز
    'LOG_CLEANUP_BATCH_SIZE': 1000,
    
    # تنظیمات AI پزشکی
    'MEDICAL_AI_MODELS': {
        'symptoms_analysis': 'gpt-4',
        'diagnosis_suggestion': 'gpt-4',
        'prescription_review': 'gpt-4',
        'medical_transcription': 'whisper-1'
    },
    
    # تنظیمات امنیتی
    'CREDENTIAL_ENCRYPTION_KEY': '',  # باید در محیط تنظیم شود
    'WEBHOOK_SIGNATURE_ALGORITHM': 'sha256',
    
    # تنظیمات پیش‌فرض providers
    'DEFAULT_PROVIDERS': {
        'sms': 'kavenegar',
        'ai': 'openai',
        'payment': 'zarinpal',
        'storage': 'minio'
    },
    
    # تنظیمات اعلان‌ها
    'NOTIFICATION_CHANNELS': {
        'sms': {
            'provider': 'kavenegar',
            'priority': 1
        },
        'push': {
            'provider': 'firebase',
            'priority': 2
        },
        'email': {
            'provider': 'sendgrid',
            'priority': 3
        }
    },
    
    # تنظیمات صف و Celery
    'CELERY_INTEGRATION_QUEUES': {
        'sms': 'integrations.sms',
        'webhooks': 'integrations.webhooks',
        'ai': 'integrations.ai',
        'notifications': 'integrations.notifications'
    },
    
    # تنظیمات Monitoring
    'MONITOR_INTEGRATION_HEALTH': True,
    'HEALTH_CHECK_INTERVAL': 300,  # 5 دقیقه
    'ALERT_ON_FAILURE_COUNT': 3,
}


def get_integration_setting(name, default=None):
    """
    دریافت تنظیمات integration با fallback به مقدار پیش‌فرض
    
    Args:
        name: نام تنظیم
        default: مقدار پیش‌فرض اضافی
        
    Returns:
        مقدار تنظیم
    """
    # ابتدا از settings اصلی Django
    if hasattr(settings, name):
        return getattr(settings, name)
    
    # سپس از تنظیمات پیش‌فرض
    if name in INTEGRATIONS_DEFAULTS:
        return INTEGRATIONS_DEFAULTS[name]
    
    # در نهایت مقدار default ارسالی
    return default


# Middleware class برای integrations
class IntegrationMiddleware:
    """
    Middleware برای مدیریت درخواست‌های integration
    """
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        # قبل از پردازش درخواست
        request.integration_context = {}
        
        # پردازش درخواست
        response = self.get_response(request)
        
        # بعد از پردازش
        return response


# تنظیمات URL patterns
INTEGRATION_URL_NAMESPACE = 'integrations'
WEBHOOK_URL_PREFIX = 'webhook/'


# Helper functions
def validate_integration_settings():
    """
    اعتبارسنجی تنظیمات integrations
    """
    errors = []
    
    # بررسی API keys
    if not get_integration_setting('KAVENEGAR_API_KEY'):
        errors.append('KAVENEGAR_API_KEY is not configured')
    
    if not get_integration_setting('WEBHOOK_SECRET'):
        errors.append('WEBHOOK_SECRET is not configured')
    
    # بررسی تنظیمات امنیتی
    if not get_integration_setting('CREDENTIAL_ENCRYPTION_KEY'):
        errors.append('CREDENTIAL_ENCRYPTION_KEY is not configured')
    
    return errors


# تنظیمات Logging
INTEGRATION_LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'integration': {
            'format': '[%(asctime)s] %(levelname)s [%(name)s:%(lineno)s] %(message)s',
            'datefmt': '%d/%b/%Y %H:%M:%S',
        },
    },
    'handlers': {
        'integration_file': {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': 'logs/integrations.log',
            'maxBytes': 1024 * 1024 * 15,  # 15MB
            'backupCount': 10,
            'formatter': 'integration',
        },
        'integration_error_file': {
            'level': 'ERROR',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': 'logs/integrations_error.log',
            'maxBytes': 1024 * 1024 * 15,  # 15MB
            'backupCount': 10,
            'formatter': 'integration',
        },
    },
    'loggers': {
        'integrations': {
            'handlers': ['integration_file', 'integration_error_file'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}