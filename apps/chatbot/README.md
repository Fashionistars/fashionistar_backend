# سیستم چت‌بات فشن‌استار (Fashionistar Chatbot System)

سیستم چت‌بات هوشمند برای مشتریان و فروشندگان/خیاط‌ها در پلتفرم فشن‌استار که با استفاده از هوش مصنوعی پاسخ‌های مناسب در مورد تناسب سایز بدنی، مشخصات پارچه، روندهای طراحی لباس و سفارش‌های شخصی‌سازی شده ارائه می‌دهد.

## ویژگی‌ها

### چت‌بات مشتریان
- **محاسبه دقیق سایز**: بررسی اولیه اندازه‌های بدنی و ارائه پیشنهاد سایز مناسب.
- **مشخصات فنی و نگهداری محصول**: دریافت اطلاعات درباره شستشو، اتو و محدودیت‌های الیاف.
- **مشاوره و رزرو سفارشی (Bespoke)**: هماهنگی جلسات مشاوره با طراحان و خیاط‌ها.
- **راهنمایی استایلینگ**: پاسخ به سؤالات عمومی پیرامون ست لباس و روندهای مد.

### چت‌بات خیاط‌ها / فروشندگان
- **پشتیبانی کاتالوگ**: کمک به دسته‌بندی و تحلیل قیمت کاتالوگ محصولات.
- **الگوهای دوخت**: راهنماهای فنی دوخت و مراحل سوار کردن لباس بر اساس پیچیدگی.
- **مشخصات فنی پارچه**: آنالیز تداخلات الیاف و محدودیت‌های اتوکشی و شستشوی پارچه‌های حساس.
- **جستجوی مراجع طراحی**: دسترسی به منابع الهام‌بخش، مراجع طراحی و ژورنال‌های مد.

## معماری سیستم

```
chatbot/
├── models.py              # مدل‌های پایگاه داده جلسات، پیام‌ها و پاسخ‌های از پیش تعیین شده
├── serializers.py         # سریالایزرهای REST API (اعتبارسنجی ورودی‌ها و خروجی‌ها)
├── views.py              # ViewSet ها و API endpoints
├── urls.py               # تعریف URL های سیستم چت‌بات
├── admin.py              # پنل مدیریت Django برای ثبت کلیدواژه‌ها و پاسخ‌های آماده
├── settings.py           # تنظیمات چت‌بات (تایم‌اوت، محدودیت طول پیام، آستانه اطمینان AI)
├── tests.py              # تست‌های جامع سیستم
├── services/             # سرویس‌های کسب‌وکار
│   ├── base_chatbot.py   # کلاس پایه چت‌بات
│   ├── client_chatbot.py  # سرویس چت‌بات مشتری
│   ├── vendor_chatbot.py  # سرویس چت‌بات فروشنده/خیاط
│   ├── ai_integration.py  # یکپارچه‌سازی با لایه AI
│   └── response_matcher.py # تطبیق پاسخ‌های آماده بر اساس امتیاز کلیدواژه‌ها
└── middleware/           # میان‌افزارهای امنیتی
    └── rate_limiting.py  # محدودسازی نرخ درخواست‌ها
```

## مدل‌های داده

### ChatbotSession
جلسه چت‌بات که تمام مکالمات کاربر را نگهداری می‌کند.

**فیلدهای مهم:**
- `user`: کاربر (مشتری یا فروشنده)
- `session_type`: نوع جلسه (`client` یا `vendor`)
- `status`: وضعیت جلسه (`active`, `paused`, `completed`, `expired`)
- `context_data`: داده‌های زمینه‌ای مکالمه
- `expires_at`: زمان انقضای جلسه

### Conversation
مکالمه خاص در یک جلسه.

**فیلدهای مهم:**
- `session`: جلسه مربوطه
- `conversation_type`: نوع مکالمه (`size_recommendation`, `product_inquiry`, `bespoke_consultation`, etc.)
- `title`: عنوان مکالمه
- `summary`: خلاصه مکالمه

### Message
پیام‌های رد و بدل شده در مکالمه.

**فیلدهای مهم:**
- `conversation`: مکالمه مربوطه
- `sender_type`: نوع فرستنده (`user`, `bot`, `system`)
- `message_type`: نوع پیام (`text`, `quick_reply`, `attachment`, etc.)
- `content`: محتوای پیام
- `ai_confidence`: درجه اطمینان AI
- `is_sensitive`: آیا پیام حاوی داده‌های حساس است؟

### ChatbotResponse
پاسخ‌های از پیش تعریف شده چت‌بات بر اساس تطبیق کلیدواژه‌ها.

**فیلدهای مهم:**
- `category`: دسته‌بندی پاسخ
- `target_user`: کاربر هدف (`client`, `vendor`, `both`)
- `trigger_keywords`: کلمات کلیدی محرک
- `response_text`: متن پاسخ
- `priority`: اولویت پاسخ

## API Endpoints

### مشتریان (Clients)

#### شروع جلسه
```http
POST /chatbot/api/client/start-session/
```

