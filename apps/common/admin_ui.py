from __future__ import annotations

import csv
from io import StringIO
from typing import Iterable

from django.contrib import admin
from django.http import HttpResponse
from django.urls import NoReverseMatch, reverse
from django.utils.html import format_html, format_html_join
from django.utils.translation import gettext_lazy as _


class FashionistarAdminUIMixin:
    """
    Shared presentation helpers for admin classes.

    Keeps repeated admin polish in one place without forcing every app to
    inherit a heavyweight custom ModelAdmin base.
    """

    empty_value_display = "-N/A-"
    admin_select_related: tuple[str, ...] = ()
    admin_prefetch_related: tuple[str, ...] = ()
    change_history_limit = 5

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if self.admin_select_related:
            qs = qs.select_related(*self.admin_select_related)
        if self.admin_prefetch_related:
            qs = qs.prefetch_related(*self.admin_prefetch_related)
        return qs

    @staticmethod
    def format_ngn(amount) -> str:
        try:
            value = float(amount or 0)
        except (TypeError, ValueError):
            value = 0
        return f"\u20a6{value:,.2f}"

    def render_status_badge(
        self,
        label: str,
        *,
        background: str = "#E5E7EB",
        foreground: str = "#111827",
    ):
        return format_html(
            '<span class="fsn-badge" style="background:{};color:{};">{}</span>',
            background,
            foreground,
            label,
        )

    def render_image_preview(
        self,
        url: str | None,
        *,
        alt: str = "Preview",
        size: int = 50,
    ):
        if not url:
            return self.empty_value_display
        return format_html(
            '<img src="{}" alt="{}" width="{}" height="{}" '
            'style="border-radius:10px;object-fit:cover;border:1px solid #E5E7EB;" />',
            url,
            alt,
            size,
            size,
        )

    @admin.display(description="Live Site")
    def live_site_link(self, obj):
        if hasattr(obj, "get_absolute_url"):
            try:
                return format_html(
                    '<a class="button" href="{}" target="_blank" rel="noopener">View on Live Site</a>',
                    obj.get_absolute_url(),
                )
            except Exception:
                return self.empty_value_display
        return self.empty_value_display

    @admin.display(description="Change History")
    def change_history_summary(self, obj):
        from apps.audit_logs.models import AuditEventLog

        entries = (
            AuditEventLog.objects.filter(
                resource_type=obj.__class__.__name__,
                resource_id=str(obj.pk),
            )
            .select_related("actor")
            .order_by("-created_at")[: self.change_history_limit]
        )
        if not entries:
            return self.empty_value_display

        return format_html(
            '<div class="fsn-history-summary"><ul>{}</ul></div>',
            format_html_join(
                "",
                "<li><strong>{}</strong> · {} · {}</li>",
                (
                    (
                        entry.action,
                        getattr(entry.actor, "email", "System"),
                        entry.created_at.strftime("%d %b %Y %H:%M"),
                    )
                    for entry in entries
                ),
            ),
        )


class ReadOnlyForNonSuperusersMixin:
    """
    Appends fields to readonly mode for non-superusers.
    """

    non_superuser_readonly_fields: tuple[str, ...] = ()

    def get_readonly_fields(self, request, obj=None):
        base = list(super().get_readonly_fields(request, obj))
        if request.user.is_superuser:
            return tuple(base)
        return tuple(dict.fromkeys([*base, *self.non_superuser_readonly_fields]))


class CSVExportAdminMixin:
    """
    Small shared CSV export action for admin changelists.
    """

    export_fields: tuple[str, ...] = ()

    @admin.action(description=_("Export selected to CSV"))
    def export_selected_to_csv(self, request, queryset):
        fields = self.export_fields or tuple(
            field.name
            for field in queryset.model._meta.fields
        )
        buffer = StringIO()
        writer = csv.writer(buffer)
        writer.writerow(fields)
        for obj in queryset.iterator(chunk_size=500):
            writer.writerow([self._resolve_export_value(obj, field) for field in fields])

        response = HttpResponse(buffer.getvalue(), content_type="text/csv")
        response["Content-Disposition"] = (
            f'attachment; filename="{queryset.model._meta.model_name}-export.csv"'
        )
        return response

    def _resolve_export_value(self, obj, field_name: str):
        value = obj
        for chunk in field_name.split("__"):
            value = getattr(value, chunk, None)
            if value is None:
                return ""
        if callable(value):
            try:
                value = value()
            except TypeError:
                return ""
        return value
