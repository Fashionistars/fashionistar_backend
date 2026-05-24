# اپلیکیشن جستجو (search)

این اپلیکیشن بر اساس مستندات نمونه در `agent/sample_codes/search` پیاده‌سازی شده و شامل:

- مدل‌ها: `SearchableContent`, `SearchQuery`, `SearchResult`
- سرویس جستجو هیبریدی: FULLTEXT (برای MySQL) + fallback ساده برای sqlite
- API ها: `/api/search/content/`, `/api/search/suggestions/`, `/api/search/analytics/`
- فایل‌های مهاجرت و تنظیمات deployment (افزودن به INSTALLED_APPS)

## نکات و محدودیت‌ها

- دیتابیس پیش‌فرض پروژه sqlite است. FULLTEXT MySQL در مهاجرت `0002_fulltext_mysql` فقط در صورت استفاده از MySQL اعمال می‌شود. در sqlite از جستجوی ساده `icontains` استفاده شده است.
- مدل `encounters.Encounter` و سرویس امبدینگ در این مخزن وجود ندارد. برای جلوگیری از وابستگی سخت، فیلد `encounter` اختیاری (nullable) است و بخش semantic-rerank به‌صورت placeholder اجرا می‌شود.
- برای یکپارچه‌سازی کامل با embeddings و Encounter، باید سرویس‌ها/مدل‌های مربوطه اضافه شوند.

## نصب

- فایل `deployment/settings_additions.py` را به تنظیمات پروژه اضافه کنید (یا معادل آن را اعمال کنید).
- آدرس‌ها با `deployment/urls_additions.py` اضافه می‌شوند.
- مایگریشن:

```bash
python manage.py makemigrations search
python manage.py migrate
```

## تست سریع

- ایجاد چند رکورد `SearchableContent` و فراخوانی `/api/search/content/?q=متن`

## API Spec

- مستندات در `docs/api_spec.yaml` موجود است.