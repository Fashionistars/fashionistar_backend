# apps/ai/admin.py
"""
Django Admin registrations for the AI Orchestration Engine.

Provides operational visibility into:
  - WorkflowExecution: audit of all AI workflow runs (measurement, recommendation, analytics)
  - ProductEmbedding: vector embeddings generated for each product
  - DBChangeEvent: log of model-save events that triggered AI ingestion

All models are read-only in admin (no edits — AI data is generated, not manually entered).
"""

from django.contrib import admin
from django.utils.html import format_html


# ── WorkflowExecution ─────────────────────────────────────────────────────────

@admin.register(*[])   # Registered conditionally below
class WorkflowExecutionAdmin(admin.ModelAdmin):
    list_display = [
        "id", "workflow_type", "status_badge", "user",
        "duration_ms", "model_version", "started_at", "completed_at",
    ]
    list_filter = ["workflow_type", "status", "model_version"]
    search_fields = ["user__email", "celery_task_id", "id"]
    readonly_fields = [
        "id", "workflow_type", "status", "user", "input_snapshot",
        "output_snapshot", "error_detail", "model_version",
        "celery_task_id", "duration_ms", "started_at", "completed_at",
        "created_at", "updated_at",
    ]
    ordering = ["-started_at"]
    date_hierarchy = "started_at"
    list_per_page = 50

    def status_badge(self, obj):
        colours = {
            "running":   "#3b82f6",  # Blue
            "completed": "#22c55e",  # Green
            "failed":    "#ef4444",  # Red
        }
        colour = colours.get(obj.status, "#6b7280")
        return format_html(
            '<span style="background:{};color:white;padding:2px 8px;border-radius:4px">{}</span>',
            colour,
            obj.status.upper(),
        )
    status_badge.short_description = "Status"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


# ── ProductEmbedding ──────────────────────────────────────────────────────────

@admin.register(*[])
class ProductEmbeddingAdmin(admin.ModelAdmin):
    list_display = [
        "product", "model_version", "has_text_vector",
        "has_image_vector", "has_combined_vector", "created_at", "updated_at",
    ]
    list_filter = ["model_version"]
    search_fields = ["product__name", "product__id"]
    readonly_fields = [
        "product", "model_version", "text_vector", "image_vector",
        "combined_vector", "created_at", "updated_at",
    ]
    ordering = ["-updated_at"]
    list_per_page = 50

    def has_text_vector(self, obj):
        has = obj.text_vector is not None and len(obj.text_vector) > 0
        return format_html(
            '<span style="color:{}">{}</span>',
            "#22c55e" if has else "#ef4444",
            "✓" if has else "✗",
        )
    has_text_vector.short_description = "Text Vec"

    def has_image_vector(self, obj):
        has = obj.image_vector is not None and len(obj.image_vector) > 0
        return format_html(
            '<span style="color:{}">{}</span>',
            "#22c55e" if has else "#6b7280",
            "✓" if has else "—",
        )
    has_image_vector.short_description = "Image Vec"

    def has_combined_vector(self, obj):
        has = obj.combined_vector is not None and len(obj.combined_vector) > 0
        return format_html(
            '<span style="color:{}">{}</span>',
            "#22c55e" if has else "#ef4444",
            "✓" if has else "✗",
        )
    has_combined_vector.short_description = "Combined Vec"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


# ── DBChangeEvent ──────────────────────────────────────────────────────────────

@admin.register(*[])
class DBChangeEventAdmin(admin.ModelAdmin):
    list_display = [
        "id", "app_label", "model_name", "object_id",
        "event_type", "is_processed", "processed_at", "created_at",
    ]
    list_filter = ["app_label", "event_type", "is_processed"]
    search_fields = ["object_id", "model_name"]
    readonly_fields = [
        "app_label", "model_name", "object_id", "event_type",
        "is_processed", "processed_at", "created_at", "updated_at",
    ]
    ordering = ["-created_at"]
    date_hierarchy = "created_at"
    list_per_page = 100

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


# ── Dynamic registration (models loaded after Django setup) ───────────────────

def _register_ai_admin():
    """
    Deferred admin registration to avoid AppRegistryNotReady.
    Called from AppConfig.ready() — safe after all apps are loaded.
    """
    try:
        from apps.ai.models import WorkflowExecution, ProductEmbedding, DBChangeEvent
        admin.site.register(WorkflowExecution, WorkflowExecutionAdmin)
        admin.site.register(ProductEmbedding, ProductEmbeddingAdmin)
        admin.site.register(DBChangeEvent, DBChangeEventAdmin)
    except Exception:
        pass


# Self-register when this module is imported during Django setup
try:
    from apps.ai.models import WorkflowExecution, ProductEmbedding, DBChangeEvent

    if not admin.site.is_registered(WorkflowExecution):
        admin.site.register(WorkflowExecution, WorkflowExecutionAdmin)
    if not admin.site.is_registered(ProductEmbedding):
        admin.site.register(ProductEmbedding, ProductEmbeddingAdmin)
    if not admin.site.is_registered(DBChangeEvent):
        admin.site.register(DBChangeEvent, DBChangeEventAdmin)
except Exception:
    pass
