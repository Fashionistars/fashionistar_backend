# apps/ai/tests/test_zerogpu_smoke.py
"""ZeroGPU model loading smoke tests.

These are lightweight, pre-merge sanity checks that exercise the HF Space
AI engine loading path without downloading weights or requiring a GPU.
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# The HF Space engine is not a package under apps/ai; it lives in
# deploy/huggingface-ai-engine.  Insert that directory onto sys.path so the
# module can be imported by filename.
_DEPLOY_AI_ENGINE = Path(__file__).resolve().parents[3] / "deploy" / "huggingface-ai-engine"
sys.path.insert(0, str(_DEPLOY_AI_ENGINE))

import zerogpu_engine


@pytest.mark.smoke
def test_siglip_loads_via_open_clip():
    """_load_siglip() must use open_clip and move the model to CUDA.

    This is a mock-only test: it validates the open_clip loading path and
    catches the meta-tensor / ``AutoModel.get_image_features`` style of
    failures that broke the HF Space before PR #24/25.
    """
    mock_model = MagicMock()
    mock_model.to.return_value = mock_model
    mock_processor = MagicMock()

    with patch("open_clip.create_model_and_transforms", return_value=(mock_model, None, mock_processor)):
        assert zerogpu_engine._load_siglip() is True

    mock_model.to.assert_called_once_with("cuda")
    mock_model.eval.assert_called_once()
    assert zerogpu_engine._siglip_model is mock_model
    assert zerogpu_engine._siglip_processor is mock_processor
