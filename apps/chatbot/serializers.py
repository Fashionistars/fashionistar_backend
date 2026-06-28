"""
سریالایزرهای سیستم چت‌بات
Chatbot Serializers
"""

from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import ChatbotSession, Conversation, Message, ChatbotResponse

User = get_user_model()


class UserBasicSerializer(serializers.ModelSerializer):
    """
    سریالایزر اطلاعات پایه کاربر
    """
    class Meta:
        model = User
        fields = ['id', 'first_name', 'last_name', 'phone_number']
        read_only_fields = ['id', 'phone_number']


class ChatbotSessionSerializer(serializers.ModelSerializer):
    """
    سریالایزر جلسه چت‌بات
    """
    user = UserBasicSerializer(read_only=True)
    duration = serializers.ReadOnlyField()
    is_active = serializers.ReadOnlyField()
    conversation_count = serializers.SerializerMethodField()
    
    class Meta:
        model = ChatbotSession
        fields = [
            'id', 'user', 'session_type', 'status', 'context_data',
            'started_at', 'last_activity', 'ended_at', 'expires_at',
            'duration', 'is_active', 'conversation_count', 'metadata'
        ]
        read_only_fields = [
            'id', 'user', 'started_at', 'last_activity', 'duration', 'is_active'
        ]
    
    def get_conversation_count(self, obj):
        """
        تعداد مکالمات مرتبط با یک جلسه چت‌بات را برمی‌گرداند.
        
        پارامترها:
            obj (ChatbotSession): نمونه‌ی جلسه‌ای که شمارش مکالمات مرتبط با آن انجام می‌شود.
        
        برگردانده:
            int: تعداد مدل‌های Conversation مرتبط با جلسه (استفاده از رابطه معکوس `conversations`).
        """
        return obj.conversations.count()


class MessageSerializer(serializers.ModelSerializer):
    """
    سریالایزر پیام‌ها
    """
    is_from_user = serializers.ReadOnlyField()
    is_from_bot = serializers.ReadOnlyField()
    
    class Meta:
        model = Message
        fields = [
            'id', 'sender_type', 'message_type', 'content', 'response_data',
            'ai_confidence', 'processing_time', 'is_sensitive',
            'created_at', 'edited_at', 'is_from_user', 'is_from_bot', 'metadata'
        ]
        read_only_fields = [
            'id', 'created_at', 'edited_at', 'is_from_user', 'is_from_bot'
        ]
    
    def validate_content(self, value):
        """
        اعتبارسنجی و تمیزسازی محتوای پیام کاربر.
        
        این متد محتوای ورودی را بررسی می‌کند: مقدار باید غیرخالی پس از حذف فضاهای اطراف باشد و طول آن نباید از ۴۰۰۰ کاراکتر بیشتر باشد. در صورت معتبر بودن، رشتهٔ پیغام با حذف فاصله‌های انتها و ابتدا بازگردانده می‌شود.
        
        Parameters:
            value (str): متن پیام ورودی که باید اعتبارسنجی و trim شود.
        
        Returns:
            str: متن پیام پس از حذف فاصله‌های جانبی.
        
        Raises:
            serializers.ValidationError: اگر پیام خالی باشد یا تنها شامل فضا باشد، یا طول آن بیش از ۴۰۰۰ کاراکتر باشد.
        """
        if not value or not value.strip():
            raise serializers.ValidationError("محتوای پیام نمی‌تواند خالی باشد.")
        
        if len(value) > 4000:
            raise serializers.ValidationError("محتوای پیام نمی‌تواند بیشتر از ۴۰۰۰ کاراکتر باشد.")
        
        return value.strip()


