# apps/notification/tasks.py
"""
Celery tasks for the Notification domain.

Architecture:
  - dispatch_notification_task: routes a persisted Notification record
    to the correct channel handler (email, push, sms).
  - For `in_app` channel, no external dispatch is needed — the record
    is retrieved by the WebSocket feed and the REST endpoint.
  - Failed tasks update the Notification record with retry_count and error_msg.
"""
import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=60, name="notification.dispatch")
def dispatch_notification_task(self, notification_id: str):
    """
    Dispatch a single notification to its delivery channel.
    Retries up to 3 times with 60s delay on failure.
    """
    try:
        from django.utils import timezone
        from apps.notification.models import Notification, NotificationChannel

        try:
            notif = Notification.objects.get(id=notification_id)
        except Notification.DoesNotExist:
            logger.warning("dispatch_notification_task: notif %s not found", notification_id)
            return

        if notif.channel == NotificationChannel.IN_APP:
            # In-app: just mark as sent — WebSocket/REST will surface it
            notif.sent_at = timezone.now()
            notif.save(update_fields=["sent_at"])
            logger.debug("In-app notification %s marked sent", notification_id)
            return

        if notif.channel == NotificationChannel.EMAIL:
            _dispatch_email(notif)

        elif notif.channel == NotificationChannel.PUSH:
            _dispatch_push(notif)

        elif notif.channel == NotificationChannel.SMS:
            _dispatch_sms(notif)

        notif.sent_at = timezone.now()
        notif.save(update_fields=["sent_at", "retry_count", "error_msg"])

    except Exception as exc:
        logger.exception("dispatch_notification_task failed: notif=%s", notification_id)
        # Update retry count on the record
        try:
            from apps.notification.models import Notification
            Notification.objects.filter(id=notification_id).update(
                retry_count=self.request.retries + 1,
                error_msg=str(exc)[:500],
            )
        except Exception:
            pass
        raise self.retry(exc=exc)


def _dispatch_email(notif) -> None:
    """Send notification via Django email framework."""
    from django.core.mail import send_mail
    if not notif.recipient or not getattr(notif.recipient, "email", None):
        return
    send_mail(
        subject=notif.title,
        message=notif.body,
        from_email=None,  # Uses DEFAULT_FROM_EMAIL
        recipient_list=[notif.recipient.email],
        fail_silently=False,
    )


def _dispatch_push(notif) -> None:
    """
    Push notification stub — integrate with FCM/APNs here.
    Future: connect to Firebase Cloud Messaging via fcm-django or similar.
    """
    logger.info(
        "PUSH stub: notif=%s to user=%s title=%s",
        notif.id,
        notif.recipient_id,
        notif.title[:40],
    )


def _dispatch_sms(notif) -> None:
    """
    SMS stub — integrate with Twilio/Termii here.
    """
    logger.info(
        "SMS stub: notif=%s to user=%s title=%s",
        notif.id,
        notif.recipient_id,
        notif.title[:40],
    )
