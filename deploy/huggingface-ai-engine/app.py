"""
FASHIONISTAR AI Engine — ZeroGPU Gradio Application
=====================================================
Hosts all GPU-intensive AI/ML inference tasks for the FASHIONISTAR platform.

ZeroGPU Architecture:
  - Models are loaded at MODULE LEVEL onto 'cuda' (ZeroGPU emulation mode outside @spaces.GPU)
  - @spaces.GPU decorator requests a real GPU for the duration of the function
  - GPU is released after each function call (ZeroGPU is shared, not persistent)

Services:
  - Body measurement extraction (MediaPipe Pose)
  - Fashion visual embeddings (SigLIP / google/siglip-so400m-patch14-384)
  - Health check endpoint (queried by fashionistar-api-v1)

Internal API: Celery workers call this via Gradio Client API
External URL: https://fashionistar-fashionistar-ai-engine.hf.space
"""
import os
import json
import time
import logging
import base64
from io import BytesIO
from typing import Optional, Dict, Any

import gradio as gr
import spaces  # ZeroGPU decorator — no-op outside HF Spaces
import numpy as np
from PIL import Image

# ── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("fashionistar.ai_engine")

# ── Environment ────────────────────────────────────────────────────────────────
HF_TOKEN          = os.environ.get("HF_TOKEN", "")
INTERNAL_TOKEN    = os.environ.get("INTERNAL_SERVICE_TOKEN", "fashionistar-internal-telemetry-2026")
PORT              = int(os.environ.get("PORT", 7860))
AI_ENGINE_VERSION = "2.0.0"

# ── ZeroGPU: Load models at MODULE LEVEL onto 'cuda' ──────────────────────────
# Outside @spaces.GPU, CUDA emulation is active. Inside @spaces.GPU, real GPU is used.
# NEVER lazy-load inside @spaces.GPU — it breaks ZeroGPU's CUDA transfer optimizations.

_mediapipe_pose    = None
_siglip_model      = None
_siglip_processor  = None
_models_loaded     = False

def _initialize_models():
    """Load all models at startup time (module level, as required by ZeroGPU)."""
    global _mediapipe_pose, _siglip_model, _siglip_processor, _models_loaded

    # ── MediaPipe Pose ─────────────────────────────────────────────────────────
    try:
        import mediapipe as mp
        mp_pose = mp.solutions.pose
        _mediapipe_pose = mp_pose.Pose(
            static_image_mode=True,
            model_complexity=2,
            enable_segmentation=True,
            min_detection_confidence=0.5,
        )
        logger.info("✅ MediaPipe Pose loaded")
    except Exception as e:
        logger.warning(f"⚠️  MediaPipe load failed (non-fatal): {e}")

    # ── SigLIP Vision Model ────────────────────────────────────────────────────
    # google/siglip-so400m-patch14-384 — state-of-art fashion embedding
    try:
        import torch
        from transformers import AutoProcessor, AutoModel

        model_id = os.environ.get("SIGLIP_MODEL_ID", "google/siglip-base-patch16-224")
        logger.info(f"Loading SigLIP: {model_id} ...")
        _siglip_processor = AutoProcessor.from_pretrained(model_id)
        _siglip_model = AutoModel.from_pretrained(model_id, torch_dtype=torch.float16)
        # Move to CUDA at module level (ZeroGPU requirement)
        _siglip_model = _siglip_model.to("cuda")
        _siglip_model.eval()
        logger.info("✅ SigLIP model loaded on CUDA")
    except Exception as e:
        logger.warning(f"⚠️  SigLIP load failed (non-fatal): {e}")

    _models_loaded = True
    logger.info(
        f"AI Engine v{AI_ENGINE_VERSION} initialized — "
        f"MediaPipe: {'✅' if _mediapipe_pose else '❌'}, "
        f"SigLIP: {'✅' if _siglip_model else '❌'}"
    )


# Initialize models at startup
_initialize_models()


# ── ZeroGPU-decorated AI Functions ─────────────────────────────────────────────

