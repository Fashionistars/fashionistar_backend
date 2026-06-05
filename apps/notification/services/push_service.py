# apps/notification/services/push_service.py
"""
PushDeviceService — FCM / APNs push token management.
BatchNotificationService — bulk fan-out lifecycle management.

Architecture:
  - PushDeviceService: upsert device token on app launch, invalidate on logout.
  - BatchNotificationService: create batch → celery fan-out → update progress.
  - All writes: transaction.atomic() + transaction.on_commit() for Celery enqueue.
  - select_for_update() on Batch counter updates to prevent race conditions.

GDPR:
  - PushDevice tokens pruned after 90 days of inactivity (data minimisation).
  - NotificationReadReceipt IP field anonymized after 30 days.
"""

from __future__ import annotations

import logging

from django.db import transaction
from django.utils import timezone

from apps.notification.models import (
    NotificationBatch,
    NotificationChannel,
    NotificationType,
)
from apps.notification.models.batch import NotificationReadReceipt
from apps.notification.models.push_device import PushDevice

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# PUSH DEVICE SERVICE
# ─────────────────────────────────────────────────────────────────────────────


class PushDeviceService:
    """
    Manages push notification device token lifecycle.

    Methods:
        upsert_device: Register or update a device token (idempotent by device_id).
        deactivate_device: Mark a device token as invalid (logout or delivery failure).
        deactivate_all_for_user: Revoke all tokens on account deletion or full logout.
        get_active_tokens: Return all active tokens for a user (for fan-out).
        prune_inactive_devices: Hard-delete tokens inactive for 90+ days (GDPR task).
    """

    @staticmethod
    @transaction.atomic
    def upsert_device(
        *,
        user,
        platform: str,
        device_id: str,
        token: str,
        device_name: str = "",
        app_version: str = "",
        os_version: str = "",
    ) -> PushDevice:
        """
        Register or update a device push token (idempotent).

        Uses update_or_create keyed on (user, device_id) so that token
        refreshes from FCM do not create duplicate rows.

        Args:
            user: The authenticated user registering the device.
            platform: 'fcm', 'apns', or 'web'.
            device_id: Stable client-generated UUID identifying the device.
            token: Current push token from FCM/APNs/VAPID.
            device_name: Human-readable device label.
            app_version: App version string for diagnostics.
            os_version: OS version string for diagnostics.

        Returns:
            The created or updated PushDevice instance.
        """
        device, created = PushDevice.objects.update_or_create(
            user=user,
            device_id=device_id,
            defaults={
                "platform": platform,
                "token": token,
                "device_name": device_name,
                "app_version": app_version,
                "os_version": os_version,
                "is_active": True,
                "last_used_at": timezone.now(),
            },
        )
        action = "registered" if created else "refreshed"
        logger.info(
            "PushDevice %s: user=%s device_id=%s platform=%s",
            action, user.id, device_id[:12], platform,
        )
        return device

    @staticmethod
    @transaction.atomic
    def deactivate_device(*, device_id: str, user) -> bool:
        """
        Deactivate a specific device token.

        Called on:
          - Explicit user logout from a specific device.
          - FCM/APNs delivery error (NotRegistered / BadDeviceToken).

        Returns:
            True if a device was deactivated, False if not found.
        """
        updated = PushDevice.objects.filter(
            user=user,
            device_id=device_id,
            is_active=True,
        ).update(is_active=False)
        if updated:
            logger.info("PushDevice deactivated: user=%s device_id=%s", user.id, device_id[:12])
        return bool(updated)

    @staticmethod
    @transaction.atomic
    def deactivate_all_for_user(*, user) -> int:
        """
        Revoke ALL push tokens for a user.

        Called on:
          - Full account logout (revoke-all-sessions flow).
          - Account deletion (GDPR Article 17).

        Returns:
            Count of tokens deactivated.
        """
        count = PushDevice.objects.filter(user=user, is_active=True).update(is_active=False)
        logger.info("PushDevice bulk-deactivate: user=%s count=%d", user.id, count)
        return count

    @staticmethod
    def get_active_tokens(*, user) -> list[PushDevice]:
        """
        Return all active push device tokens for a user.
        Used by the push notification fan-out task.
        """
        return list(
            PushDevice.objects.filter(user=user, is_active=True).only(
                "id", "platform", "token", "device_id"
            )
        )

    @staticmethod
    def prune_inactive_devices(*, days_inactive: int = 90) -> int:
        """
        Hard-delete push tokens inactive for more than `days_inactive` days.
        Called by the GDPR data minimisation Celery task (weekly).

        Returns:
            Count of records deleted.
        """
        cutoff = timezone.now() - timezone.timedelta(days=days_inactive)
        deleted_count, _ = PushDevice.objects.filter(
            is_active=False,
            last_used_at__lt=cutoff,
        ).delete()
        logger.info("PushDevice pruned: count=%d cutoff=%s", deleted_count, cutoff.date())
        return deleted_count


