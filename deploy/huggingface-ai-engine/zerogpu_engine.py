# apps/ai/engines/zerogpu_engine.py
"""
ZeroGPU AI Engine — HF Spaces GPU Inference Module
====================================================

Hosts all GPU-intensive AI/ML inference for the FASHIONISTAR platform.
This module is imported by deploy/huggingface-ai-engine/app.py when running
on HF Spaces, and can also be called by Celery tasks that dispatch to the space.

ZeroGPU Architecture:
  - Models MUST be loaded at MODULE LEVEL onto 'cuda'
  - @spaces.GPU decorator requests a real A10G GPU for each function call
  - GPU is released after each call (ZeroGPU is shared, not persistent)
  - Never lazy-load inside @spaces.GPU — breaks CUDA tensor transfer

Models:
  - Body Pose:   MediaPipe Tasks PoseLandmarker (pose_landmarker_heavy.task)
  - Embeddings:  Marqo/marqo-FashionSigLIP-B-16 (512-dim, Apache 2.0)
  - LLM:         Groq API / Llama-3.3-70B-Versatile (if GROQ_API_KEY set)

External URL: https://fashionistar-fashionistar-ai-engine.hf.space
"""

from __future__ import annotations

import base64
import logging
import math
import os
import time
import urllib.request
from io import BytesIO
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

logger = logging.getLogger("fashionistar.zerogpu_engine")

# ── Constants ──────────────────────────────────────────────────────────────────
AI_ENGINE_VERSION = "3.0.0"

SIGLIP_MODEL_ID   = os.environ.get("SIGLIP_MODEL_ID",   "Marqo/marqo-FashionSigLIP-B-16")
SAMBANOVA_API_KEY = os.environ.get("SAMBANOVA_API_KEY",  "")
SAMBANOVA_MODEL   = os.environ.get("SAMBANOVA_MODEL",    "Meta-Llama-3.3-70B-Instruct")
CEREBRAS_API_KEY  = os.environ.get("CEREBRAS_API_KEY",   "")
CEREBRAS_MODEL    = os.environ.get("CEREBRAS_MODEL",     "llama-3.3-70b")
GROQ_API_KEY      = os.environ.get("GROQ_API_KEY",       "")
GROQ_MODEL        = os.environ.get("GROQ_MODEL",         "llama-3.3-70b-versatile")
HF_TOKEN          = os.environ.get("HF_TOKEN",           "")

_MP_MODEL_URL  = (
    "https://storage.googleapis.com/mediapipe-models/"
    "pose_landmarker/pose_landmarker_heavy/float16/latest/"
    "pose_landmarker_heavy.task"
)
_MP_MODEL_PATH = Path("/tmp/pose_landmarker_heavy.task")

# Active LLM provider (set by _get_llm_client)
_ACTIVE_LLM_PROVIDER = "none"



# ── ZeroGPU Decorator (no-op outside HF Spaces) ────────────────────────────────
try:
    import spaces  # noqa: F401
    _HAS_SPACES = True
    logger.info("Running inside HF Spaces — ZeroGPU available")
except ImportError:
    class _NoOpSpaces:
        def GPU(self, fn=None, duration=60):
            if fn is not None:
                return fn
            return lambda f: f
    spaces = _NoOpSpaces()  # type: ignore[assignment]
    _HAS_SPACES = False

# ── Module-level model handles ─────────────────────────────────────────────────
_pose_landmarker    = None
_siglip_model       = None
_siglip_processor   = None
_llm_client         = None   # active LLM client (SambaNova, Cerebras, or Groq)
_models_initialized = False


def _download_mediapipe_model() -> bool:
    """Download pose_landmarker_heavy.task if not cached."""
    if _MP_MODEL_PATH.exists() and _MP_MODEL_PATH.stat().st_size > 1_000_000:
        logger.info("MediaPipe model cached: %s", _MP_MODEL_PATH)
        return True
    logger.info("Downloading MediaPipe pose_landmarker_heavy.task (~4.7MB)...")
    try:
        urllib.request.urlretrieve(_MP_MODEL_URL, _MP_MODEL_PATH)
        logger.info("Downloaded: %.1f MB", _MP_MODEL_PATH.stat().st_size / 1e6)
        return True
    except Exception as exc:
        logger.warning("MediaPipe download failed: %s", exc)
        return False


