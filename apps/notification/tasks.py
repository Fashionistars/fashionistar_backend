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


# ─────────────────────────────────────────────────────────────────────────────
# PHASE 5: BATCH FAN-OUT TASK
# ─────────────────────────────────────────────────────────────────────────────


@shared_task(bind=True, max_retries=2, default_retry_delay=120, name="notification.fan_out_batch")
def fan_out_batch_task(self, batch_id: str):
    """
    Fan out a NotificationBatch to all target recipients.

    Chunked delivery (500/chunk) with atomic progress counter updates
    via BatchNotificationService.record_batch_progress().

    Args:
        batch_id: UUID string of the NotificationBatch to dispatch.

    Flow:
        1. Load batch and resolve target user queryset.
        2. Chunk users into groups of 500.
        3. For each chunk: create notifications via bulk_notify().
        4. After each chunk: update sent/failed counters.
        5. On completion: mark batch COMPLETED or FAILED.
    """
    from django.contrib.auth import get_user_model
    from apps.notification.models import NotificationBatch
    from apps.notification.services.notification_service import bulk_notify
    from apps.notification.services.push_service import BatchNotificationService

    User = get_user_model()

    try:
        batch = NotificationBatch.objects.get(batch_id=batch_id)
    except NotificationBatch.DoesNotExist:
        logger.error("fan_out_batch_task: batch %s not found", batch_id)
        return

    if batch.status == NotificationBatch.Status.CANCELLED:
        logger.info("fan_out_batch_task: batch %s was cancelled, skipping", batch_id)
        return

    # ── Resolve target users ────────────────────────────────────────────────
    qs = User.objects.filter(is_active=True, is_deleted=False)
    if batch.target_roles:
        qs = qs.filter(role__in=batch.target_roles)
    qs = qs.only("id", "email", "role")

    CHUNK_SIZE = 500
    total = qs.count()
    offset = 0
    total_sent = 0
    total_failed = 0

    logger.info("fan_out_batch_task: batch=%s total_recipients=%d", batch_id, total)

    while offset < total:
        chunk = list(qs[offset : offset + CHUNK_SIZE])
        try:
            created = bulk_notify(
                recipients=chunk,
                notification_type=batch.notification_type,
                title=batch.template_context.get("title", batch.title),
                body=batch.template_context.get("body", ""),
                channel=batch.channel,
                metadata={"batch_id": batch_id, **batch.template_context},
            )
            sent_delta = len(created)
            failed_delta = len(chunk) - sent_delta
        except Exception as exc:
            logger.exception("fan_out_batch_task chunk failed: batch=%s offset=%d", batch_id, offset)
            sent_delta = 0
            failed_delta = len(chunk)

        BatchNotificationService.record_batch_progress(
            batch_id=batch_id,
            sent_delta=sent_delta,
            failed_delta=failed_delta,
        )
        total_sent += sent_delta
        total_failed += failed_delta
        offset += CHUNK_SIZE

    BatchNotificationService.complete_batch(batch_id=batch_id, total_count=total)
    logger.info(
        "fan_out_batch_task complete: batch=%s sent=%d failed=%d",
        batch_id, total_sent, total_failed,
    )


# ─────────────────────────────────────────────────────────────────────────────
# PHASE 5: GDPR COMPLIANCE TASKS
# ─────────────────────────────────────────────────────────────────────────────


@shared_task(name="notification.prune_inactive_push_devices", bind=True)
def prune_inactive_push_devices_task(self):
    """
    GDPR Data Minimisation: hard-delete push device tokens
    that have been inactive for 90+ days.

    Beat schedule: weekly (Sunday 02:00 UTC).
    """
    from apps.notification.services.push_service import PushDeviceService
    count = PushDeviceService.prune_inactive_devices(days_inactive=90)
    logger.info("prune_inactive_push_devices: pruned=%d", count)
    return {"pruned": count}


@shared_task(name="notification.anonymize_read_receipt_ips", bind=True)
def anonymize_read_receipt_ips_task(self):
    """
    GDPR Data Minimisation: nullify client_ip on NotificationReadReceipt
    records older than 30 days.

    Beat schedule: daily (03:00 UTC).
    """
    from apps.notification.services.push_service import ReadReceiptService
    count = ReadReceiptService.anonymize_old_ips(days=30)
    logger.info("anonymize_read_receipt_ips: anonymized=%d", count)
    return {"anonymized": count}
