"""
ویوهای سیستم چت‌بات
Chatbot Views
"""

from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.db.models import Q
from drf_spectacular.utils import extend_schema, OpenApiParameter
from drf_spectacular.types import OpenApiTypes

from .models import ChatbotSession, Conversation, Message, ChatbotResponse
from .serializers import (
    ChatbotSessionSerializer, ConversationSerializer, ConversationListSerializer,
    MessageSerializer, ChatbotResponseSerializer, SendMessageRequestSerializer,
    SendMessageResponseSerializer, StartSessionResponseSerializer,
    SymptomAssessmentRequestSerializer, DiagnosisSupportRequestSerializer,
    MedicationInfoRequestSerializer, AppointmentRequestSerializer,
    ConversationHistorySerializer
)
from .services import PatientChatbotService, DoctorChatbotService

User = get_user_model()


class StandardResultsSetPagination(PageNumberPagination):
    """
    صفحه‌بندی استاندارد
    """
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


class BaseChatbotViewSet(viewsets.ModelViewSet):
    """
    کلاس پایه برای ViewSet های چت‌بات
    """
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    
    def get_queryset(self):
        """
        بازگرداندن queryset فیلترشده برای شیءهای متعلق به کاربر فعلی.
        
        این متد queryset پایه‌ی ویوست را محدود می‌کند تا تنها رکوردهایی که فیلد `user` آن‌ها برابر با کاربر احراز هویت‌شدهٔ جاری (`self.request.user`) است بازگردانده شوند. از این متد برای ایجاد محدوده (scoping) داده‌ها به کاربر فعلی در تمام ViewSet‌های پایه استفاده می‌شود؛ کلاس‌های فرعی می‌توانند روی نتیجهٔ آن فیلتر یا مرتب‌سازی‌های اضافی اعمال کنند.
        """
        return self.queryset.filter(user=self.request.user)


