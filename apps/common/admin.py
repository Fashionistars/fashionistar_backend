# apps/common/admin.py
"""
Admin registrations for shared ``apps.common`` models.

Registers:
    - DeletedRecords: Read-only archive of all soft-deleted
      records from any model that inherits SoftDeleteModel.
      Searchable by model name and record ID, filterable by
      deletion date.
"""

import json

from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from apps.common.models import DeletedRecords


@admin.register(DeletedRecords)
class DeletedRecordsAdmin(admin.ModelAdmin):
    """
    Read-only admin for the global soft-delete archive.

    Each row represents a snapshot of a model instance at
    the moment of its soft-deletion. No records can be
    modified or re-deleted here — this is purely an audit
    and forensic view.

    Features:
        - Search by model_name, record_id.
        - Filter by model_name, deleted_at date.
        - Pretty-printed JSON data preview.
        - Date hierarchy for temporal browsing.
        - All fields are read-only — no accidental edits.
    """

    list_display = (
        'model_name',
        'record_id',
        'deleted_at',
    )
    list_filter = (
        'model_name',
        'deleted_at',
    )
    search_fields = (
        'model_name',
        'record_id',
    )
    readonly_fields = (
        'model_name',
        'record_id',
        'deleted_at',
        'data_pretty',
    )
    date_hierarchy = 'deleted_at'
    ordering = ('-deleted_at',)

    # Exclude the raw data field — replaced by data_pretty
    exclude = ('data',)

    def data_pretty(self, obj):
        """
        Render archived JSON data as indented, coloured HTML.

        Args:
            obj: The DeletedRecords instance.

        Returns:
            str: Safe HTML ``<pre>`` block with the JSON.
        """
        try:
            pretty = json.dumps(obj.data, indent=2, default=str)
        except Exception:
            pretty = str(obj.data)

        return format_html(
            '<pre style="'
            'background:#1e1e1e;color:#d4d4d4;'
            'padding:12px;border-radius:6px;'
            'font-size:12px;max-height:400px;'
            'overflow:auto;white-space:pre-wrap;'
            '">{}</pre>',
            pretty,
        )

    data_pretty.short_description = _('Archived Data (JSON)')

    def has_add_permission(self, request):
        """Prevent manual creation — records are auto-archived."""
        return False

    def has_change_permission(self, request, obj=None):
        """Prevent edits — this is a forensic audit table."""
        return False

    def has_delete_permission(self, request, obj=None):
        """
        Only superusers may purge archive entries.

        Restricts deletion to superusers only — regular staff
        should NOT be able to erase the audit trail.
        """
        return request.user.is_superuser
