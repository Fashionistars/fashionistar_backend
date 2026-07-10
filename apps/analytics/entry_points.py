"""
AI Engine Entry Points for Analytics Integration.

This module provides a single, controlled access point for analytics
to use AI engines from apps/ai. This maintains clean separation:
- apps/ai: AI orchestration and engines (no analytics endpoints)
- apps/analytics: Analytics dashboards and insights (imports AI via entry points)

Constraints:
    - Only LLM insights are imported here for analytics-specific use.
    - RecommendationEngine, MeasurementEngine, and their endpoints/workflows
      remain inside apps/ai and are NEVER moved/copied to apps/analytics.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def get_llm_engine() -> Optional[object]:
    """
    Get the best available LLM engine for analytics insights.

    Returns:
        LLM engine instance if available, None otherwise.
    """
    try:
        from apps.ai.engines.llm_engine import get_llm_engine as _get_ai_llm_engine

        engine = _get_ai_llm_engine()
        if engine and engine.is_available():
            logger.info("LLM engine available for analytics")
            return engine
        logger.warning("LLM engine unavailable for analytics")
        return None
    except Exception as exc:  # noqa: BLE001
        logger.error("Error getting LLM engine for analytics: %s", exc)
        return None


def generate_llm_insights(
    metrics_summary: str,
    anomalies: List[Dict[str, Any]],
    max_tokens: int = 400,
) -> str:
    """
    Generate LLM-powered insights from analytics metrics.

    Args:
        metrics_summary: Condensed metrics summary string.
        anomalies: List of detected anomalies.
        max_tokens: Maximum tokens for LLM generation.

    Returns:
        Generated insights string (empty if LLM unavailable).
    """
    engine = get_llm_engine()
    if not engine:
        logger.warning("Cannot generate LLM insights: engine unavailable")
        return ""

    prompt = f"""
You are FASHIONISTAR's AI analytics engine. Analyze the following platform metrics
and provide 3 concise, actionable business insights for the operations team.
Format: bullet points, max 2 sentences each.

METRICS SUMMARY:
{metrics_summary}

ANOMALIES DETECTED: {len(anomalies)}
{_format_anomalies(anomalies)}

Provide your insights:
""".strip()

    try:
        system = (
            "You are FASHIONISTAR's AI analytics engine. Analyze platform metrics "
            "and provide concise, actionable business insights."
        )
        insights = engine.generate(system=system, prompt=prompt, max_tokens=max_tokens)
        logger.info("Generated LLM insights (%d chars)", len(insights))
        return insights
    except Exception as exc:  # noqa: BLE001
        logger.error("Error generating LLM insights: %s", exc)
        return ""


def _format_anomalies(anomalies: List[Dict[str, Any]]) -> str:
    """Format anomalies for LLM prompt."""
    if not anomalies:
        return "None detected."
    return "\n".join(
        f"[{a.get('severity', 'INFO')}] {a.get('type', 'UNKNOWN')}: {a.get('message', '')}"
        for a in anomalies
    )
