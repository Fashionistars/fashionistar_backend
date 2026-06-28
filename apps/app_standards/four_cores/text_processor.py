"""
هسته پردازش متن - الگوی استاندارد
Text Processing Core - Standard Pattern
"""

from typing import Dict, List, Any, Optional
from dataclasses import dataclass
import logging
import re
from django.conf import settings
from unified_ai.services import UnifiedAIService
from django.core.cache import cache
import hashlib
import json

logger = logging.getLogger(__name__)


@dataclass
class TextProcessingResult:
    """نتیجه پردازش متن"""
    processed_text: str
    entities: List[Dict[str, Any]]
    summary: Optional[str] = None
    keywords: List[str] = None
    sentiment: Optional[str] = None
    confidence: float = 0.0
    metadata: Dict[str, Any] = None


class TextProcessorCore:
    """
    هسته پردازش متن
    مسئول NLP، تولید متن، خلاصه‌سازی و تحلیل متن پزشکی
    """
    
    def __init__(self):
        self.ai_service = UnifiedAIService()
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self.cache_enabled = getattr(settings, 'TEXT_PROCESSING_CACHE_ENABLED', True)
        self.cache_ttl = getattr(settings, 'TEXT_PROCESSING_CACHE_TTL', 3600)
        
    def process_medical_text(self, text: str, context: Dict[str, Any] = None,
                           task: str = 'analysis') -> TextProcessingResult:
        """
        پردازش متن پزشکی با AI
        
        Args:
            text: متن ورودی
            context: اطلاعات زمینه‌ای
            task: نوع وظیفه (analysis, summary, generation)
            
        Returns:
            TextProcessingResult object
        """
        try:
            # بررسی کش
            cache_key = self._generate_cache_key(text, context, task)
            if self.cache_enabled:
                cached_result = cache.get(cache_key)
                if cached_result:
                    self.logger.info("Returning cached result")
                    return cached_result
            
            # پیش‌پردازش متن
            cleaned_text = self._preprocess_text(text)
            
            # فراخوانی سرویس AI
            ai_result = self.ai_service.process_text(
                text=cleaned_text,
                context=context or {},
                task=f'medical_{task}'
            )
            
            # استخراج موجودیت‌ها
            entities = self._extract_medical_entities(
                ai_result.get('text', cleaned_text)
            )
            
            # تحلیل احساسات (در صورت نیاز)
            sentiment = None
            if task in ['analysis', 'chat']:
                sentiment = self._analyze_sentiment(cleaned_text)
            
            # ساخت نتیجه
            result = TextProcessingResult(
                processed_text=ai_result.get('text', cleaned_text),
                entities=entities,
                summary=ai_result.get('summary'),
                keywords=ai_result.get('keywords', []),
                sentiment=sentiment,
                confidence=ai_result.get('confidence', 0.0),
                metadata={
                    'original_length': len(text),
                    'processed_length': len(ai_result.get('text', cleaned_text)),
                    'task': task,
                    'model_used': ai_result.get('model', 'unknown')
                }
            )
            
            # ذخیره در کش
            if self.cache_enabled:
                cache.set(cache_key, result, self.cache_ttl)
            
            return result
            
        except Exception as e:
            self.logger.error(f"Text processing error: {str(e)}")
            raise
    
    def generate_medical_response(self, prompt: str, 
                                patient_context: Dict[str, Any]) -> str:
        """
        تولید پاسخ پزشکی با در نظر گرفتن زمینه بیمار
        
        Args:
            prompt: سوال یا درخواست
            patient_context: اطلاعات بیمار
            
        Returns:
            پاسخ تولید شده
        """
        system_prompt = self._build_medical_system_prompt(patient_context)
        
        try:
            response = self.ai_service.generate_text(
                prompt=prompt,
                system_prompt=system_prompt,
                max_tokens=500,
                temperature=0.7
            )
            
            # اعتبارسنجی پاسخ پزشکی
            if self._contains_medical_advice(response):
                response = self._add_medical_disclaimer(response)
            
            return response
            
        except Exception as e:
            self.logger.error(f"Response generation error: {str(e)}")
            return "متاسفانه در پردازش درخواست شما مشکلی پیش آمد. لطفا دوباره تلاش کنید."
    
    def summarize_conversation(self, messages: List[Dict[str, str]]) -> str:
        """
        خلاصه‌سازی گفتگوی پزشکی
        
        Args:
            messages: لیست پیام‌ها
            
        Returns:
            خلاصه گفتگو
        """
        # ترکیب پیام‌ها
        conversation = "\n".join([
            f"{msg['role']}: {msg['content']}" 
            for msg in messages
        ])
        
        result = self.process_medical_text(
            conversation,
            context={'task': 'summarization'},
            task='summary'
        )
        
        return result.summary or "خلاصه‌ای در دسترس نیست"
    
    def extract_symptoms(self, text: str) -> List[Dict[str, Any]]:
        """
        استخراج علائم از متن
        
        Args:
            text: متن حاوی علائم
            
        Returns:
            لیست علائم استخراج شده
        """
        result = self.process_medical_text(
            text,
            context={'extraction_type': 'symptoms'},
            task='analysis'
        )
        
        symptoms = []
        for entity in result.entities:
            if entity.get('type') == 'symptom':
                symptoms.append({
                    'name': entity['value'],
                    'severity': entity.get('severity', 'unknown'),
                    'duration': entity.get('duration'),
                    'confidence': entity.get('confidence', 0.5)
                })
        
        return symptoms
    
    def _preprocess_text(self, text: str) -> str:
        """پیش‌پردازش و تمیزسازی متن"""
        # حذف کاراکترهای اضافی
        text = re.sub(r'\s+', ' ', text)
        text = text.strip()
        
        # نرمال‌سازی اعداد فارسی
        persian_numbers = '۰۱۲۳۴۵۶۷۸۹'
        english_numbers = '0123456789'
        translation_table = str.maketrans(persian_numbers, english_numbers)
        text = text.translate(translation_table)
        
        return text
    
    def _extract_medical_entities(self, text: str) -> List[Dict[str, Any]]:
        """استخراج موجودیت‌های پزشکی از متن"""
        entities = []
        
        # الگوهای پزشکی
        patterns = {
            'symptom': r'(درد|تب|سردرد|سرگیجه|تهوع|ضعف|خستگی)',
            'medication': r'(قرص|کپسول|شربت|آمپول|پماد)',
            'body_part': r'(سر|گردن|شکم|سینه|پا|دست|چشم|گوش)',
            'test': r'(آزمایش|سونوگرافی|رادیولوژی|MRI|CT)',
        }
        
        for entity_type, pattern in patterns.items():
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                entities.append({
                    'type': entity_type,
                    'value': match.group(),
                    'start': match.start(),
                    'end': match.end(),
                    'confidence': 0.8
                })
        
        return entities
    
    def _analyze_sentiment(self, text: str) -> str:
        """تحلیل احساسات متن"""
        # این یک پیاده‌سازی ساده است
        negative_words = ['درد', 'ناراحت', 'نگران', 'بد', 'مشکل']
        positive_words = ['خوب', 'بهتر', 'عالی', 'راضی', 'سالم']
        
        text_lower = text.lower()
        negative_count = sum(1 for word in negative_words if word in text_lower)
        positive_count = sum(1 for word in positive_words if word in text_lower)
        
        if negative_count > positive_count:
            return 'negative'
        elif positive_count > negative_count:
            return 'positive'
        else:
            return 'neutral'
    
    def _build_medical_system_prompt(self, patient_context: Dict[str, Any]) -> str:
        """ساخت system prompt برای پاسخ‌های پزشکی"""
        base_prompt = """شما یک دستیار پزشکی هوشمند هستید که به بیماران کمک می‌کنید.
        قوانین:
        1. هرگز تشخیص قطعی ندهید
        2. همیشه توصیه به مراجعه به پزشک کنید
        3. اطلاعات کلی و آموزشی ارائه دهید
        4. با همدلی و احترام پاسخ دهید
        """
        
        if patient_context.get('age'):
            base_prompt += f"\nسن بیمار: {patient_context['age']} سال"
        
        if patient_context.get('gender'):
            base_prompt += f"\nجنسیت: {patient_context['gender']}"
            
        return base_prompt
    
    def _contains_medical_advice(self, text: str) -> bool:
        """بررسی وجود توصیه پزشکی در متن"""
        medical_keywords = ['مصرف', 'درمان', 'دارو', 'تجویز', 'دوز']
        return any(keyword in text for keyword in medical_keywords)
    
    def _add_medical_disclaimer(self, text: str) -> str:
        """افزودن disclaimer پزشکی"""
        disclaimer = "\n\n⚠️ توجه: این اطلاعات صرفاً جنبه آموزشی دارد و جایگزین مشاوره پزشکی نیست."
        return text + disclaimer
    
    def _generate_cache_key(self, text: str, context: Dict, task: str) -> str:
        """تولید کلید کش یکتا"""
        data = {
            'text': text[:100],  # فقط 100 کاراکتر اول
            'context': context,
            'task': task
        }
        data_str = json.dumps(data, sort_keys=True)
        return f"text_proc:{hashlib.md5(data_str.encode()).hexdigest()}"


# نمونه استفاده
if __name__ == "__main__":
    processor = TextProcessorCore()
    
    # پردازش متن پزشکی
    result = processor.process_medical_text(
        "از دیروز سردرد شدید دارم و احساس تهوع می‌کنم",
        context={'patient_age': 35}
    )
    
    print(f"Processed: {result.processed_text}")
    print(f"Entities: {result.entities}")
    print(f"Sentiment: {result.sentiment}")