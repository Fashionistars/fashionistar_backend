# سیستم چت‌بات هلسا

سیستم چت‌بات هوشمند برای بیماران و پزشکان در پلتفرم هلسا که با استفاده از هوش مصنوعی پاسخ‌های مناسب و کاربردی ارائه می‌دهد.

## ویژگی‌ها

### چت‌بات بیماران
- **ارزیابی علائم**: بررسی اولیه علائم و ارائه راهنمایی
- **اطلاعات دارویی**: دریافت اطلاعات در مورد داروها
- **نوبت‌گیری**: رزرو نوبت با پزشکان
- **راهنمایی کلی**: پاسخ به سؤالات عمومی سلامت

### چت‌بات پزشکان
- **پشتیبانی تشخیصی**: کمک در تشخیص بر اساس علائم
- **اطلاعات دارویی پیشرفته**: تداخلات، دوزاژ، عوارض جانبی
- **پروتکل‌های درمان**: راهنماهای درمانی استاندارد
- **جستجو در مراجع**: دسترسی به منابع علمی پزشکی

## معماری سیستم

```
chatbot/
├── models.py              # مدل‌های پایگاه داده
├── serializers.py         # سریالایزرهای REST API
├── views.py              # ViewSet ها و API endpoints
├── urls.py               # تعریف URL ها
├── admin.py              # پنل مدیریت Django
├── settings.py           # تنظیمات اپ
├── tests.py              # تست‌های جامع
├── services/             # سرویس‌های کسب‌وکار
│   ├── base_chatbot.py   # کلاس پایه چت‌بات
│   ├── patient_chatbot.py # سرویس چت‌بات بیمار
│   ├── doctor_chatbot.py  # سرویس چت‌بات پزشک
│   ├── ai_integration.py  # یکپارچه‌سازی AI
│   └── response_matcher.py # تطبیق پاسخ‌ها
└── middleware/           # میان‌افزارهای امنیتی
    └── rate_limiting.py  # محدودسازی نرخ درخواست
```

## مدل‌های داده

### ChatbotSession
جلسه چت‌بات که تمام مکالمات کاربر را نگهداری می‌کند.

**فیلدهای مهم:**
- `user`: کاربر (بیمار یا پزشک)
- `session_type`: نوع جلسه (`patient` یا `doctor`)
- `status`: وضعیت جلسه (`active`, `paused`, `completed`, `expired`)
- `context_data`: داده‌های زمینه‌ای مکالمه
- `expires_at`: زمان انقضای جلسه

### Conversation
مکالمه خاص در یک جلسه.

**فیلدهای مهم:**
- `session`: جلسه مربوطه
- `conversation_type`: نوع مکالمه (`symptom_check`, `medication_info`, `appointment`, etc.)
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
- `is_sensitive`: آیا پیام حساس است؟

### ChatbotResponse
پاسخ‌های از پیش تعریف شده چت‌بات.

**فیلدهای مهم:**
- `category`: دسته‌بندی پاسخ
- `target_user`: کاربر هدف (`patient`, `doctor`, `both`)
- `trigger_keywords`: کلمات کلیدی محرک
- `response_text`: متن پاسخ
- `priority`: اولویت پاسخ

## API Endpoints

### بیماران

#### شروع جلسه
```http
POST /chatbot/api/patient/start-session/
```

#### ارسال پیام
```http
POST /chatbot/api/patient/send-message/
Content-Type: application/json

{
    "message": "سردرد دارم",
    "message_type": "text",
    "context": {}
}
```

#### شروع ارزیابی علائم
```http
POST /chatbot/api/patient/symptom-assessment/
```

#### ارسال پاسخ‌های ارزیابی
```http
POST /chatbot/api/patient/submit-assessment/
Content-Type: application/json

{
    "main_symptom": "سردرد",
    "symptom_duration": "۲ روز",
    "symptom_severity": 7
}
```

#### درخواست نوبت
```http
POST /chatbot/api/patient/request-appointment/
Content-Type: application/json

{
    "specialty": "پزشک عمومی",
    "preferred_time": "صبح",
    "urgency": "medium"
}
```

### پزشکان

#### شروع جلسه
```http
POST /chatbot/api/doctor/start-session/
```

#### پشتیبانی تشخیصی
```http
POST /chatbot/api/doctor/diagnosis-support/
Content-Type: application/json

{
    "symptoms": ["سردرد", "تب", "گلودرد"],
    "patient_age": 30,
    "patient_gender": "M",
    "medical_history": "سابقه فشار خون"
}
```

#### اطلاعات دارو
```http
POST /chatbot/api/doctor/medication-info/
Content-Type: application/json

{
    "medication_name": "آسپرین",
    "patient_age": 45,
    "current_medications": ["متفورمین"]
}
```