@spaces.GPU(duration=30)
def extract_body_measurements(image_b64: str, height_cm: float = 170.0) -> dict:
    """
    Extract body measurements from a base64-encoded image.
    Uses MediaPipe Pose + geometric estimation.

    Args:
        image_b64: Base64-encoded JPEG/PNG image
        height_cm: Known user height in cm for scale calibration

    Returns:
        dict with measurements: chest, waist, hips, etc.
    """
    try:
        import mediapipe as mp
        import cv2

        if _mediapipe_pose is None:
            return {"error": "MediaPipe not available", "success": False}

        # Decode image
        img_bytes  = base64.b64decode(image_b64)
        img        = Image.open(BytesIO(img_bytes)).convert("RGB")
        img_array  = np.array(img)
        img_bgr    = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)

        results = _mediapipe_pose.process(cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB))
        if not results.pose_landmarks:
            return {"error": "No pose detected in image", "success": False}

        landmarks   = results.pose_landmarks.landmark
        h_px, w_px  = img_array.shape[:2]

        # Key landmark indices (MediaPipe BlazePose)
        LEFT_SHOULDER  = 11
        RIGHT_SHOULDER = 12
        LEFT_HIP       = 23
        RIGHT_HIP      = 24
        LEFT_ANKLE     = 27
        RIGHT_ANKLE    = 28
        LEFT_EAR       = 7
        RIGHT_EAR      = 8

        def px(idx: int) -> np.ndarray:
            lm = landmarks[idx]
            return np.array([lm.x * w_px, lm.y * h_px])

        # Pixel distances
        shoulder_px     = np.linalg.norm(px(LEFT_SHOULDER)  - px(RIGHT_SHOULDER))
        hip_px          = np.linalg.norm(px(LEFT_HIP)       - px(RIGHT_HIP))
        torso_px        = np.mean([
            np.linalg.norm(px(LEFT_SHOULDER)  - px(LEFT_HIP)),
            np.linalg.norm(px(RIGHT_SHOULDER) - px(RIGHT_HIP)),
        ])
        body_height_px  = np.linalg.norm(
            (px(LEFT_ANKLE) + px(RIGHT_ANKLE)) / 2
            - (px(LEFT_EAR) + px(RIGHT_EAR)) / 2
        )

        if body_height_px < 1:
            return {
                "error": "Cannot determine scale — ensure full body is visible",
                "success": False,
            }

        px_per_cm   = body_height_px / height_cm
        shoulder_cm = (shoulder_px / px_per_cm) * 2.2
        chest_cm    = shoulder_cm * 0.95
        waist_cm    = (hip_px     / px_per_cm) * 1.8
        hip_cm      = (hip_px     / px_per_cm) * 2.1
        inseam_cm   = (torso_px   / px_per_cm) * 0.6

        return {
            "success": True,
            "measurements": {
                "shoulder_cm": round(shoulder_cm, 1),
                "chest_cm":    round(chest_cm,    1),
                "waist_cm":    round(waist_cm,    1),
                "hip_cm":      round(hip_cm,      1),
                "inseam_cm":   round(inseam_cm,   1),
                "height_cm":   round(height_cm,   1),
            },
            "confidence": round(results.pose_landmarks.landmark[LEFT_SHOULDER].visibility, 3),
            "model":       "mediapipe-pose-v2",
        }

    except Exception as e:
        logger.error(f"Measurement extraction failed: {e}")
        return {"error": str(e), "success": False}


@spaces.GPU(duration=20)
def generate_fashion_embedding(image_b64: str) -> dict:
    """
    Generate SigLIP visual embedding for a fashion item image.

    Args:
        image_b64: Base64-encoded image

    Returns:
        dict with 'embedding' vector (list of floats) and metadata
    """
    try:
        if _siglip_model is None or _siglip_processor is None:
            return {"error": "SigLIP model not available", "success": False}

        import torch

        img_bytes = base64.b64decode(image_b64)
        img       = Image.open(BytesIO(img_bytes)).convert("RGB")

        inputs = _siglip_processor(images=img, return_tensors="pt")
        # Move inputs to GPU (real GPU inside @spaces.GPU)
        inputs = {k: v.to("cuda") for k, v in inputs.items()}

        with torch.no_grad():
            image_features = _siglip_model.get_image_features(**inputs)
            embedding      = image_features[0].float().cpu().numpy()
            embedding      = embedding / np.linalg.norm(embedding)

        return {
            "success":   True,
            "embedding": embedding.tolist(),
            "dimension": len(embedding),
            "model":     os.environ.get("SIGLIP_MODEL_ID", "google/siglip-base-patch16-224"),
        }

    except Exception as e:
        logger.error(f"Embedding generation failed: {e}")
        return {"error": str(e), "success": False}


