"""
الگوهای Serializer پایه
Base Serializer Patterns
"""

from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.core.validators import RegexValidator
from decimal import Decimal
import re
from typing import Dict, Any

User = get_user_model()


class BaseSerializer(serializers.Serializer):
    """
    Serializer پایه با قابلیت‌های استاندارد
    """
    
    def validate_empty_values(self, data):
        """حذف whitespace از رشته‌ها"""
        if isinstance(data, str):
            data = data.strip()
        return super().validate_empty_values(data)
    
    def to_representation(self, instance):
        """تبدیل None به رشته خالی در خروجی"""
        data = super().to_representation(instance)
        for key, value in data.items():
            if value is None and isinstance(self.fields.get(key), serializers.CharField):
                data[key] = ''
        return data


class BaseModelSerializer(serializers.ModelSerializer):
    """
    ModelSerializer پایه با فیلدهای استاندارد
    """
    created_at = serializers.DateTimeField(read_only=True, format='%Y-%m-%d %H:%M:%S')
    updated_at = serializers.DateTimeField(read_only=True, format='%Y-%m-%d %H:%M:%S')
    created_by = serializers.StringRelatedField(read_only=True)
    
    class Meta:
        abstract = True
        read_only_fields = ['id', 'created_at', 'updated_at', 'created_by']
    
    def create(self, validated_data):
        """افزودن created_by خودکار"""
        request = self.context.get('request')
        if request and hasattr(request, 'user'):
            validated_data['created_by'] = request.user
        return super().create(validated_data)


class UserSerializer(BaseModelSerializer):
    """
    Serializer استاندارد برای User
    """
    full_name = serializers.SerializerMethodField()
    user_type_display = serializers.CharField(source='get_user_type_display', read_only=True)
    
    class Meta:
        model = User
        fields = [
            'id', 'username', 'email', 'first_name', 'last_name',
            'full_name', 'user_type', 'user_type_display',
            'is_active', 'created_at'
        ]
        read_only_fields = ['id', 'username', 'created_at']
    
    def get_full_name(self, obj):
        """نام کامل کاربر"""
        return f"{obj.first_name} {obj.last_name}".strip() or obj.username


class PhoneNumberField(serializers.CharField):
    """
    فیلد شماره تلفن ایران
    """
    default_validators = [
        RegexValidator(
            regex=r'^(\+98|0)?9\d{9}$',
            message='شماره موبایل معتبر نیست. فرمت صحیح: 09123456789'
        )
    ]
    
    def to_internal_value(self, data):
        """نرمال‌سازی شماره تلفن"""
        if data:
            # حذف فاصله‌ها
            data = re.sub(r'\s+', '', data)
            # تبدیل اعداد فارسی به انگلیسی
            persian_numbers = '۰۱۲۳۴۵۶۷۸۹'
            english_numbers = '0123456789'
            translation_table = str.maketrans(persian_numbers, english_numbers)
            data = data.translate(translation_table)
            # حذف +98 و تبدیل به 0
            if data.startswith('+98'):
                data = '0' + data[3:]
            elif not data.startswith('0'):
                data = '0' + data
                
        return super().to_internal_value(data)


class NationalCodeField(serializers.CharField):
    """
    فیلد کد ملی ایران
    """
    default_validators = [
        RegexValidator(
            regex=r'^\d{10}$',
            message='کد ملی باید 10 رقم باشد'
        )
    ]
    
    def validate(self, value):
        """اعتبارسنجی کد ملی"""
        if not self._is_valid_national_code(value):
            raise serializers.ValidationError('کد ملی معتبر نیست')
        return value
    
    def _is_valid_national_code(self, code):
        """الگوریتم اعتبارسنجی کد ملی"""
        if not code or len(code) != 10:
            return False
            
        check = int(code[9])
        s = sum(int(code[i]) * (10 - i) for i in range(9)) % 11
        return check == (s if s < 2 else 11 - s)