class ConversationSerializer(serializers.ModelSerializer):
    """
    سریالایزر مکالمات
    """
    session = ChatbotSessionSerializer(read_only=True)
    messages = MessageSerializer(many=True, read_only=True)
    message_count = serializers.ReadOnlyField()
    last_message_time = serializers.ReadOnlyField()
    
    class Meta:
        model = Conversation
        fields = [
            'id', 'session', 'conversation_type', 'title', 'is_active',
            'started_at', 'updated_at', 'summary', 'tags', 'messages',
            'message_count', 'last_message_time', 'metadata'
        ]
        read_only_fields = [
            'id', 'session', 'started_at', 'updated_at', 'message_count', 'last_message_time'
        ]


class ConversationListSerializer(serializers.ModelSerializer):
    """
    سریالایزر فهرست مکالمات (بدون پیام‌ها)
    """
    message_count = serializers.ReadOnlyField()
    last_message_time = serializers.ReadOnlyField()
    
    class Meta:
        model = Conversation
        fields = [
            'id', 'conversation_type', 'title', 'is_active',
            'started_at', 'updated_at', 'message_count', 'last_message_time'
        ]


class ChatbotResponseSerializer(serializers.ModelSerializer):
    """
    سریالایزر پاسخ‌های چت‌بات
    """
    class Meta:
        model = ChatbotResponse
        fields = [
            'id', 'category', 'target_user', 'trigger_keywords',
            'response_text', 'response_data', 'is_active', 'priority',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


# سریالایزرهای درخواست و پاسخ


class SendMessageRequestSerializer(serializers.Serializer):
    """
    سریالایزر درخواست ارسال پیام
    """
    message = serializers.CharField(
        max_length=4000,
        help_text="محتوای پیام کاربر"
    )
    message_type = serializers.ChoiceField(
        choices=Message.MESSAGE_TYPES,
        default='text',
        help_text="نوع پیام"
    )
    context = serializers.JSONField(
        required=False,
        help_text="زمینه اضافی برای پردازش پیام"
    )
    
    def validate_message(self, value):
        """
        اعتبارسنجی متن پیام ارسال‌شده توسط کاربر.
        
        پارامترها:
            value (str): متن پیام ورودی؛ امکان دارد شامل فضاهای خالی اطراف باشد.
        
        توضیحات:
            پیام باید دارای حداقل یک کاراکتر غیرِ فاصله باشد. فضای خالی آغاز و پایان پیام حذف (strip) می‌شود
            و مقدار مرتب‌شده بازگردانده می‌گردد.
        
        بازگشت:
            str: متن پیام پردازش‌شده (بدون فاصله‌های زائد).
        
        خطاها:
            serializers.ValidationError: اگر پیام خالی یا صرفاً شامل فاصله باشد، با پیام خطای فارسی پرتاب می‌شود.
        """
        if not value or not value.strip():
            raise serializers.ValidationError("پیام نمی‌تواند خالی باشد.")
        return value.strip()


class ChatbotResponseDataSerializer(serializers.Serializer):
    """
    سریالایزر داده‌های پاسخ چت‌بات
    """
    content = serializers.CharField(help_text="محتوای پاسخ")
    message_type = serializers.CharField(help_text="نوع پیام")
    response_data = serializers.JSONField(
        required=False,
        help_text="داده‌های ساختاریافته پاسخ"
    )
    ai_confidence = serializers.FloatField(
        required=False,
        help_text="درجه اطمینان AI"
    )
    processing_time = serializers.FloatField(
        required=False,
        help_text="زمان پردازش به ثانیه"
    )
    quick_replies = serializers.ListField(
        child=serializers.DictField(),
        required=False,
        help_text="پاسخ‌های سریع پیشنهادی"
    )


class SendMessageResponseSerializer(serializers.Serializer):
    """
    سریالایزر پاسخ ارسال پیام
    """
    response = ChatbotResponseDataSerializer(help_text="پاسخ چت‌بات")
    user_message_id = serializers.UUIDField(help_text="شناسه پیام کاربر")
    bot_message_id = serializers.UUIDField(help_text="شناسه پیام ربات")
    conversation_id = serializers.UUIDField(help_text="شناسه مکالمه")
    session_id = serializers.UUIDField(help_text="شناسه جلسه")


class StartSessionResponseSerializer(serializers.Serializer):
    """
    سریالایزر پاسخ شروع جلسه
    """
    session = ChatbotSessionSerializer(help_text="اطلاعات جلسه")
    greeting_message = ChatbotResponseDataSerializer(
        required=False,
        help_text="پیام خوشامدگویی"
    )
    quick_replies = serializers.ListField(
        child=serializers.DictField(),
        required=False,
        help_text="پاسخ‌های سریع اولیه"
    )


class SymptomAssessmentRequestSerializer(serializers.Serializer):
    """
    سریالایزر درخواست ارزیابی علائم (بیمار)
    """
    main_symptom = serializers.CharField(help_text="علامت اصلی")
    symptom_duration = serializers.CharField(help_text="مدت زمان علائم")
    symptom_severity = serializers.IntegerField(
        min_value=1,
        max_value=10,
        help_text="شدت علائم (۱-۱۰)"
    )
    additional_symptoms = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        help_text="علائم اضافی"
    )
    medical_history = serializers.CharField(
        required=False,
        help_text="سابقه پزشکی"
    )


