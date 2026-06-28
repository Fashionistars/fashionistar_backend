"""
سرویس تطبیق پاسخ‌ها
Response Matcher Service
"""

import re
from typing import List, Optional, Dict, Any
from django.db.models import Q
from ..models import ChatbotResponse


class ResponseMatcherService:
    """
    سرویس تطبیق پاسخ‌های از پیش تعریف شده
    """
    
    def __init__(self, target_user: str = 'both'):
        """
        مقداردهی اولیه سرویس تطبیق پاسخ‌ها با تعیین دامنه کاربری.
        
        این سازنده محدوده هدفِ پاسخ‌ها را در نمونه ذخیره می‌کند و رویهٔ جستجو/فیلتر پاسخ‌ها را تحت تأثیر قرار می‌دهد: مقدار self.target_user برای فیلتر کردن رکوردهای ChatbotResponse به‌کار می‌رود (مثلاً فقط پاسخ‌هایی که برای 'patient'، 'doctor' یا 'both' تعیین شده‌اند). مقدار پیش‌فرض 'both' است؛ مقدار رشته‌ای که پاس داده شود به‌عنوان معیار مقایسه استفاده می‌شود.
        """
        self.target_user = target_user
    
    def find_matching_response(
        self, 
        message: str, 
        category: Optional[str] = None
    ) -> Optional[ChatbotResponse]:
        """
        پاسخ اولین ردیف ChatbotResponse که با پیام ورودی منطبق است را برمی‌گرداند.
        
        این متد مجموعه‌ای از پاسخ‌های فعال (is_active=True) را می‌گیرد و آن‌ها را بر اساس محدوده هدف (target_user برابر با مقدار سرویس یا 'both') فیلتر می‌کند. در صورت ارسال پارامتر category، مجموعه نتایج به آن دسته محدود می‌شود. نتایج بر اساس اولویت (نزولی) و سپس زمان ایجاد (جدیدترین اول) مرتب می‌شوند. پیام ورودی پیش از بررسی نرمال‌سازی شده (تبدیل به حروف کوچک و حذف فاصله‌های اضافی) و سپس برای هر پاسخ، کلیدواژه‌های تریگر با پیام با استفاده از _matches_keywords (که شامل تطبیق ساده متن و بررسی الگوهای منطبق با regex است) مقایسه می‌شوند. اولین پاسخ مطابق بازگردانده می‌شود؛ در غیر این صورت None بازگردانده می‌شود.
        
        Parameters:
            message (str): متن پیام کاربر؛ این مقدار پیش از تطبیق به‌صورت lowercase و با trim شده استفاده می‌شود.
            category (Optional[str]): در صورت تعیین، جستجو را به پاسخ‌های آن دسته محدود می‌کند.
        
        Returns:
            Optional[ChatbotResponse]: اولین شیء ChatbotResponse که با پیام مطابقت دارد یا None اگر مطابقتی یافت نشود.
        """
        # فیلتر کردن پاسخ‌های فعال
        queryset = ChatbotResponse.objects.filter(
            is_active=True
        ).filter(
            Q(target_user=self.target_user) | Q(target_user='both')
        )
        
        # فیلتر بر اساس دسته‌بندی
        if category:
            queryset = queryset.filter(category=category)
        
        # مرتب‌سازی بر اساس اولویت
        responses = queryset.order_by('-priority', '-created_at')
        
        message_lower = message.lower().strip()
        
        # جستجو برای تطبیق کلمات کلیدی
        for response in responses:
            if self._matches_keywords(message_lower, response.trigger_keywords):
                return response
        
        return None
    
    def get_responses_by_category(self, category: str) -> List[ChatbotResponse]:
        """
        فهرست پاسخ‌های فعال از مدل ChatbotResponse را برای یک دسته‌بندی مشخص برمی‌گرداند.
        
        این متد تمامی پاسخ‌هایی را که:
        - در فیلد `category` با مقدار ورودی مطابقت دارند،
        - `is_active` آنها True است،
        - و برای `target_user` با مقدار سرویس یا برای `both` تعریف شده‌اند،
        فیلتر کرده و بر اساس اولویت (از بالا به پایین) و زمان ایجاد (جدیدتر اول) مرتب می‌کند و به‌صورت لیست بازمی‌گرداند.
        
        Parameters:
            category (str): نام دسته‌بندی مورد جستجو (مثلاً 'greeting', 'error', 'unknown').
        
        Returns:
            List[ChatbotResponse]: لیستی از نمونه‌های ChatbotResponse منطبق، یا لیست خالی در صورت عدم وجود پاسخ.
        """
        return list(
            ChatbotResponse.objects.filter(
                category=category,
                is_active=True
            ).filter(
                Q(target_user=self.target_user) | Q(target_user='both')
            ).order_by('-priority', '-created_at')
        )
    
    def get_greeting_response(self) -> Optional[ChatbotResponse]:
        """
        بازگرداندن اولین پاسخ از دسته «خوشامدگویی» مناسب برای target_user سرویس.
        
        این متد لیستی از پاسخ‌های فعال با دسته 'greeting' را از get_responses_by_category فراخوانی می‌کند (که نتایج را بر اساس اولویت و زمان ایجاد مرتب می‌کند و فیلتر target_user را اعمال می‌کند) و اولین مورد را برمی‌گرداند. در صورتی که هیچ پاسخ مطابقی وجود نداشته باشد، مقدار None بازگردانده می‌شود.
        
        Returns:
            Optional[ChatbotResponse]: شیء ChatbotResponse با بالاترین اولویت در دسته‌ی خوشامدگویی یا None اگر پاسخی موجود نباشد.
        """
        responses = self.get_responses_by_category('greeting')
        return responses[0] if responses else None
    
    def get_error_response(self) -> Optional[ChatbotResponse]:
        """
        بررسی و بازگرداندن اولین پاسخ پیش‌تعریف‌شده از دسته "error" برای target_user فعلی.
        
        این متد پاسخ‌های فعال با دسته 'error' را برمی‌گرداند که مطابق محدوده کاربر (self.target_user یا 'both') فیلتر شده و بر اساس اولویت (بالاتر اول) و زمان ایجاد (جدیدتر اول) مرتب شده‌اند. در صورتی که حداقل یک پاسخ موجود باشد، اولین (بالاترین اولویت) مورد را بازمی‌گرداند، در غیر این صورت None برمی‌گرداند.
        
        Returns:
            Optional[ChatbotResponse]: اولین پاسخ خطا یا None اگر پاسخی موجود نباشد.
        """
        responses = self.get_responses_by_category('error')
        return responses[0] if responses else None
    
    def get_unknown_response(self) -> Optional[ChatbotResponse]:
        """
        بازگرداندن اولین پاسخ دسته 'unknown' مناسب برای target_user پیکربندی‌شده
        
        این متد مجموعه پاسخ‌های فعال در دسته‌بندی 'unknown' را مطابق با محدودهٔ target_user (یا 'both') بازیابی می‌کند (با ترتیب نزولی بر اساس priority و زمان ایجاد) و اولین پاسخ (بالاترین اولویت) را برمی‌گرداند. اگر هیچ پاسخی موجود نباشد، None بازگردانده می‌شود.
        
        Returns:
            Optional[ChatbotResponse]: نمونهٔ ChatbotResponse منتخب یا None اگر پاسخی یافت نشود.
        """
        responses = self.get_responses_by_category('unknown')
        return responses[0] if responses else None
    
    def _matches_keywords(self, message: str, keywords: List[str]) -> bool:
        """
        بررسی می‌کند که آیا پیام وارد شده با هر یک از کلمات‌کلیدی مشخص شده مطابقت دارد.
        
        جزئیات:
        - پیام و هر کلمه‌کلیدی پیش از مقایسه به حروف کوچک تبدیل و پیرایش می‌شوند.
        - در صورتی که هر کلمه‌کلیدی به‌صورت زیررشته در پیام ظاهر شود، مطابقت مثبت در نظر گرفته می‌شود.
        - اگر تطبیق زیررشته‌ای پیدا نشود، تابع به‌عنوان مسیر دوم الگوهای پیچیده‌تر (regex) را برای هر کلیدواژه بررسی می‌کند و در صورت تطابق regex نیز مثبت برمی‌گردد.
        - اگر فهرست کلیدواژه‌ها خالی باشد، همیشه False بازگردانده می‌شود.
        
        Parameters:
            message (str): متن پیام کاربر (انتظار می‌رود از قبل به صورت کلیترشده یا نرمال شده باشد).
            keywords (List[str]): فهرستی از کلمات‌کلیدی یا الگوها که باید با پیام بررسی شوند.
        
        Returns:
            bool: True اگر حداقل یکی از کلیدواژه‌ها (به‌صورت زیررشته یا مطابق regex) در پیام یافت شود، در غیر این صورت False.
        """
        if not keywords:
            return False
        
        for keyword in keywords:
            keyword_lower = keyword.lower().strip()
            
            # تطبیق دقیق
            if keyword_lower in message:
                return True
            
            # تطبیق با regex (برای کلمات کلیدی پیچیده)
            if self._regex_match(keyword_lower, message):
                return True
        
        return False
    
    def _regex_match(self, pattern: str, message: str) -> bool:
        """
        بررسی می‌کند آیا یک الگو (که می‌تواند رشته عادی یا عبارت‌نگاره/regex باشد) در متن پیام یافت می‌شود.
        
        این تابع اول تلاش می‌کند تشخیص دهد که پارامتر `pattern` حاوی کاراکترهای ویژهٔ regex هست یا خیر. اگر شامل کاراکترهای ویژه باشد، از جستجوی مستقیم با `re.search(pattern, message)` استفاده می‌کند (الگوی ارائه‌شده به‌عنوان یک regex تفسیر می‌شود). در غیر این صورت، جستجو به‌صورت تطبیق دقیق کلمه انجام می‌شود که از مرز کلمه (`\b`) و `re.escape` برای فرار امن الگو استفاده می‌کند تا فقط کلمات کامل تطبیق داده شوند. در صورت بروز خطای مرتبط با regex (re.error) تابع False برمی‌گرداند.
        
        Parameters:
            pattern (str): الگوی جستجو؛ می‌تواند یک رشته ساده یا یک عبارت‌نگارهٔ regex باشد.
            message (str): متن پیام که در آن جستجو انجام می‌شود.
        
        Returns:
            bool: True اگر الگو در پیام مطابق باشد، در غیر این صورت False.
        """
        try:
            # بررسی اینکه آیا pattern یک regex است
            if any(char in pattern for char in r'.*+?[]{}()|^$\\'):
                return bool(re.search(pattern, message))
            else:
                # تطبیق ساده کلمه
                return bool(re.search(r'\b' + re.escape(pattern) + r'\b', message))
        except re.error:
            return False
    
    def analyze_message_intent(self, message: str) -> Dict[str, Any]:
        """
        تحلیل و تشخیص نیت‌های احتمالی یک پیام متنی کاربر.
        
        توضیحات:
            این تابع پیام ورودی را نرمال‌سازی (حروف کوچک و حذف فاصلهٔ سر و ته) می‌کند و بر اساس نگاشت از پیش‌تعریف‌شده‌ای از نیت‌ها به لیست کلمات کلیدی، نیت‌های مربوطه را تشخیص می‌دهد. برای هر نیت:
            - تعداد کلمات کلیدیِ پیدا‌شده در پیام شمرده می‌شود (با مقایسهٔ سادهٔ درون‌رشته‌ای).
            - امتیاز اطمینان (confidence) به‌صورت نسبت تعداد مطابقت‌ها به مجموع کلمات کلیدی آن نیت محاسبه می‌شود (مقدار بین 0 و 1).
            اگر حداقل یک نیت تشخیص داده شود، نیت اصلی (primary_intent) به‌عنوان نیت با بیشترین امتیاز انتخاب می‌شود.
            تابع خروجی را به‌صورت دیکشنری شامل اطلاعات زیر برمی‌گرداند.
        
        پارامترها:
            message (str): پیام متنی کاربر (رشته) که قرار است نیت آن تحلیل شود.
        
        مقدار بازگشتی:
            Dict[str, Any]: دیکشنری با کلیدهای زیر
                - primary_intent (Optional[str]): نیت با بالاترین امتیاز یا None در صورت عدم تشخیص.
                - detected_intents (List[str]): لیست نیت‌هایی که حداقل یک کلمهٔ کلیدی آن‌ها در پیام یافت شده.
                - confidence_scores (Dict[str, float]): نقشهٔ نیت -> امتیاز اطمینان (0..1).
                - message_length (int): طول پیام به تعداد کاراکتر.
                - word_count (int): تعداد واژه‌ها براساس جداشدن با فاصلهٔ سفید.
        
        نکات پیاده‌سازی (مختصر و مهم):
            - تشخیص بر پایهٔ مقایسهٔ سادهٔ زیررشته‌ای است و از تطابق‌های پیچیدهٔ رگِکس یا پردازش زبان طبیعی استفاده نمی‌کند.
            - امتیازها نسبی به تعداد کلمات کلیدی هر نیت هستند؛ نیتی با کلیدواژهٔ بیشتر ممکن است امتیاز کلی متفاوتی نسبت به نیتی با کلیدواژهٔ کمتر کسب کند.
            - تابع هیچ استثنایی را به‌طور صریح پرتاب نمی‌کند و هیچ اثر جانبی (مانند تغییر پایگاه‌داده یا لاگ‌نویسی) ندارد.
        """
        message_lower = message.lower().strip()
        
        # کلمات کلیدی برای دسته‌بندی‌های مختلف
        intent_keywords = {
            'greeting': ['سلام', 'درود', 'صبح بخیر', 'عصر بخیر', 'hello', 'hi'],
            'symptom_inquiry': ['علائم', 'درد', 'تب', 'سردرد', 'مشکل', 'بیماری'],
            'medication_info': ['دارو', 'قرص', 'کپسول', 'شربت', 'مصرف', 'دوز'],
            'appointment': ['نوبت', 'وقت', 'رزرو', 'appointment'],
            'emergency': ['اورژانس', 'فوری', 'emergency', 'urgent'],
            'farewell': ['خداحافظ', 'خدانگهدار', 'bye', 'goodbye']
        }
        
        detected_intents = []
        confidence_scores = {}
        
        for intent, keywords in intent_keywords.items():
            matches = sum(1 for keyword in keywords if keyword in message_lower)
            if matches > 0:
                detected_intents.append(intent)
                confidence_scores[intent] = matches / len(keywords)
        
        # تعیین هدف اصلی
        primary_intent = None
        if detected_intents:
            primary_intent = max(detected_intents, key=lambda x: confidence_scores[x])
        
        return {
            'primary_intent': primary_intent,
            'detected_intents': detected_intents,
            'confidence_scores': confidence_scores,
            'message_length': len(message),
            'word_count': len(message.split())
        }