"""
سرویس چت‌بات بیمار
Patient Chatbot Service
"""

from typing import Dict, List, Optional, Any
from .base_chatbot import BaseChatbotService
from .ai_integration import AIIntegrationService


class PatientChatbotService(BaseChatbotService):
    """
    سرویس چت‌بات اختصاصی بیماران
    """
    
    def __init__(self, user):
        """
        سرویس چت‌بات ویژه بیمار را مقداردهی اولیه می‌کند.
        
        این سازنده سرویس پایه را با نقش/نوع 'patient' برای کاربر مشخص‌شده راه‌اندازی می‌کند و یک نمونه از سرویس یکپارچه‌سازی هوش مصنوعی (برای دامنه‌ی بیمار) را در self.ai_service ایجاد می‌کند تا تمام پردازش‌های زبانی و تولید پاسخ‌های مبتنی بر زمینه برای این سرویس استفاده شود.
        
        Parameters:
            user: شیء نمایانگر کاربر بیمار (حاوی شناسه و داده‌های مرتبط با جلسه/پروفایل) که سرویس برای آن ساخته می‌شود.
        """
        super().__init__(user, 'patient')
        self.ai_service = AIIntegrationService('patient')
    
    def process_message(self, message: str, context: Optional[Dict] = None) -> Dict[str, Any]:
        """
        یک پیام کاربر را پردازش کرده، به مدل هوش مصنوعی ارسال می‌کند، پاسخ حاصل را ذخیره و زمینه جلسه را به‌روز می‌کند.
        
        شرح:
        - پیام کاربر را در پایگاه داده ذخیره می‌کند.
        - آخرین ۱۰ پیام مکالمه را برای زمینه گفتگو فراخوانی کرده و همراه با پارامترهای اختیاری `context` به سرویس AI می‌فرستد.
        - از پاسخ سرویس AI محتوا، نوع پیام، داده‌های پاسخ، امتیاز اطمینان و زمان پردازش استخراج و یک پیام ربات جدید ذخیره می‌کند.
        - زمینه جلسه/کاربر را بر اساس متادیتای خروجی AI و ورودی `context` به‌روزرسانی می‌کند.
        - شناسه‌های پیام کاربر، پیام ربات، مکالمه جاری و جلسه جاری را در قالب یک دیکشنری بازمی‌گرداند.
        
        پارامترها:
            message (str): متن پیام کاربر که باید پردازش شود.
            context (Optional[Dict]): داده‌های زمینه‌ای اضافی که می‌تواند اطلاعات مربوط به وضعیت کاربر، متادیتا یا گزینه‌های خاص پردازش را شامل شود.
        
        مقدار بازگشتی:
            Dict[str, Any]: دیکشنری شامل:
                - 'response': پاسخ کامل سرویس AI (محتوا، response_data، ai_confidence، processing_time و غیره).
                - 'user_message_id': شناسه ذخیره‌شده پیام کاربر (رشته).
                - 'bot_message_id': شناسه پیام تولیدشده و ذخیره‌شده ربات (رشته).
                - 'conversation_id': شناسه مکالمه جاری (رشته).
                - 'session_id': شناسه جلسه جاری (رشته).
        
        تأثیرات جانبی:
        - تغییر وضعیت ذخیره‌شده: ایجاد/ذخیره پیام کاربر و پیام ربات، و به‌روزرسانی زمینه جلسه.
        - فراخوانی سرویس خارجی AI برای تولید پاسخ.
        """
        # ذخیره پیام کاربر
        user_message = self.save_user_message(message)
        
        # دریافت تاریخچه مکالمه
        conversation_history = self.get_conversation_history(10)
        
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
        self._update_patient_context(ai_response, context)
        
        return {
            'response': ai_response,
            'user_message_id': str(user_message.id),
            'bot_message_id': str(bot_message.id),
            'conversation_id': str(self.current_conversation.id),
            'session_id': str(self.current_session.id)
        }
    
    def get_quick_replies(self, context: Optional[Dict] = None) -> List[Dict]:
        """
        فهرست پاسخ‌های سریع مناسب برای رابط گفتگو با بیمار را تولید می‌کند.
        
        این متد یک مجموعه پایه از گزینه‌های سریع (مانند بررسی علائم، اطلاعات دارو، رزرو نوبت و تماس با پزشک) را بازمی‌گرداند و در صورت وجود زمینه (context) گزینه‌های مرتبط‌تری را اضافه می‌کند. فیلدهای قابل‌پذیرش در context که رفتار را تغییر می‌دهند:
        - has_symptoms (bool): اگر true باشد، گزینه‌های مرتبط با تشدید یا بهبود علائم اضافه می‌شوند.
        - has_medication (bool): اگر true باشد، گزینه‌های مرتبط با عوارض و زمان‌بندی دارو اضافه می‌شوند.
        
        بازگشتی:
        لیستی از دیکشنری‌ها که هر کدام با کلیدهای 'title' (نمایش/متن گزینه) و 'payload' (شناسه عملیاتی که هنگام انتخاب ارسال می‌شود) نمایانگر یک پاسخ سریع هستند.
        """
        base_replies = [
            {'title': 'علائم من چیست؟', 'payload': 'symptoms_check'},
            {'title': 'اطلاعات دارو', 'payload': 'medication_info'},
            {'title': 'رزرو نوبت', 'payload': 'book_appointment'},
            {'title': 'تماس با پزشک', 'payload': 'contact_doctor'}
        ]
        
        # پاسخ‌های زمینه‌محور
        if context:
            if context.get('has_symptoms'):
                base_replies.extend([
                    {'title': 'علائم تشدید شده', 'payload': 'symptoms_worsened'},
                    {'title': 'علائم بهبود یافته', 'payload': 'symptoms_improved'}
                ])
            
            if context.get('has_medication'):
                base_replies.extend([
                    {'title': 'عوارض دارو', 'payload': 'medication_side_effects'},
                    {'title': 'زمان مصرف', 'payload': 'medication_timing'}
                ])
        
        return base_replies
    
    def start_symptom_assessment(self) -> Dict[str, Any]:
        """
        شروع فرایند ارزیابی علائم بیمار و بازگرداندن بسته‌ی سؤال‌های ساختاریافته برای تکمیل توسط کاربر.
        
        این متد:
        - در صورتی که یک مکالمه جاری وجود داشته باشد، نوع آن را به 'symptom_check' تغییر داده و تغییر را ذخیره می‌کند (تأثیر جانبی روی شیء مکالمه).
        - یک پیام اولیه قابل نمایش به کاربر تولید می‌کند که شامل مجموعه‌ای از سوالات ارزیابی ساختاریافته است:
          - `main_symptom`: سؤال چندگزینه‌ای برای انتخاب علامت اصلی (درد، تب، سردرد، تهوع، خستگی، سایر).
          - `symptom_duration`: سؤال چندگزینه‌ای برای بازهٔ زمانی شروع علائم.
          - `symptom_severity`: سؤال مقیاسی از 1 تا 10 برای تعیین شدت علائم همراه با برچسب‌های انتهای مقیاس.
        - ساختار بازگشتی شامل کلیدهای `content` (متن نمایش)، `message_type` (نوع پیام، مثلاً 'text') و `response_data` است که در آن `assessment_questions` به عنوان لیستی از سوالات با شناسه‌ها، نوع‌ها و گزینه‌ها قرار دارد.
        
        نکات پیاده‌سازی و استفاده:
        - این متد تنها سوالات اولیه را آماده می‌کند؛ پردازش پاسخ‌های کاربر باید توسط متدهای بعدی (مثلاً `process_symptom_response`) انجام شود.
        - تغییر نوع مکالمه ذخیره می‌شود تا مراحل بعدی گفتگو (تحلیل، انتقال به نوبت‌دهی و ...) بر اساس زمینهٔ مناسب صورت گیرد.
        """
        # تغییر نوع مکالمه به بررسی علائم
        if self.current_conversation:
            self.current_conversation.conversation_type = 'symptom_check'
            self.current_conversation.save()
        
        return {
            'content': 'برای ارزیابی بهتر وضعیت شما، لطفاً به سؤالات زیر پاسخ دهید:',
            'message_type': 'text',
            'response_data': {
                'assessment_questions': [
                    {
                        'id': 'main_symptom',
                        'question': 'اصلی‌ترین علامت شما چیست؟',
                        'type': 'multiple_choice',
                        'options': [
                            'درد',
                            'تب',
                            'سردرد',
                            'تهوع',
                            'خستگی',
                            'سایر'
                        ]
                    },
                    {
                        'id': 'symptom_duration',
                        'question': 'این علائم چه مدت است که شروع شده؟',
                        'type': 'multiple_choice',
                        'options': [
                            'کمتر از یک روز',
                            '۱-۳ روز',
                            '۴-۷ روز',
                            'بیشتر از یک هفته'
                        ]
                    },
                    {
                        'id': 'symptom_severity',
                        'question': 'شدت علائم چگونه است؟',
                        'type': 'scale',
                        'scale': {'min': 1, 'max': 10, 'labels': {'1': 'خفیف', '10': 'شدید'}}
                    }
                ]
            }
        }
    
    def process_symptom_response(self, responses: Dict) -> Dict[str, Any]:
        """
        پردازش و تحلیل پاسخ‌های ارزیابی علائم بیمار و تولید نتیجهٔ عملیاتی
        
        این متد پاسخ‌های ساختاریافتهٔ ارسال‌شده توسط بیمار برای ارزیابی علائم را در نشست ذخیره می‌کند، سپس با فراخوانی منطق داخلی تحلیل ( `_analyze_symptom_responses`) آنها را ارزیابی می‌کند تا سطح فوریت، نمرهٔ شدت و توصیه‌های مناسب تعیین شوند. در پایان یک پیام متنی مناسب برای نمایش به کاربر به‌همراه داده‌های ساختاری‌شده شامل تحلیل کامل، توصیه‌ها، سطح فوریت و گزینه‌های پاسخ سریع (quick_replies) بازمی‌گرداند.
        
        Parameters:
            responses (Dict): دیکشنری حاوی پاسخ‌های ارزیابی علائم؛ انتظار می‌رود کلیدهای مرسومی مانند `main_symptom`، `duration` و `severity` (یا معادل‌های آنها) موجود باشند. مقادیر می‌توانند جبراً از پرسش‌های چندگزینه‌ای یا ورودی عددی برای شدت باشند.
        
        Returns:
            Dict[str, Any]: یک ساختار شامل:
                - content (str): پیام متنی تولیدشده بر اساس تحلیل که برای نمایش به کاربر استفاده می‌شود.
                - message_type (str): نوع پیام (معمولاً `'text'`).
                - response_data (Dict): داده‌های مفصل شامل:
                    - analysis: خروجی کامل تابع تحلیل شامل پیام، سطح فوریت، توصیه‌ها، نمرهٔ شدت و سایر فیلدهای مرتبط.
                    - recommendations (List[str]): فهرست توصیه‌های عملیاتی استخراج‌شده از تحلیل.
                    - urgency_level (str): برچسب سطح فوریت (`'high'`, `'medium'`, `'normal'`).
                    - quick_replies (List[Dict]): گزینه‌های دنبال‌کننده برای کاربر که مطابق با سطح فوریت و تحلیل تولید می‌شوند.
        
        Side effects:
            - ذخیرهٔ پاسخ‌های ارسالی در متن نشست کاربری تحت کلید `symptom_assessment` و ثبت زمان تکمیل (`assessment_completed_at`).
            - استفاده از منطق داخلی تحلیل برای تعیین سطح فوریت و توصیه‌ها.
        """
        # ذخیره پاسخ‌ها در زمینه
        self._update_session_context({
            'symptom_assessment': responses,
            'assessment_completed_at': str(timezone.now())
        })
        
        # تحلیل پاسخ‌ها
        analysis = self._analyze_symptom_responses(responses)
        
        return {
            'content': analysis['message'],
            'message_type': 'text',
            'response_data': {
                'analysis': analysis,
                'recommendations': analysis.get('recommendations', []),
                'urgency_level': analysis.get('urgency_level', 'normal'),
                'quick_replies': self._get_symptom_followup_replies(analysis)
            }
        }
    
    def request_appointment(self, specialty: str = None, preferred_time: str = None) -> Dict[str, Any]:
        """
        درخواست نوبت برای کاربر و ثبت جزئیات آن در کانتکست جلسۀ کاربر.
        
        این متد نوع مکالمۀ جاری را به 'appointment' تغییر می‌دهد (و اگر مکالمه‌ای وجود داشته باشد آن را ذخیره می‌کند)، سپس یک رکورد درخواست نوبت شامل تخصص مورد نظر، بازۀ زمانی ترجیحی و زمان ثبت درخواست را در کانتکست جلسه ذخیره می‌کند. تابع ساختاری از پیش‌تعریف‌شده شامل پیام تأیید دریافت، یک فرم پیشنهادی نوبت (گزینه‌های تخصص و بازه‌های زمانی) و گزینه‌های پاسخ سریع (تأیید، تغییر زمان، انصراف) را برمی‌گرداند که برای رابط کاربری جهت ادامهٔ جریان رزرو نوبت استفاده می‌شود.
        
        Parameters:
            specialty (str, optional): رشته‌ای که تخصص مورد نظر بیمار را مشخص می‌کند (مثلاً 'ارتوپدی'). اگر None باشد، فرم بازه‌ای از گزینه‌ها را به کاربر ارائه می‌دهد تا انتخاب کند.
            preferred_time (str, optional): بازۀ زمانی یا زمان ترجیحی کاربر برای نوبت (مثلاً 'صبح (۸-۱۲)'). اگر ارائه نشده باشد، کاربر می‌تواند از میان گزینه‌های فرم انتخاب کند.
        
        Returns:
            dict: آبجکتی حاوی:
                - content (str): متن پیام برای کاربر.
                - message_type (str): نوع پیام ('text').
                - response_data (dict): شامل:
                    - appointment_form (dict): داده‌های فرم پیشنهادی شامل 'specialty_options' و 'time_slots' برای انتخاب کاربر.
                    - quick_replies (list): لیستی از گزینه‌های پاسخ سریع با عناوین و payloadهایی که جریان بعدی را مشخص می‌کنند.
        
        Side effects:
            - ممکن است current_conversation.conversation_type را به 'appointment' تغییر داده و ذخیره کند.
            - کانتکست جلسه را با کلید 'appointment_request' شامل specialty، preferred_time و timestamp به‌روزرسانی می‌کند.
        """
        # تغییر نوع مکالمه
        if self.current_conversation:
            self.current_conversation.conversation_type = 'appointment'
            self.current_conversation.save()
        
        # ذخیره درخواست در زمینه
        self._update_session_context({
            'appointment_request': {
                'specialty': specialty,
                'preferred_time': preferred_time,
                'requested_at': str(timezone.now())
            }
        })
        
        return {
            'content': 'درخواست نوبت شما دریافت شد. لطفاً اطلاعات تکمیلی را ارائه دهید:',
            'message_type': 'text',
            'response_data': {
                'appointment_form': {
                    'specialty_options': [
                        'پزشک عمومی',
                        'متخصص داخلی',
                        'قلب و عروق',
                        'ارتوپدی',
                        'روانپزشک',
                        'زنان و زایمان'
                    ],
                    'time_slots': [
                        'صبح (۸-۱۲)',
                        'عصر (۱۴-۱۸)',
                        'شب (۱۸-۲۱)'
                    ]
                },
                'quick_replies': [
                    {'title': 'تأیید درخواست', 'payload': 'confirm_appointment'},
                    {'title': 'تغییر زمان', 'payload': 'change_time'},
                    {'title': 'انصراف', 'payload': 'cancel_appointment'}
                ]
            }
        }
    
    def _analyze_symptom_responses(self, responses: Dict) -> Dict[str, Any]:
        """
        تحلیل پاسخ‌های ارزیابی علائم و تعیین سطح فوریت و توصیه‌های مرتبط.
        
        دقیق‌تر: این تابع ورودی `responses` را که شامل پاسخ‌های کاربر از ارزیابی علائم است بررسی می‌کند، امتیاز شدت را خوانده، سطح فوریت را بر اساس قواعد ساده‌ای (شدت و وجود علائم پرخطر) تعیین می‌کند و پیام متنی همراه با فهرست توصیه‌ها تولید می‌نماید. خروجی خلاصه‌ای ساختاری شامل پیام پیشنهادی، سطح فوریت، توصیه‌ها و مقادیر استخراج‌شده بازمی‌گرداند.
        
        پارامترها:
            responses (Dict): نقشه‌ای از پاسخ‌های ارزیابی علامت. کلیدهای متداول:
                - 'main_symptom' (str): علامت اصلی گزارش‌شده توسط بیمار (مثلاً 'سرفه', 'تب بالا').
                - 'symptom_duration' (str): مدت زمان تقریبی بروز علامت (مثلاً '2 روز').
                - 'symptom_severity' (int|str): شدت علامت به صورت عددی یا رشته‌ای قابل تبدیل به عدد (مقیاس 1-10).
        
        مقدار بازگشتی (Dict):
            بازگشتی یک دیکشنری با کلیدهای زیر است:
                - 'message' (str): پیام متنی خلاصه شامل توصیه فوریتی مناسب.
                - 'urgency_level' (str): سطح فوریت، یکی از 'high'، 'medium' یا 'normal'.
                - 'recommendations' (List[str]): لیستی از اقدامات پیشنهادی متناسب با سطح فوریت.
                - 'severity_score' (int): امتیاز شدت نهایی استخراج‌شده.
                - 'main_symptom' (str): علامت اصلی استخراج‌شده.
                - 'duration' (str): مدت زمان علامت همان‌گونه که در ورودی آمده.
        
        توجه:
            - قواعد تعیین فوریت: اگر شدت >= 8 یا علامت اصلی یکی از علائم پرخطر (مثلاً 'تب بالا' یا 'درد قفسه سینه') باشد، فوریت 'high' است؛ اگر شدت >= 6، 'medium'؛ در غیر این صورت 'normal'.
            - تابع مقادیر پیش‌فرض منطقی را در صورت فقدان کلیدها اعمال می‌کند (مثلاً شدت پیش‌فرض 5).
        """
        main_symptom = responses.get('main_symptom', '')
        duration = responses.get('symptom_duration', '')
        severity = int(responses.get('symptom_severity', 5))
        
        # تعیین سطح فوریت
        urgency_level = 'normal'
        if severity >= 8 or main_symptom in ['تب بالا', 'درد قفسه سینه']:
            urgency_level = 'high'
        elif severity >= 6:
            urgency_level = 'medium'
        
        # تولید پیام بر اساس تحلیل
        if urgency_level == 'high':
            message = 'بر اساس علائم ذکر شده، توصیه می‌شود در اسرع وقت با پزشک مراجعه کنید.'
            recommendations = [
                'مراجعه فوری به پزشک',
                'در صورت تشدید علائم، به اورژانس مراجعه کنید',
                'داروهای مسکن را بدون نظر پزشک مصرف نکنید'
            ]
        elif urgency_level == 'medium':
            message = 'علائم شما نیاز به بررسی پزشک دارد. توصیه می‌شود طی ۲-۳ روز آینده مراجعه کنید.'
            recommendations = [
                'رزرو نوبت پزشک',
                'استراحت کافی داشته باشید',
                'مایعات زیادی بنوشید'
            ]
        else:
            message = 'علائم شما خفیف به نظر می‌رسد. می‌توانید ابتدا مراقبت‌های خانگی را امتحان کنید.'
            recommendations = [
                'استراحت کافی',
                'مصرف مایعات فراوان',
                'در صورت تداوم یا تشدید علائم، با پزشک مشورت کنید'
            ]
        
        return {
            'message': message,
            'urgency_level': urgency_level,
            'recommendations': recommendations,
            'severity_score': severity,
            'main_symptom': main_symptom,
            'duration': duration
        }
    
    def _get_symptom_followup_replies(self, analysis: Dict) -> List[Dict]:
        """
        یک لیست از گزینه‌های پیگیری علائم را برمی‌گرداند.
        
        جزئیات:
        این تابع بر اساس نتیجه تحلیل علائم (پارامتر `analysis`) مجموعه‌ای از پاسخ‌های سریع (quick replies) را تولید می‌کند که برای هدایت کاربر به اقدام بعدی در چت بیمار استفاده می‌شوند. خروجی یک لیست از دیکشنری‌ها با کلیدهای `title` (متن نمایشی) و `payload` (شناسه عملیاتی) است.
        
        رفتار خاص:
        - همیشه دو گزینه پایه برمی‌گردد: "رزرو نوبت" (`book_appointment`) و "اطلاعات بیشتر" (`more_info`).
        - اگر در `analysis` کلید `urgency_level` وجود داشته باشد و مقدار آن `'high'` باشد، گزینهٔ "تماس اورژانس" (`emergency_contact`) در ابتدای لیست درج می‌شود تا در اولویت نمایش قرار گیرد.
        
        پارامترها:
        - analysis (Dict): دیکشنری تحلیل علائم که حداقل می‌تواند شامل کلید `urgency_level` با مقادیری مانند `'high'`, `'medium'`, `'normal'` باشد.
        
        خروجی:
        - List[Dict]: لیستی از گزینه‌های پیگیری که هر مورد شامل `title` و `payload` است. هیچ تأثیری بر حالت داخلی شیء ندارد.
        """
        base_replies = [
            {'title': 'رزرو نوبت', 'payload': 'book_appointment'},
            {'title': 'اطلاعات بیشتر', 'payload': 'more_info'}
        ]
        
        if analysis.get('urgency_level') == 'high':
            base_replies.insert(0, {'title': 'تماس اورژانس', 'payload': 'emergency_contact'})
        
        return base_replies
    
    def _update_patient_context(self, ai_response: Dict, context: Optional[Dict]):
        """
        به‌روزرسانی زمینه (context) جلسه بیمار با متادیتای پاسخ هوش‌مصنوعی و داده‌های اضافه.
        
        این متد یک دیکشنری از به‌روزرسانی‌ها می‌سازد که شامل زمان آخرین تعامل (timestamp)، دسته‌بندی تعیین‌شده توسط مدل (از کلید `category` در ai_response) و نمره اعتماد مدل (از کلید `ai_confidence` در ai_response) است. در صورت وجود، هر داده اضافی موجود در پارامتر `context` به این به‌روزرسانی‌ها ادغام می‌شود. در نهایت با فراخوانی `_update_session_context` این مجموعه تغییرات در زمینه جلسه کاربر ذخیره می‌شود.
        
        نکات مهم:
        - این تابع مقدار بازگشتی ندارد و تنها یک اثر جانبی (update به session context) انجام می‌دهد.
        - در صورت نبودن کلیدهای `category` یا `ai_confidence` در `ai_response`، مقدار مربوطه در دیکشنری به‌صورت None قرار می‌گیرد.
        - تابع ورودی‌ها را اعتبارسنجی یا تغییر شکل پیچیده‌ای نمی‌کند؛ صرفاً ادغام و ثبت را انجام می‌دهد.
        """
        updates = {
            'last_interaction': str(timezone.now()),
            'last_category': ai_response.get('category'),
            'confidence_score': ai_response.get('ai_confidence')
        }
        
        if context:
            updates.update(context)
        
        self._update_session_context(updates)