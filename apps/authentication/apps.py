# apps/authentication/apps.py
from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class AuthenticationConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.authentication'
    verbose_name = _("Identity Access Management")

    def ready(self):
        try:
            import apps.authentication.signals  # noqa: F401
        except ImportError:
            pass

        # ── django-auditlog: register authentication models ─────────────────
        # ORM-level audit trail — every save/delete is captured as a LogEntry.
        # Password and last_login are excluded for security.
        try:
            from auditlog.registry import auditlog
            from apps.authentication.models import UnifiedUser, LoginEvent, UserSession, ClientProfile

            auditlog.register(
                UnifiedUser,
                exclude_fields=['password', 'last_login'],
            )
            auditlog.register(LoginEvent)
            auditlog.register(UserSession, exclude_fields=['jti', 'fingerprint_hash'])
            auditlog.register(ClientProfile)

        except Exception:
            import logging
            logging.getLogger('application').debug(
                "django-auditlog authentication registration skipped"
            )

        # ── Admin login attempt capture ──────────────────────────────────────
        # Catch django.contrib.admin.site login via user_logged_in / user_login_failed
        # signals so all hits to /admin/ are recorded in AuditEventLog.
        # NOTE: The correct Django signal name is `user_login_failed` (NOT `user_logged_failed`)
        try:
            from django.contrib.auth.signals import user_logged_in, user_login_failed
            from django.dispatch import receiver

            @receiver(user_logged_in)
            def _on_admin_login(sender, request, user, **kwargs):
                """Capture successful logins from the Django admin panel."""
                try:
                    if not request or not getattr(request, 'path', '').startswith('/admin'):
                        return
                    from apps.audit_logs.services.audit import AuditService
                    from apps.audit_logs.models import EventType, EventCategory, SeverityLevel
                    AuditService.log(
                        event_type=EventType.LOGIN_SUCCESS,
                        event_category=EventCategory.SECURITY,
                        severity=SeverityLevel.INFO,
                        action=f"Admin panel login: {getattr(user, 'email', user)}",
                        request=request,
                        actor=user,
                        resource_type="UnifiedUser",
                        resource_id=str(user.pk),
                        metadata={"admin_login": True, "path": request.path},
                        is_compliance=True,
                    )
                except Exception:
                    pass

            @receiver(user_login_failed)
            def _on_admin_login_failed(sender, credentials, request, **kwargs):
                """Capture failed login attempts on the Django admin panel."""
                try:
                    if not request or not getattr(request, 'path', '').startswith('/admin'):
                        return
                    from apps.audit_logs.services.audit import AuditService
                    from apps.audit_logs.models import EventType, EventCategory, SeverityLevel
                    # Redact the actual password from credentials before logging
                    safe_credentials = {
                        k: v for k, v in (credentials or {}).items()
                        if k not in ('password', 'passwd', 'secret')
                    }
                    AuditService.log(
                        event_type=EventType.LOGIN_FAILED,
                        event_category=EventCategory.SECURITY,
                        severity=SeverityLevel.WARNING,
                        action="Admin panel login FAILED — invalid credentials",
                        request=request,
                        metadata={
                            "admin_login_failed": True,
                            "path": request.path,
                            "credentials_hint": safe_credentials,
                        },
                        error_message="Admin login failed",
                        is_compliance=True,
                    )
                except Exception:
                    pass

        except Exception:
            import logging
            logging.getLogger('application').warning(
                "Admin login signal wiring skipped"
            )
