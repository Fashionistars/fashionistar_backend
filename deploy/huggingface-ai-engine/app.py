# deploy/huggingface-ai-engine/app.py
"""
FASHIONISTAR AI Engine — Hugging Face ZeroGPU Space (v3.0.0)
=============================================================

Production entry point for the fashionistar/fashionistar-ai-engine HF Space.

Architecture:
  This file is a thin Gradio wrapper around zerogpu_engine.py.
  All core AI logic lives in zerogpu_engine.py, which is co-deployed here.

  When running standalone (not inside Django), the inline geometry fallback
  in zerogpu_engine.py handles body measurements without Django ORM access.

Models Loaded at Startup (ZeroGPU requirement):
  - Marqo/marqo-fashionSigLIP      (512-dim fashion embeddings, open_clip + ZeroGPU)
  - MediaPipe pose_landmarker_heavy    (33 3D body pose landmarks, ZeroGPU)
  - LLM provider (auto-selected)       (Cloud API, no GPU needed)

LLM Provider Waterfall (fastest available wins):
  1. SambaNova  (~4,000 tok/s) — set SAMBANOVA_API_KEY
  2. Cerebras   (~2,000 tok/s) — set CEREBRAS_API_KEY  (1M tok/day FREE)
  3. Groq       (~300   tok/s) — set GROQ_API_KEY      (14,400 req/day FREE)

Environment Variables (set in HF Space secrets):
  - HF_TOKEN             — HF Hub token (faster model downloads, auth)
  - SAMBANOVA_API_KEY    — SambaNova API key (FASTEST: ~4,000 tok/s)
  - CEREBRAS_API_KEY     — Cerebras API key (FREE 1M tokens/day)
  - GROQ_API_KEY         — Groq API key (fallback LLM, 14,400 req/day free)
  - SIGLIP_MODEL_ID      -- Override model ID (default: Marqo/marqo-fashionSigLIP)
  - GROQ_MODEL           — Override Groq model (default: llama-3.3-70b-versatile)
  - SAMBANOVA_MODEL      — Override SambaNova model (default: Meta-Llama-3.3-70B-Instruct)
  - CEREBRAS_MODEL       — Override Cerebras model (default: llama-3.3-70b)

Endpoints exposed via Gradio API (/run/<api_name>):
  POST /run/health_check       — Service health + model availability + LLM provider
  POST /run/body_measurements  — Body pose extraction from image
  POST /run/fashion_embedding  — Product visual embedding (512-dim)
  POST /run/llm_fashion        — Fashion LLM advice (multi-provider)
  POST /run/warmup             — Pre-warm GPU memory (called by CI/CD)

Queried by fashionistar-api-v1 at:
  GET /api/v1/ninja/ai/health/
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from pathlib import Path

import gradio as gr

# ── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("fashionistar.ai_engine")

# ── Load environment from .env (if present, e.g. local dev) ───────────────────
try:
    from dotenv import load_dotenv
    _env = Path(__file__).parent / ".env"
    if _env.exists():
        load_dotenv(_env)
        logger.info("Loaded .env from %s", _env)
except ImportError:
    pass  # python-dotenv not required in production

# ── Phase 2.3: ZeroGPU Token Authentication ───────────────────────────────────
# Authenticating with HF_TOKEN grants 8x more ZeroGPU GPU quota.
# Must be called BEFORE any @spaces.GPU decorator is evaluated.
try:
    import spaces as _sp
    _hf_token = os.environ.get("HF_TOKEN")
    if _hf_token:
        if hasattr(_sp, "configure"):
            _sp.configure(hf_token=_hf_token)
            logger.info("ZeroGPU authenticated with HF_TOKEN (8x quota)")
        else:
            logger.warning("Installed spaces package has no configure(); continuing without token configuration")
    else:
        logger.warning("HF_TOKEN not set -- ZeroGPU running with reduced quota")
except Exception as _spaces_err:
    logger.warning("spaces.configure failed (non-critical): %s", _spaces_err)

# ── Import ZeroGPU Engine ─────────────────────────────────────────────────────
# Try to import from the deployed zerogpu_engine.py (co-deployed in same dir)
# Fall back to apps.ai.engines if running inside full Django project
_engine = None
_engine_error = None

try:
    # Primary: import from the same directory (HF Space deploy)
    _script_dir = Path(__file__).parent
    if str(_script_dir) not in sys.path:
        sys.path.insert(0, str(_script_dir))

    from zerogpu_engine import (
        initialize_models,
        extract_body_measurements,
        generate_fashion_embedding,
        generate_llm_response,
        health_check as _engine_health_check,
        AI_ENGINE_VERSION,
    )
    logger.info("✅ Loaded zerogpu_engine from %s", _script_dir)
except ImportError:
    try:
        # Secondary: import from Django apps (full project deploy)
        from apps.ai.engines.zerogpu_engine import (
            initialize_models,
            extract_body_measurements,
            generate_fashion_embedding,
            generate_llm_response,
            health_check as _engine_health_check,
            AI_ENGINE_VERSION,
        )
        logger.info("✅ Loaded zerogpu_engine from apps.ai.engines")
    except ImportError as e:
        _engine_error = str(e)
        logger.error("❌ zerogpu_engine not found: %s", e)
        # Minimal stubs so Gradio can still start
        AI_ENGINE_VERSION = "error"

        def initialize_models():
            return {"mediapipe": False, "siglip": False, "groq": False}

        def extract_body_measurements(img_b64, height_cm=170.0):
            return {"success": False, "error": "zerogpu_engine not loaded"}

        def generate_fashion_embedding(img_b64):
            return {"success": False, "error": "zerogpu_engine not loaded"}

        def generate_llm_response(prompt, system="", max_tokens=512, temperature=0.7):
            return {"success": False, "error": "zerogpu_engine not loaded", "text": None}

        def _engine_health_check():
            return {"status": "error", "error": _engine_error}


# ── Startup: load all models NOW (required before any @spaces.GPU call) ────────
logger.info("═" * 60)
logger.info("🎀 FASHIONISTAR AI Engine v%s — Starting...", AI_ENGINE_VERSION)
logger.info("═" * 60)
_startup_results = initialize_models()
logger.info("Startup complete: %s", _startup_results)


# ══════════════════════════════════════════════════════════════════════════════
# Gradio Interface Functions
# (These wrap zerogpu_engine functions with JSON string I/O for easy API use)
# ══════════════════════════════════════════════════════════════════════════════

def health_check_fn() -> dict:
    """
    Return AI Engine health status as a dict (Gradio 5.x gr.JSON expects dict, not str).
    Queried by fashionistar-api-v1 at /api/v1/ninja/ai/health/ via queue/join SSE.
    """
    result = _engine_health_check()
    result["startup_results"] = _startup_results
    return result  # gr.JSON auto-serialises — do NOT json.dumps()



def body_measurements_fn(image_b64: str, height_cm: float = 170.0) -> str:
    """
    Extract body measurements from a base64-encoded body photo.

    Args:
        image_b64: Base64-encoded JPEG/PNG of the user's full body (front-facing)
        height_cm: Known user height in cm for scale calibration

    Returns:
        JSON string with: success, measurements, confidence, errors
    """
    if not image_b64 or not image_b64.strip():
        return json.dumps({"success": False, "error": "image_b64 is required"})
    # Strip data URI prefix if present
    if "," in image_b64:
        image_b64 = image_b64.split(",", 1)[1]
    result = extract_body_measurements(image_b64, float(height_cm))
    return json.dumps(result)


def fashion_embedding_fn(image_b64: str) -> str:
    """
    Generate marqo-FashionSigLIP-B-16 visual embedding for a product image.

    Args:
        image_b64: Base64-encoded product/fashion image

    Returns:
        JSON string with: success, embedding (list[float]), dimension
    """
    if not image_b64 or not image_b64.strip():
        return json.dumps({"success": False, "error": "image_b64 is required"})
    if "," in image_b64:
        image_b64 = image_b64.split(",", 1)[1]
    result = generate_fashion_embedding(image_b64)
    return json.dumps(result)


def llm_fashion_fn(
    prompt: str,
    system: str = "You are a professional fashion advisor for FASHIONISTAR.",
    max_tokens: int = 512,
    temperature: float = 0.7,
) -> str:
    """
    Generate fashion LLM response via Groq API (Llama-3.3-70B-Versatile).

    Args:
        prompt:      User request / task description
        system:      System prompt (optional, defaults to fashion advisor)
        max_tokens:  Maximum response tokens (default 512)
        temperature: Sampling temperature (0=deterministic, 1=creative)

    Returns:
        JSON string with: success, text, model, usage
    """
    if not prompt or not prompt.strip():
        return json.dumps({"success": False, "error": "prompt is required"})
    result = generate_llm_response(
        prompt=prompt.strip(),
        system=system.strip() if system else "You are a professional fashion advisor for FASHIONISTAR.",
        max_tokens=int(max_tokens),
        temperature=float(temperature),
    )
    return json.dumps(result)



# Phase 2: Warmup cooldown — prevents ZeroGPU quota exhaustion (429 Too Many Requests)
# Warmup consumes 30-45s of ZeroGPU quota per call. CI/CD + repeated restarts
# can exhaust the daily quota. 10-minute cooldown prevents back-to-back calls.
_last_warmup_time: float = 0.0
WARMUP_COOLDOWN_SECS: int = 600  # 10 minutes


def warmup_fn() -> dict:
    """
    Pre-warm GPU memory by running a minimal forward pass.
    Called by GitHub Actions CI/CD after successful deploy.
    Eliminates the 15s cold-start for the first real user request.
    Includes 10-minute cooldown to prevent ZeroGPU quota exhaustion (429 errors).
    """
    global _last_warmup_time
    import base64
    from io import BytesIO

    # Phase 2: Cooldown guard — skip if called within WARMUP_COOLDOWN_SECS
    elapsed = time.time() - _last_warmup_time
    if elapsed < WARMUP_COOLDOWN_SECS:
        remaining = int(WARMUP_COOLDOWN_SECS - elapsed)
        logger.info("Warmup skipped — cooldown active (%ds remaining)", remaining)
        return {
            "status":           "skipped",
            "reason":           "cooldown",
            "seconds_remaining": remaining,
            "next_warmup_at":   time.strftime(
                "%Y-%m-%dT%H:%M:%SZ",
                time.gmtime(_last_warmup_time + WARMUP_COOLDOWN_SECS)
            ),
        }

    try:
        # 1x1 white pixel — minimal valid image for SigLIP warmup
        from PIL import Image as _Image
        img = _Image.new("RGB", (1, 1), (255, 255, 255))
        buf = BytesIO()
        img.save(buf, format="JPEG")
        tiny_b64 = base64.b64encode(buf.getvalue()).decode()

        results = {}

        # Warmup SigLIP
        emb_result = generate_fashion_embedding(tiny_b64)
        results["siglip"] = emb_result.get("success", False)

        # Warmup MediaPipe (use a slightly larger image)
        img_large = _Image.new("RGB", (224, 224), (128, 128, 128))
        buf2      = BytesIO()
        img_large.save(buf2, format="JPEG")
        large_b64 = base64.b64encode(buf2.getvalue()).decode()
        mp_result = extract_body_measurements(large_b64, 170.0)
        # No person in the image -- that's fine, just warming GPU
        results["mediapipe"] = mp_result.get("success", False) or "error" in mp_result

        _last_warmup_time = time.time()  # update cooldown timestamp only on success
        return {
            "status":    "warmed_up",
            "results":   results,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
    except Exception as exc:
        logger.warning("Warmup failed (non-critical): %s", exc)
        return {"status": "warmup_failed", "error": str(exc)}


# ══════════════════════════════════════════════════════════════════════════════
# Gradio App
# ══════════════════════════════════════════════════════════════════════════════

with gr.Blocks(
    title="FASHIONISTAR AI Engine",
    theme=gr.themes.Soft(primary_hue="pink", secondary_hue="rose"),
) as demo:
    gr.Markdown(
        """
        # 🎀 FASHIONISTAR AI Engine
        **Production ZeroGPU AI Service** — `v""" + AI_ENGINE_VERSION + """`

        Powers the FASHIONISTAR platform with:
        - 📐 Body measurement extraction (MediaPipe Tasks PoseLandmarker, 95%+ accuracy)
        - 🖼️ Fashion visual embeddings (Marqo/marqo-fashionSigLIP, open_clip, 512-dim)
        - 💬 AI fashion advisor (SambaNova / Cerebras / Groq — fastest wins)

        > This is a machine-to-machine API space.
        > Queried by `fashionistar-api-v1` at `/api/v1/ninja/ai/health/`.
        """
    )

    with gr.Tab("Health"):
        health_btn    = gr.Button("🩺 Check Health", variant="primary")
        health_output = gr.JSON(label="Health Status")
        # api_name exposes this as POST /run/health_check
        health_btn.click(
            fn=health_check_fn,
            inputs=[],
            outputs=[health_output],
            api_name="health_check",
        )

    with gr.Tab("Body Measurements"):
        gr.Markdown("Upload a base64-encoded body photo and user height for measurement extraction.")
        img_input    = gr.Textbox(label="Base64 Image", placeholder="data:image/jpeg;base64,/9j/...")
        height_input = gr.Number(label="Height (cm)", value=170, minimum=100, maximum=250)
        meas_btn     = gr.Button("Extract Measurements", variant="primary")
        meas_output  = gr.JSON(label="Measurements")
        # api_name exposes this as POST /run/body_measurements
        meas_btn.click(
            fn=body_measurements_fn,
            inputs=[img_input, height_input],
            outputs=[meas_output],
            api_name="body_measurements",
        )

    with gr.Tab("Fashion Embedding"):
        gr.Markdown("Generate a 512-dim fashion visual embedding using marqo-FashionSigLIP.")
        emb_img_input = gr.Textbox(label="Base64 Product Image", placeholder="data:image/jpeg;base64,...")
        emb_btn       = gr.Button("Generate Embedding", variant="primary")
        emb_output    = gr.JSON(label="Embedding Result")
        # api_name exposes this as POST /run/fashion_embedding
        emb_btn.click(
            fn=fashion_embedding_fn,
            inputs=[emb_img_input],
            outputs=[emb_output],
            api_name="fashion_embedding",
        )

    with gr.Tab("Fashion LLM"):
        gr.Markdown("Generate fashion AI advice via multi-provider LLM waterfall (SambaNova → Cerebras → Groq).")
        llm_system_input = gr.Textbox(
            label="System Prompt",
            value="You are a professional fashion advisor for FASHIONISTAR.",
        )
        llm_prompt_input = gr.Textbox(
            label="User Prompt",
            placeholder="Recommend a size for someone with bust 90cm, waist 72cm, hips 96cm.",
            lines=3,
        )
        llm_max_tokens   = gr.Slider(100, 2048, value=512, step=64, label="Max Tokens")
        llm_temperature  = gr.Slider(0.0, 1.0, value=0.7, step=0.1, label="Temperature")
        llm_btn          = gr.Button("Generate", variant="primary")
        llm_output       = gr.JSON(label="LLM Response")
        # api_name exposes this as POST /run/llm_fashion
        llm_btn.click(
            fn=llm_fashion_fn,
            inputs=[llm_prompt_input, llm_system_input, llm_max_tokens, llm_temperature],
            outputs=[llm_output],
            api_name="llm_fashion",
        )

    with gr.Tab("Warmup"):
        gr.Markdown(
            "> Called by GitHub Actions CI/CD after deploy to pre-warm GPU memory.\n"
            "> Prevents 15s cold-start for first user request."
        )
        warmup_btn    = gr.Button("🔥 Run GPU Warmup", variant="secondary")
        warmup_output = gr.JSON(label="Warmup Result")
        # api_name exposes this as POST /run/warmup
        warmup_btn.click(
            fn=warmup_fn,
            inputs=[],
            outputs=[warmup_output],
            api_name="warmup",
        )


# ── Named API endpoints are declared via api_name= on each .click() handler ────
# Gradio 5.x exposes these as POST /run/<api_name> automatically.
# demo.add_api() does NOT exist in Gradio 5.x — do not use it.

if __name__ == "__main__":
    demo.launch(
        server_name="0.0.0.0",
        server_port=int(os.environ.get("PORT", 7860)),
        show_api=True,
    )
