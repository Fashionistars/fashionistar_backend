"""
سرویس مدیریت Webhook ها
"""
from typing import Dict, Any, Optional, List
import hmac
import hashlib
import json
import logging
from datetime import datetime, timedelta
from django.conf import settings
from django.utils import timezone
from integrations.models import WebhookEndpoint, WebhookEvent
from integrations.services.base_service import BaseIntegrationService

logger = logging.getLogger(__name__)


class WebhookService(BaseIntegrationService):
    """
    سرویس مدیریت و پردازش Webhook ها
    """
    
    def __init__(self):
        super().__init__('webhook')
    
    def validate_config(self) -> bool:
        """اعتبارسنجی تنظیمات"""
        # Webhook ها نیاز به تنظیمات خاصی ندارند
        return True
    
    def health_check(self) -> Dict[str, Any]:
        """بررسی سلامت سرویس"""
        try:
            # بررسی تعداد webhook های فعال
            active_webhooks = WebhookEndpoint.objects.filter(is_active=True).count()
            
            # بررسی رویدادهای پردازش نشده
            pending_events = WebhookEvent.objects.filter(
                is_processed=False,
                received_at__gte=timezone.now() - timedelta(hours=24)
            ).count()
            
            return {
                'status': 'healthy',
                'active_webhooks': active_webhooks,
                'pending_events': pending_events,
                'details': {
                    'oldest_pending': self._get_oldest_pending_event()
                }
            }
            
        except Exception as e:
            return {
                'status': 'unhealthy',
                'error': str(e)
            }
    
    def register_webhook(self, provider_slug: str, name: str,
                        endpoint_url: str, events: List[str],
                        secret_key: Optional[str] = None) -> Dict[str, Any]:
        """
        ثبت یک webhook جدید
        
        Args:
            provider_slug: شناسه ارائه‌دهنده
            name: نام webhook
            endpoint_url: آدرس endpoint
            events: لیست رویدادها
            secret_key: کلید امنیتی
            
        Returns:
            نتیجه ثبت
        """
        try:
            # دریافت provider
            from integrations.models import IntegrationProvider
            provider = IntegrationProvider.objects.get(slug=provider_slug)
            
            # تولید کلید امنیتی در صورت عدم وجود
            if not secret_key:
                import secrets
                secret_key = secrets.token_urlsafe(32)
            
            # ایجاد webhook
            webhook = WebhookEndpoint.objects.create(
                provider=provider,
                name=name,
                endpoint_url=endpoint_url,
                secret_key=secret_key,
                events=events
            )
            
            # ثبت لاگ
            self.log_activity(
                action='register_webhook',
                request_data={
                    'provider': provider_slug,
                    'name': name,
                    'endpoint': endpoint_url,
                    'events': events
                },
                response_data={'webhook_id': str(webhook.id)}
            )
            
            return {
                'success': True,
                'webhook_id': str(webhook.id),
                'endpoint_url': endpoint_url,
                'secret_key': secret_key
            }
            
        except Exception as e:
            # ثبت لاگ خطا
            self.log_activity(
                action='register_webhook',
                log_level='error',
                request_data={'provider': provider_slug, 'name': name},
                error_message=str(e)
            )
            
            return {
                'success': False,
                'error': f'خطا در ثبت webhook: {str(e)}'
            }
    
    def process_webhook(self, endpoint_url: str, headers: Dict[str, str],
                       payload: Dict[str, Any], raw_body: bytes) -> Dict[str, Any]:
        """
        پردازش درخواست webhook دریافتی
        
        Args:
            endpoint_url: آدرس endpoint
            headers: هدرهای درخواست
            payload: محتوای درخواست
            raw_body: محتوای خام درخواست
            
        Returns:
            نتیجه پردازش
        """
        try:
            # یافتن webhook
            webhook = WebhookEndpoint.objects.get(
                endpoint_url=endpoint_url,
                is_active=True
            )
            
            # تأیید امضا
            is_valid = self.verify_signature(
                webhook.secret_key,
                raw_body,
                headers.get('X-Signature', '')
            )
            
            # استخراج نوع رویداد
            event_type = payload.get('event', payload.get('type', 'unknown'))
            
            # ثبت رویداد
            event = WebhookEvent.objects.create(
                webhook=webhook,
                event_type=event_type,
                payload=payload,
                headers=dict(headers),
                signature=headers.get('X-Signature', ''),
                is_valid=is_valid
            )
            
            if not is_valid:
                # ثبت لاگ امنیتی
                self.log_activity(
                    action='webhook_invalid_signature',
                    log_level='warning',
                    request_data={
                        'webhook_id': str(webhook.id),
                        'event_type': event_type
                    },
                    error_message='Invalid webhook signature'
                )
                
                return {
                    'success': False,
                    'error': 'Invalid signature',
                    'event_id': str(event.id)
                }
            
            # پردازش رویداد
            result = self._process_event(webhook, event)
            
            # به‌روزرسانی وضعیت
            if result['success']:
                event.is_processed = True
                event.processed_at = timezone.now()
            else:
                event.error_message = result.get('error', '')
            
            event.save()
            
            return {
                'success': result['success'],
                'event_id': str(event.id),
                'message': result.get('message', 'Event processed')
            }
            
        except WebhookEndpoint.DoesNotExist:
            return {
                'success': False,
                'error': 'Webhook endpoint not found'
            }
        except Exception as e:
            # ثبت لاگ خطا
            self.log_activity(
                action='process_webhook',
                log_level='error',
                request_data={'endpoint': endpoint_url},
                error_message=str(e)
            )
            
            return {
                'success': False,
                'error': f'خطا در پردازش webhook: {str(e)}'
            }
    
    def verify_signature(self, secret_key: str, payload: bytes,
                        signature: str) -> bool:
        """
        تأیید امضای webhook
        
        Args:
            secret_key: کلید امنیتی
            payload: محتوای درخواست
            signature: امضای دریافتی
            
        Returns:
            معتبر بودن امضا
        """
        # محاسبه امضای مورد انتظار
        expected_signature = hmac.new(
            secret_key.encode(),
            payload,
            hashlib.sha256
        ).hexdigest()
        
        # مقایسه امن
        return hmac.compare_digest(signature, expected_signature)
    
    def retry_failed_events(self, hours: int = 24) -> Dict[str, Any]:
        """
        تلاش مجدد برای پردازش رویدادهای ناموفق
        
        Args:
            hours: بازه زمانی (ساعت)
            
        Returns:
            نتیجه پردازش مجدد
        """
        try:
            # یافتن رویدادهای ناموفق
            failed_events = WebhookEvent.objects.filter(
                is_processed=False,
                is_valid=True,
                received_at__gte=timezone.now() - timedelta(hours=hours),
                retry_count__lt=3  # حداکثر 3 بار تلاش
            )
            
            processed = 0
            failed = 0
            
            for event in failed_events:
                # افزایش شمارنده تلاش
                event.retry_count += 1
                event.save()
                
                # تلاش برای پردازش
                result = self._process_event(event.webhook, event)
                
                if result['success']:
                    event.is_processed = True
                    event.processed_at = timezone.now()
                    event.save()
                    processed += 1
                else:
                    event.error_message = result.get('error', '')
                    event.save()
                    failed += 1
            
            return {
                'success': True,
                'total_events': failed_events.count(),
                'processed': processed,
                'failed': failed
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': f'خطا در پردازش مجدد: {str(e)}'
            }
    
    def get_event_stats(self, provider_slug: Optional[str] = None,
                       days: int = 7) -> Dict[str, Any]:
        """
        دریافت آمار رویدادهای webhook
        
        Args:
            provider_slug: شناسه ارائه‌دهنده (اختیاری)
            days: تعداد روز
            
        Returns:
            آمار رویدادها
        """
        try:
            # فیلتر بر اساس زمان
            start_date = timezone.now() - timedelta(days=days)
            events = WebhookEvent.objects.filter(received_at__gte=start_date)
            
            # فیلتر بر اساس provider
            if provider_slug:
                events = events.filter(webhook__provider__slug=provider_slug)
            
            # محاسبه آمار
            total_events = events.count()
            processed_events = events.filter(is_processed=True).count()
            failed_events = events.filter(is_processed=False, retry_count__gte=3).count()
            invalid_events = events.filter(is_valid=False).count()
            
            # آمار بر اساس نوع رویداد
            event_types = {}
            for event in events.values('event_type').annotate(count=models.Count('id')):
                event_types[event['event_type']] = event['count']
            
            return {
                'success': True,
                'period_days': days,
                'total_events': total_events,
                'processed_events': processed_events,
                'failed_events': failed_events,
                'invalid_events': invalid_events,
                'success_rate': (processed_events / total_events * 100) if total_events > 0 else 0,
                'event_types': event_types
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': f'خطا در دریافت آمار: {str(e)}'
            }
    
    def _process_event(self, webhook: WebhookEndpoint,
                      event: WebhookEvent) -> Dict[str, Any]:
        """
        پردازش داخلی یک رویداد
        
        Args:
            webhook: webhook endpoint
            event: رویداد
            
        Returns:
            نتیجه پردازش
        """
        try:
            # بررسی نوع رویداد
            if event.event_type not in webhook.events:
                return {
                    'success': False,
                    'error': f'Event type {event.event_type} not configured for this webhook'
                }
            
            # routing بر اساس provider و event type
            provider_slug = webhook.provider.slug
            
            if provider_slug == 'payment_gateway':
                return self._process_payment_event(event)
            elif provider_slug == 'sms_provider':
                return self._process_sms_event(event)
            elif provider_slug == 'ai_service':
                return self._process_ai_event(event)
            else:
                # پردازش عمومی
                return self._process_generic_event(event)
                
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
    
    def _process_payment_event(self, event: WebhookEvent) -> Dict[str, Any]:
        """پردازش رویدادهای پرداخت"""
        payload = event.payload
        
        if event.event_type == 'payment.success':
            # به‌روزرسانی وضعیت پرداخت
            payment_id = payload.get('payment_id')
            # TODO: اتصال به سرویس billing
            return {'success': True, 'message': f'Payment {payment_id} processed'}
            
        elif event.event_type == 'payment.failed':
            # مدیریت پرداخت ناموفق
            return {'success': True, 'message': 'Payment failure handled'}
            
        return {'success': False, 'error': 'Unknown payment event'}
    
    def _process_sms_event(self, event: WebhookEvent) -> Dict[str, Any]:
        """پردازش رویدادهای SMS"""
        payload = event.payload
        
        if event.event_type == 'sms.delivered':
            # به‌روزرسانی وضعیت تحویل
            message_id = payload.get('message_id')
            return {'success': True, 'message': f'SMS {message_id} delivered'}
            
        elif event.event_type == 'sms.failed':
            # مدیریت خطای ارسال
            return {'success': True, 'message': 'SMS failure handled'}
            
        return {'success': False, 'error': 'Unknown SMS event'}
    
    def _process_ai_event(self, event: WebhookEvent) -> Dict[str, Any]:
        """پردازش رویدادهای AI"""
        # پردازش رویدادهای مربوط به سرویس‌های AI
        return {'success': True, 'message': 'AI event processed'}
    
    def _process_generic_event(self, event: WebhookEvent) -> Dict[str, Any]:
        """پردازش عمومی رویدادها"""
        # ثبت در لاگ و پردازش پایه
        self.log_activity(
            action=f'webhook_event_{event.event_type}',
            request_data=event.payload
        )
        
        return {'success': True, 'message': 'Event logged successfully'}
    
    def _get_oldest_pending_event(self) -> Optional[str]:
        """دریافت قدیمی‌ترین رویداد پردازش نشده"""
        try:
            oldest = WebhookEvent.objects.filter(
                is_processed=False
            ).order_by('received_at').first()
            
            if oldest:
                return oldest.received_at.isoformat()
            return None
            
        except Exception:
            return None