def _load_mediapipe() -> bool:
    """Load MediaPipe Tasks PoseLandmarker (NEW API — replaces deprecated mp.solutions)."""
    global _pose_landmarker
    try:
        from mediapipe.tasks import python as mp_tasks
        from mediapipe.tasks.python import vision as mp_vision

        if not _download_mediapipe_model():
            return False

        base_options = mp_tasks.BaseOptions(model_asset_path=str(_MP_MODEL_PATH))
        options = mp_vision.PoseLandmarkerOptions(
            base_options=base_options,
            output_segmentation_masks=False,
            num_poses=1,
            min_pose_detection_confidence=0.5,
            min_pose_presence_confidence=0.5,
            min_tracking_confidence=0.5,
            running_mode=mp_vision.RunningMode.IMAGE,
        )
        _pose_landmarker = mp_vision.PoseLandmarker.create_from_options(options)
        logger.info("✅ MediaPipe PoseLandmarker (heavy) loaded via Tasks API")
        return True
    except Exception as exc:
        logger.warning("⚠️  MediaPipe load failed (non-fatal): %s", exc)
        return False


def _load_siglip() -> bool:
    """Load marqo-FashionSigLIP onto CUDA at module level (ZeroGPU requirement)."""
    global _siglip_model, _siglip_processor
    try:
        import torch
        from transformers import AutoModel, AutoProcessor

        logger.info("Loading %s ...", SIGLIP_MODEL_ID)
        _siglip_processor = AutoProcessor.from_pretrained(
            SIGLIP_MODEL_ID, token=HF_TOKEN or None,
        )
        _siglip_model = AutoModel.from_pretrained(
            SIGLIP_MODEL_ID,
            dtype=torch.float16,  # dtype= replaces deprecated torch_dtype=
            token=HF_TOKEN or None,
        )
        _siglip_model = _siglip_model.to("cuda")
        _siglip_model.eval()
        logger.info("✅ %s loaded on CUDA", SIGLIP_MODEL_ID)
        return True
    except Exception as exc:
        logger.warning("⚠️  SigLIP load failed (non-fatal): %s", exc)
        return False


def _get_llm_client():
    """
    Multi-provider LLM client — waterfall:
      1. SambaNova   (~4,000 tok/s)  — set SAMBANOVA_API_KEY
      2. Cerebras    (~2,000 tok/s)  — set CEREBRAS_API_KEY
      3. Groq        (~300   tok/s)  — set GROQ_API_KEY
    All use OpenAI-compatible interface.
    """
    global _llm_client, _ACTIVE_LLM_PROVIDER
    if _llm_client is not None:
        return _llm_client

    # 1. SambaNova (fastest, OpenAI-compatible)
    if SAMBANOVA_API_KEY:
        try:
            from openai import OpenAI
            _llm_client = OpenAI(
                api_key=SAMBANOVA_API_KEY,
                base_url="https://api.sambanova.ai/v1",
            )
            _ACTIVE_LLM_PROVIDER = f"sambanova/{SAMBANOVA_MODEL}"
            logger.info("✅ LLM: SambaNova (%s, ~4000 tok/s)", SAMBANOVA_MODEL)
            return _llm_client
        except Exception as exc:
            logger.warning("SambaNova client init failed: %s", exc)

    # 2. Cerebras (highest free throughput, OpenAI-compatible)
    if CEREBRAS_API_KEY:
        try:
            from openai import OpenAI
            _llm_client = OpenAI(
                api_key=CEREBRAS_API_KEY,
                base_url="https://api.cerebras.ai/v1",
            )
            _ACTIVE_LLM_PROVIDER = f"cerebras/{CEREBRAS_MODEL}"
            logger.info("✅ LLM: Cerebras (%s, ~2000 tok/s, 1M tok/day free)", CEREBRAS_MODEL)
            return _llm_client
        except Exception as exc:
            logger.warning("Cerebras client init failed: %s", exc)

    # 3. Groq (lowest latency per request)
    if GROQ_API_KEY:
        try:
            from groq import Groq
            _llm_client = Groq(api_key=GROQ_API_KEY)
            _ACTIVE_LLM_PROVIDER = f"groq/{GROQ_MODEL}"
            logger.info("✅ LLM: Groq (%s, ~300 tok/s)", GROQ_MODEL)
            return _llm_client
        except ImportError:
            logger.debug("groq package not installed")
        except Exception as exc:
            logger.warning("Groq client init failed: %s", exc)

    logger.warning("⚠️  No LLM API keys configured. Set SAMBANOVA_API_KEY, CEREBRAS_API_KEY, or GROQ_API_KEY.")
    return None