# ─────────────────────────────────────────────────────────────────────────────
# BATCH NOTIFICATION SERVICE
# ─────────────────────────────────────────────────────────────────────────────


class BatchNotificationService:
    """
    Manages the lifecycle of bulk notification batches.

    Flow:
        1. create_batch() → status=DRAFT
        2. schedule_batch() → status=SCHEDULED (or SENDING if immediate)
        3. Celery task: fan_out_batch_task() updates sent/failed counts
        4. complete_batch() → status=COMPLETED / FAILED
        5. cancel_batch() → status=CANCELLED (only from DRAFT/SCHEDULED)

    All counter updates use select_for_update() to prevent race conditions
    when multiple Celery workers update the same batch concurrently.
    """

    @staticmethod
    @transaction.atomic
    def create_batch(
        *,
        title: str,
        notification_type: str,
        channel: str = NotificationChannel.IN_APP,
        target_roles: list[str] | None = None,
        template_context: dict | None = None,
        scheduled_at=None,
        created_by=None,
    ) -> NotificationBatch:
        """
        Create a new notification batch in DRAFT status.

        Args:
            title: Internal label for the batch.
            notification_type: NotificationType slug.
            channel: Delivery channel.
            target_roles: Role slugs to target. Empty = all users.
            template_context: Shared context merged into each render.
            scheduled_at: When to dispatch. None = immediate on approval.
            created_by: Staff user creating the batch.

        Returns:
            The created NotificationBatch instance.
        """
        batch = NotificationBatch.objects.create(
            title=title,
            notification_type=notification_type,
            channel=channel,
            target_roles=target_roles or [],
            template_context=template_context or {},
            scheduled_at=scheduled_at,
            created_by=created_by,
            status=NotificationBatch.Status.DRAFT,
        )
        logger.info("NotificationBatch created: id=%s title=%s", batch.batch_id, title)
        return batch

    @staticmethod
    @transaction.atomic
    def schedule_batch(*, batch_id: str) -> NotificationBatch:
        """
        Transition batch from DRAFT → SCHEDULED (or SENDING if immediate).
        Enqueues the fan-out Celery task after commit.
        """
        batch = NotificationBatch.objects.select_for_update().get(batch_id=batch_id)
        if batch.status != NotificationBatch.Status.DRAFT:
            raise ValueError(f"Batch {batch_id} is not in DRAFT status (current: {batch.status})")

        is_immediate = batch.scheduled_at is None
        batch.status = (
            NotificationBatch.Status.SENDING if is_immediate
            else NotificationBatch.Status.SCHEDULED
        )
        batch.save(update_fields=["status", "updated_at"])

        _batch_id = str(batch.batch_id)

        def _enqueue():
            try:
                from apps.notification.tasks import fan_out_batch_task
                fan_out_batch_task.delay(_batch_id)
            except Exception:
                logger.warning("fan_out_batch_task enqueue failed for batch=%s", _batch_id, exc_info=True)

        transaction.on_commit(_enqueue)
        logger.info("NotificationBatch scheduled: id=%s immediate=%s", batch_id, is_immediate)
        return batch

    @staticmethod
    @transaction.atomic
    def record_batch_progress(
        *,
        batch_id: str,
        sent_delta: int = 0,
        failed_delta: int = 0,
    ) -> None:
        """
        Atomically increment sent/failed counters on a batch.
        Called by the fan-out Celery task after each chunk is processed.
        Uses select_for_update() to prevent concurrent worker race conditions.
        """
        batch = NotificationBatch.objects.select_for_update().get(batch_id=batch_id)
        batch.sent_count += sent_delta
        batch.failed_count += failed_delta
        batch.save(update_fields=["sent_count", "failed_count", "updated_at"])

    @staticmethod
    @transaction.atomic
    def complete_batch(*, batch_id: str, total_count: int) -> NotificationBatch:
        """
        Mark a batch as COMPLETED (or FAILED if all messages failed).
        Called by the fan-out task when all recipients have been processed.
        """
        batch = NotificationBatch.objects.select_for_update().get(batch_id=batch_id)
        batch.total_count = total_count
        batch.completed_at = timezone.now()
        batch.status = (
            NotificationBatch.Status.FAILED
            if batch.sent_count == 0 and total_count > 0
            else NotificationBatch.Status.COMPLETED
        )
        batch.save(update_fields=["total_count", "completed_at", "status", "updated_at"])
        logger.info(
            "NotificationBatch complete: id=%s status=%s sent=%d failed=%d total=%d",
            batch_id, batch.status, batch.sent_count, batch.failed_count, total_count,
        )
        return batch

    @staticmethod
    @transaction.atomic
    def cancel_batch(*, batch_id: str) -> NotificationBatch:
        """
        Cancel a DRAFT or SCHEDULED batch. Cannot cancel a SENDING or COMPLETED batch.
        """
        batch = NotificationBatch.objects.select_for_update().get(batch_id=batch_id)
        if batch.status not in (
            NotificationBatch.Status.DRAFT, NotificationBatch.Status.SCHEDULED
        ):
            raise ValueError(
                f"Cannot cancel batch {batch_id} with status={batch.status}. "
                "Only DRAFT and SCHEDULED batches can be cancelled."
            )
        batch.status = NotificationBatch.Status.CANCELLED
        batch.save(update_fields=["status", "updated_at"])
        logger.info("NotificationBatch cancelled: id=%s", batch_id)
        return batch


