"""
Chatbot Views for Fashionistar.
"""

from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from django.contrib.auth import get_user_model
from drf_spectacular.utils import extend_schema, OpenApiParameter
from drf_spectacular.types import OpenApiTypes

from .models import ChatbotSession, Conversation, Message
from .serializers import (
    ChatbotSessionSerializer, ConversationSerializer, ConversationListSerializer,
    MessageSerializer, SendMessageRequestSerializer,
    SendMessageResponseSerializer, StartSessionResponseSerializer,
    StyleAssessmentRequestSerializer, SizeRecommendationRequestSerializer,
    ProductInquiryRequestSerializer, BespokeConsultationRequestSerializer
)
from .services import ClientChatbotService, VendorChatbotService

User = get_user_model()


class StandardResultsSetPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


class BaseChatbotViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    
    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False) or self.request.user.is_anonymous:
            return self.queryset.none()
        return self.queryset.filter(user=self.request.user)


class ClientChatbotViewSet(viewsets.GenericViewSet):
    """
    API for client-facing chatbot services.
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
        return ClientChatbotService(self.request.user)
    
    @extend_schema(
        summary="Start client chatbot session",
        description="Initialize or get active chatbot session for client",
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
            greeting_response = chatbot_service.ai_service.response_matcher.get_greeting_response()
            
            greeting_message = None
            if greeting_response:
                greeting_message = {
                    'content': greeting_response.response_text,
                    'message_type': 'text',
                    'response_data': greeting_response.response_data,
                    'ai_confidence': 1.0,
                    'processing_time': 0.0
                }
            
            quick_replies = chatbot_service.get_quick_replies()
            
            return Response({
                'session': ChatbotSessionSerializer(session).data,
                'greeting_message': greeting_message,
                'quick_replies': quick_replies
            })
        except Exception as e:
            return Response(
                {'error': f'Error starting session: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @extend_schema(
        summary="Send message to chatbot",
        description="Send client message and get chatbot response",
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
                {'error': f'Error processing message: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @extend_schema(
        summary="Start style assessment",
        description="Initialize style assessment questionnaire for the client",
        responses={200: dict}
    )
    @action(detail=False, methods=['post'])
    def start_style_assessment(self, request):
        """
        شروع یک ارزیابی علائم جدید از طرف چت‌بات و بازگرداندن داده‌های اولیه ارزیابی.
        
        این متد یک جلسهٔ ارزیابی علائم را از طریق سرویس چت‌بات مرتبط با کاربر جاری آغاز می‌کند (تماس با متد `start_symptom_assessment` در سرویس). در پاسخ دادهٔ ارزیابی اولیه را برمی‌گرداند که معمولاً شامل پرسش‌های مرحله‌ای، شناسهٔ نشست/ارزیابی و متادیتا لازم برای ادامهٔ ارزیابی توسط کلاینت است.
        
        بازگشت:
            Response: یک شیٔ DRF Response حاوی داده‌های ارزیابی در صورت موفقیت یا در صورت بروز خطا یک ساختار شامل کلید `error` و وضعیت HTTP 500.
        """
        try:
            chatbot_service = self.get_chatbot_service()
            assessment = chatbot_service.start_style_assessment()
            return Response(assessment)
        except Exception as e:
            return Response(
                {'error': f'Error starting style assessment: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @extend_schema(
        summary="Submit style assessment responses",
        description="Submit style preferences and get outfits recommendations",
        request=StyleAssessmentRequestSerializer,
        responses={200: dict}
    )
    @action(detail=False, methods=['post'])
    def submit_style_assessment(self, request):
        """
        ارسال پاسخ‌های ارزیابی استایل و دریافت توصیه‌های لباس.
        
        این متد پاسخ‌های کاربر به ارزیابی استایل را از طریق `StyleAssessmentRequestSerializer` اعتبارسنجی کرده و سپس از طریق سرویس چت‌بات مرتبط با کاربر جاری (متد `process_style_response`) پردازش می‌کند. در صورت موفقیت، ساختاری حاوی نتایج ارزیابی و توصیه‌های لباس برگردانده می‌شود؛ در غیر این صورت، خطا با وضعیت HTTP 500 نشان داده می‌شود.
        """
        serializer = StyleAssessmentRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            chatbot_service = self.get_chatbot_service()
            result = chatbot_service.process_style_response(serializer.validated_data)
            return Response(result)
        except Exception as e:
            return Response(
                {'error': f'Error submitting style assessment: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @extend_schema(
        summary="Request bespoke consultation",
        description="Initiate request for custom tailoring consultation",
        request=BespokeConsultationRequestSerializer,
        responses={200: dict}
    )
    @action(detail=False, methods=['post'])
    def request_appointment(self, request):
        serializer = BespokeConsultationRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            chatbot_service = self.get_chatbot_service()
            result = chatbot_service.request_appointment(
                specialty=serializer.validated_data.get('tailoring_type'),
                preferred_time=serializer.validated_data.get('preferred_time')
            )
            return Response(result)
        except Exception as e:
            return Response(
                {'error': f'Error requesting consultation: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
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
            return Response({'status': 'Session completed successfully.'})
        except Exception as e:
            return Response(
                {'error': f'Error ending session: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class VendorChatbotViewSet(viewsets.GenericViewSet):
    """
    API for vendor-facing chatbot services.
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def get_chatbot_service(self):
        """
        بازگرداندن نمونه‌ی VendorChatbotService متصل به کاربر جاری.
        
        این متد یک شیء VendorChatbotService مقداردهی‌شده با کاربر احراز هویت‌شده‌ی جاری (self.request.user) را برمی‌گرداند. از این سرویس برای پردازش پیام‌ها، پشتیبانی تشخیصی، اطلاعات دارویی و سایر عملیات مربوط به چت‌بات پزشک استفاده می‌شود.
        
        Returns:
            VendorChatbotService: سرویس چت‌بات مخصوص پزشک که درخواست‌ها و وضعیت را برای کاربر جاری مدیریت می‌کند.
        """
        return VendorChatbotService(self.request.user)
    
    @extend_schema(
        summary="Start vendor chatbot session",
        description="Initialize or get active chatbot session for vendor",
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
            greeting_response = chatbot_service.ai_service.response_matcher.get_greeting_response()
            
            greeting_message = None
            if greeting_response:
                greeting_message = {
                    'content': greeting_response.response_text,
                    'message_type': 'text',
                    'response_data': greeting_response.response_data,
                    'ai_confidence': 1.0,
                    'processing_time': 0.0
                }
            
            quick_replies = chatbot_service.get_quick_replies()
            
            return Response({
                'session': ChatbotSessionSerializer(session).data,
                'greeting_message': greeting_message,
                'quick_replies': quick_replies
            })
        except Exception as e:
            return Response(
                {'error': f'Error starting session: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @extend_schema(
        summary="Send message to chatbot",
        description="Send vendor message and get chatbot response",
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
                {'error': f'Error processing message: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @extend_schema(
        summary="Request product catalog support",
        description="Get recommendation and categorization for new products",
        request=SizeRecommendationRequestSerializer,
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
        serializer = SizeRecommendationRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            chatbot_service = self.get_chatbot_service()
            vendor_info = {
                'height_cm': serializer.validated_data.get('height_cm'),
                'gender': serializer.validated_data.get('gender'),
                'fit_preference': serializer.validated_data.get('fit_preference'),
                'prior_purchases': serializer.validated_data.get('prior_purchases', [])
            }
            
            support = chatbot_service.get_catalog_support(
                products=serializer.validated_data['measurements'],
                vendor_info=vendor_info
            )
            return Response(support)
        except Exception as e:
            return Response(
                {'error': f'Error generating catalog support: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @extend_schema(
        summary="Request product specifications",
        description="Get fabric, pricing and packaging details",
        request=ProductInquiryRequestSerializer,
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
        serializer = ProductInquiryRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            chatbot_service = self.get_chatbot_service()
            vendor_context = {
                'size': serializer.validated_data.get('client_size'),
                'height': serializer.validated_data.get('client_height'),
                'fabric_preferences': serializer.validated_data.get('fabric_preferences', []),
                'similar_products': serializer.validated_data.get('similar_products', [])
            }
            
            info = chatbot_service.get_product_info(
                product_sku=serializer.validated_data['product_sku'],
                vendor_context=vendor_context
            )
            return Response(info)
        except Exception as e:
            return Response(
                {'error': f'Error loading product specs: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @extend_schema(
        summary="Get tailoring guideline",
        description="Fetch custom tailoring assembly and pattern details",
        parameters=[
            OpenApiParameter('condition', OpenApiTypes.STR, description="Garment Type"),
            OpenApiParameter('severity', OpenApiTypes.STR, description="Complexity", default="moderate")
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
            return Response({'error': 'condition parameter is required.'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            chatbot_service = self.get_chatbot_service()
            protocol = chatbot_service.get_treatment_protocol(condition, severity)
            return Response(protocol)
        except Exception as e:
            return Response(
                {'error': f'Error fetching tailoring guidelines: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @extend_schema(
        summary="Search fashion references",
        description="Search design ideas, trends and fabric references",
        parameters=[
            OpenApiParameter('query', OpenApiTypes.STR, description="Search Query"),
            OpenApiParameter('specialty', OpenApiTypes.STR, description="Specialty Niche", required=False)
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
            return Response({'error': 'query parameter is required.'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            chatbot_service = self.get_chatbot_service()
            results = chatbot_service.search_medical_references(query, specialty)
            return Response(results)
        except Exception as e:
            return Response(
                {'error': f'Error searching fashion references: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class ChatbotSessionViewSet(BaseChatbotViewSet):
    """
    مدیریت جلسات چت‌بات
    """
    queryset = ChatbotSession.objects.all()
    serializer_class = ChatbotSessionSerializer


class ConversationViewSet(BaseChatbotViewSet):
    queryset = Conversation.objects.all()
    serializer_class = ConversationSerializer
    
    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False) or self.request.user.is_anonymous:
            return self.queryset.none()
        return self.queryset.filter(session__user=self.request.user)
    
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
        messages = conversation.messages.all().order_by('created_at')
        
        return Response({
            'conversation': ConversationListSerializer(conversation).data,
            'messages': MessageSerializer(messages, many=True).data,
            'total_messages': messages.count(),
            'has_more': False
        })


class MessageViewSet(BaseChatbotViewSet):
    queryset = Message.objects.all()
    serializer_class = MessageSerializer
    
    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False) or self.request.user.is_anonymous:
            return self.queryset.none()
        return self.queryset.filter(conversation__session__user=self.request.user)