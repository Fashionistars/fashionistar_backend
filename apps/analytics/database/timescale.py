"""
apps/analytics/database/timescale.py
=====================================
TimescaleDB integration for high-volume time-series analytics data.

Provides:
  - Hypertable creation for Metric and PerformanceMetric
  - Native retention policies via TimescaleDB
  - Chunk time interval configuration
  - Compression settings for historical data

Note: TimescaleDB extension must be enabled in PostgreSQL before use.
This module gracefully degrades to standard PostgreSQL when TimescaleDB
is not available.
"""

from __future__ import annotations

import logging

from django.db import connection

logger = logging.getLogger(__name__)


class TimescaleDB:
    """
    TimescaleDB integration manager for analytics time-series data.

    All methods check for TimescaleDB availability and gracefully
    degrade to standard PostgreSQL when the extension is not present.
    """

    # Chunk time intervals (optimized for query patterns)
    METRIC_CHUNK_INTERVAL = "1 day"
    PERFORMANCE_CHUNK_INTERVAL = "1 day"

    # Compression settings
    COMPRESSION_AFTER_DAYS = 7

    # Retention settings (native TimescaleDB retention)
    METRIC_RETENTION_DAYS = 30
    PERFORMANCE_RETENTION_DAYS = 30

    @classmethod
    def is_available(cls) -> bool:
        """Check if TimescaleDB extension is installed."""
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT extversion FROM pg_extension WHERE extname = 'timescaledb';")
                result = cursor.fetchone()
                return result is not None
        except Exception:
            return False

    @classmethod
    def setup_hypertables(cls) -> dict[str, bool]:
        """
        Convert Metric and PerformanceMetric tables to hypertables.

        Returns:
            dict: Status of each hypertable creation.
        """
        if not cls.is_available():
            logger.warning("[TimescaleDB] Extension not available — skipping hypertable setup")
            return {"metric": False, "performance_metric": False, "reason": "extension_not_available"}

        results = {}

        # Metric hypertable
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT create_hypertable('analytics_metric', 'timestamp', "
                    "chunk_time_interval => INTERVAL '1 day', if_not_exists => TRUE);"
                )
                results["metric"] = True
                logger.info("[TimescaleDB] Metric hypertable created/confirmed")
        except Exception as exc:
            logger.error("[TimescaleDB] Metric hypertable creation failed: %s", exc)
            results["metric"] = False

        # PerformanceMetric hypertable
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT create_hypertable('analytics_performancemetric', 'timestamp', "
                    "chunk_time_interval => INTERVAL '1 day', if_not_exists => TRUE);"
                )
                results["performance_metric"] = True
                logger.info("[TimescaleDB] PerformanceMetric hypertable created/confirmed")
        except Exception as exc:
            logger.error("[TimescaleDB] PerformanceMetric hypertable creation failed: %s", exc)
            results["performance_metric"] = False

        # Enable compression
        if results.get("metric"):
            cls._enable_compression("analytics_metric")
        if results.get("performance_metric"):
            cls._enable_compression("analytics_performancemetric")

        return results

    @classmethod
    def _enable_compression(cls, table_name: str) -> bool:
        """Enable TimescaleDB compression on a hypertable."""
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"ALTER TABLE {table_name} SET ("
                    f"timescaledb.compress, "
                    f"timescaledb.compress_segmentby = 'name', "
                    f"timescaledb.compress_orderby = 'timestamp DESC'"
                    f");"
                )
                cursor.execute(
                    f"SELECT add_compression_policy('{table_name}', INTERVAL '{cls.COMPRESSION_AFTER_DAYS} days');"
                )
                logger.info("[TimescaleDB] Compression enabled for %s", table_name)
                return True
        except Exception as exc:
            logger.error("[TimescaleDB] Compression setup failed for %s: %s", table_name, exc)
            return False

    @classmethod
    def add_retention_policy(cls, table_name: str, retention_days: int) -> bool:
        """
        Add a native TimescaleDB retention policy to a hypertable.

        Args:
            table_name: Name of the hypertable.
            retention_days: Number of days to retain data.

        Returns:
            bool: True if policy was added successfully.
        """
        if not cls.is_available():
            return False

        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"SELECT add_retention_policy('{table_name}', INTERVAL '{retention_days} days');"
                )
                logger.info("[TimescaleDB] Retention policy added for %s (%d days)", table_name, retention_days)
                return True
        except Exception as exc:
            logger.error("[TimescaleDB] Retention policy failed for %s: %s", table_name, exc)
            return False

    @classmethod
    def get_chunk_stats(cls) -> dict:
        """
        Get statistics about TimescaleDB chunks.

        Returns:
            dict: Chunk count, total size, and compression stats.
        """
        if not cls.is_available():
            return {"available": False}

        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT count(*), "
                    "pg_size_pretty(sum(hypertable_size(h.id))) as total_size, "
                    "count(*) FILTER (WHERE h.compressed_hypertable_id IS NOT NULL) as compressed_chunks "
                    "FROM timescaledb_information.chunks c "
                    "JOIN timescaledb_information.hypertables h ON c.hypertable_name = h.hypertable_name;"
                )
                row = cursor.fetchone()
                return {
                    "available": True,
                    "total_chunks": row[0],
                    "total_size": row[1],
                    "compressed_chunks": row[2],
                }
        except Exception as exc:
            logger.error("[TimescaleDB] Chunk stats failed: %s", exc)
            return {"available": True, "error": str(exc)}