# ─────────────────────────────────────────────────────────────────────────────
# READ RECEIPT SERVICE
# ─────────────────────────────────────────────────────────────────────────────


class ReadReceiptService:
    """
    Creates read receipts for multi-device notification read tracking.
    Decoupled from the core Notification.read_at field.
    """

    @staticmethod
    @transaction.atomic
    def mark_read(
        *,
        notification,
        user,
        device_id: str = "",
        client_ip: str | None = None,
    ) -> NotificationReadReceipt:
        """
        Create a read receipt for the notification.
        Idempotent: update_or_create keyed on (notification, user, device_id).

        Args:
            notification: The Notification instance being read.
            user: The user who read it.
            device_id: Client device fingerprint (optional).
            client_ip: Client IP for geo-analytics (anonymized after 30 days).

        Returns:
            The created or existing NotificationReadReceipt.
        """
        now = timezone.now()
        receipt, created = NotificationReadReceipt.objects.update_or_create(
            notification=notification,
            user=user,
            device_id=device_id,
            defaults={"read_at": now, "client_ip": client_ip},
        )
        if created:
            logger.debug(
                "ReadReceipt created: notif=%s user=%s device=%s",
                notification.id, user.id, device_id[:12] if device_id else "—",
            )
        return receipt

    @staticmethod
    def anonymize_old_ips(*, days: int = 30) -> int:
        """
        Nullify client_ip on read receipts older than `days` days.
        GDPR data minimisation. Called by weekly compliance task.

        Returns:
            Count of receipts anonymized.
        """
        cutoff = timezone.now() - timezone.timedelta(days=days)
        count = NotificationReadReceipt.objects.filter(
            read_at__lt=cutoff,
            client_ip__isnull=False,
        ).update(client_ip=None)
        logger.info("ReadReceipt IPs anonymized: count=%d cutoff=%s", count, cutoff.date())
        return count