class DiagnosisSupportRequestSerializer(serializers.Serializer):
    """
    سریالایزر درخواست پشتیبانی تشخیصی (پزشک)
    """
    symptoms = serializers.ListField(
        child=serializers.CharField(),
        help_text="فهرست علائم"
    )
    patient_age = serializers.IntegerField(
        required=False,
        min_value=0,
        max_value=150,
        help_text="سن بیمار"
    )
    patient_gender = serializers.ChoiceField(
        choices=[('M', 'مرد'), ('F', 'زن'), ('O', 'سایر')],
        required=False,
        help_text="جنسیت بیمار"
    )
    medical_history = serializers.CharField(
        required=False,
        help_text="سابقه پزشکی بیمار"
    )
    current_medications = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        help_text="داروهای فعلی"
    )


class MedicationInfoRequestSerializer(serializers.Serializer):
    """
    سریالایزر درخواست اطلاعات دارو
    """
    medication_name = serializers.CharField(help_text="نام دارو")
    patient_age = serializers.IntegerField(
        required=False,
        min_value=0,
        max_value=150,
        help_text="سن بیمار"
    )
    patient_weight = serializers.FloatField(
        required=False,
        min_value=0,
        help_text="وزن بیمار (کیلوگرم)"
    )
    allergies = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        help_text="آلرژی‌های شناخته شده"
    )
    current_medications = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        help_text="داروهای فعلی"
    )


class AppointmentRequestSerializer(serializers.Serializer):
    """
    سریالایزر درخواست نوبت
    """
    specialty = serializers.CharField(
        required=False,
        help_text="تخصص مورد نیاز"
    )
    preferred_date = serializers.DateField(
        required=False,
        help_text="تاریخ ترجیحی"
    )
    preferred_time = serializers.CharField(
        required=False,
        help_text="زمان ترجیحی"
    )
    urgency = serializers.ChoiceField(
        choices=[
            ('low', 'کم'),
            ('medium', 'متوسط'),
            ('high', 'بالا'),
            ('emergency', 'اورژانس')
        ],
        default='medium',
        help_text="سطح فوریت"
    )
    reason = serializers.CharField(
        required=False,
        help_text="دلیل مراجعه"
    )


class ConversationHistorySerializer(serializers.Serializer):
    """
    سریالایزر تاریخچه مکالمه
    """
    conversation = ConversationListSerializer(help_text="اطلاعات مکالمه")
    messages = MessageSerializer(many=True, help_text="پیام‌های مکالمه")
    total_messages = serializers.IntegerField(help_text="تعداد کل پیام‌ها")
    has_more = serializers.BooleanField(
        help_text="آیا پیام‌های بیشتری وجود دارد؟"
    )