class AmountField(serializers.DecimalField):
    """
    فیلد مبلغ مالی (ریال)
    """
    def __init__(self, **kwargs):
        kwargs['max_digits'] = kwargs.get('max_digits', 12)
        kwargs['decimal_places'] = kwargs.get('decimal_places', 0)
        kwargs['min_value'] = kwargs.get('min_value', Decimal('0'))
        super().__init__(**kwargs)
    
    def to_representation(self, value):
        """نمایش با فرمت کاما"""
        if value is None:
            return None
        return f"{int(value):,}"


class FileUploadSerializer(serializers.Serializer):
    """
    Serializer برای آپلود فایل
    """
    file = serializers.FileField(
        max_length=255,
        allow_empty_file=False,
        use_url=False
    )
    description = serializers.CharField(
        max_length=500,
        required=False,
        allow_blank=True
    )
    
    def validate_file(self, value):
        """اعتبارسنجی فایل"""
        # بررسی حجم (10MB)
        if value.size > 10 * 1024 * 1024:
            raise serializers.ValidationError('حجم فایل نباید بیشتر از 10 مگابایت باشد')
            
        # بررسی نوع فایل
        allowed_types = [
            'image/jpeg', 'image/png', 'image/gif',
            'application/pdf',
            'application/msword',
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        ]
        
        if value.content_type not in allowed_types:
            raise serializers.ValidationError('نوع فایل مجاز نیست')
            
        return value


class ListQuerySerializer(serializers.Serializer):
    """
    Serializer برای query parameters لیست‌ها
    """
    page = serializers.IntegerField(min_value=1, required=False, default=1)
    page_size = serializers.IntegerField(
        min_value=1,
        max_value=100,
        required=False,
        default=20
    )
    search = serializers.CharField(max_length=100, required=False)
    ordering = serializers.ChoiceField(
        choices=[],  # باید در subclass تعریف شود
        required=False
    )
    
    def __init__(self, *args, **kwargs):
        # دریافت ordering_fields از kwargs
        ordering_fields = kwargs.pop('ordering_fields', [])
        super().__init__(*args, **kwargs)
        
        # تنظیم choices برای ordering
        if ordering_fields:
            choices = []
            for field in ordering_fields:
                choices.append((field, field))
                choices.append((f'-{field}', f'-{field}'))
            self.fields['ordering'].choices = choices


class DateRangeSerializer(serializers.Serializer):
    """
    Serializer برای بازه تاریخی
    """
    start_date = serializers.DateField(
        required=False,
        input_formats=['%Y-%m-%d', '%d/%m/%Y']
    )
    end_date = serializers.DateField(
        required=False,
        input_formats=['%Y-%m-%d', '%d/%m/%Y']
    )
    
    def validate(self, attrs):
        """اعتبارسنجی بازه تاریخی"""
        start_date = attrs.get('start_date')
        end_date = attrs.get('end_date')
        
        if start_date and end_date and start_date > end_date:
            raise serializers.ValidationError(
                'تاریخ شروع نمی‌تواند بعد از تاریخ پایان باشد'
            )
            
        return attrs


class StatusChangeSerializer(serializers.Serializer):
    """
    Serializer برای تغییر وضعیت
    """
    status = serializers.ChoiceField(choices=[])  # باید در subclass تعریف شود
    reason = serializers.CharField(
        max_length=500,
        required=False,
        allow_blank=True
    )
    
    def __init__(self, *args, **kwargs):
        # دریافت status_choices از kwargs
        status_choices = kwargs.pop('status_choices', [])
        super().__init__(*args, **kwargs)
        
        if status_choices:
            self.fields['status'].choices = status_choices


class BulkOperationSerializer(serializers.Serializer):
    """
    Serializer برای عملیات دسته‌ای
    """
    ids = serializers.ListField(
        child=serializers.UUIDField(),
        min_length=1,
        max_length=100
    )
    action = serializers.ChoiceField(
        choices=[
            ('delete', 'حذف'),
            ('activate', 'فعال‌سازی'),
            ('deactivate', 'غیرفعال‌سازی'),
        ]
    )
    confirm = serializers.BooleanField(default=False)
    
    def validate(self, attrs):
        """اعتبارسنجی عملیات دسته‌ای"""
        if attrs['action'] == 'delete' and not attrs['confirm']:
            raise serializers.ValidationError(
                'برای حذف باید تأیید را true قرار دهید'
            )
        return attrs


