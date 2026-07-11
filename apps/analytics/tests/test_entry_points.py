"""
Unit tests for apps.analytics.entry_points.

Verifies that analytics accesses AI engines only through the controlled entry
point and that no recommendation/measurement engines are exposed.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from apps.analytics.entry_points import generate_llm_insights, get_llm_engine


def test_get_llm_engine_returns_engine_when_available():
    """get_llm_engine should return the engine when the AI engine is available."""
    mock_engine = MagicMock()
    mock_engine.is_available.return_value = True

    with patch(
        "apps.ai.engines.llm_engine.get_llm_engine",
        return_value=mock_engine,
    ):
        engine = get_llm_engine()

    assert engine is mock_engine


def test_get_llm_engine_returns_none_when_unavailable():
    """get_llm_engine should return None when the AI engine is unavailable."""
    mock_engine = MagicMock()
    mock_engine.is_available.return_value = False

    with patch(
        "apps.ai.engines.llm_engine.get_llm_engine",
        return_value=mock_engine,
    ):
        engine = get_llm_engine()

    assert engine is None


def test_generate_llm_insights_returns_empty_when_engine_unavailable():
    """generate_llm_insights should return empty string when LLM is unavailable."""
    with patch("apps.analytics.entry_points.get_llm_engine", return_value=None):
        result = generate_llm_insights(metrics_summary="summary", anomalies=[])

    assert result == ""


def test_generate_llm_insights_calls_engine_generate():
    """generate_llm_insights should call engine.generate with correct arguments."""
    mock_engine = MagicMock()
    mock_engine.generate.return_value = "Insight text"

    with patch(
        "apps.analytics.entry_points.get_llm_engine", return_value=mock_engine
    ):
        result = generate_llm_insights(
            metrics_summary="Total GMV: 1000",
            anomalies=[{"severity": "CRITICAL", "type": "GMV_DROP", "message": "Drop"}],
            max_tokens=400,
        )

    assert result == "Insight text"
    mock_engine.generate.assert_called_once()
    call_kwargs = mock_engine.generate.call_args.kwargs
    assert "system" in call_kwargs
    assert "prompt" in call_kwargs
    assert call_kwargs["max_tokens"] == 400


def test_entry_points_does_not_expose_recommendation_or_measurement_engines():
    """The entry_points module must not import or expose recommendation/measurement engines."""
    import apps.analytics.entry_points as entry_points

    public_names = {name for name in dir(entry_points) if not name.startswith("_")}
    assert "get_recommendation_engine" not in public_names
    assert "get_measurement_engine" not in public_names
