# apps/measurements/migrations/0008_add_ai_engine_version_and_scan_confidence.py
"""
Migration: Rec 6 + Rec 7 — AI Engine Provenance Fields

Adds to MeasurementProfile:
  - ai_engine_version (CharField): tracks which engine version produced the measurements
    for A/B testing and quality audits.
  - ai_scan_confidence (FloatField): MediaPipe pose confidence at scan time (0.0-1.0).
    Only profiles above MEASUREMENT_MIN_CONFIDENCE (default: 0.65) are stored.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("measurements", "0007_measurementprofile_ai_recommendation_fields"),
    ]

    operations = [
        # Rec 6 -- AI Engine Version tracking
        migrations.AddField(
            model_name="measurementprofile",
            name="ai_engine_version",
            field=models.CharField(
                blank=True,
                default="",
                help_text=(
                    "AI engine version that produced these measurements. "
                    "Format: <major>.<minor>.<patch>-<provider> (e.g. '3.0.0-zerogpu'). "
                    "Used for A/B testing and quality audits."
                ),
                max_length=64,
                verbose_name="AI Engine Version",
            ),
        ),
        # Rec 7 -- Scan Confidence score storage
        migrations.AddField(
            model_name="measurementprofile",
            name="ai_scan_confidence",
            field=models.FloatField(
                blank=True,
                default=None,
                null=True,
                help_text=(
                    "MediaPipe pose confidence score (0.0-1.0) at scan time. "
                    "Profiles below MEASUREMENT_MIN_CONFIDENCE (default: 0.65) "
                    "are rejected and never stored."
                ),
                verbose_name="Scan Confidence",
            ),
        ),
    ]
