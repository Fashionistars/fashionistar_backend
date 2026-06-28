# apps/measurements/migrations/0007_measurementprofile_ai_recommendation_fields.py
"""
Migration: Add AI recommendation snapshot fields to MeasurementProfile.

Fields added:
  - ai_recommendation_snapshot (JSONField, nullable)
      Stores the cached recommendation output from RecommendationWorkflow.
  - last_recommendation_at (DateTimeField, nullable)
      Timestamp of the last AI recommendation generation.

These fields are populated by:
  apps.ai.workflows.recommendation.RecommendationWorkflow._persist_recommendations()

They allow the recommendation endpoint to serve a snapshot directly from the
profile model without an extra cache lookup when Redis is unavailable.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("measurements", "0006_alter_bodyscansession_scan_provider"),
    ]

    operations = [
        migrations.AddField(
            model_name="measurementprofile",
            name="ai_recommendation_snapshot",
            field=models.JSONField(
                blank=True,
                default=None,
                null=True,
                help_text=(
                    "Latest AI product recommendations snapshot for this profile. "
                    "Auto-populated by the RecommendationWorkflow Celery task. "
                    "Schema: {recommendations: [...], generated_at: str, model_version: str}"
                ),
            ),
        ),
        migrations.AddField(
            model_name="measurementprofile",
            name="last_recommendation_at",
            field=models.DateTimeField(
                blank=True,
                default=None,
                null=True,
                help_text="Timestamp of the last AI recommendation generation for this profile.",
            ),
        ),
    ]
