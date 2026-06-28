"""
پنل مدیریت سیستم چت‌بات
Chatbot Admin Panel
"""

from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils.safestring import mark_safe
from .models import ChatbotSession, Conversation, Message, ChatbotResponse


@admin.register(ChatbotSession)
class ChatbotSessionAdmin(admin.ModelAdmin):
    """
    پنل مدیریت جلسات چت‌بات
    """
    list_display = [
        'id', 'user', 'session_type', 'status', 
        'started_at', 'last_activity', 'conversation_count'
    ]
    list_filter = [
        'session_type', 'status', 'started_at'
    ]
    search_fields = [
        'user__phone_number', 'user__first_name', 'user__last_name'
    ]
    readonly_fields = [
        'id', 'started_at', 'duration_display'
    ]
    fieldsets = (
        ('اطلاعات اصلی', {
            'fields': ('id', 'user', 'session_type', 'status')
        }),
        ('زمان‌بندی', {
            'fields': ('started_at', 'last_activity', 'ended_at', 'expires_at', 'duration_display')
        }),
        ('داده‌ها', {
            'fields': ('context_data', 'metadata'),
            'classes': ('collapse',)
        }),
    )
    
    def conversation_count(self, obj):
        """
        تعداد مکالمات مرتبط با یک جلسه را برمی‌گرداند.
        
        برای شیء جلسه (obj) تعداد مکالمات مرتبط را محاسبه می‌کند و در صورتی که بزرگتر از صفر باشد، یک رشته HTML ایمن شامل لینک به صفحه‌ی لیست مکالمات با فیلتر مربوط به آن جلسه را برمی‌گرداند؛ در غیر اینصورت متن «0 مکالمه» را بازمی‌گرداند. این خروجی برای نمایش در ستون‌های لیست ادمین مناسب است.
        """
        count = obj.conversations.count()
        if count > 0:
            url = reverse('admin:chatbot_conversation_changelist') + f'?session__id__exact={obj.id}'
            return format_html('<a href="{}">{} مکالمه</a>', url, count)
        return '0 مکالمه'
    conversation_count.short_description = 'تعداد مکالمات'
    
    def duration_display(self, obj):
        """
        یک خطی: مقدار مدت زمان جلسه را به صورت رشته‌ی فرمت‌شده‌ی `HH:MM:SS` برمی‌گرداند.
        
        توضیح بیشتر: این متد از فیلد `duration` شیء ورودی (انتظار می‌رود نوع آن `datetime.timedelta` باشد) مقدار ثانیه‌ها را استخراج کرده و آن را به ساعت، دقیقه و ثانیه تبدیل و به صورت صفرپر شده (مثال: `01:05:09`) بازمی‌گرداند. مناسب برای نمایش در ستون‌های لیست ادمین یا فیلدهای readonly.
        """
        duration = obj.duration
        hours, remainder = divmod(duration.total_seconds(), 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{int(hours):02d}:{int(minutes):02d}:{int(seconds):02d}"
    duration_display.short_description = 'مدت زمان'


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    """
    پنل مدیریت مکالمات
    """
    list_display = [
        'id', 'session_user', 'conversation_type', 'title',
        'is_active', 'started_at', 'message_count_display'
    ]
    list_filter = [
        'conversation_type', 'is_active', 'started_at',
        'session__session_type'
    ]
    search_fields = [
        'title', 'session__user__phone_number',
        'session__user__first_name', 'session__user__last_name'
    ]
    readonly_fields = [
        'id', 'started_at', 'message_count_display', 'last_message_time'
    ]
    fieldsets = (
        ('اطلاعات اصلی', {
            'fields': ('id', 'session', 'conversation_type', 'title', 'is_active')
        }),
        ('زمان‌بندی', {
            'fields': ('started_at', 'updated_at', 'last_message_time')
        }),
        ('آمار', {
            'fields': ('message_count_display',)
        }),
        ('محتوا', {
            'fields': ('summary', 'tags'),
            'classes': ('collapse',)
        }),
        ('داده‌ها', {
            'fields': ('metadata',),
            'classes': ('collapse',)
        }),
    )
    
    def session_user(self, obj):
        """
        یک‌خطی:
        بازگرداندن کاربر مرتبط با جلسهٔ یک Conversation.
        
        توضیحات:
        این متد کاربر (instance از مدل User یا None) مرتبط با session مربوط به شیٔ Conversation داده‌شده را برمی‌گرداند. برای استفاده در نمایش لیست ادمین (list_display) طراحی شده است تا نام یا شناسه کاربر مربوط به جلسهٔ هر مکالمه را نشان دهد.
        
        Parameters:
            obj (Conversation): نمونهٔ مکالمه که دارای رابطهٔ `session` است.
        
        Returns:
            User | None: شیٔ کاربر مرتبط با آن session یا None در صورتی که session یا user مقدار نداشته باشد.
        """
        return obj.session.user
    session_user.short_description = 'کاربر'
    
    def message_count_display(self, obj):
        """
        یک نمایش‌دهنده برای ستون «تعداد پیام‌ها» در پنل ادمین Conversation.
        
        در صورتی که مکالمه دارای پیام باشد، یک لینک HTML امن به لیست پیام‌ها در ادمین باز می‌گرداند که با فیلتر conversation__id__exact به آن مکالمه اشاره می‌کند (مثال: "3 پیام"). در غیر اینصورت رشتهٔ سادهٔ "0 پیام" بازگردانده می‌شود.
        
        Parameters:
            obj (Conversation): نمونهٔ Conversation که شمار پیام‌های مربوط به آن در صفت `message_count` قرار دارد.
        
        Returns:
            str: متن یا HTML ایمن‌شده (با format_html) حاوی شمار پیام‌ها؛ در صورت وجود پیام، مقدار به صورت لینک قابل کلیک بازگردانده می‌شود.
        """
        count = obj.message_count
        if count > 0:
            url = reverse('admin:chatbot_message_changelist') + f'?conversation__id__exact={obj.id}'
            return format_html('<a href="{}">{} پیام</a>', url, count)
        return '0 پیام'
    message_count_display.short_description = 'تعداد پیام‌ها'


class MessageInline(admin.TabularInline):
    """
    نمایش پیام‌ها به صورت inline
    """
    model = Message
    extra = 0
    readonly_fields = ['id', 'created_at', 'processing_time']
    fields = [
        'sender_type', 'message_type', 'content', 
        'ai_confidence', 'is_sensitive', 'created_at'
    ]
    
    def has_add_permission(self, request, obj=None):
        """
        همیشه اجازه افزودن آیتم جدید را غیرفعال می‌کند (برای استفاده در MessageInline).
        
        این متد به‌طور صریح افزودن ردیف‌های جدید از طریق بخش inline در پنل ادمین را ممنوع می‌کند و در نتیجه در صفحات add/change مربوط به مدل اصلی دکمه یا فرم افزودن عنصر inline نمایش داده نخواهد شد. پارامتر `obj` در تصمیم‌گیری نادیده گرفته می‌شود؛ همیشه مقدار بولی False برگردانده می‌شود.
        """
        return False


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    """
    پنل مدیریت پیام‌ها
    """
    list_display = [
        'id', 'conversation_title', 'sender_type', 'message_type',
        'content_preview', 'ai_confidence', 'is_sensitive', 'created_at'
    ]
    list_filter = [
        'sender_type', 'message_type', 'is_sensitive', 'created_at',
        'conversation__session__session_type'
    ]
    search_fields = [
        'content', 'conversation__title',
        'conversation__session__user__phone_number'
    ]
    readonly_fields = [
        'id', 'created_at', 'processing_time'
    ]
    fieldsets = (
        ('اطلاعات اصلی', {
            'fields': ('id', 'conversation', 'sender_type', 'message_type')
        }),
        ('محتوا', {
            'fields': ('content', 'response_data')
        }),
        ('تحلیل AI', {
            'fields': ('ai_confidence', 'processing_time'),
            'classes': ('collapse',)
        }),
        ('امنیت', {
            'fields': ('is_sensitive',)
        }),
        ('زمان‌بندی', {
            'fields': ('created_at', 'edited_at')
        }),
        ('داده‌ها', {
            'fields': ('metadata',),
            'classes': ('collapse',)
        }),
    )
    
    def conversation_title(self, obj):
        """
        بازگرداندن عنوان قابل نمایش یک پیام بر اساس مکالمه مرتبط.
        
        اگر پیام به یک Conversation مرتبط باشد، عنوان آن Conversation را برمی‌گرداند؛ در غیر این صورت یک عنوان جایگزین به‌صورت "مکالمه <conversation_type>" بازمی‌گرداند.
        
        Parameters:
            obj (Message): نمونه‌ی پیام (انتظار می‌رود صفت `conversation` روی آن تنظیم شده باشد).
        
        Returns:
            str: عنوان نمایش‌شده برای ستون لیست در پنل ادمین.
        """
        return obj.conversation.title or f"مکالمه {obj.conversation.conversation_type}"
    conversation_title.short_description = 'مکالمه'
    
    def content_preview(self, obj):
        """
        پیش‌نمایش کوتاه و امن محتوای یک پیام برای نمایش در لیست ادمین.
        
        این متد محتوای پیام را تا ۵۰ کاراکتر کوتاه می‌کند و در صورت بیشتر بودن، انتهای آن را با "..." علامت‌گذاری می‌کند. اگر پیام حساس (is_sensitive) علامت‌گذاری شده باشد، متن به‌صورت HTML امن با رنگ قرمز برگردانده می‌شود تا در نمای لیست ادمین برجسته شود.
        
        Parameters:
            obj: نمونهٔ Message که دارای فیلدهای `content` و `is_sensitive` است؛ متد روی این نمونه عمل می‌کند.
        
        Returns:
            str: رشتهٔ پیش‌نمایش؛ در حالت حساس، یک مقدار HTML امن (تولیدشده توسط `format_html`) برگردانده می‌شود، در غیر این صورت متن سادهٔ کوتاه‌شده.
        """
        content = obj.content
        if len(content) > 50:
            content = content[:50] + '...'
        
        if obj.is_sensitive:
            return format_html('<span style="color: red;">{}</span>', content)
        return content
    content_preview.short_description = 'محتوا'


@admin.register(ChatbotResponse)
class ChatbotResponseAdmin(admin.ModelAdmin):
    """
    پنل مدیریت پاسخ‌های چت‌بات
    """
    list_display = [
        'id', 'category', 'target_user', 'response_preview',
        'priority', 'is_active', 'created_at'
    ]
    list_filter = [
        'category', 'target_user', 'is_active', 'priority'
    ]
    search_fields = [
        'response_text', 'trigger_keywords'
    ]
    readonly_fields = [
        'id', 'created_at', 'updated_at'
    ]
    fieldsets = (
        ('اطلاعات اصلی', {
            'fields': ('id', 'category', 'target_user', 'is_active', 'priority')
        }),
        ('محرک‌ها', {
            'fields': ('trigger_keywords',)
        }),
        ('پاسخ', {
            'fields': ('response_text', 'response_data')
        }),
        ('زمان‌بندی', {
            'fields': ('created_at', 'updated_at')
        }),
    )
    
    def response_preview(self, obj):
        """
        خلاصه: پیش‌نمایش متنی از فیلد `response_text` برای نمایش در لیست ادمین.
        
        توضیح: متن پاسخ را تا حداکثر ۵۰ کاراکتر برش می‌دهد و در صورت کوتاه‌سازی، انتهای آن را با "..." مشخص می‌کند.
        
        Parameters:
            obj (ChatbotResponse): شیء مدل پاسخ که دارای صفت `response_text` است.
        
        Returns:
            str: رشته‌ی پیش‌نمایش (حداکثر ۵۰ کاراکتر، با "..." در صورت کوتاه‌شدن).
        """
        text = obj.response_text
        if len(text) > 50:
            text = text[:50] + '...'
        return text
    response_preview.short_description = 'پیش‌نمایش پاسخ'


# تنظیمات اضافی admin
admin.site.site_header = 'پنل مدیریت سیستم چت‌بات هلسا'
admin.site.site_title = 'مدیریت چت‌بات'
admin.site.index_title = 'خوش آمدید به پنل مدیریت چت‌بات'