#### پروتکل درمان
```http
GET /chatbot/api/doctor/treatment-protocol/?condition=سردرد&severity=moderate
```

#### جستجو در مراجع
```http
GET /chatbot/api/doctor/search-references/?query=diabetes&specialty=endocrinology
```

## تنظیمات

### فایل settings.py پروژه

```python
INSTALLED_APPS = [
    # ...
    'chatbot',
    # ...
]

MIDDLEWARE = [
    # ...
    'chatbot.middleware.rate_limiting.ChatbotRateLimitMiddleware',
    'chatbot.middleware.rate_limiting.ChatbotSecurityMiddleware',
    # ...
]

# تنظیمات اختصاصی چت‌بات
CHATBOT_SETTINGS = {
    'DEFAULT_SESSION_TIMEOUT': 3600,  # 1 ساعت
    'MAX_MESSAGE_LENGTH': 4000,
    'ENABLE_RATE_LIMITING': True,
    'AI_CONFIDENCE_THRESHOLD': 0.7,
    'PATIENT_CHATBOT': {
        'MAX_DAILY_SESSIONS': 10,
        'SESSION_TIMEOUT': 1800,  # 30 دقیقه
    },
    'DOCTOR_CHATBOT': {
        'MAX_DAILY_SESSIONS': 50,
        'SESSION_TIMEOUT': 3600,  # 1 ساعت
    }
}
```

### متغیرهای محیط

```bash
# تنظیمات چت‌بات
CHATBOT_SESSION_TIMEOUT=3600
CHATBOT_MAX_MESSAGE_LENGTH=4000
CHATBOT_ENABLE_RATE_LIMITING=true
CHATBOT_AI_CONFIDENCE_THRESHOLD=0.7
```

## امنیت

### Rate Limiting
- **پیام‌ها**: حداکثر 30 پیام در دقیقه
- **جلسات جدید**: حداکثر 5 جلسه در 5 دقیقه
- **پشتیبانی تشخیصی**: حداکثر 10 درخواست در 10 دقیقه

### فیلتر محتوای حساس
سیستم محتوای حساس مانند رمز عبور، شماره کارت و کد ملی را تشخیص داده و مانع از ارسال آن می‌شود.

### احراز هویت
تمام API ها نیاز به احراز هویت دارند و بر اساس نوع کاربر (بیمار/پزشک) دسترسی‌ها تعریف شده است.

## استفاده در تولید

### Migration ها
```bash
python manage.py makemigrations chatbot
python manage.py migrate
```

### جمع‌آوری فایل‌های Static
```bash
python manage.py collectstatic
```

### پاکسازی خودکار
برای پاکسازی جلسات قدیمی می‌توانید از Celery task استفاده کنید:

```python
# tasks.py
from celery import shared_task
from django.utils import timezone
from datetime import timedelta
from .models import ChatbotSession

@shared_task
def cleanup_old_sessions():
    """پاکسازی جلسات قدیمی"""
    cutoff_date = timezone.now() - timedelta(days=30)
    ChatbotSession.objects.filter(
        last_activity__lt=cutoff_date,
        status__in=['completed', 'expired']
    ).delete()
```

## نظارت و لاگ‌گذاری

### لاگ‌های مهم
- تعداد پیام‌ها و جلسات
- زمان پردازش AI
- خطاهای سیستم
- تلاش‌های ارسال محتوای حساس

### متریک‌های عملکرد
- میانگین زمان پاسخ
- درجه اطمینان AI
- نرخ موفقیت در پاسخ‌گویی
- تعداد جلسات فعال

## توسعه و تست

### اجرای تست‌ها
```bash
python manage.py test chatbot
```

### تست Coverage
```bash
coverage run --source='.' manage.py test chatbot
coverage report
```

### Linting
```bash
flake8 chatbot/
black chatbot/
```

## یکپارچه‌سازی‌های آتی

- **API های پزشکی خارجی**: اتصال به پایگاه‌داده‌های دارویی
- **سیستم نوبت‌گیری**: یکپارچه‌سازی با تقویم پزشکان
- **تحلیل احساسات**: تشخیص حالت روحی کاربر
- **پشتیبانی چندزبانه**: افزودن زبان‌های دیگر

## مشارکت

برای مشارکت در توسعه:

1. ابتدا Issue ایجاد کنید
2. Branch جدید بسازید
3. تغییرات را پیاده‌سازی کنید
4. تست‌های مربوطه را اضافه کنید
5. Pull Request ارسال کنید

## مجوز

این کد تحت مجوز اختصاصی هلسا/Medogram قرار دارد.