# Keep backward-compat alias
def _get_groq_client():
    return _get_llm_client()



def initialize_models() -> dict[str, bool]:
    """
    Load all models at startup (required BEFORE any @spaces.GPU call).
    Call this once at module level in app.py.
    """
    global _models_initialized
    results = {
        "mediapipe": _load_mediapipe(),
        "siglip":    _load_siglip(),
        "groq":      bool(GROQ_API_KEY),
    }
    _models_initialized = True
    _get_groq_client()  # warm up the Groq client connection
    logger.info(
        "AI Engine v%s ready — MediaPipe: %s  SigLIP: %s  Groq: %s",
        AI_ENGINE_VERSION,
        "✅" if results["mediapipe"] else "❌",
        "✅" if results["siglip"]    else "❌",
        "✅" if results["groq"]      else "❌ (no GROQ_API_KEY)",
    )
    return results


@spaces.GPU(duration=30)
def extract_body_measurements(image_b64: str, height_cm: float = 170.0) -> dict[str, Any]:
    """
    Extract body measurements from a base64-encoded image.
    Uses MediaPipe Tasks PoseLandmarker (NEW API — replaces deprecated mp.solutions).
    """
    if _pose_landmarker is None:
        return {"success": False, "error": "MediaPipe PoseLandmarker not available"}

    try:
        import mediapipe as mp

        img_bytes = base64.b64decode(image_b64)
        img_pil   = Image.open(BytesIO(img_bytes)).convert("RGB")
        img_array = np.array(img_pil, dtype=np.uint8)

        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=img_array)
        result   = _pose_landmarker.detect(mp_image)

        if not result.pose_world_landmarks:
            return {"success": False, "error": "No pose detected — ensure full body visible"}

        world_lms = result.pose_world_landmarks[0]
        landmarks = [
            {
                "x":          lm.x,
                "y":          lm.y,
                "z":          lm.z,
                "visibility": getattr(lm, "visibility", 1.0),
            }
            for lm in world_lms
        ]

        # Try Django engine first; fall back to inline geometry
        try:
            from apps.ai.engines.measurement_engine import MeasurementEngine
            geo = MeasurementEngine().process(landmarks=landmarks, user_height_cm=float(height_cm))
        except ImportError:
            geo = _inline_geometry(landmarks, float(height_cm))

        return {
            "success":       True,
            "measurements":  geo.get("measurements", {}),
            "confidence":    geo.get("quality_score", 0.0),
            "height_source": geo.get("height_source", "user_provided"),
            "model":         "mediapipe-tasks-pose-landmarker-heavy",
            "errors":        geo.get("errors", []),
        }

    except Exception as exc:
        logger.error("Measurement extraction error: %s", exc, exc_info=True)
        return {"success": False, "error": str(exc)}


@spaces.GPU(duration=20)
def generate_fashion_embedding(image_b64: str) -> dict[str, Any]:
    """
    Generate marqo-FashionSigLIP-B-16 visual embedding (512-dim, L2-normalized).
    57% better fashion retrieval vs generic CLIP/SigLIP.
    """
    if _siglip_model is None or _siglip_processor is None:
        return {"success": False, "error": "SigLIP model not available"}

    try:
        import torch

        img_bytes = base64.b64decode(image_b64)
        img_pil   = Image.open(BytesIO(img_bytes)).convert("RGB")

        inputs = _siglip_processor(images=img_pil, return_tensors="pt")
        inputs = {k: v.to("cuda") for k, v in inputs.items()}

        with torch.no_grad():
            feats     = _siglip_model.get_image_features(**inputs)
            embedding = feats[0].float().cpu().numpy()

        norm      = float(np.linalg.norm(embedding))
        embedding = (embedding / norm) if norm > 0 else embedding

        return {
            "success":   True,
            "embedding": embedding.tolist(),
            "dimension": len(embedding),
            "model":     SIGLIP_MODEL_ID,
        }

    except Exception as exc:
        logger.error("Embedding error: %s", exc, exc_info=True)
        return {"success": False, "error": str(exc)}


