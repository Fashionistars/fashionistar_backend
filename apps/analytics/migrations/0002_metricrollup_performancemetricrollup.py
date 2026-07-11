"""
Migration: Add MetricRollup and PerformanceMetricRollup models.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("analytics", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="MetricRollup",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("name", models.CharField(max_length=255, verbose_name="Metric Name")),
                (
                    "metric_type",
                    models.CharField(default="gauge", max_length=20, verbose_name="Metric Type"),
                ),
                (
                    "window",
                    models.CharField(
                        choices=[("1m", "1 Minute"), ("5m", "5 Minutes"), ("1h", "1 Hour"), ("1d", "1 Day")],
                        max_length=5,
                        verbose_name="Aggregation Window",
                    ),
                ),
                (
                    "timestamp",
                    models.DateTimeField(verbose_name="Window Start Timestamp"),
                ),
                ("avg", models.FloatField(default=0, verbose_name="Average Value")),
                ("min", models.FloatField(default=0, verbose_name="Minimum Value")),
                ("max", models.FloatField(default=0, verbose_name="Maximum Value")),
                (
                    "count",
                    models.PositiveIntegerField(default=0, verbose_name="Sample Count"),
                ),
                ("sum", models.FloatField(default=0, verbose_name="Sum of Values")),
            ],
            options={
                "verbose_name": "Metric Rollup",
                "verbose_name_plural": "Metric Rollups",
                "ordering": ["-timestamp"],
                "unique_together": {("name", "metric_type", "window", "timestamp")},
            },
        ),
        migrations.CreateModel(
            name="PerformanceMetricRollup",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("endpoint", models.CharField(max_length=255, verbose_name="Endpoint Route")),
                ("method", models.CharField(default="GET", max_length=10, verbose_name="HTTP Method")),
                (
                    "window",
                    models.CharField(
                        choices=[("1m", "1 Minute"), ("5m", "5 Minutes"), ("1h", "1 Hour"), ("1d", "1 Day")],
                        max_length=5,
                        verbose_name="Aggregation Window",
                    ),
                ),
                (
                    "timestamp",
                    models.DateTimeField(verbose_name="Window Start Timestamp"),
                ),
                (
                    "avg_response_time",
                    models.FloatField(default=0, verbose_name="Average Response Time (ms)"),
                ),
                (
                    "max_response_time",
                    models.PositiveIntegerField(default=0, verbose_name="Max Response Time (ms)"),
                ),
                (
                    "error_count",
                    models.PositiveIntegerField(default=0, verbose_name="Error Count (non-2xx)"),
                ),
                ("total", models.PositiveIntegerField(default=0, verbose_name="Total Requests")),
            ],
            options={
                "verbose_name": "Performance Metric Rollup",
                "verbose_name_plural": "Performance Metric Rollups",
                "ordering": ["-timestamp"],
                "unique_together": {("endpoint", "method", "window", "timestamp")},
            },
        ),
        migrations.AddIndex(
            model_name="metricrollup",
            index=models.Index(
                fields=["name", "window", "timestamp"],
                name="analytics_met_name_wind_timestamp_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="metricrollup",
            index=models.Index(
                fields=["window", "timestamp"],
                name="analytics_met_wind_timestamp_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="performancemetricrollup",
            index=models.Index(
                fields=["endpoint", "window", "timestamp"],
                name="analytics_per_endp_wind_timestamp_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="performancemetricrollup",
            index=models.Index(
                fields=["window", "timestamp"],
                name="analytics_per_wind_timestamp_idx",
            ),
        ),
    ]
