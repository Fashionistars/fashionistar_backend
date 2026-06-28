"""
کلاس پایه برای سرویس‌های چت‌بات
Base Chatbot Service
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any
from django.utils import timezone
from django.contrib.auth import get_user_model
from ..models import ChatbotSession, Conversation, Message, ChatbotResponse

User = get_user_model()


class BaseChatbotService(ABC):
    """
    کلاس پایه برای سرویس‌های چت‌بات
    """
    
    def __init__(self, user: User, session_type: str):
        """
        ابتدا ساز برای سرویس چت‌بات را انجام می‌دهد و وضعیت شروعی را تنظیم می‌کند.
        
        پارامترها:
            user: مالک جلسات و گفتگوها — شیئ User مربوط به کاربری که سرویس برای او عمل می‌کند.
            session_type: نوع جلسه؛ مقدارهای مرسوم شامل 'patient' یا 'doctor' هستند که برای تفکیک رفتار و نگهداری جلسه استفاده می‌شود.
        
        رفتار:
            مقداردهی فیلدهای داخلی: user و session_type را ذخیره می‌کند و current_session و current_conversation را به None مقداردهی می‌کند تا در زمان نیاز با فراخوانی متدهای مربوطه ایجاد یا بارگذاری شوند.
        """
        self.user = user
        self.session_type = session_type
        self.current_session: Optional[ChatbotSession] = None
        self.current_conversation: Optional[Conversation] = None
    
    def get_or_create_session(self) -> ChatbotSession:
        """
        یک جلسه چت فعال برای کاربر بازمی‌گرداند یا در صورت عدم وجود، یک جلسه جدید ایجاد می‌کند.
        
        این متد ابتدا به‌دنبال یک ChatbotSession فعال برای کاربر و نوع جلسه جاری می‌گردد. اگر جلسهٔ فعال و قابل‌استفاده‌ای پیدا شود، آن را در self.current_session قرار می‌دهد و بازمی‌گرداند؛ در غیر این صورت یک ChatbotSession جدید با وضعیت 'active' می‌سازد، فیلد expires_at آن را ۲۴ ساعت بعد تنظیم می‌کند، self.current_session را به آن اشاره می‌دهد و آن را بازمی‌گرداند. این متد وضعیت داخلی سرویس (self.current_session) را تغییر می‌دهد و از مدل‌های Django ORM برای خواندن/نوشتن استفاده می‌کند.
        
        Returns:
            ChatbotSession: جلسهٔ فعال موجود یا جلسهٔ تازه ایجاد شده برای کاربر.
        """
        # جستجو برای جلسه فعال موجود
        active_session = ChatbotSession.objects.filter(
            user=self.user,
            session_type=self.session_type,
            status='active'
        ).first()
        
        if active_session and active_session.is_active:
            self.current_session = active_session
        else:
            # ایجاد جلسه جدید
            self.current_session = ChatbotSession.objects.create(
                user=self.user,
                session_type=self.session_type,
                status='active',
                expires_at=timezone.now() + timezone.timedelta(hours=24)
            )
        
        return self.current_session
    
    def get_or_create_conversation(self, conversation_type: str = 'general') -> Conversation:
        """
        یک مکالمه فعال را برای جلسه جاری بازیابی یا در صورت عدم وجود ایجاد می‌کند.
        
        این متد اطمینان حاصل می‌کند که یک جلسه (ChatbotSession) فعال در self.current_session وجود دارد (در صورت نیاز با فراخوانی get_or_create_session). سپس تلاش می‌کند تا اولین Conversation فعال (is_active=True) مرتبط با آن جلسه را بازیابی کند. اگر چنین مکالمه‌ای پیدا شود، آن را در self.current_conversation قرار می‌دهد و بازمی‌گرداند؛ در غیر این صورت یک Conversation جدید می‌سازد، عنوان آن را با _generate_conversation_title بر اساس conversation_type تولید می‌کند، self.current_conversation را به آن مقداردهی می‌کند و آن را بازمی‌گرداند.
        
        Parameters:
            conversation_type (str): نوع مکالمه که برای فیلد `conversation_type` در صورت ایجاد مکالمه جدید استفاده می‌شود؛ مقدار پیش‌فرض `'general'` است و همچنین بر تولید عنوان پیش‌فرض مکالمه تأثیر می‌گذارد.
        
        Returns:
            Conversation: نمونه Conversation فعال که همواره در self.current_conversation نگهداری می‌شود.
        
        Side effects:
            - ممکن است یک ChatbotSession جدید ایجاد شود (از طریق get_or_create_session) اگر جلسه فعالی موجود نباشد.
            - ممکن است یک Conversation جدید در پایگاه‌داده ایجاد شود و self.current_conversation و در صورت نیاز self.current_session را به‌روزرسانی کند.
        """
        if not self.current_session:
            self.get_or_create_session()
        
        # جستجو برای مکالمه فعال موجود
        active_conversation = self.current_session.conversations.filter(
            is_active=True
        ).first()
        
        if active_conversation:
            self.current_conversation = active_conversation
        else:
            # ایجاد مکالمه جدید
            self.current_conversation = Conversation.objects.create(
                session=self.current_session,
                conversation_type=conversation_type,
                title=self._generate_conversation_title(conversation_type)
            )
        
        return self.current_conversation
    
    def save_user_message(self, content: str, message_type: str = 'text') -> Message:
        """
        یک پیام ارسالی توسط کاربر را در پایگاه‌داده ذخیره می‌کند.
        
        اگر جلسه/مکالمه جاری وجود نداشته باشد، ابتدا یک مکالمه جدید ایجاد می‌کند و سپس پیام را به آن پیوست کرده و ذخیره می‌کند. این تابع یک شیٔ Message جدید با sender_type برابر 'user' ایجاد و بازمی‌گرداند.
        
        Parameters:
            content (str): متن یا محتوای پیام کاربر.
            message_type (str, optional): نوع پیام (پیش‌فرض: 'text').
        
        Returns:
            Message: نمونه‌ی ذخیره‌شده‌ی Message مرتبط با current_conversation.
        """
        if not self.current_conversation:
            self.get_or_create_conversation()
        
        return Message.objects.create(
            conversation=self.current_conversation,
            sender_type='user',
            message_type=message_type,
            content=content
        )
    
    def save_bot_message(
        self, 
        content: str, 
        message_type: str = 'text',
        response_data: Optional[Dict] = None,
        ai_confidence: Optional[float] = None,
        processing_time: Optional[float] = None
    ) -> Message:
        """
        پیام تولیدشده توسط بات را در گفت‌وگو جاری ذخیره می‌کند.
        
        در صورت نبود گفت‌وگوی جاری، ابتدا یک گفت‌وگو ایجاد یا واکشی می‌شود سپس یک رکورد Message با فرستنده 'bot' ساخته و برمی‌گردانده می‌شود. از response_data برای نگهداری ساختارهای اضافی پاسخ (مثلاً متادیتا، کارت‌ها یا دکمه‌ها)، ai_confidence برای ثبت مقدار اطمینان خروجی مدل و processing_time برای ثبت زمان صرف‌شده در تولید پاسخ استفاده می‌شود.
        
        Parameters:
            content (str): متن یا محتوای اصلی پیغام بات.
            message_type (str): نوع پیام (مثلاً 'text', 'image', 'card') — برای دسته‌بندی نمایش یا پردازش بعدی استفاده می‌شود.
            response_data (Optional[Dict]): داده‌های ساختاری اضافی مرتبط با پاسخ که به صورت دیکشنری ذخیره می‌شود (پیش‌فرض {}).
            ai_confidence (Optional[float]): درجه اطمینان مدل هوش مصنوعی درباره پاسخ (در محدوده 0.0–1.0)، در صورت در دسترس بودن.
            processing_time (Optional[float]): زمان صرف‌شده برای تولید پاسخ به ثانیه، در صورت اندازه‌گیری.
        
        Returns:
            Message: نمونه پیام ذخیره‌شده در پایگاه‌داده که نمایانگر پاسخ بات است.
        """
        if not self.current_conversation:
            self.get_or_create_conversation()
        
        return Message.objects.create(
            conversation=self.current_conversation,
            sender_type='bot',
            message_type=message_type,
            content=content,
            response_data=response_data or {},
            ai_confidence=ai_confidence,
            processing_time=processing_time
        )
    
    def get_conversation_history(self, limit: int = 50) -> List[Message]:
        """
        آخرین پیام‌های مکالمه جاری را برمی‌گرداند.
        
        در صورت وجود یک مکالمه فعال، پیام‌ها را به‌ترتیب زمانی نزولی (جدیدترین اول) بازمی‌گرداند و حداکثر به تعداد مشخص‌شده محدود می‌کند. اگر مکالمه جاری تنظیم نشده باشد، لیست خالی برمی‌گرداند.
        
        Parameters:
            limit (int): حداکثر تعداد پیام‌هایی که باید بازگردانده شوند (پیش‌فرض ۵۰).
        
        Returns:
            List[Message]: لیستی از نمونه‌های Message مرتب‌شده بر اساس زمان ایجاد (جدیدترین تا قدیمی‌ترین).
        """
        if not self.current_conversation:
            return []
        
        return list(
            self.current_conversation.messages.order_by('-created_at')[:limit]
        )
    
    def end_conversation(self, summary: str = "") -> None:
        """
        مکالمه جاری را به‌صورت ایمن خاتمه می‌دهد.
        
        اگر یک مکالمه فعال در حال حاضر وجود داشته باشد، این متد فِلِگ is_active آن را به False تنظیم می‌کند، در صورت ارسال پارامتر summary آن را به فیلد summary مکالمه می‌افزاید و سپس تغییرات را با فراخوانی save() ذخیره می‌کند. هیچ مقداری بازنمی‌گرداند.
        
        Parameters:
            summary (str): خلاصه‌ای اختیاری از نتیجه یا نکات مهم مکالمه که در صورت ارائه در رکورد مکالمه ذخیره می‌شود.
        """
        if self.current_conversation:
            self.current_conversation.is_active = False
            if summary:
                self.current_conversation.summary = summary
            self.current_conversation.save()
    
    def end_session(self) -> None:
        """
        پایان دادن جلسهٔ فعال کاربر.
        
        اگر جلسهٔ جاری وجود داشته باشد، فراخوانی‌ای به متد `end_session()` روی شیٔ `ChatbotSession` انجام می‌دهد تا وضعیت جلسه به حالت پایان‌یافته تغییر کند (مثلاً تعیین `is_active=False` و ذخیرهٔ تغییرات طبق پیاده‌سازی مدل). اگر جلسهٔ جاری وجود نداشته باشد، بدون انجام هیچ‌عملی بازمی‌گردد. این تابع مقدار بازگشتی ندارد و خودِ ارجاعات `current_session` یا `current_conversation` را پاک نمی‌کند.
        """
        if self.current_session:
            self.current_session.end_session()
    
    @abstractmethod
    def process_message(self, message: str, context: Optional[Dict] = None) -> Dict[str, Any]:
        """
        پردازش یک پیام کاربر و تولید پاسخ ساختاریافته برای ربات.
        
        این متد قرارداد (interface) برای پیاده‌سازی‌های فرزند را تعیین می‌کند: پیغام کاربر را دریافت کرده، در صورت نیاز از سرویس‌های AI/مدل‌های زبان استفاده می‌کند، وضعیت جلسه/مکالمه را به‌روزرسانی و پیام‌های مرتبط را ذخیره می‌کند و یک ساختار پاسخ بازمی‌گرداند. پیاده‌سازی‌ها باید پردازش متن، استخراج نیت/موجودیت‌ها، تولید پاسخ طبیعی و هر تسک پس‌پردازشی (مانند ثبت لاگ، به‌روزرسانی کانتکست جلسه یا برنامه‌ریزی تسک‌های آتی) را در این متد انجام دهند.
        
        پارامترها:
            message (str): متن ورودی کاربر؛ می‌تواند شامل پرسش، فرمان یا انتخاب سریع باشد.
            context (Optional[Dict]): داده‌های زمینه‌ای اضافی که برای تفسیر پیام یا کنترل جریان مکالمه استفاده می‌شود (مثلاً تاریخچه مختصر، پارامترهای جلسه، یا متادیتای درخواست).
        
        مقدار بازگشتی:
            Dict[str, Any]: یک دیکشنری ساختاریافته که حداقل شامل کلیدهای زیر باشد یا کلیدهای مرتبط را برگرداند:
                - "reply" (str): متن پاسخ تولیدشده برای ارسال به کاربر.
                - "quick_replies" (Optional[List[Dict]]): لیستی از گزینه‌های پاسخ سریع (هر مورد حداقل باید عنوان نمایش و شناسه داشته باشد).
                - "ai_confidence" (Optional[float]): امتیاز اعتماد مدل (میزان اطمینان) بین 0.0 تا 1.0 در صورت قابل‌محاسبه.
                - "response_data" (Optional[Dict]): داده‌های ساختاریافته اضافی تولیدشده توسط مدل (مثل جداول، منابع یا نتایج استخراج).
                - "end_conversation" (Optional[bool]): اگر True باشد نشان‌دهنده پایان مکالمه پس از این پاسخ است.
                - "processing_time" (Optional[float]): زمان صرف‌شده برای تولید پاسخ بر حسب ثانیه.
                - "metadata" (Optional[Dict]): هر اطلاعات عملیاتی یا تشخیصی دیگر (مثلاً نیت تشخیص‌داده‌شده، موجودیت‌ها یا شناسه درخواست).
        
        توجه: این متد باید در پیاده‌سازی فرزند پیام/پاسخ را در مدل‌های داده (Message/Conversation/Session) ذخیره کند یا حداقل قرارداد ذخیره‌سازی را رعایت نماید، ولی نحوهٔ دقیق ذخیره‌سازی به پیاده‌سازی بستگی دارد.
        """
        pass
    
    @abstractmethod
    def get_quick_replies(self, context: Optional[Dict] = None) -> List[Dict]:
        """
        بازگرداندن لیستی از گزینه‌های پاسخ سریع (quick replies) مناسب برای رابط کاربری چت.
        
        این متد باید توسط زیرکلاس‌ها پیاده‌سازی شود و بر اساس متن یا وضعیت جاری (پارامتر `context`) مجموعه‌ای از آیتم‌های پاسخ سریع را تولید کند که کاربر می‌تواند با یک لمس انتخاب کند. هر آیتم باید به‌صورت دیکشنری حاوی کلیدهای زیر باشد تا برای مصرف در کلاینت و پردازش سرور قابل استفاده باشد:
        - `title` (str): متن قابل‌نمایش روی دکمه پاسخ سریع.
        - `payload` (str | dict): داده‌ای که هنگام انتخاب پاسخ به سرور فرستاده می‌شود (مثلاً شناسه اقدام یا متن پیام).
        - `type` (str, optional): نوع پاسخ (مثلاً `"text"`, `"intent"`, `"action"`) تا کلاینت یا پردازش‌کننده بداند چگونه آن را تفسیر کند.
        - `meta` (dict, optional): اطلاعات کمکی یا ساختاری اضافی (مثلاً پارامترهای لازم برای اجرای یک task).
        - `requires_followup` (bool, optional): آیا انتخاب این پاسخ نیاز به گام بعدی از کاربر دارد یا خیر.
        
        پارامترها:
            context (Optional[Dict]): زمینه‌ای که می‌تواند شامل وضعیت جلسه، آخرین پیام‌ها، پروفایل کاربر، یا نتایج مدل‌های AI باشد تا تولید پاسخ‌ها را شخصی‌سازی یا محدود کند.
        
        مقدار بازگشتی:
            List[Dict]: لیستی از دیکشنری‌های پاسخ سریع طبق قالب بالا. اگر پاسخ سریع مناسب وجود نداشته باشد، باید لیست خالی بازگردانده شود.
        
        توجه:
        - پیاده‌سازی باید فقط مشخصات آیتم‌های پاسخ را تهیه کند و تصمیم‌گیری اجرا/ارسالِ payload را به لایه‌های بالاتر واگذار نماید.
        - متد نباید تغییر پایداری در داده‌های جلسه انجام دهد؛ در صورت نیاز به به‌روزرسانی زمینه یا لاگ، آن را صریحاً در متدهای مربوطه انجام دهید یا قرارداد مشخصی تعریف کنید.
        """
        pass
    
    def _generate_conversation_title(self, conversation_type: str) -> str:
        """
        یک عنوان خوانا و محلی‌سازی‌شده برای مکالمه تولید می‌کند.
        
        این تابع بر اساس نوع مکالمه یک عنوان پایه از نگاشت داخلی انتخاب می‌کند؛ اگر نوع شناخته‌شده نباشد، از مقدار پیش‌فرض «مکالمه» استفاده می‌گردد. سپس زمان جاریِ حساس به ناحیه زمانی سیستم (فرمت HH:MM) را به انتهای عنوان می‌افزاید تا عنوان نهایی یکتا و قابل‌خواندن شود.
        
        Parameters:
            conversation_type (str): کلید نوع مکالمه که یکی از مقادیر شناخته‌شده مانند
                'patient_inquiry', 'doctor_consultation', 'symptom_check',
                'medication_info', 'appointment' یا 'general' است. برای مقادیر ناشناخته
                عنوان پایه‌ی «مکالمه» استفاده خواهد شد.
        
        Returns:
            str: عنوان نهایی مکالمه به قالب "{عنوان پایه} - HH:MM" که زمان به‌صورت
            timezone-aware گرفته شده است.
        """
        type_titles = {
            'patient_inquiry': 'استعلام بیمار',
            'doctor_consultation': 'مشاوره پزشک',
            'symptom_check': 'بررسی علائم',
            'medication_info': 'اطلاعات دارو',
            'appointment': 'نوبت‌گیری',
            'general': 'گفتگوی عمومی'
        }
        
        base_title = type_titles.get(conversation_type, 'مکالمه')
        timestamp = timezone.now().strftime('%H:%M')
        return f"{base_title} - {timestamp}"
    
    def _update_session_context(self, context_updates: Dict) -> None:
        """
        یک‌خطی:
        زمینه (context) جلسه‌ی جاری را با مقادیر داده‌شده بروزرسانی و آخرین زمان فعالیت را ذخیره می‌کند.
        
        توضیحات:
        اگر جلسه‌ی جاری موجود باشد، مقادیر موجود در `context_updates` را در فیلد `context_data` جلسه ادغام می‌کند و سپس تغییرات را ذخیره می‌نماید. این تابع مقدار بازگشتی ندارد و باعث به‌روزرسانی پایگاه‌داده (فیلدهای `context_data` و `last_activity`) می‌شود.
        
        پارامترها:
            context_updates (Dict): دیکشنری شامل کلید/مقدارهای جدید یا به‌روزرسانی‌شده که باید به زمینه‌ی جلسه افزوده یا جایگزین شوند.
        """
        if self.current_session:
            self.current_session.context_data.update(context_updates)
            self.current_session.save(update_fields=['context_data', 'last_activity'])