def generate_llm_response(
    prompt: str,
    system: str = "You are a professional fashion advisor for FASHIONISTAR.",
    max_tokens: int = 512,
    temperature: float = 0.7,
) -> dict[str, Any]:
    """
    Generate LLM response via the fastest available provider.
    Waterfall: SambaNova (~4000 tok/s) → Cerebras (~2000 tok/s) → Groq (~300 tok/s).
    No @spaces.GPU needed — all providers run on their own cloud chips.
    """
    client = _get_llm_client()
    if client is None:
        return {
            "success": False,
            "error":   "No LLM configured (set SAMBANOVA_API_KEY, CEREBRAS_API_KEY, or GROQ_API_KEY)",
            "text":    None,
        }

    # Determine which model name to use based on active provider
    if "sambanova" in _ACTIVE_LLM_PROVIDER:
        active_model = SAMBANOVA_MODEL
    elif "cerebras" in _ACTIVE_LLM_PROVIDER:
        active_model = CEREBRAS_MODEL
    else:
        active_model = GROQ_MODEL

    try:
        t0 = time.time()
        response = client.chat.completions.create(
            model=active_model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user",   "content": prompt},
            ],
            max_tokens=max_tokens,
            temperature=temperature,
        )
        elapsed = time.time() - t0
        return {
            "success":  True,
            "text":     response.choices[0].message.content,
            "model":    _ACTIVE_LLM_PROVIDER,
            "usage": {
                "prompt_tokens":     getattr(response.usage, "prompt_tokens", 0),
                "completion_tokens": getattr(response.usage, "completion_tokens", 0),
                "latency_ms":        round(elapsed * 1000),
            },
        }
    except Exception as exc:
        logger.error("LLM error [%s]: %s", _ACTIVE_LLM_PROVIDER, exc)
        return {"success": False, "error": str(exc), "text": None}


def health_check() -> dict[str, Any]:
    """
    Returns AI Engine health status.
    Called by fashionistar-api-v1 /api/v1/ninja/ai/health/ via /run/health_check.

    Response includes: models.siglip, models.mediapipe, models.llm_available, llm_provider.
    """
    llm_client = _get_llm_client()
    return {
        "status":  "ok" if (_siglip_model or _pose_landmarker) else "degraded",
        "service": "fashionistar-ai-engine",
        "version": AI_ENGINE_VERSION,
        "models": {
            "siglip":        _siglip_model    is not None,
            "mediapipe":     _pose_landmarker is not None,
            "llm_available": llm_client       is not None,
            # Legacy compat
            "groq":          llm_client       is not None,
        },
        "llm_provider":       _ACTIVE_LLM_PROVIDER,
        "gpu_available":      _HAS_SPACES,
        "models_initialized": _models_initialized,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }



def _inline_geometry(landmarks: list[dict], height_cm: float) -> dict[str, Any]:
    """Standalone measurement geometry (no Django dependency)."""
    KEY_IDX = [11, 12, 23, 24, 25, 26, 27, 28]
    MIN_VIS = 0.60

    vis = [float(landmarks[i].get("visibility", 0)) for i in KEY_IDX if i < len(landmarks)]
    quality = sum(vis) / len(vis) if vis else 0.0
    if quality < 0.50:
        return {"measurements": {}, "quality_score": quality,
                "errors": ["Pose quality too low"], "height_source": None}

    def dist(i: int, j: int, s: float):
        if i >= len(landmarks) or j >= len(landmarks):
            return None
        a, b = landmarks[i], landmarks[j]
        if float(a.get("visibility", 0)) < MIN_VIS or float(b.get("visibility", 0)) < MIN_VIS:
            return None
        return math.sqrt((a["x"]-b["x"])**2 + (a["y"]-b["y"])**2 + (a["z"]-b["z"])**2) * 100 * s

    ankle_y = (float(landmarks[27]["y"]) + float(landmarks[28]["y"])) / 2
    det_h   = abs(float(landmarks[0]["y"]) - ankle_y) * 100 * 1.07
    scale   = (height_cm / det_h) if (det_h > 1 and 120 <= height_cm <= 250) else 1.0
    src     = "user_provided" if scale != 1.0 else "auto_estimated"

    sw = dist(11, 12, scale)
    hw = dist(23, 24, scale)
    ins = dist(25, 27, scale)
    m: dict[str, float] = {}
    if sw:
        m["shoulder_width"] = round(sw, 1)
        m["bust"]           = round(sw * 2.75, 1)
    if hw:
        m["hip_width"] = round(hw, 1)
        m["waist"]     = round(hw * 1.85, 1)
        m["hips"]      = round(hw * math.pi * 0.875, 1)
    if ins:
        m["inseam"] = round(ins, 1)
    m["estimated_height"] = round(det_h, 1)

    return {"measurements": m, "quality_score": round(quality, 3),
            "errors": [], "height_source": src}
