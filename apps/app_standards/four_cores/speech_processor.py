"""
هسته پردازش صوت - الگوی استاندارد
Speech Processing Core - Standard Pattern
"""

from typing import Dict, List, Any, Optional, BinaryIO
from dataclasses import dataclass
import logging
import os
import tempfile
import hashlib
from django.conf import settings
from django.core.files.storage import default_storage
from unified_ai.services import STTService, TTSService
from django.core.cache import cache
from django.core.files.storage import default_storage
from pydub import AudioSegment


logger = logging.getLogger(__name__)


@dataclass
class AudioTranscriptionResult:
    """نتیجه رونویسی صوت"""
    text: str
    segments: List[Dict[str, Any]]
    language: str
    duration: float
    confidence: float
    metadata: Dict[str, Any]


@dataclass
class AudioGenerationResult:
    """نتیجه تولید صوت"""
    audio_file: str
    duration: float
    format: str
    metadata: Dict[str, Any]


class SpeechProcessorCore:
    """
    هسته پردازش صوت
    مسئول STT، TTS، پردازش صوت و تحلیل صوتی
    """
    
    SUPPORTED_FORMATS = ['mp3', 'wav', 'ogg', 'm4a', 'webm']
    MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB
    CHUNK_DURATION = 60  # seconds
    
    def __init__(self):
        self.stt_service = STTService()
        self.tts_service = TTSService()
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self.cache_enabled = getattr(settings, 'SPEECH_CACHE_ENABLED', True)
        self.cache_ttl = getattr(settings, 'SPEECH_CACHE_TTL', 86400)  # 24 hours
        
    def transcribe_audio(self, audio_file: BinaryIO, 
                        language: str = 'fa',
                        medical_mode: bool = True) -> AudioTranscriptionResult:
        """
        تبدیل صوت به متن
        
        Args:
            audio_file: فایل صوتی
            language: زبان صوت
            medical_mode: حالت پزشکی برای بهبود دقت
            
        Returns:
            AudioTranscriptionResult object
        """
        try:
            # بررسی و اعتبارسنجی فایل
            file_info = self._validate_audio_file(audio_file)
            
            # بررسی کش
            cache_key = self._generate_cache_key(audio_file, 'transcribe', language)
            if self.cache_enabled:
                cached_result = cache.get(cache_key)
                if cached_result:
                    self.logger.info("Returning cached transcription")
                    return cached_result
            
            # ذخیره موقت فایل
            with tempfile.NamedTemporaryFile(suffix=f'.{file_info["format"]}', delete=False) as tmp_file:
                tmp_file.write(audio_file.read())
                tmp_path = tmp_file.name
            
            try:
                # پیش‌پردازش صوت
                processed_path = self._preprocess_audio(tmp_path)
                
                # تقسیم به قطعات در صورت نیاز
                if file_info['duration'] > self.CHUNK_DURATION:
                    chunks = self._split_audio_chunks(processed_path)
                    transcription_result = self._transcribe_chunks(chunks, language, medical_mode)
                else:
                    transcription_result = self._transcribe_single(processed_path, language, medical_mode)
                
                # پس‌پردازش متن
                if medical_mode:
                    transcription_result['text'] = self._post_process_medical_text(
                        transcription_result['text']
                    )
                
                # ساخت نتیجه
                result = AudioTranscriptionResult(
                    text=transcription_result['text'],
                    segments=transcription_result.get('segments', []),
                    language=language,
                    duration=file_info['duration'],
                    confidence=transcription_result.get('confidence', 0.0),
                    metadata={
                        'original_format': file_info['format'],
                        'file_size': file_info['size'],
                        'sample_rate': file_info.get('sample_rate'),
                        'channels': file_info.get('channels'),
                        'medical_mode': medical_mode
                    }
                )
                
                # ذخیره در کش
                if self.cache_enabled:
                    cache.set(cache_key, result, self.cache_ttl)
                
                return result
                
            finally:
                # پاکسازی فایل‌های موقت
                os.unlink(tmp_path)
                if 'processed_path' in locals() and processed_path != tmp_path:
                    os.unlink(processed_path)
                    
        except Exception as e:
            self.logger.error(f"Transcription error: {str(e)}")
            raise
    
    def generate_speech(self, text: str, voice: str = 'default',
                       speed: float = 1.0) -> AudioGenerationResult:
        """
        تولید صوت از متن
        
        Args:
            text: متن ورودی
            voice: نوع صدا
            speed: سرعت پخش
            
        Returns:
            AudioGenerationResult object
        """
        try:
            # تمیزسازی متن
            cleaned_text = self._clean_text_for_tts(text)
            
            # تولید صوت
            audio_data = self.tts_service.generate_speech(
                text=cleaned_text,
                voice=voice,
                speed=speed,
                format='mp3'
            )
            
            # ذخیره فایل
            file_hash = hashlib.md5(f"{text}{voice}{speed}".encode()).hexdigest()
            file_name = f"tts_{file_hash}.mp3"
            file_path = default_storage.save(f"speech/generated/{file_name}", audio_data)
            
            # محاسبه مدت زمان
            duration = self._get_audio_duration(file_path)
            
            return AudioGenerationResult(
                audio_file=file_path,
                duration=duration,
                format='mp3',
                metadata={
                    'voice': voice,
                    'speed': speed,
                    'text_length': len(text),
                    'file_size': len(audio_data)
                }
            )
            
        except Exception as e:
            self.logger.error(f"Speech generation error: {str(e)}")
            raise
    
    def analyze_audio_quality(self, audio_file: BinaryIO) -> Dict[str, Any]:
        """
        تحلیل کیفیت صوت
        
        Args:
            audio_file: فایل صوتی
            
        Returns:
            دیکشنری حاوی اطلاعات کیفیت
        """
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp_file:
            tmp_file.write(audio_file.read())
            tmp_path = tmp_file.name
        
        try:
            audio = AudioSegment.from_file(tmp_path)
            
            # محاسبات کیفیت
            quality_metrics = {
                'duration': len(audio) / 1000.0,  # seconds
                'sample_rate': audio.frame_rate,
                'channels': audio.channels,
                'bit_depth': audio.sample_width * 8,
                'bitrate': audio.frame_rate * audio.channels * audio.sample_width * 8,
                'db_peak': audio.max_dBFS,
                'rms': audio.rms,
                'quality_score': self._calculate_quality_score(audio)
            }
            
            return quality_metrics
            
        finally:
            os.unlink(tmp_path)
    
    def _validate_audio_file(self, audio_file: BinaryIO) -> Dict[str, Any]:
        """اعتبارسنجی فایل صوتی"""
        # بررسی حجم
        audio_file.seek(0, 2)  # Go to end
        file_size = audio_file.tell()
        audio_file.seek(0)  # Reset to beginning
        
        if file_size > self.MAX_FILE_SIZE:
            raise ValueError(f"File size {file_size} exceeds maximum {self.MAX_FILE_SIZE}")
        
        # تشخیص فرمت
        header = audio_file.read(12)
        audio_file.seek(0)
        
        format_signatures = {
            b'RIFF': 'wav',
            b'ID3': 'mp3',
            b'\xff\xfb': 'mp3',
            b'OggS': 'ogg',
            b'ftyp': 'm4a',
        }
        
        file_format = None
        for signature, fmt in format_signatures.items():
            if header.startswith(signature):
                file_format = fmt
                break
        
        if not file_format:
            raise ValueError("Unsupported audio format")
        
        return {
            'size': file_size,
            'format': file_format,
            'duration': self._estimate_duration(audio_file, file_format)
        }
    
    def _preprocess_audio(self, audio_path: str) -> str:
        """پیش‌پردازش صوت برای بهبود کیفیت"""
        audio = AudioSegment.from_file(audio_path)
        
        # نرمال‌سازی صدا
        normalized = audio.normalize()
        
        # حذف نویز (ساده)
        if normalized.dBFS < -30:
            normalized = normalized + (-normalized.dBFS - 20)
        
        # تبدیل به فرمت مناسب برای STT
        processed = normalized.set_frame_rate(16000).set_channels(1)
        
        output_path = audio_path.replace('.', '_processed.')
        processed.export(output_path, format='wav')
        
        return output_path
    
    def _split_audio_chunks(self, audio_path: str) -> List[str]:
        """تقسیم فایل صوتی به قطعات کوچکتر"""
        audio = AudioSegment.from_file(audio_path)
        chunk_length = self.CHUNK_DURATION * 1000  # milliseconds
        
        chunks = []
        for i in range(0, len(audio), chunk_length):
            chunk = audio[i:i + chunk_length]
            chunk_path = f"{audio_path}_chunk_{i//chunk_length}.wav"
            chunk.export(chunk_path, format='wav')
            chunks.append(chunk_path)
        
        return chunks
    
    def _transcribe_single(self, audio_path: str, language: str, 
                         medical_mode: bool) -> Dict[str, Any]:
        """رونویسی یک فایل صوتی"""
        # تنظیمات خاص برای حالت پزشکی
        if medical_mode:
            prompt = "این یک مکالمه پزشکی است. توجه ویژه به اصطلاحات پزشکی داشته باشید."
        else:
            prompt = None
        
        result = self.stt_service.transcribe(
            audio_file=audio_path,
            language=language,
            prompt=prompt,
            return_segments=True
        )
        
        return result
    
    def _transcribe_chunks(self, chunks: List[str], language: str,
                         medical_mode: bool) -> Dict[str, Any]:
        """رونویسی و ترکیب قطعات صوتی"""
        all_text = []
        all_segments = []
        total_confidence = 0
        
        for i, chunk_path in enumerate(chunks):
            result = self._transcribe_single(chunk_path, language, medical_mode)
            all_text.append(result['text'])
            
            # تنظیم زمان‌بندی segments
            chunk_offset = i * self.CHUNK_DURATION
            for segment in result.get('segments', []):
                segment['start'] += chunk_offset
                segment['end'] += chunk_offset
                all_segments.append(segment)
            
            total_confidence += result.get('confidence', 0)
            
            # پاکسازی chunk
            os.unlink(chunk_path)
        
        return {
            'text': ' '.join(all_text),
            'segments': all_segments,
            'confidence': total_confidence / len(chunks)
        }
    
    def _post_process_medical_text(self, text: str) -> str:
        """پس‌پردازش متن پزشکی"""
        # اصلاح اصطلاحات پزشکی رایج
        medical_corrections = {
            'اس پی او تو': 'SpO2',
            'سی تی': 'CT',
            'ام آر آی': 'MRI',
            'ای سی جی': 'ECG',
            'بی پی': 'BP',
            'آی سی یو': 'ICU',
        }
        
        for wrong, correct in medical_corrections.items():
            text = text.replace(wrong, correct)
        
        return text
    
    def _clean_text_for_tts(self, text: str) -> str:
        """تمیزسازی متن برای TTS"""
        # حذف کاراکترهای خاص
        import re
        text = re.sub(r'[<>{}[\]\\]', '', text)
        
        # تبدیل اعداد انگلیسی به حروف
        # این قسمت می‌تواند پیچیده‌تر شود
        
        return text.strip()
    
    def _get_audio_duration(self, file_path: str) -> float:
        """محاسبه مدت زمان فایل صوتی"""
        audio = AudioSegment.from_file(file_path)
        return len(audio) / 1000.0  # seconds
    
    def _estimate_duration(self, audio_file: BinaryIO, format: str) -> float:
        """تخمین مدت زمان بدون لود کامل فایل"""
        # این یک تخمین ساده است
        file_size = audio_file.seek(0, 2)
        audio_file.seek(0)
        
        # تخمین بر اساس bitrate متوسط
        bitrate_estimates = {
            'mp3': 128000,  # 128 kbps
            'wav': 1411000,  # 1411 kbps
            'ogg': 160000,   # 160 kbps
            'm4a': 256000,   # 256 kbps
        }
        
        bitrate = bitrate_estimates.get(format, 128000)
        duration = (file_size * 8) / bitrate
        
        return duration
    
    def _calculate_quality_score(self, audio: AudioSegment) -> float:
        """محاسبه امتیاز کیفیت صوت"""
        score = 100.0
        
        # بررسی sample rate
        if audio.frame_rate < 16000:
            score -= 20
        elif audio.frame_rate < 44100:
            score -= 10
        
        # بررسی تعداد کانال‌ها
        if audio.channels > 2:
            score -= 5
        
        # بررسی dynamic range
        if audio.max_dBFS < -30:
            score -= 15
        elif audio.max_dBFS > -3:
            score -= 10
        
        # بررسی bit depth
        if audio.sample_width < 2:
            score -= 15
        
        return max(0, score)
    
    def _generate_cache_key(self, audio_file: BinaryIO, 
                          operation: str, *args) -> str:
        """تولید کلید کش برای عملیات صوتی"""
        # محاسبه hash فایل
        hasher = hashlib.md5()
        for chunk in iter(lambda: audio_file.read(4096), b""):
            hasher.update(chunk)
        audio_file.seek(0)
        
        file_hash = hasher.hexdigest()
        args_str = '_'.join(str(arg) for arg in args)
        
        return f"speech:{operation}:{file_hash}:{args_str}"


# نمونه استفاده
if __name__ == "__main__":
    processor = SpeechProcessorCore()
    
    # تبدیل صوت به متن
    with open('audio_sample.mp3', 'rb') as audio_file:
        result = processor.transcribe_audio(
            audio_file,
            language='fa',
            medical_mode=True
        )
        print(f"Transcription: {result.text}")
        print(f"Duration: {result.duration}s")
        print(f"Confidence: {result.confidence}")
    
    # تولید صوت از متن
    speech_result = processor.generate_speech(
        "سلام، نتیجه آزمایش شما آماده است",
        voice='female'
    )
    print(f"Generated audio: {speech_result.audio_file}")