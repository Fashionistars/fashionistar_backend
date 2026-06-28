"""
سرویس چت‌بات پزشک
Doctor Chatbot Service
"""

from typing import Dict, List, Optional, Any
from django.utils import timezone
from .base_chatbot import BaseChatbotService
from .ai_integration import AIIntegrationService


class DoctorChatbotService(BaseChatbotService):
    """
    سرویس چت‌بات اختصاصی پزشکان
    """
    
    def __init__(self, user):
        """
        سرویس چت‌بات مرتبط با پزشک را مقداردهی اولیه می‌کند.
        
        این سازنده شیء را با نقش 'doctor' در کلاس پایه‌ی BaseChatbotService مقداردهی می‌کند و یک نمونه از AIIntegrationService مخصوص پزشک (با تنظیمات/هماهنگی برای نقش 'doctor') را در self.ai_service قرار می‌دهد تا پردازش پیام‌ها و پاسخ‌های هوش مصنوعی را انجام دهد. این متد شناسهٔ کاربر را به کلاس پایه می‌سپارد تا زمینهٔ جلسه و دسترسی‌های مربوط به آن کاربر در سرویسِ پایه برقرار شود.
        
        Parameters:
            user: شیء نمایانگر کاربر پزشک — باید نمایانگر کاربر لاگین‌شده یا مدل کاربر مرتبط با پزشک باشد و توسط کلاس پایه برای مدیریت جلسه/ذخیره پیام استفاده شود.
        """
        super().__init__(user, 'doctor')
        self.ai_service = AIIntegrationService('doctor')
    
    def process_message(self, message: str, context: Optional[Dict] = None) -> Dict[str, Any]:
        """
        پردازش یک پیام از طرف پزشک و دریافت پاسخ تولیدشده توسط سرویس هوش مصنوعی.
        
        عملکرد:
        - پیام ورودی را با save_user_message ذخیره می‌کند.
        - آخرین ۱۵ پیام مکالمه را با get_conversation_history(15) بازیابی می‌نماید.
        - پیام، زمینه (context) و تاریخچه مکالمه را به ai_service.process_message ارسال می‌کند تا پاسخ هوش مصنوعی تولید شود.
        - پاسخ دریافتی از AI را با save_bot_message ذخیره می‌کند (شامل content، message_type، response_data، ai_confidence و processing_time در صورت وجود).
        - زمینه‌ی جلسه/سشن پزشک را با _update_doctor_context بر اساس پاسخ AI و زمینه ورودی به‌روزرسانی می‌کند.
        - شناسه‌های ایجادشده برای پیام کاربر و پیام ربات و شناسه‌های مکالمه و سشن جاری را به‌صورت رشته در خروجی برمی‌گرداند.
        
        پارامترها:
            message (str): متن پیام ارسالی توسط پزشک.
            context (Optional[Dict]): زمینه‌ی اضافی مرتبط با پیام (مثل اطلاعات بیمار، نوع درخواست یا متادیتا) که در فراخوانی AI و به‌روزرسانی سشن استفاده می‌شود.
        
        مقدار بازگشتی:
            Dict[str, Any]: دیکشنری شامل:
                - response: دیکشنری پاسخ کامل برگشتی از ai_service.process_message (شامل دستورات، محتوا، داده‌های پاسخ، امتیاز اطمینان و زمان پردازش در صورت وجود).
                - user_message_id: شناسه پیام کاربر به‌صورت رشته.
                - bot_message_id: شناسه پیام ربات ذخیره‌شده به‌صورت رشته.
                - conversation_id: شناسه مکالمه جاری به‌صورت رشته.
                - session_id: شناسه سشن جاری به‌صورت رشته.
        
        اثرات جانبی مهم:
        - ذخیره دائمی پیام کاربر و پیام ربات در سیستم.
        - به‌روزرسانی زمینه/حالت جلسه که ممکن است تماس‌های بعدی به AI را متاثر کند.
        """
        # ذخیره پیام کاربر
        user_message = self.save_user_message(message)
        
        # دریافت تاریخچه مکالمه
        conversation_history = self.get_conversation_history(15)
        
        # پردازش با AI
        ai_response = self.ai_service.process_message(
            message=message,
            context=context,
            conversation_history=conversation_history
        )
        
        # ذخیره پاسخ ربات
        bot_message = self.save_bot_message(
            content=ai_response['content'],
            message_type=ai_response.get('message_type', 'text'),
            response_data=ai_response.get('response_data', {}),
            ai_confidence=ai_response.get('ai_confidence'),
            processing_time=ai_response.get('processing_time')
        )
        
        # بروزرسانی زمینه جلسه
        self._update_doctor_context(ai_response, context)
        
        return {
            'response': ai_response,
            'user_message_id': str(user_message.id),
            'bot_message_id': str(bot_message.id),
            'conversation_id': str(self.current_conversation.id),
            'session_id': str(self.current_session.id)
        }
    
    def get_quick_replies(self, context: Optional[Dict] = None) -> List[Dict]:
        """
        بازگرداندن فهرست پاسخ‌های سریع (quick replies) مناسب برای پزشک براساس زمینه جلسه
        
        توضیح:
        این متد مجموعه‌ای از گزینه‌های پیش‌فرض پاسخ سریع را تولید می‌کند و در صورت وجود زمینه (context) آن‌ها را با گزینه‌های مرتبط تکمیل می‌کند. هر آیتم یک دیکشنری با کلیدهای `title` (متن قابل نمایش برای پزشک) و `payload` (شناسه عملیاتی که هنگام انتخاب ارسال می‌شود) است. پاسخ‌های پیش‌فرض شامل راهنمای تشخیص، پروتکل‌های درمانی، تداخلات دارویی و مراجع علمی است.
        
        پارامترها:
            context (Optional[Dict]): زمینه جلسه/نشست که می‌تواند نشان‌دهنده حالت‌های خاصی برای ارائه گزینه‌های زمینه‌محور باشد.
                - اگر context شامل کلید `'patient_case'` باشد، گزینه‌های مرتبط با مرور کیس و تشخیص افتراقی (`case_review`, `differential_diagnosis`) اضافه می‌شوند.
                - اگر context شامل کلید `'medication_query'` باشد، گزینه‌های مرتبط با دارو مانند دوزاژ استاندارد و عوارض جانبی (`standard_dosage`, `side_effects`) اضافه می‌شوند.
                - سایر کلیدهای زمینه در حال حاضر نادیده گرفته می‌شوند، اما تابع طوری طراحی شده که به‌راحتی بتوان گزینه‌های زمینه‌ای جدید را بر اساس کلیدهای اضافی افزود.
        
        مقدار بازگشتی:
            List[Dict]: لیستی از دیکشنری‌ها با ساختار {'title': str, 'payload': str}. `payload` برای مسیردهی داخلی یا فراخوانی سرویس‌های بعدی (مثل درخواست تشخیص، بازیابی اطلاعات دارویی، یا جستجوی مراجع) استفاده می‌شود.
        
        نکات عملیاتی:
            - این تابع حالت را تغییر نمی‌دهد و تنها گزینه‌ها را برمی‌گرداند؛ تصمیم‌گیری نهایی و پردازش زمانی که کاربر یک payload را انتخاب کند باید در لایه‌های بالاتر (مانند process_message یا روت‌های API) انجام شود.
            - شناسه‌های payload باید در سیستم با هندلرهای مرتبط مطابقت داشته باشند تا هنگام انتخاب، عملیات مناسب اجرا شود.
        """
        base_replies = [
            {'title': 'راهنمای تشخیص', 'payload': 'diagnosis_guide'},
            {'title': 'پروتکل‌های درمان', 'payload': 'treatment_protocols'},
            {'title': 'تداخلات دارویی', 'payload': 'drug_interactions'},
            {'title': 'مراجع علمی', 'payload': 'medical_references'}
        ]
        
        # پاسخ‌های زمینه‌محور
        if context:
            if context.get('patient_case'):
                base_replies.extend([
                    {'title': 'بررسی کیس', 'payload': 'case_review'},
                    {'title': 'تشخیص احتمالی', 'payload': 'differential_diagnosis'}
                ])
            
            if context.get('medication_query'):
                base_replies.extend([
                    {'title': 'دوزاژ استاندارد', 'payload': 'standard_dosage'},
                    {'title': 'عوارض جانبی', 'payload': 'side_effects'}
                ])
        
        return base_replies
    
    def get_diagnosis_support(self, symptoms: List[str], patient_info: Dict = None) -> Dict[str, Any]:
        """
        ایجاد پشتیبانی تشخیصی برای پزشک.
        
        این متد درخواست تشخیصی را از روی فهرست علائم (و در صورت فراهم بودن اطلاعات بیمار) پردازش می‌کند: در صورت وجود مکالمه جاری، نوع آن را به 'doctor_consultation' تغییر می‌دهد، یک ورودی `diagnosis_request` شامل علائم، اطلاعات بیمار و زمان درخواست را در زمینه جلسه ذخیره می‌کند و سپس با فراخوانی هِلپر تحلیلی `_analyze_symptoms_for_diagnosis` (که می‌تواند شامل قواعد بالینی داخلی یا فراخوانی سرویس‌های هوش مصنوعی/تحلیل باشد) یک تحلیل تشخیصی تولید می‌کند. پاسخ بازگشتی ساختاری استاندارد شامل متن خلاصه، نوع پیام و داده‌های تفصیلی تشخیصی (تشخیص‌های تفاضلی، تست‌های پیشنهادی، گزینه‌های درمانی، راهنمای پیگیری) و گزینه‌های سریع (quick replies) برای اقدامات بعدی را فراهم می‌آورد.
        
        Parameters:
            symptoms (List[str]): فهرست علائم گزارش‌شده که باید برای تولید فهرست تشخیص‌های محتمل تحلیل شوند.
            patient_info (Dict, optional): اطلاعات تکمیلی بیمار (مثلاً سن، جنس، سابقه بیماری، آلرژی‌ها) که در تحلیل تشخیصی و توصیه‌های تست/درمان تأثیر می‌گذارد.
        
        Returns:
            Dict[str, Any]: دیکشنری حاوی:
                - content (str): متن خلاصه‌ای که به پزشک نمایش داده می‌شود.
                - message_type (str): نوع پیام (معمولاً 'text').
                - response_data (dict): شامل کلیدهای:
                    - differential_diagnoses: لیست تشخیص‌های تفاضلی با جزئیات (نام، احتمال، علائم مرتبط، شدت).
                    - recommended_tests: فهرست تست‌های تشخیصی پیشنهادشده با دلایل.
                    - treatment_options: گزینه‌های درمانی اولیه و ملاحظات مرتبط.
                    - guidelines: نکات پایشی، پیگیری و آموزش بیمار.
                    - quick_replies: گزینه‌های آماده برای تعامل بعدی (مثلاً درخواست آزمایش بیشتر، ارجاع به متخصص، دریافت پروتکل درمان).
        """
        # تغییر نوع مکالمه
        if self.current_conversation:
            self.current_conversation.conversation_type = 'doctor_consultation'
            self.current_conversation.save()
        
        # ذخیره اطلاعات کیس در زمینه
        self._update_session_context({
            'diagnosis_request': {
                'symptoms': symptoms,
                'patient_info': patient_info,
                'requested_at': str(timezone.now())
            }
        })
        
        # تحلیل علائم
        diagnosis_analysis = self._analyze_symptoms_for_diagnosis(symptoms, patient_info)
        
        return {
            'content': 'بر اساس علائم ارائه شده، تشخیص‌های احتمالی زیر پیشنهاد می‌شود:',
            'message_type': 'text',
            'response_data': {
                'differential_diagnoses': diagnosis_analysis['diagnoses'],
                'recommended_tests': diagnosis_analysis['tests'],
                'treatment_options': diagnosis_analysis['treatments'],
                'guidelines': diagnosis_analysis['guidelines'],
                'quick_replies': [
                    {'title': 'آزمایش‌های بیشتر', 'payload': 'additional_tests'},
                    {'title': 'مشاوره تخصصی', 'payload': 'specialist_consult'},
                    {'title': 'پروتکل درمان', 'payload': 'treatment_protocol'}
                ]
            }
        }
    
    def get_medication_info(self, medication_name: str, patient_context: Dict = None) -> Dict[str, Any]:
        """
        بازگرداندن اطلاعات جامع دربارهٔ یک دارو و به‌روزرسانی زمینهٔ جلسه با جزئیات پرس‌وجو.
        
        این متد:
        - یک ورودی جستجوی دارویی را در زمینهٔ جلسه ذخیره می‌کند (کلید `medication_query`) که شامل نام دارو، زمینهٔ بیمار (در صورت وجود) و زمان پرس‌وجو است.
        - جزئیات دارو را از متد کمکی `_get_medication_details` واکشی می‌کند.
        - پاسخِ آماده برای ارسال به کاربر را شامل متن خلاصه، نوع پیام و داده‌های ساختاری‌شده بازمی‌گرداند.
        
        پارامترها:
            medication_name (str): نام دارویی که باید اطلاعات آن بازیابی شود.
            patient_context (Dict, optional): اطلاعات بالینی یا ویژگی‌های بیمار که می‌تواند بر تداخل‌ها، دوزاژ یا احتیاط‌ها تأثیر بگذارد.
        
        مقدار بازگشتی:
            Dict[str, Any]: دیکشنری شامل:
                - content (str): متن خلاصه‌ای که برای نمایش به کاربر ساخته شده (مثلاً "اطلاعات دارویی <نام>").
                - message_type (str): نوع پیام (اینجا 'text').
                - response_data (dict):
                    - medication_details (dict): ساختار جزئیات دارو که از `_get_medication_details` برگشت داده می‌شود (نام عمومی، اشکال دارویی، دوزاژ‌های استاندارد، موارد منع مصرف، عوارض جانبی، تداخلات و غیره).
                    - quick_replies (List[dict]): گزینه‌های پاسخ سریع مرتبط (مثلاً تداخلات، دوزاژ بالغین، عوارض جانبی، موارد احتیاط) به شکل آرایه‌ای از آبجکت‌هایی با فیلدهای `title` و `payload`.
        
        اثرات جانبی:
            - زمینهٔ جلسه با کلید `medication_query` و زمان پرس‌وجو به‌روزرسانی می‌شود.
        """
        # ذخیره درخواست در زمینه
        self._update_session_context({
            'medication_query': {
                'medication': medication_name,
                'patient_context': patient_context,
                'queried_at': str(timezone.now())
            }
        })
        
        # دریافت اطلاعات دارو
        medication_info = self._get_medication_details(medication_name, patient_context)
        
        return {
            'content': f'اطلاعات دارویی {medication_name}:',
            'message_type': 'text',
            'response_data': {
                'medication_details': medication_info,
                'quick_replies': [
                    {'title': 'تداخلات دارویی', 'payload': f'interactions_{medication_name}'},
                    {'title': 'دوزاژ بالغین', 'payload': f'adult_dosage_{medication_name}'},
                    {'title': 'عوارض جانبی', 'payload': f'side_effects_{medication_name}'},
                    {'title': 'موارد احتیاط', 'payload': f'precautions_{medication_name}'}
                ]
            }
        }
    
    def get_treatment_protocol(self, condition: str, severity: str = 'moderate') -> Dict[str, Any]:
        """
        بازگرداندن پروتکل درمانی برای یک بیماری با سطح شدت مشخص.
        
        این متد یک درخواست پروتکل درمانی را در زمینه‌ی جلسه ثبت می‌کند (فیلدی به نام `treatment_protocol_request` شامل `condition`، `severity`` و `requested_at` با زمان فعلی) و سپس از هِلپر داخلی `_get_treatment_protocol_details` برای واکشی جزئیات پروتکل استفاده می‌کند. خروجی ساختاری است که برای ارسال به لایه‌ی چت/رابط کاربری مناسب است و شامل متن خلاصه، نوع پیام و داده‌های پاسخ (`protocol` و گزینه‌های پاسخ سریع) می‌باشد.
        
        پارامترها:
            condition (str): نام بیماری یا وضعیت بالینی که پروتکل برای آن خواسته شده است.
            severity (str, optional): میزان شدت وضعیت؛ مقدارهای متداول: `'mild'`, `'moderate'`, `'severe'`. مقدار پیش‌فرض `'moderate'` است.
        
        مقدار بازگشتی:
            Dict[str, Any]: دیکشنری شامل:
                - content (str): متن خلاصه قابل نمایش به کاربر دربارهٔ پروتکل.
                - message_type (str): نوع پیام (معمولاً `'text'`).
                - response_data (dict): شامل کلیدهای:
                    - protocol: ساختار جزئیات پروتکل برگرفته از `_get_treatment_protocol_details`.
                    - quick_replies: لیستی از گزینه‌های سریع مرتبط (مثل مرحله بعدی، عوارض احتمالی، پیگیری درمان).
        
        توجه:
            - زمان ثبت درخواست با Django `timezone.now()` گرفته می‌شود.
            - خودِ استخراج و نگارش دقیق پروتکل توسط `_get_treatment_protocol_details` انجام می‌شود؛ این متد فقط زمینه را به‌روز و پاسخ را قالب‌بندی می‌کند.
        """
        # ذخیره درخواست در زمینه
        self._update_session_context({
            'treatment_protocol_request': {
                'condition': condition,
                'severity': severity,
                'requested_at': str(timezone.now())
            }
        })
        
        protocol = self._get_treatment_protocol_details(condition, severity)
        
        return {
            'content': f'پروتکل درمان {condition} (شدت: {severity}):',
            'message_type': 'text',
            'response_data': {
                'protocol': protocol,
                'quick_replies': [
                    {'title': 'مرحله بعدی', 'payload': 'next_step'},
                    {'title': 'عوارض احتمالی', 'payload': 'potential_complications'},
                    {'title': 'پیگیری درمان', 'payload': 'treatment_followup'}
                ]
            }
        }
    
    def search_medical_references(self, query: str, specialty: str = None) -> Dict[str, Any]:
        """
        جستجوی مراجع پزشکی و به‌روزرسانی زمینه جلسه برای ثبت عملیات جستجو.
        
        شرح:
            این متد عبارت جستجو و تخصص (اختیاری) را دریافت کرده، یک ورودی `medical_search` شامل query، specialty و زمان جستجو را در زمینه جلسه ذخیره می‌کند و سپس با استفاده از هِلمپر داخلی `_search_medical_literature` نتایج مرتبط را بازیابی می‌کند. خروجی شامل متن خلاصه نتایج، نوع پیام و داده‌های ساختاری‌شده‌ای است که نتایج جستجو، تعداد نتایج و گزینه‌های پاسخ سریع (quick replies) را ارائه می‌دهد.
        
        پارامترها:
            query (str): متن یا عبارت جستجو که برای یافتن مقالات، راهنماها یا منابع بالینی استفاده می‌شود.
            specialty (str | None): تخصص پزشکی مورد نظر برای محدود کردن یا فیلتر کردن نتایج (اختیاری).
        
        بازگشت:
            Dict[str, Any]: دیکشنری شامل:
                - content (str): متن خلاصه‌ای از نتایج برای نمایش به کاربر.
                - message_type (str): نوع پیام (مثلاً 'text').
                - response_data (dict): شامل کلیدهای:
                    - search_results (list): لیستی از نتیجه‌های بازگشتی توسط `_search_medical_literature` (هر مورد شامل عنوان، نویسندگان/سازمان، سال، خلاصه و لینک).
                    - total_results (int): تعداد نتایج بازگشتی.
                    - quick_replies (list): گزینه‌های پیشنهادی برای ادامه تعامل (مثلاً جستجوی دقیق‌تر، مراجع مرتبط، راهنماهای بالینی).
        
        تأثیرات جانبی:
            - زمینه جلسه (session context) با کلید `medical_search` به‌روزرسانی می‌شود تا تاریخچه و پارامترهای جستجو ثبت شود.
            - از هِلمپر داخلی `_search_medical_literature` برای دریافت نتایج استفاده می‌شود؛ این متد ممکن است دادهٔ ساختگی یا نتایج واقعی بسته به پیاده‌سازی داخلی برگرداند.
        """
        # ذخیره جستجو در زمینه
        self._update_session_context({
            'medical_search': {
                'query': query,
                'specialty': specialty,
                'searched_at': str(timezone.now())
            }
        })
        
        search_results = self._search_medical_literature(query, specialty)
        
        return {
            'content': f'نتایج جستجو برای "{query}":',
            'message_type': 'text',
            'response_data': {
                'search_results': search_results,
                'total_results': len(search_results),
                'quick_replies': [
                    {'title': 'جستجوی دقیق‌تر', 'payload': 'refine_search'},
                    {'title': 'مراجع مرتبط', 'payload': 'related_references'},
                    {'title': 'راهنماهای بالینی', 'payload': 'clinical_guidelines'}
                ]
            }
        }
    
    def _analyze_symptoms_for_diagnosis(self, symptoms: List[str], patient_info: Dict = None) -> Dict[str, Any]:
        """
        تحلیل علائم بالینی و تولید پیشنهادات تشخیصی، آزمایشی و درمانی مبتنی بر ورودی‌ها.
        
        شرح:
        این متد فهرستی از علائم و در صورت موجود، اطلاعات پایه بیمار را دریافت می‌کند و یک تحلیل تشخیصی خلاصه‌شده برمی‌گرداند که شامل فهرست تشخیص‌های محتمل (با تخمین احتمال و علائم منطبق و شدت)، آزمایش‌های پیشنهادی، گزینه‌های درمانی و راهنمایی‌های پیگیری است. در پیاده‌سازی کنونی خروجی نمونه‌ای و ثابت است و محل جایگزینی با موتور تحلیل بالینی واقعی (پایگاه‌داده پزشکی، قوانین بالینی یا API سرویس هوش مصنوعی) را نشان می‌دهد.
        
        پارامترها:
            symptoms (List[str]): فهرست علائم گزارش‌شده توسط پزشک یا بیمار؛ برای مطابقت با الگوهای تشخیصی استفاده می‌شود.
            patient_info (Dict, optional): اطلاعات تکمیلی مربوط به بیمار (مثلاً سن، جنس، تاریخچه بیماری، داروهای جاری) که می‌تواند در نسخه‌های آینده برای تعدیل احتمالات و توصیه‌ها به‌کار رود.
        
        مقدار بازگشتی:
            Dict[str, Any]: دیکشنری شامل کلیدهای زیر:
              - diagnoses (List[Dict]): فهرست کاندیدهای تشخیصی؛ هر مورد شامل
                    - name (str): نام تشخیص پیشنهادی
                    - probability (float): برآورد احتمال (۰ تا ۱)
                    - symptoms_match (List[str]): علائمی از ورودی که با این تشخیص منطبق‌اند
                    - severity (str): برآورد شدت یا دامنهٔ بیماری
              - tests (List[str]): آزمایش‌ها و بررسی‌های تکمیلی پیشنهادی برای ارزیابی یا تایید تشخیص‌ها
              - treatments (List[str]): گزینه‌های درمانی اولیه یا حمایتی که می‌توانند در نظر گرفته شوند
              - guidelines (List[str]): نکات پیگیری، هشدارهای بالینی و آموزش‌های بیمار
        
        نکات پیاده‌سازی:
        - این متد باید در آینده با یک موتور تشخیصی واقعی (قواعد بالینی، مدل‌های AI یا پایگاه‌های داده دارویی/تشخیصی) یکپارچه شود تا خروجی‌ها بر اساس محتوای ورودی و زمینهٔ بیمار سفارشی شوند.
        - اگر patient_info ارائه شود، پیاده‌سازی واقعی باید از آن برای تعدیل احتمال‌ها، متوقف کردن پیشنهادات نامناسب (مثلاً تداخل دارویی یا منع مصرف) و شخصی‌سازی دوزها/رهنمودها استفاده کند.
        """
        # این بخش باید با پایگاه‌داده پزشکی یا AI API یکپارچه شود
        # در حال حاضر نمونه‌ای ساده ارائه می‌دهیم
        
        common_diagnoses = [
            {
                'name': 'عفونت دستگاه تنفسی فوقانی',
                'probability': 0.7,
                'symptoms_match': ['سردرد', 'تب', 'گلودرد'],
                'severity': 'خفیف تا متوسط'
            },
            {
                'name': 'گاستریت',
                'probability': 0.5,
                'symptoms_match': ['درد شکم', 'تهوع'],
                'severity': 'متوسط'
            }
        ]
        
        recommended_tests = [
            'آزمایش خون کامل (CBC)',
            'CRP و ESR',
            'کشت ادرار (در صورت نیاز)'
        ]
        
        treatment_options = [
            'درمان علامتی',
            'آنتی‌بیوتیک (در صورت تأیید عفونت باکتریال)',
            'مسکن و ضد تب'
        ]
        
        guidelines = [
            'پیگیری بیمار در صورت عدم بهبودی ظرف ۴۸ ساعت',
            'آموزش بیمار در مورد علائم خطر',
            'تجویز استراحت و مصرف مایعات فراوان'
        ]
        
        return {
            'diagnoses': common_diagnoses,
            'tests': recommended_tests,
            'treatments': treatment_options,
            'guidelines': guidelines
        }
    
    def _get_medication_details(self, medication_name: str, patient_context: Dict = None) -> Dict[str, Any]:
        """
        بازگرداندن جزئیات دارویی (قالب داده‌ای استاندارد، نمونهٔ موقتی)
        
        شرح:
            این متد اطلاعات ساختاریافته دربارهٔ یک دارو را برمی‌گرداند. داده‌های خروجی نمونه (mock) هستند و باید در سطح تولید با پایگاه‌داده دارویی/خدمات اطلاعات دارویی واقعی یکپارچه شوند.
            مقدار بازگشتی برای ساخت پاسخ‌های چت، نمایش اطلاعات دارو به پزشک و استفادهٔ داخلی (مثلاً تکمیل سریع‌پاسخ‌ها یا بررسی تداخلات) طراحی شده است.
        
        پارامترها:
            medication_name (str):
                نام عمومی یا نام معاملاتی دارو که برای پر کردن فیلد `generic_name` و جستجوی اطلاعات استفاده می‌شود.
            patient_context (Dict, اختیاری):
                زمینهٔ بالینی بیمار که می‌تواند برای تنظیم دوز، هشدارهای مبتنی بر وضعیت (مثلاً نارسایی کلیه، سن، بارداری) یا ارائهٔ توصیه‌های اختصاصی مورد استفاده قرار گیرد. در پیاده‌سازی نمونه فعلی از patient_context صرفاً برای ثبت زمینه نگهداری می‌شود اما باید در نسخهٔ نهایی برای محاسبات دوز و فیلتر کردن هشدارها به کار گرفته شود.
        
        خروجی:
            Dict[str, Any]: یک دیکشنری با ساختار نمونه شامل کلیدهای زیر:
                - generic_name: نام عمومی دارو (str)
                - brand_names: فهرست نام‌های تجاری (List[str])
                - dosage_forms: اشکال دارویی (List[str])
                - standard_dosage: دوزهای مرجع برای گروه‌های سنی/وزنی (Dict)
                - contraindications: موارد منع مصرف (List[str])
                - side_effects: عوارض جانبی شایع/مهم (List[str])
                - interactions: داروهایی که تداخل بالینی دارند (List[str])
                - pregnancy_category: دسته‌بندی بارداری/شیردهی (str)
                - monitoring_required: آزمایش‌ها یا پایش‌های توصیه‌شده (List[str])
        
        توجهات عملی:
            - این متد در حال حاضر دادهٔ ثابت نمونه بازمی‌گرداند؛ آسوده‌سازی بالینی یا تصمیم‌گیری نباید بر اساس این خروجی صورت گیرد تا زمانی که منبع دادهٔ معتبر جایگزین شود.
            - در ادغام نهایی، patient_context باید برای محاسبهٔ دوز واقعی، بررسی تداخلات مبتنی بر داروهای جاری بیمار و تولید هشدارهای ایمنی استفاده شود.
        """
        # نمونه اطلاعات دارویی - باید با پایگاه‌داده دارویی یکپارچه شود
        return {
            'generic_name': medication_name,
            'brand_names': ['نام تجاری ۱', 'نام تجاری ۲'],
            'dosage_forms': ['قرص', 'کپسول', 'شربت'],
            'standard_dosage': {
                'adult': '۵۰۰ میلی‌گرم هر ۸ ساعت',
                'pediatric': '۲۵ میلی‌گرم/کیلوگرم هر ۸ ساعت'
            },
            'contraindications': ['حساسیت به دارو', 'نارسایی کلیوی شدید'],
            'side_effects': ['تهوع', 'سردرد', 'خستگی'],
            'interactions': ['وارفارین', 'دیگوکسین'],
            'pregnancy_category': 'B',
            'monitoring_required': ['تست‌های کبدی', 'تست‌های کلیوی']
        }
    
    def _get_treatment_protocol_details(self, condition: str, severity: str) -> Dict[str, Any]:
        """
        بازگرداندن جزئیات پروتکل درمانی برای یک بیماری و شدت مشخص.
        
        این متد ساختاری استاندارد شده از جزئیات پروتکل درمانی را برمی‌گرداند که برای نمایش به پزشک یا استفاده در جریان گفتگو با چت‌بات طراحی شده است. خروجی شامل گزینه‌های درمان خط اول و دوم، مدت درمان، مانیتورینگ لازم، زمان‌بندی پیگیری، عوارضی که باید رصد شوند و نکات آموزش به بیمار است. در پیاده‌سازی فعلی مقادیر نمونه (placeholder) هستند و باید با راهنماهای بالینی و منابع دارویی معتبر یکپارچه و بروز شوند. مقدار بازگشتی می‌تواند بر اساس پارامتر severity شخصی‌سازی شود؛ در نسخه نمونه فعلی تطبیق واقعی انجام نمی‌پذیرد.
        
        Parameters:
            condition (str): نام یا شناسه بیماری/شرایط بالینی که پروتکل برای آن درخواست شده است.
            severity (str): شدت وضعیت بالینی (مثلاً 'mild'، 'moderate'، 'severe') که برای تعدیل گزینه‌ها و مدت درمان به کار می‌رود.
        
        Returns:
            Dict[str, Any]: دیکشنری حاوی کلیدهای زیر:
                - 'first_line_treatment' (List[str]): گزینه‌های درمان خط اول.
                - 'second_line_treatment' (List[str]): گزینه‌های درمان خط دوم در صورت شکست یا عدم پاسخ.
                - 'duration' (str): مدت یا بازه زمانی درمان توصیه‌شده.
                - 'monitoring' (List[str]): آیتم‌های ضروری برای پایش بیمار حین درمان.
                - 'follow_up' (str): توصیه زمان‌بندی بازدید/پیگیری بعدی.
                - 'complications_to_watch' (List[str]): عوارض یا هشدارهایی که باید رصد شوند.
                - 'patient_education' (List[str]): نکات آموزشی که باید به بیمار منتقل شود.
        """
        # نمونه پروتکل درمان - باید با راهنماهای بالینی یکپارچه شود
        return {
            'first_line_treatment': ['دارو A', 'دارو B'],
            'second_line_treatment': ['دارو C', 'دارو D'],
            'duration': '۷-۱۰ روز',
            'monitoring': ['علائم حیاتی', 'پاسخ به درمان'],
            'follow_up': 'بازدید مجدد پس از ۴۸ ساعت',
            'complications_to_watch': ['عارضه A', 'عارضه B'],
            'patient_education': ['نکات مراقبتی', 'علائم خطر']
        }
    
    def _search_medical_literature(self, query: str, specialty: str = None) -> List[Dict]:
        """
        جستجوی متون و منابع پزشکی مرتبط با عبارت و تخصص مشخص و بازگرداندن نتایج ساخت‌یافته.
        
        توضیح:
        این متد عبارت جستجو (query) و در صورت وجود تخصص (specialty) را می‌گیرد، جستجوی منابع پزشکی را اجرا می‌کند و لیستی از نتایج ساخت‌یافته شامل مقالات، راهنماهای بالینی یا منابع مرتبط را برمی‌گرداند. خروجی برای هر مورد اطلاعاتی مانند عنوان، نویسندگان یا سازمان منتشرکننده، مجله/سال، خلاصه یا چکیده و لینک دسترسی را شامل می‌شود. پیاده‌سازی فعلی نمونه (placeholder) است و باید با موتور جستجو یا پایگاه‌داده مراجع پزشکی (کتابخانه‌های علمی، APIهای مقالات، آرشیوهای بالینی) یکپارچه شود تا:
        - نتایج بر اساس مرتبط بودن (relevance) و تاریخ مرتب یا رتبه‌بندی شوند،
        - فیلترهای تخصصی اعمال شوند (specialty) برای محدودسازی به حوزه‌های بالینی خاص،
        - متادیتاهای کامل‌تری مانند DOI، شناسه PubMed، نوع سند (مقاله پژوهشی، مرور، راهنما) و امتیاز اعتبار منابع افزوده شود.
        
        پارامترها:
            query (str): متن یا عبارات جستجو؛ می‌تواند شامل علائم، بیماری‌ها، داروها یا عبارات بالینی باشد.
            specialty (str | None): در صورت مشخص شدن، جستجو را به حوزهٔ تخصصی (مثلاً 'cardiology', 'endocrinology') محدود می‌کند.
        
        بازگشت:
            List[Dict]: لیستی از دیکشنری‌ها که هرکدام نمایانگر یک نتیجه هستند. فیلدهای معمول شامل:
                - title (str): عنوان منبع
                - authors (List[str]) یا organization (str): فهرست نویسندگان یا سازمان منتشرکننده
                - journal (str) یا source (str): نام مجله یا منبع
                - year (int): سال انتشار
                - abstract یا summary (str): چکیده یا خلاصه
                - link (str): آدرس دسترسی به منبع
        توجه: ساختار خروجی ممکن است بسته به منبع داده تغییر کند؛ هنگام یکپارچه‌سازی با پایگاه واقعی، سازگاری و نرمال‌سازی فیلدها الزامی است.
        """
        # نمونه نتایج - باید با پایگاه‌داده مراجع پزشکی یکپارچه شود
        return [
            {
                'title': f'مقاله مرتبط با {query}',
                'authors': ['نویسنده ۱', 'نویسنده ۲'],
                'journal': 'مجله پزشکی',
                'year': 2023,
                'abstract': 'خلاصه مقاله...',
                'link': 'https://example.com/article1'
            },
            {
                'title': f'راهنمای بالینی {query}',
                'organization': 'انجمن پزشکی',
                'year': 2023,
                'summary': 'خلاصه راهنما...',
                'link': 'https://example.com/guideline1'
            }
        ]
    
    def _update_doctor_context(self, ai_response: Dict, context: Optional[Dict]):
        """
        به‌روزرسانی زمینه (session context) مخصوص کاربری با نقش پزشک بر اساس پاسخ مدل هوش مصنوعی و زمینه ورودی.
        
        این متد یک ساختار به‌روزرسانی تولید می‌کند که شامل:
        - last_interaction: زمان فعلی به‌عنوان نشانگر آخرین تعامل
        - last_category: دسته‌بندی‌ای که از ai_response استخراج می‌شود (اگر موجود باشد)
        - confidence_score: نمره اطمینان/اعتماد مدل از ai_response (ai_confidence)
        - consultation_type: در صورت وجود، نوع مشاوره از context
        
        در ادامه، اگر context ارائه شده باشد، کل کلید-مقدارهای آن با اولویت بر مقادیر پیش‌فرض با ساختار updates ادغام می‌شوند. در نهایت این داده‌ها از طریق متد داخلی _update_session_context در جلسه ذخیره می‌شوند.
        
        پارامترها:
            ai_response (Dict): پاسخ تولیدشده توسط سرویس/مدل هوش مصنوعی؛ حداقل برای استخراج کلیدهای `category` و `ai_confidence` مورد استفاده قرار می‌گیرد.
            context (Optional[Dict]): زمینه جلسه یا اطلاعات تکمیلی مرتبط با گفتگو که باید در زمینه جلسه ادغام شود.
        
        تأثیرات جانبی:
            - زمینه جلسه را با اطلاعات جدید به‌روزرسانی می‌کند (از طریق _update_session_context).
        """
        updates = {
            'last_interaction': str(timezone.now()),
            'last_category': ai_response.get('category'),
            'confidence_score': ai_response.get('ai_confidence'),
            'consultation_type': context.get('consultation_type') if context else None
        }
        
        if context:
            updates.update(context)
        
        self._update_session_context(updates)