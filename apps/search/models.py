"""
مدل‌های اپلیکیشن جستجو
Search app models (compatible with MySQL FULLTEXT and sqlite fallback)
"""

from __future__ import annotations

import json
from django.db import models
from django.contrib.auth import get_user_model


User = get_user_model()


class SearchableContent(models.Model):
    """
    ایندکس محتوای قابل جستجو برای FULLTEXT (MySQL) یا جستجوی ساده در sqlite.
    """

    CONTENT_TYPE_CHOICES = [
        ("encounter", "Encounter"),
        ("transcript", "Transcript"),
        ("soap", "SOAP Note"),
        ("checklist", "Checklist"),
        ("notes", "Clinical Notes"),
    ]

    # توجه: مدل encounters.Encounter ممکن است در این پروژه موجود نباشد.
    # برای جلوگیری از وابستگی سخت، از ForeignKey به رشته استفاده می‌کنیم.
    encounter = models.ForeignKey(
        "encounters.Encounter",
        on_delete=models.CASCADE,
        related_name="search_content",
        null=True,
        blank=True,
    )
    content_type = models.CharField(max_length=20, choices=CONTENT_TYPE_CHOICES)
    content_id = models.PositiveIntegerField()
    title = models.CharField(max_length=200)
    content = models.TextField()

    # به‌جای SearchVectorField (Postgres)، متن کمکی برای ایندکس
    search_vector = models.TextField(null=True, blank=True)

    metadata = models.JSONField(default=dict)
    metadata_text = models.TextField(blank=True, default="")

    # ستون fulltext_all در مهاجرت 0002 برای MySQL ساخته می‌شود (Generated column)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["encounter", "content_type"]),
            models.Index(fields=["content_type", "content_id"]),
            models.Index(fields=["created_at"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["encounter", "content_type", "content_id"],
                name="uniq_search_encounter_contenttype_contentid",
            ),
        ]
        verbose_name = "محتوای قابل جستجو"
        verbose_name_plural = "محتوای قابل جستجو"

    def __str__(self) -> str:
        return f"{self.content_type}:{self.content_id} - {self.title}"

    def save(self, *args, **kwargs) -> None:
        """
        تولید metadata_text از فیلد JSON برای استفاده در fulltext_all
        """
        try:
            self.metadata_text = json.dumps(self.metadata, ensure_ascii=False, separators=(", ", ": "))
        except Exception:
            self.metadata_text = ""
        super().save(*args, **kwargs)


class SearchQuery(models.Model):
    """
    نگهداری کوئری‌های جستجو برای آنالیتیکس و کش نتایج
    """

    query_text = models.TextField()
    filters = models.JSONField(default=dict)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    results_count = models.PositiveIntegerField(default=0)
    execution_time_ms = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["user", "created_at"]),
            models.Index(fields=["created_at"]),
        ]
        verbose_name = "کوئری جستجو"
        verbose_name_plural = "کوئری‌های جستجو"

    def __str__(self) -> str:
        return f"Search: {self.query_text[:50]}..."


class SearchResult(models.Model):
    """
    نتایج کش شده برای هر کوئری
    """

    query = models.ForeignKey(SearchQuery, on_delete=models.CASCADE, related_name="cached_results")
    content = models.ForeignKey(SearchableContent, on_delete=models.CASCADE)
    relevance_score = models.FloatField()
    rank = models.PositiveIntegerField()
    snippet = models.TextField()

    class Meta:
        indexes = [
            models.Index(fields=["query", "rank"]),
            models.Index(fields=["relevance_score"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["query", "content"], name="uniq_query_content"
            ),
        ]
        ordering = ["rank"]
        verbose_name = "نتیجه جستجو"
        verbose_name_plural = "نتایج جستجو"

    def __str__(self) -> str:
        return f"Result {self.rank} for query {self.query.id}"

