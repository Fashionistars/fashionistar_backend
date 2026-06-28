"""
سرویس یکپارچه‌سازی با هوش مصنوعی
AI Integration Service
"""

import time
import logging
from typing import Dict, List, Optional, Any, Tuple
from django.conf import settings
from .response_matcher import ResponseMatcherService

logger = logging.getLogger(__name__)


class AIIntegrationService:
    """
    سرویس یکپارچه‌سازی با خدمات هوش مصنوعی
    """
    
    def __init__(self, user_type: str = 'patient'):
        """
        یک‌خطی: نمونه‌سازی سرویس یکپارچه‌سازی هوش‌مصنوعی با تعیین نوع کاربر و ساخت ResponseMatcherService مرتبط.
        
        توضیح: سازنده AIIntegrationService را مقداردهی اولیه می‌کند؛ نوع کاربر (پیش‌فرض 'patient') را ذخیره می‌نماید و یک نمونه‌ی ResponseMatcherService را با همان هدف (target_user) می‌سازد تا تحلیل نیت و جستجوی پاسخ‌های از پیش‌تعریف‌شده بر اساس نقش کاربر انجام شود. مقدار user_type تعیین می‌کند که مسیرهای تولید پاسخ و مجموعه پاسخ‌های سریع و منطق مرتبط با patient یا doctor انتخاب شوند.
        
        Parameters:
            user_type (str): نوع کاربر—معمولاً 'patient' یا 'doctor'—که رفتار سرویس (تحلیل نیت، انتخاب پاسخ‌های از پیش‌تعریف‌شده و تولید پاسخ AI) را مشخص می‌کند.
        """
        self.user_type = user_type
        self.response_matcher = ResponseMatcherService(target_user=user_type)
    
    def process_message(
        self, 
        message: str, 
        context: Optional[Dict] = None,
        conversation_history: Optional[List] = None
    ) -> Dict[str, Any]:
        """
        پردازش یک پیام ورودی و تولید پاسخ مناسب با ترکیب جستجوی پاسخ‌های از پیش‌تعریف‌شده و تولید پاسخ مبتنی بر هوش مصنوعی.
        
        این متد ابتدا نیت (intent) پیام را با سرویس ResponseMatcher تحلیل می‌کند و تلاش می‌کند پاسخ متناظر از پیش‌تعریف‌شده را بیابد. در صورت وجود پاسخ از پیش‌تعریف‌شده، آن را به فرمت خروجی استاندارد می‌سازد و سطح اطمینان مدل (`ai_confidence`) را روی 0.9 قرار می‌دهد. اگر پاسخی یافت نشود، تولید پاسخ به روش‌های مخصوص کاربر (patient یا doctor) به `_generate_ai_response` محول می‌شود. در انتها مدت زمان پردازش (`processing_time`) و نتیجه تحلیل نیت (`intent_analysis`) به پاسخ افزوده می‌شود.
        
        پارامترها:
            message: متن پیام ارسالی توسط کاربر — ورودی اصلی برای تحلیل نیت و تولید/جستجوی پاسخ.
            context: اطلاعات اختیاری مرتبط با زمینه یا متادیتای مکالمه که برای تولید پاسخ AI ممکن است استفاده شود.
            conversation_history: تاریخچه‌ی اختیاری پیام‌های قبلی در همان گفتگو که می‌تواند به تولید پاسخ‌های زمینه‌محور کمک کند.
        
        مقدار بازگشتی:
            Dict[str, Any] — ساختاری شامل حداقل فیلدهای `content`، `message_type`، `response_data`، `source`، `category`، `ai_confidence` و همچنین `processing_time` و `intent_analysis`. در حالت خطا مقدار بازگشتی از `_get_error_response()` استفاده می‌شود.
        
        مدیریت خطا:
            هر استثنایی که در جریان پردازش رخ دهد ثبت و با بازگشت مقدار جایگزین از `_get_error_response()` بازیابی می‌شود (یعنی متد استثنا را پاس‌نمی‌دهد).
        """
        start_time = time.time()
        
        try:
            # تحلیل هدف پیام
            intent_analysis = self.response_matcher.analyze_message_intent(message)
            
            # جستجو برای پاسخ از پیش تعریف شده
            predefined_response = self.response_matcher.find_matching_response(
                message, 
                category=intent_analysis.get('primary_intent')
            )
            
            if predefined_response:
                response = self._format_predefined_response(predefined_response)
                response['ai_confidence'] = 0.9
            else:
                # استفاده از AI برای تولید پاسخ
                response = self._generate_ai_response(
                    message, context, conversation_history, intent_analysis
                )
            
            # محاسبه زمان پردازش
            processing_time = time.time() - start_time
            response['processing_time'] = processing_time
            
            # اضافه کردن تحلیل هدف
            response['intent_analysis'] = intent_analysis
            
            return response
            
        except Exception as e:
            logger.error(f"خطا در پردازش پیام: {str(e)}")
            return self._get_error_response()
    
    def _format_predefined_response(self, response_obj) -> Dict[str, Any]:
        """
        فرمت یک پاسخ از پیش‌تعریف‌شده به ساختار خروجی استاندارد سرویس.
        
        پارامترها:
            response_obj: شیئی که نشان‌دهنده پاسخ از پیش‌تعریف‌شده است و باید دسترسی‌پذیر بودن این فیلدها را داشته باشد:
                - response_text: متن اصلی پاسخ (string)
                - response_data: داده‌های تکمیلی نمایش (مانند quick_replies یا متادیتا)
                - category: دسته‌بندی/نیت مرتبط با پاسخ (string)
        
        بازگشت:
            Dict[str, Any]: دیکشنری خروجی آماده برای مصرف توسط لایه نمایش که شامل کلیدهای زیر است:
                - content: متن پاسخ
                - message_type: نوع پیام (مثلاً 'text')
                - response_data: داده‌های تکمیلی
                - source: مشخص‌کننده منبع ('predefined')
                - category: دسته‌بندی نیت
                - ai_confidence: مقدار اطمینان مرتبط با این پاسخ (۰.۹)
        """
        return {
            'content': response_obj.response_text,
            'message_type': 'text',
            'response_data': response_obj.response_data,
            'source': 'predefined',
            'category': response_obj.category,
            'ai_confidence': 0.9
        }
    
    def _generate_ai_response(
        self, 
        message: str,
        context: Optional[Dict],
        conversation_history: Optional[List],
        intent_analysis: Dict
    ) -> Dict[str, Any]:
        """
        تولید پاسخ مبتنی بر هوش مصنوعی برای پیام ورودی و مسیردهی به تولیدکننده مناسب بر اساس نوع کاربر.
        
        این متد پاسخ AI را برای پیام ورودی آماده می‌کند و بسته به مقدار self.user_type مسیر تولید را به یکی از مولدهای اختصاصی منتقل می‌کند: برای 'patient' از _generate_patient_response و برای سایر انواع (مثل 'doctor') از _generate_doctor_response استفاده می‌شود. در نسخهٔ کنونی تولید پاسخ‌ها محلی و مبتنی بر نقشهٔ نیت‌ها است؛ پارامترهای context و conversation_history برای استفاده‌های آتی (مثلاً ارسال به API بیرونی یا حفظ وضعیت گفتگو) پذیرفته شده‌اند اما اکنون مستقیماً به تولیدکننده‌ها پاس داده نمی‌شوند.
        
        Parameters:
            message (str): متن پیام کاربر.
            context (Optional[Dict]): زمینهٔ مکالمه یا متادیتا (برای یکپارچه‌سازی با سرویس‌های خارجی یا منطق پیشرفتهٔ پاسخ‌دهی).
            conversation_history (Optional[List]): فهرست پیام‌های قبلی در گفتگو (برای استفاده در تولید پاسخ مبتنی بر زمینه).
            intent_analysis (Dict): خروجی تحلیل نیت پیام که شامل نیت‌های اصلی و احتمالات مرتبط است؛ مولدهای داخلی از این ساختار برای تعیین محتوای پاسخ استفاده می‌کنند.
        
        Returns:
            Dict[str, Any]: ساختار استاندارد پاسخ که شامل حداقل کلیدهای content، message_type، source، category و ai_confidence است (فرمت دقیق توسط مولدهای _generate_patient_response و _generate_doctor_response تعیین می‌شود).
        """
        # در حال حاضر از پاسخ‌های ساده استفاده می‌کنیم
        # در آینده می‌توان با API های AI خارجی یکپارچه کرد
        
        if self.user_type == 'patient':
            return self._generate_patient_response(message, intent_analysis)
        else:
            return self._generate_doctor_response(message, intent_analysis)
    
    def _generate_patient_response(self, message: str, intent_analysis: Dict) -> Dict[str, Any]:
        """
        تولید پاسخ مناسب برای کاربر از نوع "patient" بر اساس تحلیل نیت پیام.
        
        شرح:
        این متد برای تولید یک پاسخ متنی هدف‌مند برای بیمار استفاده می‌شود. ابتدا نیت اصلی (primary_intent) از intent_analysis استخراج می‌شود و اگر این نیت در نقشه‌ی پاسخ‌های از پیش تعریف‌شده (مانند 'symptom_inquiry', 'medication_info', 'appointment') وجود داشته باشد، پاسخ متناظر بازگردانده می‌شود با ai_confidence برابر 0.7 و شامل فیلدهای:
        
        - content: متن پیشنهادی قابل نمایش به کاربر
        - response_data: داده‌های کمکی برای رابط کاربری (مثلاً quick_replies)
        - message_type: نوع پیام ('text')
        - source: منبع پاسخ ('ai_generated')
        - category: دسته‌بندی نیت (primary_intent)
        
        اگر نیت شناخته‌شده نباشد، یک پاسخ پیش‌فرض راهنمایی‌کننده تولید می‌شود با ai_confidence برابر 0.5 و مجموعه‌ای از پیشنهادهای سریع عمومی.
        
        مقدار بازگشتی:
        یک دیکشنری شامل حداقل کلیدهای فوق (content, response_data, ai_confidence, message_type, source, category) که برای رندر در UI و تصمیم‌گیری‌های بعدی توسط سرویس‌های بالاتر قابل استفاده است.
        
        بدون اثرات جانبی خارجی (فقط مقدار بازگشتی تولید می‌شود).
        """
        primary_intent = intent_analysis.get('primary_intent')
        
        responses = {
            'symptom_inquiry': {
                'content': 'لطفاً علائم خود را به طور دقیق‌تر شرح دهید. چه زمانی شروع شده و شدت آن چگونه است؟',
                'response_data': {
                    'quick_replies': [
                        {'title': 'درد خفیف', 'payload': 'pain_mild'},
                        {'title': 'درد شدید', 'payload': 'pain_severe'},
                        {'title': 'تب دارم', 'payload': 'fever'},
                        {'title': 'سردرد', 'payload': 'headache'}
                    ]
                }
            },
            'medication_info': {
                'content': 'برای اطلاعات دقیق دارو، لطفاً نام دارو را بنویسید یا عکس جعبه دارو را ارسال کنید.',
                'response_data': {
                    'quick_replies': [
                        {'title': 'نام دارو', 'payload': 'medication_name'},
                        {'title': 'عوارض جانبی', 'payload': 'side_effects'},
                        {'title': 'نحوه مصرف', 'payload': 'dosage'}
                    ]
                }
            },
            'appointment': {
                'content': 'برای رزرو نوبت، لطفاً تخصص مورد نظر و زمان ترجیحی خود را مشخص کنید.',
                'response_data': {
                    'quick_replies': [
                        {'title': 'پزشک عمومی', 'payload': 'general_doctor'},
                        {'title': 'متخصص داخلی', 'payload': 'internal_medicine'},
                        {'title': 'روانپزشک', 'payload': 'psychiatrist'}
                    ]
                }
            }
        }
        
        if primary_intent in responses:
            response = responses[primary_intent].copy()
            response['ai_confidence'] = 0.7
        else:
            response = {
                'content': 'سؤال شما را دریافت کردم. می‌توانید سؤال خود را واضح‌تر بیان کنید تا بتوانم بهتر کمکتان کنم؟',
                'ai_confidence': 0.5,
                'response_data': {
                    'quick_replies': [
                        {'title': 'مشکل سلامتی', 'payload': 'health_issue'},
                        {'title': 'اطلاعات دارو', 'payload': 'medication'},
                        {'title': 'نوبت‌گیری', 'payload': 'appointment'}
                    ]
                }
            }
        
        response.update({
            'message_type': 'text',
            'source': 'ai_generated',
            'category': primary_intent or 'general'
        })
        
        return response
    
    def _generate_doctor_response(self, message: str, intent_analysis: Dict) -> Dict[str, Any]:
        """
        تولید پاسخ مناسب برای کاربران از نوع «پزشک» بر اساس تحلیل نیت پیام.
        
        شرح:
        این متد بر اساس مقدار `primary_intent` استخراج‌شده از `intent_analysis` پاسخی ساخت‌یافته برای پزشک تولید می‌کند. برای نیت‌های شناخته‌شده (مثل `symptom_inquiry` و `medication_info`) یک پاسخ قالبی با محتوای تخصصی، داده‌های کمکی (`response_data`) شامل پیشنهادها و پاسخ‌های سریع و درجه‌ی اعتماد AI (`ai_confidence`) بازمی‌گرداند. در صورت نیت نامشخص یا غیرفعال، یک پاسخ پیش‌فرض راهنمایی‌کننده با اعتماد کمتر تولید می‌شود. خروجی همیشه شامل فیلدهای متاِ‌دیتا زیر است: `message_type` برابر `'text'`, `source` برابر `'ai_generated'` و `category` که از `primary_intent` گرفته می‌شود یا `'general'` در صورت نبود آن.
        
        پارامترها:
            message (str): متن ورودی کاربر — صرفاً برای بافت/ردیابی؛ محتوا مستقیماً در انتخاب قالب پاسخ استفاده نمی‌شود.
            intent_analysis (Dict): نتیجه تحلیل نیت که حداقل شامل کلید `primary_intent` است؛ مقدار این کلید تعیین‌کننده قالب پاسخ خواهد بود.
        
        مقدار بازگشتی:
            Dict[str, Any]: دیکشنری پاسخ شامل حداقل کلیدهای `content`, `response_data`, `ai_confidence`, `message_type`, `source`, و `category`. ساختار `response_data` ممکن است حاوی `quick_replies` و/یا `suggestions` باشد.
        """
        primary_intent = intent_analysis.get('primary_intent')
        
        responses = {
            'symptom_inquiry': {
                'content': 'بر اساس علائم ذکر شده، پیشنهاد می‌کنم موارد زیر را بررسی کنید:',
                'response_data': {
                    'suggestions': [
                        'بررسی علائم حیاتی بیمار',
                        'انجام آزمایش‌های لازم',
                        'در نظر گیری تشخیص‌های افتراقی'
                    ],
                    'quick_replies': [
                        {'title': 'پروتکل درمان', 'payload': 'treatment_protocol'},
                        {'title': 'آزمایش‌های مورد نیاز', 'payload': 'required_tests'},
                        {'title': 'مشاوره تخصصی', 'payload': 'specialist_consult'}
                    ]
                }
            },
            'medication_info': {
                'content': 'اطلاعات دارویی و تداخلات احتمالی:',
                'response_data': {
                    'quick_replies': [
                        {'title': 'دوزاژ استاندارد', 'payload': 'standard_dosage'},
                        {'title': 'تداخلات دارویی', 'payload': 'drug_interactions'},
                        {'title': 'عوارض جانبی', 'payload': 'adverse_effects'}
                    ]
                }
            }
        }
        
        if primary_intent in responses:
            response = responses[primary_intent].copy()
            response['ai_confidence'] = 0.8
        else:
            response = {
                'content': 'چگونه می‌توانم در مورد این موضوع کمکتان کنم؟',
                'ai_confidence': 0.6,
                'response_data': {
                    'quick_replies': [
                        {'title': 'راهنمای تشخیص', 'payload': 'diagnosis_guide'},
                        {'title': 'پروتکل درمان', 'payload': 'treatment_protocol'},
                        {'title': 'مراجع علمی', 'payload': 'references'}
                    ]
                }
            }
        
        response.update({
            'message_type': 'text',
            'source': 'ai_generated',
            'category': primary_intent or 'general'
        })
        
        return response
    
    def _get_error_response(self) -> Dict[str, Any]:
        """
        یک خطی:
            بازگردانی پاسخ خطا‌ی مناسب برای ارسال به کاربر.
        
        توضیح:
            ابتدا تلاش می‌کند پاسخ خطای تعریف‌شده در ResponseMatcherService را بگیرد؛ اگر چنین پاسخی وجود داشته باشد، آن را با ساختار پاسخ‌های از پیش تعریف‌شده (_format_predefined_response) قالب‌بندی و برمی‌گرداند. در غیر این صورت یک پاسخ خطای پیش‌فرض سیستمی با محتوای قابل نمایش به کاربر بازمی‌گرداند.
        
        Returns:
            Dict[str, Any]: یک دیکشنری شامل اطلاعات پاسخ خطا. ساختار ممکن شامل کلیدهای زیر است:
                - content (str): متن پیام خطا که به کاربر نمایش داده می‌شود.
                - message_type (str): نوع پیام (معمولاً 'text').
                - source (str): منبع پاسخ ('predefined' یا 'system').
                - category (str): دسته‌بندی پاسخ (مثلاً 'error').
                - ai_confidence (float): نمره اطمینان مرتبط با پاسخ (برای پاسخ پیش‌فرض برابر 1.0).
            توجه: در حالت وجود پاسخ خطای از پیش تعریف‌شده، خروجی همان ساختار برگشتی _format_predefined_response خواهد بود.
        """
        error_response = self.response_matcher.get_error_response()
        
        if error_response:
            return self._format_predefined_response(error_response)
        
        return {
            'content': 'متأسفانه خطایی در پردازش پیام شما رخ داده است. لطفاً دوباره تلاش کنید.',
            'message_type': 'text',
            'source': 'system',
            'category': 'error',
            'ai_confidence': 1.0
        }
    
    def get_quick_replies_for_context(self, context: Optional[Dict] = None) -> List[Dict]:
        """
        بازگرداندن لیستی از پاسخ‌های سریع (quick replies) مناسب برای نوع کاربر و زمینهٔ اختیاری
        
        این متد فهرستی از گزینه‌های آماده را برای نمایش در رابط گفتگو تولید می‌کند. هر گزینه یک دیکشنری با کلیدهای:
        - `title`: متن قابل‌نمایش برای کاربر
        - `payload`: شناسه یا پی‌لودی که هنگام انتخاب گزینه ارسال می‌شود
        
        رفتار بر اساس نوع کاربر:
        - برای `patient` مجموعه‌ای از گزینه‌های مرتبط با بیماران (مانند «علائم من»، «اطلاعات دارو»، «نوبت‌گیری»، «راهنما») بازگردانده می‌شود.
        - برای سایر نوع‌ها (مثلاً پزشک) مجموعه‌ای از گزینه‌های مرتبط حرفه‌ای (مانند «راهنمای تشخیص»، «پروتکل‌های درمان»، «مراجع علمی»، «ابزارهای تشخیصی») بازگردانده می‌شود.
        
        پارامترها:
        - context (اختیاری): ساختار زمینهٔ فعلی گفتگو که در نسخه‌های آینده یا برای تعدیل پاسخ‌ها بر اساس وضعیت کاربر می‌تواند مورد استفاده قرار گیرد. در پیاده‌سازی فعلی برای انتخاب مجموعهٔ پایه استفاده می‌شود.
        
        بازگشتی:
        - List[Dict]: فهرستی از دیکشنری‌های quick-reply با کلیدهای `title` و `payload`.
        """
        if self.user_type == 'patient':
            return [
                {'title': 'علائم من', 'payload': 'my_symptoms'},
                {'title': 'اطلاعات دارو', 'payload': 'medication_info'},
                {'title': 'نوبت‌گیری', 'payload': 'book_appointment'},
                {'title': 'راهنما', 'payload': 'help'}
            ]
        else:
            return [
                {'title': 'راهنمای تشخیص', 'payload': 'diagnosis_guide'},
                {'title': 'پروتکل‌های درمان', 'payload': 'treatment_protocols'},
                {'title': 'مراجع علمی', 'payload': 'medical_references'},
                {'title': 'ابزارهای تشخیصی', 'payload': 'diagnostic_tools'}
            ]