# ── Health Check (no GPU needed, called by fashionistar-api-v1) ────────────────
def health_check() -> dict:
    """
    Returns AI Engine service health.
    Called by fashionistar-api-v1 /api/v1/ninja/ai/health/ endpoint.
    Response shape must include: models.siglip and models.mediapipe (bool).
    """
    return {
        "status":  "ok",
        "service": "fashionistar-ai-engine",
        "version": AI_ENGINE_VERSION,
        "models": {
            "siglip":    _siglip_model is not None,
            "mediapipe": _mediapipe_pose is not None,
        },
        "gpu_available": True,  # ZeroGPU provides GPU on-demand
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


# ── Gradio UI Wrappers ─────────────────────────────────────────────────────────

def measurements_ui(image: Image.Image, height_cm: float) -> str:
    """Gradio UI wrapper for body measurements."""
    if image is None:
        return json.dumps({"error": "No image provided"}, indent=2)
    buf = BytesIO()
    image.save(buf, format="JPEG", quality=90)
    result = extract_body_measurements(base64.b64encode(buf.getvalue()).decode(), height_cm)
    return json.dumps(result, indent=2)


def embedding_ui(image: Image.Image) -> str:
    """Gradio UI wrapper for fashion embeddings (truncates for display)."""
    if image is None:
        return json.dumps({"error": "No image provided"}, indent=2)
    buf = BytesIO()
    image.save(buf, format="JPEG", quality=90)
    result = generate_fashion_embedding(base64.b64encode(buf.getvalue()).decode())
    if result.get("success") and "embedding" in result:
        result["embedding_preview"] = result["embedding"][:8]
        result["embedding"]         = f"[{result['dimension']} dimensions — use API for full vector]"
    return json.dumps(result, indent=2)


# ── Build Gradio Blocks App ────────────────────────────────────────────────────
with gr.Blocks(
    title="FASHIONISTAR AI Engine",
    theme=gr.themes.Soft(primary_hue="purple"),
    css="""
    .header    { text-align: center; margin-bottom: 20px; }
    .badge     { display: inline-block; padding: 3px 8px; border-radius: 12px;
                 background: #7c3aed; color: #fff; font-size: 12px; font-weight: 700; }
    .api-note  { background: #1e1b4b; color: #c4b5fd; border-radius: 8px;
                 padding: 12px; font-family: monospace; font-size: 13px; }
    """,
) as demo:

    gr.Markdown(
        f"""
        # 🤖 FASHIONISTAR AI Engine <span class="badge">v{AI_ENGINE_VERSION}</span>

        **ZeroGPU-powered AI inference — NVIDIA RTX Pro 6000 Blackwell (48 GB VRAM)**

        > Internal API used by `fashionistar-api-v1` and `fashionistar-celery-queues` for background AI tasks.

        <div class="api-note">
        🔗 API Gateway: <code>https://fashionistar-fashionistar-api-v1.hf.space/api/v1/ninja/ai/health/</code>
        </div>
        """,
        elem_classes="header",
    )

    with gr.Tabs():

        # ── Tab 1: Body Measurements ──────────────────────────────────────────
        with gr.Tab("📏 Body Measurements"):
            gr.Markdown(
                "Extract body measurements from a photo using **MediaPipe Pose** estimation.\n\n"
                "Requires a full-body standing photo for accurate results."
            )
            with gr.Row():
                with gr.Column(scale=1):
                    meas_image  = gr.Image(
                        label="Body Photo (full body, standing, front-facing)",
                        type="pil",
                    )
                    meas_height = gr.Slider(
                        minimum=140, maximum=220, value=170, step=1,
                        label="Known Height (cm) — for pixel→cm scale calibration",
                    )
                    meas_btn = gr.Button("📏 Extract Measurements", variant="primary", size="lg")
                with gr.Column(scale=1):
                    meas_output = gr.Code(label="Measurements (JSON)", language="json")
            meas_btn.click(
                fn=measurements_ui,
                inputs=[meas_image, meas_height],
                outputs=meas_output,
                api_name="extract_measurements",
            )

        # ── Tab 2: Fashion Embeddings ──────────────────────────────────────────
        with gr.Tab("🎨 Fashion Embeddings"):
            gr.Markdown(
                "Generate **SigLIP visual embeddings** for fashion items.\n\n"
                "Embeddings are stored in pgvector and used for visual similarity search."
            )
            with gr.Row():
                with gr.Column(scale=1):
                    emb_image = gr.Image(label="Fashion Item Image", type="pil")
                    emb_btn   = gr.Button("🎨 Generate Embedding", variant="primary", size="lg")
                with gr.Column(scale=1):
                    emb_output = gr.Code(label="Embedding Result (JSON)", language="json")
            emb_btn.click(
                fn=embedding_ui,
                inputs=[emb_image],
                outputs=emb_output,
                api_name="generate_embedding",
            )

        # ── Tab 3: Health Check ─────────────────────────────────────────────────
        with gr.Tab("💚 Health Status"):
            gr.Markdown(
                "**Internal health check** — queried by `fashionistar-api-v1` via "
                "`/run/health_check` to report SigLIP & MediaPipe availability."
            )
            health_btn    = gr.Button("🔍 Check Health", variant="secondary")
            health_output = gr.JSON(label="Health Status")
            health_btn.click(
                fn=health_check,
                outputs=health_output,
                api_name="health_check",  # <-- API gateway calls /run/health_check
            )

    demo.queue(max_size=10)


# ── Launch ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    demo.launch(
        server_name="0.0.0.0",
        server_port=PORT,
        share=False,
        show_error=True,
    )
