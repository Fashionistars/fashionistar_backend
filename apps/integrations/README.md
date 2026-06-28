# اپلیکیشن Integrations

اپلیکیشن مدیریت یکپارچه‌سازی‌های خارجی برای پروژه هلسا

## معرفی

این اپلیکیشن مسئول مدیریت تمام یکپارچه‌سازی‌ها با سرویس‌های خارجی شامل:
- سرویس پیامک (Kavenegar)
- سرویس‌های AI (OpenAI, TalkBot)
- مدیریت Webhook ها
- سیستم Rate Limiting
- ذخیره‌سازی فایل

## ساختار

```
integrations/
├── __init__.py
├── apps.py              # تنظیمات اپلیکیشن
├── models.py            # مدل‌های دیتابیس
├── serializers.py       # سریالایزرها
├── views.py             # API Views
├── urls.py              # URL patterns
├── admin.py             # رابط ادمین
├── settings.py          # تنظیمات اپ
├── services/            # سرویس‌های یکپارچه‌سازی
│   ├── __init__.py
│   ├── base_service.py  # کلاس پایه
│   ├── kavenegar_service.py
│   ├── ai_service.py
│   └── webhook_service.py
└── tests/               # تست‌ها
    ├── __init__.py
    ├── test_models.py
    ├── test_services.py
    └── test_views.py
```

## مدل‌ها

### IntegrationProvider
ارائه‌دهندگان خدمات یکپارچه‌سازی (مثل Kavenegar, OpenAI)

### IntegrationCredential
ذخیره اطلاعات احراز هویت برای هر ارائه‌دهنده

### IntegrationLog
ثبت تمام فعالیت‌های یکپارچه‌سازی

### WebhookEndpoint
تعریف endpoint های webhook

### WebhookEvent
ثبت رویدادهای دریافتی از webhook ها

### RateLimitRule
قوانین محدودیت نرخ درخواست

## API Endpoints

### مدیریت ارائه‌دهندگان
- `GET /api/integrations/providers/` - لیست ارائه‌دهندگان
- `GET /api/integrations/providers/{slug}/` - جزئیات ارائه‌دهنده
- `GET /api/integrations/providers/{slug}/health-check/` - بررسی سلامت
- `GET /api/integrations/providers/{slug}/statistics/` - آمار استفاده

### ارسال پیامک
- `POST /api/integrations/sms/send/` - ارسال پیامک

نمونه درخواست:
```json
{
    "receptor": "09123456789",
    "message_type": "otp",
    "token": "12345",
    "template": "verify"
}
```

### تولید متن با AI
- `POST /api/integrations/ai/generate/` - تولید متن

نمونه درخواست:
```json
{
    "prompt": "متن ورودی",
    "max_tokens": 1000,
    "temperature": 0.7,
    "analysis_type": "symptoms"
}
```

### Webhook
- `POST /api/integrations/webhook/{endpoint_url}/` - دریافت webhook

## سرویس‌ها

### KavenegarService
- `send_otp()` - ارسال کد OTP
- `send_pattern()` - ارسال با قالب
- `send_bulk()` - ارسال گروهی
- `get_status()` - بررسی وضعیت پیامک

### AIIntegrationService
- `generate_text()` - تولید متن
- `analyze_medical_text()` - تحلیل متن پزشکی
- `transcribe_audio()` - تبدیل صوت به متن

### WebhookService
- `register_webhook()` - ثبت webhook جدید
- `process_webhook()` - پردازش درخواست webhook
- `verify_signature()` - تأیید امضا

## تنظیمات

در فایل `settings.py` پروژه اصلی:

```python
# Kavenegar
KAVENEGAR_API_KEY = 'your-api-key'
KAVENEGAR_SENDER = '10004346'

# OpenAI
OPENAI_API_KEY = 'your-openai-key'
OPENAI_DEFAULT_MODEL = 'gpt-4'

# Webhook
WEBHOOK_SECRET = 'your-webhook-secret'

# Security
CREDENTIAL_ENCRYPTION_KEY = 'your-encryption-key'
```

## نحوه استفاده

### ارسال پیامک OTP
```python
from integrations.services import KavenegarService

service = KavenegarService()
result = service.send_otp(
    receptor='09123456789',
    token='12345'
)
```

### تحلیل متن پزشکی
```python
from integrations.services import AIIntegrationService

service = AIIntegrationService('openai')
result = service.analyze_medical_text(
    text='بیمار از سردرد و تب شکایت دارد',
    analysis_type='symptoms',
    patient_context={'age': 35, 'gender': 'male'}
)
```

### ثبت Webhook
```python
from integrations.services import WebhookService

service = WebhookService()
result = service.register_webhook(
    provider_slug='payment-gateway',
    name='Payment Status',
    endpoint_url='payment-status',
    events=['payment.success', 'payment.failed']
)
```

## تست‌ها

برای اجرای تست‌ها:

```bash
python manage.py test integrations
```

## نکات امنیتی

1. **رمزنگاری Credentials**: تمام اطلاعات حساس باید رمزنگاری شوند
2. **تأیید امضای Webhook**: همیشه امضای webhook ها را تأیید کنید
3. **Rate Limiting**: برای جلوگیری از سوءاستفاده، rate limit اعمال کنید
4. **Logging**: تمام فعالیت‌ها را لاگ کنید

## مستندات API

مستندات کامل API در آدرس زیر:
- Swagger: `/api/docs/`
- ReDoc: `/api/redoc/`