#### ارسال پیام
```http
POST /chatbot/api/client/send-message/
Content-Type: application/json

{
    "message": "نحوه اندازه‌گیری دور سینه چگونه است؟",
    "message_type": "text",
    "context": {}
}
```

#### شروع ارزیابی سایز
```http
POST /chatbot/api/client/size-assessment/
```

#### ثبت درخواست سفارش دوخت سفارشی (Bespoke)
```http
POST /chatbot/api/client/bespoke-consultation/
Content-Type: application/json

{
    "tailoring_type": "کت و شلوار سفارشی",
    "preferred_date": "2026-07-15",
    "urgency": "medium"
}
```

### فروشندگان / خیاط‌ها (Vendors)

#### شروع جلسه
```http
POST /chatbot/api/vendor/start-session/
```

#### پشتیبانی کاتالوگ
```http
POST /chatbot/api/vendor/catalog-support/
Content-Type: application/json

{
    "measurements": ["Coats", "Jackets"],
    "height_cm": 180,
    "gender": "M",
    "fit_preference": "slim"
}
```

#### مشخصات فنی محصول
```http
POST /chatbot/api/vendor/product-specifications/
Content-Type: application/json

{
    "product_sku": "SKU-992384-WOOL",
    "client_size": "L"
}
```

#### دریافت الگوی دوخت
```http
GET /chatbot/api/vendor/tailoring-guidelines/?condition=TweedCoat&severity=complex
```

#### جستجو در مراجع طراحی
```http
GET /chatbot/api/vendor/search-design-references/?query=wool+blends&specialty=Outerwear
```

## تنظیمات (Settings)

### فایل settings.py پروژه
```python
INSTALLED_APPS = [
    # ...
    'apps.chatbot',
    # ...
]

MIDDLEWARE = [
    # ...
    'apps.chatbot.middleware.rate_limiting.ChatbotRateLimitMiddleware',
    'apps.chatbot.middleware.rate_limiting.ChatbotSecurityMiddleware',
    # ...
]

# تنظیمات اختصاصی چت‌بات فشن‌استار
CHATBOT_SETTINGS = {
    'DEFAULT_SESSION_TIMEOUT': 3600,  # 1 ساعت
    'MAX_MESSAGE_LENGTH': 4000,
    'ENABLE_RATE_LIMITING': True,
    'AI_CONFIDENCE_THRESHOLD': 0.7,
    'CLIENT_CHATBOT': {
        'MAX_DAILY_SESSIONS': 10,
        'SESSION_TIMEOUT': 1800,  # 30 دقیقه
    },
    'VENDOR_CHATBOT': {
        'MAX_DAILY_SESSIONS': 50,
        'SESSION_TIMEOUT': 3600,  # 1 ساعت
    }
}
```

### متغیرهای محیطی
```bash
CHATBOT_SESSION_TIMEOUT=3600
CHATBOT_MAX_MESSAGE_LENGTH=4000
CHATBOT_ENABLE_RATE_LIMITING=true
CHATBOT_AI_CONFIDENCE_THRESHOLD=0.7
```

## امنیت

### محدودسازی نرخ درخواست (Rate Limiting)
- **ارسال پیام عمومی**: حداکثر 30 پیام در دقیقه به ازای هر کاربر
- **شروع جلسه جدید**: حداکثر 5 جلسه در 5 دقیقه
- **تحلیل و پشتیبانی کاتالوگ**: حداکثر 15 درخواست در 10 دقیقه

### فیلتر محتوای حساس
سیستم محتوای حساس مانند شماره کارت بانکی، رمزهای عبور و کدهای ملی را به صورت خودکار شناسایی کرده و پیش از ارسال، نسبت به ماسک کردن یا رد پیام اقدام می‌کند.

### مجوزها و دسترسی‌ها (Permissions)
تمام API ها نیاز به احراز هویت دارند و سطح دسترسی‌ها بر اساس نوع نقش کاربر (`client` و `vendor`) کنترل می‌شود.

## استفاده در محیط تولید

### اعمال Migration ها
```bash
python manage.py makemigrations chatbot
python manage.py migrate
```

### بارگذاری پاسخ‌های از پیش تعیین شده اولیه
```bash
python manage.py loaddata initial_responses
```

### پاکسازی خودکار جلسات منقضی‌شده
پاکسازی جلسات قدیمی با استفاده از Celery task زیر انجام می‌شود:
```python
# tasks.py
from celery import shared_task
from django.utils import timezone
from datetime import timedelta
from .models import ChatbotSession

@shared_task
def cleanup_old_sessions():
    """پاکسازی جلسات قدیمی و غیرفعال"""
    cutoff_date = timezone.now() - timedelta(days=30)
    ChatbotSession.objects.filter(
        last_activity__lt=cutoff_date,
        status__in=['completed', 'expired']
    ).delete()
```

## توسعه و تست

### اجرای تست‌های چت‌بات
```bash
python manage.py test apps.chatbot
```

### تست Coverage
```bash
coverage run --source='apps/chatbot' manage.py test apps.chatbot
coverage report
```

### مجوزها
این پلتفرم تحت امتیاز و مجوز اختصاصی پلتفرم فشن‌استار (Fashionistar) توسعه یافته است.