class ErrorResponseSerializer(serializers.Serializer):
    """
    Serializer برای پاسخ‌های خطا
    """
    error = serializers.CharField()
    message = serializers.CharField()
    details = serializers.DictField(required=False)
    timestamp = serializers.DateTimeField(default=timezone.now)


# Mixins

class TimestampMixin(serializers.Serializer):
    """Mixin برای فیلدهای timestamp"""
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)


class CreatedByMixin(serializers.Serializer):
    """Mixin برای فیلد created_by"""
    created_by = UserSerializer(read_only=True)


class SoftDeleteMixin(serializers.Serializer):
    """Mixin برای soft delete"""
    is_active = serializers.BooleanField(default=True)
    deleted_at = serializers.DateTimeField(read_only=True, allow_null=True)


# Nested Serializers

class NestedUserSerializer(serializers.ModelSerializer):
    """Serializer ساده برای نمایش User در nested relations"""
    class Meta:
        model = User
        fields = ['id', 'username', 'full_name', 'user_type']
        read_only_fields = fields


# Custom Fields

class PersianDateField(serializers.Field):
    """
    فیلد تاریخ شمسی
    """
    def to_representation(self, value):
        """تبدیل به تاریخ شمسی برای نمایش"""
        if value is None:
            return None
            
        # استفاده از jdatetime
        try:
            import jdatetime
            return jdatetime.date.fromgregorian(date=value).strftime('%Y/%m/%d')
        except ImportError:
            return value.strftime('%Y-%m-%d')
    
    def to_internal_value(self, data):
        """تبدیل از تاریخ شمسی به میلادی"""
        if not data:
            return None
            
        try:
            import jdatetime
            # پارس تاریخ شمسی
            parts = data.split('/')
            if len(parts) != 3:
                raise serializers.ValidationError('فرمت تاریخ نامعتبر است')
                
            jdate = jdatetime.date(int(parts[0]), int(parts[1]), int(parts[2]))
            return jdate.togregorian()
            
        except (ImportError, ValueError):
            raise serializers.ValidationError('تاریخ شمسی معتبر نیست')


class DurationField(serializers.Field):
    """
    فیلد مدت زمان (به ثانیه)
    """
    def to_representation(self, value):
        """نمایش به صورت HH:MM:SS"""
        if value is None:
            return None
            
        hours = value // 3600
        minutes = (value % 3600) // 60
        seconds = value % 60
        
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    
    def to_internal_value(self, data):
        """تبدیل از HH:MM:SS به ثانیه"""
        if not data:
            return None
            
        try:
            parts = data.split(':')
            if len(parts) != 3:
                raise ValueError
                
            hours = int(parts[0])
            minutes = int(parts[1])
            seconds = int(parts[2])
            
            return hours * 3600 + minutes * 60 + seconds
            
        except ValueError:
            raise serializers.ValidationError('فرمت مدت زمان نامعتبر است (HH:MM:SS)')


# Validator Functions

def validate_future_date(value):
    """اعتبارسنجی تاریخ آینده"""
    if value <= timezone.now().date():
        raise serializers.ValidationError('تاریخ باید در آینده باشد')
    return value


def validate_past_date(value):
    """اعتبارسنجی تاریخ گذشته"""
    if value >= timezone.now().date():
        raise serializers.ValidationError('تاریخ باید در گذشته باشد')
    return value


def validate_persian_text(value):
    """اعتبارسنجی متن فارسی"""
    if not re.search(r'[\u0600-\u06FF]', value):
        raise serializers.ValidationError('متن باید حاوی حروف فارسی باشد')
    return value


# نمونه استفاده

class ExampleModelSerializer(BaseModelSerializer):
    """نمونه استفاده از BaseModelSerializer"""
    phone = PhoneNumberField()
    national_code = NationalCodeField()
    amount = AmountField()
    birth_date = PersianDateField()
    
    class Meta:
        model = None  # باید در استفاده واقعی تعریف شود
        fields = '__all__'