class PatientChatbotViewSet(viewsets.GenericViewSet):
    """
    API چت‌بات بیماران
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def get_chatbot_service(self):
        """
        یک خطی:
        سرویس چت‌بات مربوط به بیمار را برای کاربر جاری فراهم می‌کند.
        
        توضیحات:
        این متد یک نمونه از PatientChatbotService را که به کاربر احراز هویت‌شده جاری متصل است برمی‌گرداند. سرویس بازگشتی مسئول عملیات سطح بالای چت‌بات بیمار است، از جمله:
        - مدیریت و بازیابی جلسات فعال و ذخیره‌سازی وضعیت جلسه،
        - پردازش و تحلیل پیام‌های کاربر (شامل ارسال پیام به مدل‌های هوش مصنوعی و دریافت پاسخ‌های ساخت‌یافته)،
        - آغاز و پردازش ارزیابی علائم، تحلیل نتایج و ارائه توصیه‌های اولیه،
        - درخواست زمان ملاقات و هماهنگی اطلاعات مربوط به نوبت،
        - فراهم‌سازی پیام‌های خوش‌آمدگویی و گزینه‌های پاسخ سریع.
        
        این متد خود عملیاتی جانبی (side effect) انجام نمی‌دهد؛ تنها سرویسِ مرتبط با self.request.user را سازنده‌سازی و بازمی‌گرداند.
        
        Returns:
            PatientChatbotService: نمونه‌ای از سرویس چت‌بات که برای کاربر جاری پیکربندی شده است.
        """
        return PatientChatbotService(self.request.user)
    
    @extend_schema(
        summary="شروع جلسه چت‌بات بیمار",
        description="ایجاد یا دریافت جلسه فعال چت‌بات برای بیمار",
        responses={200: StartSessionResponseSerializer}
    )
    @action(detail=False, methods=['post'])
    def start_session(self, request):
        """
        ایجاد یا بازیابی یک جلسه چت‌بات فعال برای کاربر جاری و برگرداندن داده‌های اولیه UI مانند پیام خوشامدگویی و پاسخ‌های سریع.
        
        این عمل:
        - از سرویس چت‌بات (get_chatbot_service) برای ایجاد یا بازیابی یک ChatbotSession استفاده می‌کند (در صورت نبودن، جلسه جدید ساخته می‌شود).
        - از لایه هوش مصنوعی سرویس چت‌بات (ai_service.response_matcher) تلاش می‌کند یک پیام خوشامدگویی مناسب را دریافت کند و در صورت وجود آن را به شکل یک دیکشنری ساختار یافته برمی‌گرداند:
          - content: متن پیام
          - message_type: نوع پیام (مثلاً 'text')
          - response_data: داده‌های اضافی مربوط به پاسخ AI
        - از سرویس چت‌بات لیست پاسخ‌های سریع اولیه (quick_replies) را تهیه می‌کند تا برای رابط کاربری ارسال شود.
        - در صورت بروز استثناء، پاسخ HTTP 500 با پیام خطای فارسی بازگردانده می‌شود.
        
        پارامترها:
            request: درخواست HTTP دریافتی — باید کاربر احراز هویت‌شده باشد (نماگر عملکرد وابسته به self.request.user است).
        
        مقدار بازگشتی:
            شی Response حاوی ساختار JSON با کلیدهای:
              - session: داده‌های سریال‌شده جلسه (ChatbotSessionSerializer)
              - greeting_message: دیکشنری پیام خوشامدگویی یا None
              - quick_replies: فهرست پاسخ‌های سریع آماده برای نمایش در رابط
        
        عوارض جانبی:
            - ممکن است یک جلسه جدید در پایگاه داده ایجاد شود (از طریق chatbot_service.get_or_create_session).
        """
        try:
            chatbot_service = self.get_chatbot_service()
            session = chatbot_service.get_or_create_session()
            
            # دریافت پیام خوشامدگویی
            ai_response = chatbot_service.ai_service.response_matcher.get_greeting_response()
            greeting_message = None
            
            if ai_response:
                greeting_message = {
                    'content': ai_response.response_text,
                    'message_type': 'text',
                    'response_data': ai_response.response_data
                }
            
            # دریافت پاسخ‌های سریع اولیه
            quick_replies = chatbot_service.get_quick_replies()
            
            return Response({
                'session': ChatbotSessionSerializer(session).data,
                'greeting_message': greeting_message,
                'quick_replies': quick_replies
            })
            
        except Exception as e:
            return Response(
                {'error': f'خطا در شروع جلسه: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @extend_schema(
        summary="ارسال پیام به چت‌بات",
        description="ارسال پیام کاربر و دریافت پاسخ چت‌بات",
        request=SendMessageRequestSerializer,
        responses={200: SendMessageResponseSerializer}
    )
    @action(detail=False, methods=['post'])
    def send_message(self, request):
        """
        ارسال و پردازش پیام کاربر به چت‌بات و بازگشت پاسخ ساخت‌یافته‌ی سرویس هوش‌مصنوعی.
        
        این متد یک درخواست POST را می‌پذیرد که باید حداقل شامل فیلد `message` (رشته) باشد و می‌تواند فیلد اختیاری `context` (شی یا دیکشنری) برای ارائه زمینهٔ گفتگو ارسال کند. ورودی ابتدا با `SendMessageRequestSerializer` اعتبارسنجی می‌شود؛ در صورت نامعتبر بودن، خطاهای اعتبارسنجی با وضعیت HTTP 400 بازگردانده می‌شوند. سپس از سرویس چت‌بات (از طریق `self.get_chatbot_service()`) برای پردازش پیام استفاده می‌شود و متد `process_message(message, context)` فراخوانی می‌گردد؛ نتیجهٔ بازگشتی این سرویس مستقیماً در بدنهٔ پاسخ HTTP قرار می‌گیرد.
        
        بازگشت‌ها:
        - HTTP 200: پاسخ پردازش شدهٔ سرویس چت‌بات (معمولاً JSON ساخت‌یافته شامل پیام/اقدامات/گزینه‌های بعدی).
        - HTTP 400: خطاهای اعتبارسنجی ورودی.
        - HTTP 500: خطاهای غیرمنتظره در زمان پردازش پیام؛ پیام خطا در بدنه بازگردانده می‌شود.
        """
        serializer = SendMessageRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            chatbot_service = self.get_chatbot_service()
            
            # پردازش پیام
            result = chatbot_service.process_message(
                message=serializer.validated_data['message'],
                context=serializer.validated_data.get('context')
            )
            
            return Response(result)
            
        except Exception as e:
            return Response(
                {'error': f'خطا در پردازش پیام: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @extend_schema(
        summary="شروع ارزیابی علائم",
        description="شروع فرآیند ارزیابی علائم بیمار",
        responses={200: dict}
    )
    @action(detail=False, methods=['post'])
    def start_symptom_assessment(self, request):
        """
        شروع یک ارزیابی علائم جدید از طرف چت‌بات و بازگرداندن داده‌های اولیه ارزیابی.
        
        این متد یک جلسهٔ ارزیابی علائم را از طریق سرویس چت‌بات مرتبط با کاربر جاری آغاز می‌کند (تماس با متد `start_symptom_assessment` در سرویس). در پاسخ دادهٔ ارزیابی اولیه را برمی‌گرداند که معمولاً شامل پرسش‌های مرحله‌ای، شناسهٔ نشست/ارزیابی و متادیتا لازم برای ادامهٔ ارزیابی توسط کلاینت است.
        
        بازگشت:
            Response: یک شیٔ DRF Response حاوی داده‌های ارزیابی در صورت موفقیت یا در صورت بروز خطا یک ساختار شامل کلید `error` و وضعیت HTTP 500.
        """
        try:
            chatbot_service = self.get_chatbot_service()
            assessment = chatbot_service.start_symptom_assessment()
            
            return Response(assessment)
            
        except Exception as e:
            return Response(
                {'error': f'خطا در شروع ارزیابی: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @extend_schema(
        summary="ارسال پاسخ‌های ارزیابی علائم",
        description="ارسال پاسخ‌های بیمار به سؤالات ارزیابی علائم",
        request=SymptomAssessmentRequestSerializer,
        responses={200: dict}
    )
    @action(detail=False, methods=['post'])
    def submit_symptom_assessment(self, request):
        """
        ارسال و پردازش پاسخ‌های کاربر به ارزیابی علائم
        
        این متد ورودی‌های ارسال‌شده برای ارزیابی علائم را با SymptomAssessmentRequestSerializer اعتبارسنجی کرده و در صورت صحت، آن‌ها را به سرویس چت‌بات می‌فرستد تا تحلیل علائم انجام شود. سرویس هوش‌مصنوعی (process_symptom_response) پاسخ‌ها را آنالیز می‌کند و خروجی‌ای ساختاریافته بازمی‌گرداند که معمولاً شامل ارزیابی ریسک، احتمالات تشخیصی، پیشنهادات درمانی/پیگیری و هر دادهٔ کمکی دیگری برای تصمیم‌گیری بالینی است.
        
        Parameters:
            request: درخواست HTTP حاوی داده‌های ارزیابی علائم که توسط SymptomAssessmentRequestSerializer پردازش و اعتبارسنجی می‌شود.
        
        Returns:
            rest_framework.response.Response:
            - در صورت موفقیت: پاسخ حاوی دیکشنری تحلیل شده (تحلیل ساختاریافته علائم).
            - در صورت خطای اعتبارسنجی: پاسخ با خطاهای serializer و وضعیت HTTP 400.
            - در صورت خطای داخلی در پردازش سرویس چت‌بات: پاسخ با پیغام خطا و وضعیت HTTP 500.
        """
        serializer = SymptomAssessmentRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            chatbot_service = self.get_chatbot_service()
            analysis = chatbot_service.process_symptom_response(serializer.validated_data)
            
            return Response(analysis)
            
        except Exception as e:
            return Response(
                {'error': f'خطا در تحلیل علائم: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @extend_schema(
        summary="درخواست نوبت",
        description="درخواست رزرو نوبت از طریق چت‌بات",
        request=AppointmentRequestSerializer,
        responses={200: dict}
    )
    @action(detail=False, methods=['post'])
    def request_appointment(self, request):
        """
        درخواست ایجاد یا رزرو نوبت توسط چت‌بات برای کاربر فعلی.
        
        این اکشن ورودی را با AppointmentRequestSerializer اعتبارسنجی می‌کند و سپس درخواست نوبت را به سرویس چت‌بات مربوط به کاربر واگذار می‌کند. سرویس چت‌بات ممکن است زمان‌های پیشنهادی، بررسی تخصص موردنیاز و هماهنگی با سامانه‌های رزرو یا پیشنهادهای هوشمند را تولید کند و نتیجه‌ٔ نهایی (appointment_info) را بازگرداند. در پاسخ موفق، همان ساختار appointment_info به کلاینت برگردانده می‌شود.
        
        رفتارهای HTTP متداول:
        - 200: بازگشت appointment_info در صورت موفقیت.
        - 400: در صورت نامعتبر بودن ورودی (خطاهای serializer).
        - 500: در صورت بروز خطا در پردازش داخلی یا سرویس چت‌بات؛ پیام خطا به صورت {'error': '...'} بازگردانده می‌شود.
        """
        serializer = AppointmentRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            chatbot_service = self.get_chatbot_service()
            appointment_info = chatbot_service.request_appointment(
                specialty=serializer.validated_data.get('specialty'),
                preferred_time=serializer.validated_data.get('preferred_time')
            )
            
            return Response(appointment_info)
            
        except Exception as e:
            return Response(
                {'error': f'خطا در درخواست نوبت: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @extend_schema(
        summary="پایان جلسه",
        description="پایان دادن به جلسه فعال چت‌بات",
        responses={200: dict}
    )
    @action(detail=False, methods=['post'])
    def end_session(self, request):
        """
        پایان جلسهٔ فعال چت‌بات برای کاربر جاری.
        
        این اکشن، جلسهٔ فعال چت‌بات مرتبط با کاربر احراز هویت‌شده را از طریق سرویس چت‌بات (get_chatbot_service) خاتمه می‌دهد. فراخوانی سرویس معمولاً شامل عملیات‌های زیر است:
        - علامت‌گذاری جلسه به‌عنوان "پایان‌یافته" در پایگاه‌داده.
        - ذخیره/همگام‌سازی وضعیت نهایی جلسه و گفتگوها.
        - انجام پاک‌سازی زمینه‌های مرتبط در حافظه یا صف‌های پردازشی که ممکن است برای نگهداری کانتکست مکالمه استفاده شده باشند.
        - در صورت وجود وظایف پس‌زمینه (مثل انتها دادن به پردازش‌های هوش‌مصنوعی یا آزادسازی منابع مدل)، راه‌اندازی یا برنامه‌ریزی آن‌ها.
        
        پاسخ:
        - موفقیت: JSON با کلید `message` و مقدار متنی تایید (HTTP 200).
        - خطا: در صورت بروز استثنا، JSON با کلید `error` و پیام خطا بازگردانده شده و کد وضعیت HTTP 500 برگردانده می‌شود.
        
        توجه: پیاده‌سازی دقیق رفتارهای دخیل در سرویس چت‌بات (ذخیره‌سازی، همگام‌سازی مدل/وظایف پس‌زمینه و ...) در لایهٔ سرویس قرار دارد و این اکشن صرفاً درگاه فراخوانی و مدیریت پاسخ/خطا برای آن سرویس است.
        """
        try:
            chatbot_service = self.get_chatbot_service()
            chatbot_service.end_session()
            
            return Response({'message': 'جلسه با موفقیت پایان یافت'})
            
        except Exception as e:
            return Response(
                {'error': f'خطا در پایان جلسه: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class DoctorChatbotViewSet(viewsets.GenericViewSet):
    """
    API چت‌بات پزشکان
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def get_chatbot_service(self):
        """
        بازگرداندن نمونه‌ی DoctorChatbotService متصل به کاربر جاری.
        
        این متد یک شیء DoctorChatbotService مقداردهی‌شده با کاربر احراز هویت‌شده‌ی جاری (self.request.user) را برمی‌گرداند. از این سرویس برای پردازش پیام‌ها، پشتیبانی تشخیصی، اطلاعات دارویی و سایر عملیات مربوط به چت‌بات پزشک استفاده می‌شود.
        
        Returns:
            DoctorChatbotService: سرویس چت‌بات مخصوص پزشک که درخواست‌ها و وضعیت را برای کاربر جاری مدیریت می‌کند.
        """
        return DoctorChatbotService(self.request.user)
    
    @extend_schema(
        summary="شروع جلسه چت‌بات پزشک",
        description="ایجاد یا دریافت جلسه فعال چت‌بات برای پزشک",
        responses={200: StartSessionResponseSerializer}
    )
    @action(detail=False, methods=['post'])
    def start_session(self, request):
        """
        ایجاد یا بازیابی یک جلسه چت‌بات فعال برای کاربر جاری و برگرداندن داده‌های اولیه UI مانند پیام خوشامدگویی و پاسخ‌های سریع.
        
        این عمل:
        - از سرویس چت‌بات (get_chatbot_service) برای ایجاد یا بازیابی یک ChatbotSession استفاده می‌کند (در صورت نبودن، جلسه جدید ساخته می‌شود).
        - از لایه هوش مصنوعی سرویس چت‌بات (ai_service.response_matcher) تلاش می‌کند یک پیام خوشامدگویی مناسب را دریافت کند و در صورت وجود آن را به شکل یک دیکشنری ساختار یافته برمی‌گرداند:
          - content: متن پیام
          - message_type: نوع پیام (مثلاً 'text')
          - response_data: داده‌های اضافی مربوط به پاسخ AI
        - از سرویس چت‌بات لیست پاسخ‌های سریع اولیه (quick_replies) را تهیه می‌کند تا برای رابط کاربری ارسال شود.
        - در صورت بروز استثناء، پاسخ HTTP 500 با پیام خطای فارسی بازگردانده می‌شود.
        
        پارامترها:
            request: درخواست HTTP دریافتی — باید کاربر احراز هویت‌شده باشد (نماگر عملکرد وابسته به self.request.user است).
        
        مقدار بازگشتی:
            شی Response حاوی ساختار JSON با کلیدهای:
              - session: داده‌های سریال‌شده جلسه (ChatbotSessionSerializer)
              - greeting_message: دیکشنری پیام خوشامدگویی یا None
              - quick_replies: فهرست پاسخ‌های سریع آماده برای نمایش در رابط
        
        عوارض جانبی:
            - ممکن است یک جلسه جدید در پایگاه داده ایجاد شود (از طریق chatbot_service.get_or_create_session).
        """
        try:
            chatbot_service = self.get_chatbot_service()
            session = chatbot_service.get_or_create_session()
            
            # دریافت پیام خوشامدگویی
            ai_response = chatbot_service.ai_service.response_matcher.get_greeting_response()
            greeting_message = None
            
            if ai_response:
                greeting_message = {
                    'content': ai_response.response_text,
                    'message_type': 'text',
                    'response_data': ai_response.response_data
                }
            
            # دریافت پاسخ‌های سریع اولیه
            quick_replies = chatbot_service.get_quick_replies()
            
            return Response({
                'session': ChatbotSessionSerializer(session).data,
                'greeting_message': greeting_message,
                'quick_replies': quick_replies
            })
            
        except Exception as e:
            return Response(
                {'error': f'خطا در شروع جلسه: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @extend_schema(
        summary="ارسال پیام به چت‌بات",
        description="ارسال پیام پزشک و دریافت پاسخ چت‌بات",
        request=SendMessageRequestSerializer,
        responses={200: SendMessageResponseSerializer}
    )
    @action(detail=False, methods=['post'])
    def send_message(self, request):
        """
        ارسال و پردازش پیام کاربر به چت‌بات و بازگشت پاسخ ساخت‌یافته‌ی سرویس هوش‌مصنوعی.
        
        این متد یک درخواست POST را می‌پذیرد که باید حداقل شامل فیلد `message` (رشته) باشد و می‌تواند فیلد اختیاری `context` (شی یا دیکشنری) برای ارائه زمینهٔ گفتگو ارسال کند. ورودی ابتدا با `SendMessageRequestSerializer` اعتبارسنجی می‌شود؛ در صورت نامعتبر بودن، خطاهای اعتبارسنجی با وضعیت HTTP 400 بازگردانده می‌شوند. سپس از سرویس چت‌بات (از طریق `self.get_chatbot_service()`) برای پردازش پیام استفاده می‌شود و متد `process_message(message, context)` فراخوانی می‌گردد؛ نتیجهٔ بازگشتی این سرویس مستقیماً در بدنهٔ پاسخ HTTP قرار می‌گیرد.
        
        بازگشت‌ها:
        - HTTP 200: پاسخ پردازش شدهٔ سرویس چت‌بات (معمولاً JSON ساخت‌یافته شامل پیام/اقدامات/گزینه‌های بعدی).
        - HTTP 400: خطاهای اعتبارسنجی ورودی.
        - HTTP 500: خطاهای غیرمنتظره در زمان پردازش پیام؛ پیام خطا در بدنه بازگردانده می‌شود.
        """
        serializer = SendMessageRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            chatbot_service = self.get_chatbot_service()
            
            # پردازش پیام
            result = chatbot_service.process_message(
                message=serializer.validated_data['message'],
                context=serializer.validated_data.get('context')
            )
            
            return Response(result)
            
        except Exception as e:
            return Response(
                {'error': f'خطا در پردازش پیام: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @extend_schema(
        summary="درخواست پشتیبانی تشخیصی",
        description="درخواست کمک در تشخیص بر اساس علائم بیمار",
        request=DiagnosisSupportRequestSerializer,
        responses={200: dict}
    )
    @action(detail=False, methods=['post'])
    def diagnosis_support(self, request):
        """
        درخواست پشتیبانی تشخیصی برای یک بیمار و بازگرداندن نتیجه تحلیل تشخیصی توسط سرویس هوش‌مصنوعی.
        
        این متد داده‌های ورودی را با DiagnosisSupportRequestSerializer اعتبارسنجی می‌کند (خطاهای اعتبارسنجی با HTTP 400 بازگردانده می‌شوند)، سپس اطلاعات بیمار را از فیلدهای زیر می‌سازد:
        - patient_age
        - patient_gender
        - medical_history
        - current_medications (اختیاری، پیش‌فرض لیست خالی)
        
        سپس متد get_diagnosis_support سرویس چت‌بات را با پارامترهای `symptoms` و `patient_info` فراخوانی می‌کند و خروجی آن را در بدنه پاسخ بازمی‌گرداند. در صورت بروز هرگونه خطای اجرایی، پاسخ با وضعیت HTTP 500 و پیام خطا بازگردانده می‌شود.
        
        بازگشت:
            Response: در حالت موفقیت، داده‌های پشتیبانی تشخیصی بازگردانده می‌شوند؛ در صورت خطای اعتبارسنجی HTTP 400 و در صورت خطای داخلی HTTP 500.
        """
        serializer = DiagnosisSupportRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            chatbot_service = self.get_chatbot_service()
            
            patient_info = {
                'age': serializer.validated_data.get('patient_age'),
                'gender': serializer.validated_data.get('patient_gender'),
                'medical_history': serializer.validated_data.get('medical_history'),
                'current_medications': serializer.validated_data.get('current_medications', [])
            }
            
            diagnosis_support = chatbot_service.get_diagnosis_support(
                symptoms=serializer.validated_data['symptoms'],
                patient_info=patient_info
            )
            
            return Response(diagnosis_support)
            
        except Exception as e:
            return Response(
                {'error': f'خطا در پشتیبانی تشخیصی: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @extend_schema(
        summary="درخواست اطلاعات دارو",
        description="دریافت اطلاعات کامل در مورد دارو",
        request=MedicationInfoRequestSerializer,
        responses={200: dict}
    )
    @action(detail=False, methods=['post'])
    def medication_info(self, request):
        """
        درخواست و بازگردانی اطلاعات دارویی با توجه به زمینه بیمار.
        
        این متد ورودی درخواست را اعتبارسنجی می‌کند و سپس با استفاده از سرویس چت‌بات اطلاعات مربوط به داروی مشخص‌شده را با درنظر گرفتن زمینهٔ بیمار (سن، وزن، آلرژی‌ها و داروهای جاری) از لایه سرویس دریافت و برمی‌گرداند. پردازش اطلاعات دارویی (شامل تداخل‌های احتمالی، نکات احتیاطی، دوزهای معمول و هشدارها) توسط متد get_medication_info در سرویس چت‌بات انجام می‌شود.
        
        پارامترهای درخواست (بدنه JSON) که اعتبارسنجی می‌شوند:
            - medication_name: نام دارو (الزامی)
            - patient_age: سن بیمار (اختیاری)
            - patient_weight: وزن بیمار (اختیاری)
            - allergies: فهرست آلرژی‌های شناخته‌شده (اختیاری)
            - current_medications: فهرست داروهای مصرفی فعلی بیمار (اختیاری)
        
        بازگشت:
            - در صورت موفقیت: پاسخ JSON حاوی ساختار اطلاعات دارویی تولیدشده توسط سرویس چت‌بات.
            - در صورت خطای اعتبارسنجی: پاسخ با وضعیت HTTP 400 شامل خطاهای serializer.
            - در صورت خطای داخلی یا استثناء در پردازش: پاسخ با وضعیت HTTP 500 و پیام خطا.
        """
        serializer = MedicationInfoRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            chatbot_service = self.get_chatbot_service()
            
            patient_context = {
                'age': serializer.validated_data.get('patient_age'),
                'weight': serializer.validated_data.get('patient_weight'),
                'allergies': serializer.validated_data.get('allergies', []),
                'current_medications': serializer.validated_data.get('current_medications', [])
            }
            
            medication_info = chatbot_service.get_medication_info(
                medication_name=serializer.validated_data['medication_name'],
                patient_context=patient_context
            )
            
            return Response(medication_info)
            
        except Exception as e:
            return Response(
                {'error': f'خطا در دریافت اطلاعات دارو: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @extend_schema(
        summary="درخواست پروتکل درمان",
        description="دریافت پروتکل درمان برای بیماری مشخص",
        parameters=[
            OpenApiParameter('condition', OpenApiTypes.STR, description='نام بیماری'),
            OpenApiParameter('severity', OpenApiTypes.STR, description='شدت بیماری')
        ],
        responses={200: dict}
    )
    @action(detail=False, methods=['get'])
    def treatment_protocol(self, request):
        """
        درخواست پروتکل درمان برای یک بیماری مشخص.
        
        این اکشن پارامترهای کوئری زیر را می‌پذیرد و پروتکل درمانی را از سرویس چت‌بات دریافت می‌کند:
        - condition (الزامی): نام یا شناسه بیماری/شرایط بالینی.
        - severity (اختیاری): شدت وضعیت (پیش‌فرض "moderate").
        
        رفتار:
        - در صورت نبودن پارامتر condition، پاسخ با وضعیت HTTP 400 و پیام خطا بازگردانده می‌شود.
        - در حالت عادی، این متد با فراخوانی get_treatment_protocol(condition, severity) روی سرویس چت‌بات، پروتکل درمانی را درخواست می‌کند و نتیجه (ساختار JSON/دیکشنری) را در بدنه پاسخ بازمی‌گرداند.
        - هر استثنایی که طی پردازش رخ دهد با وضعیت HTTP 500 و پیام خطا پاسخ داده می‌شود.
        
        مقدار بازگشتی:
        - HTTP 200: محتوای پروتکل درمانی (معمولاً دیکشنری/JSON).
        - HTTP 400: اگر پارامتر condition ارائه نشده باشد.
        - HTTP 500: در صورت بروز خطای سرور/سرویس.
        """
        condition = request.query_params.get('condition')
        severity = request.query_params.get('severity', 'moderate')
        
        if not condition:
            return Response(
                {'error': 'نام بیماری الزامی است'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            chatbot_service = self.get_chatbot_service()
            protocol = chatbot_service.get_treatment_protocol(condition, severity)
            
            return Response(protocol)
            
        except Exception as e:
            return Response(
                {'error': f'خطا در دریافت پروتکل: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @extend_schema(
        summary="جستجو در مراجع پزشکی",
        description="جستجو در متون و مراجع پزشکی",
        parameters=[
            OpenApiParameter('query', OpenApiTypes.STR, description='عبارت جستجو'),
            OpenApiParameter('specialty', OpenApiTypes.STR, description='تخصص (اختیاری)')
        ],
        responses={200: dict}
    )
    @action(detail=False, methods=['get'])
    def search_references(self, request):
        """
        جستجوی مراجع پزشکی بر اساس عبارت و تخصص اختیاری و بازگرداندن نتایج به‌صورت پاسخ HTTP.
        
        این عملیات پارامترهای کوئری زیر را می‌خواند:
        - `query` (الزامی): عبارت جستجو برای یافتن منابع پزشکی.
        - `specialty` (اختیاری): فیلتر بر اساس تخصص پزشکی (مثلاً "cardiology").
        
        رفتار:
        - پارامتر `query` باید موجود باشد؛ در غیر این صورت پاسخ 400 با پیام خطا بازگردانده می‌شود.
        - برای انجام جستجو از سرویس چت‌بات (`self.get_chatbot_service().search_medical_references`) استفاده می‌شود که نتایج مرتبط با منابع پزشکی را بازمی‌گرداند.
        - در صورت موفقیت، محتویات برگشتی سرویس مستقیماً در بدنه پاسخ HTTP قرار می‌گیرد (معمولاً لیست یا ساختار JSON شامل مراجع، عنوان، چکیده و لینک‌ها).
        - در صورت بروز استثنا، پاسخ 500 همراه با پیام خطا بازگردانده می‌شود.
        
        مقدار بازگشتی:
        - یک شی Response حاوی نتایج جستجو یا یک پیام خطا با وضعیت‌های HTTP مناسب (400 یا 500).
        """
        query = request.query_params.get('query')
        specialty = request.query_params.get('specialty')
        
        if not query:
            return Response(
                {'error': 'عبارت جستجو الزامی است'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            chatbot_service = self.get_chatbot_service()
            search_results = chatbot_service.search_medical_references(query, specialty)
            
            return Response(search_results)
            
        except Exception as e:
            return Response(
                {'error': f'خطا در جستجو: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class ChatbotSessionViewSet(BaseChatbotViewSet):
    """
    مدیریت جلسات چت‌بات
    """
    queryset = ChatbotSession.objects.all()
    serializer_class = ChatbotSessionSerializer
    
    def get_queryset(self):
        """
        بازگرداندن queryset جلسات مربوط به کاربر جاری با فیلترهای اختیاری و مرتب‌سازی.
        
        این متد queryset پایه را (که از BaseChatbotViewSet آمده و قبلاً به کاربر جاری محدود شده) برمی‌گرداند و به آن فیلترهای اختیاری HTTP query params را اعمال می‌کند:
        - session_type: در صورت وجود، نتایج را بر اساس نوع جلسه فیلتر می‌کند.
        - status: در صورت وجود، نتایج را بر اساس وضعیت جلسه فیلتر می‌کند.
        
        نتیجه بر اساس فیلد `started_at` به صورت نزولی مرتب می‌شود تا جدیدترین جلسات اول بازگردانده شوند.
        
        Returns:
            QuerySet: مجموعه‌ی فیلتر شده و مرتب‌شدهٔ جلسات مربوط به کاربر جاری.
        """
        queryset = super().get_queryset()
        
        # فیلتر بر اساس نوع جلسه
        session_type = self.request.query_params.get('session_type')
        if session_type:
            queryset = queryset.filter(session_type=session_type)
        
        # فیلتر بر اساس وضعیت
        status_filter = self.request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        return queryset.order_by('-started_at')


class ConversationViewSet(viewsets.ReadOnlyModelViewSet):
    """
    مشاهده مکالمات چت‌بات
    """
    serializer_class = ConversationSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    
    def get_queryset(self):
        """
        بازگرداندن queryset مکالمات متعلق به کاربر احراز هویت‌شده.
        
        این متد یک QuerySet از مدل Conversation برمی‌گرداند که فقط مکالماتی را شامل می‌کند که از طریق رابطه session به کاربری که درخواست را فرستاده (request.user) تعلق دارند. برای بهینه‌سازی کوئری‌ها، رابطه‌ی session با select_related بارگذاری شده و مجموعه پیام‌ها (messages) با prefetch_related از قبل واکشی می‌شوند تا از تعداد کوئری‌های پایگاه‌داده کاسته شود. نتایج بر حسب زمان شروع جلسه (started_at) به صورت نزولی مرتب می‌شوند (جدیدترین اول).
        
        Returns:
            QuerySet: مجموعه‌ای از اشیاء Conversation فیلترشده، با session مرتبط و پیام‌های پیش‌بارگذاری‌شده، مرتب‌شده بر اساس started_at نزولی.
        """
        return Conversation.objects.filter(
            session__user=self.request.user
        ).select_related('session').prefetch_related('messages').order_by('-started_at')
    
    def get_serializer_class(self):
        """
        بازگرداندن کلاس سریالایزر مناسب برای اکشن جاری در ViewSet.
        
        این متد بر اساس مقدار `self.action` کلاس سریالایزر را انتخاب می‌کند:
        - زمانی که اکشن `list` است، از `ConversationListSerializer` استفاده می‌شود تا مجموعه‌ای از گفتگوها با فیلدهای خلاصه و بهینه‌شده برگردانده شود (مناسب برای صفحات لیست).
        - برای سایر اکشن‌ها (مثل `retrieve` و اکشن‌های سفارشی) از `ConversationSerializer` استفاده می‌شود که نمای کامل‌تر و جزئیات هر گفتگو را فراهم می‌آورد.
        
        متد توسط Django REST Framework هنگام ساخت serializer برای هر درخواست فراخوانی می‌شود تا پاسخ مناسب با نوع عملیات تولید شود.
        """
        if self.action == 'list':
            return ConversationListSerializer
        return ConversationSerializer
    
    @extend_schema(
        summary="دریافت تاریخچه مکالمه",
        description="دریافت تاریخچه کامل یک مکالمه با پیام‌ها",
        parameters=[
            OpenApiParameter('limit', OpenApiTypes.INT, description='تعداد پیام‌ها')
        ],
        responses={200: ConversationHistorySerializer}
    )
    @action(detail=True, methods=['get'])
    def history(self, request, pk=None):
        """
        بازگرداندن تاریخچه یک مکالمه مشخص.
        
        این اکشن تاریخچه پیام‌های یک گفت‌وگو را برمی‌گرداند: ابتدا شیء conversation با self.get_object() واکشی می‌شود، سپس پیام‌ها بر اساس `created_at` نزولی مرتب و تا تعداد `limit` برش داده می‌شوند. پاسخ JSON شامل نسخه‌ی سریالایز شده‌ی گفت‌وگو، لیست پیام‌ها (جدیدترین ابتدا)، تعداد کل پیام‌ها و یک فِلَگ `has_more` برای نشان دادن وجود پیام‌های بیش‌تر است.
        
        پارامترهای کوئری:
            limit (int, اختیاری): حداکثر تعداد پیام‌هایی که برگردانده می‌شوند. مقدار پیش‌فرض 50 است.
        
        مقدار بازگشتی:
            rest_framework.response.Response: بدنه‌ی JSON با کلیدهای:
                - conversation: داده‌های سریالایز شدهٔ گفت‌وگو (ConversationListSerializer).
                - messages: فهرست پیام‌های سریالایز شده (MessageSerializer) مرتب‌شده به صورت نزولی بر اساس `created_at`.
                - total_messages: تعداد کل پیام‌های موجود در آن گفت‌وگو.
                - has_more: بولین که نشان می‌دهد آیا پیام‌های بیشتری نسبت به `limit` وجود دارد یا خیر.
        """
        conversation = self.get_object()
        limit = int(request.query_params.get('limit', 50))
        
        messages = conversation.messages.order_by('-created_at')[:limit]
        total_messages = conversation.messages.count()
        
        return Response({
            'conversation': ConversationListSerializer(conversation).data,
            'messages': MessageSerializer(messages, many=True).data,
            'total_messages': total_messages,
            'has_more': total_messages > limit
        })


class MessageViewSet(viewsets.ReadOnlyModelViewSet):
    """
    مشاهده پیام‌های چت‌بات
    """
    serializer_class = MessageSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    
    def get_queryset(self):
        """
        لیست پیام‌های مرتبط با کاربر احراز هویت‌شده را برمی‌گرداند.
        
        این کوئری تمام Message‌هایی را بازمی‌گرداند که متعلق به Conversation‌هایی هستند که زیر‌مجموعه‌ی Sessionهایی با فیلد user برابر با کاربر جاری درخواست (request.user) هستند. برای کاهش تعداد کوئری‌ها از select_related('conversation') استفاده می‌کند و نتایج را بر اساس فیلد created_at به ترتیب نزولی مرتب می‌کند (آخرین پیام‌ها ابتدا).
        """
        return Message.objects.filter(
            conversation__session__user=self.request.user
        ).select_related('conversation').order_by('-created_at')