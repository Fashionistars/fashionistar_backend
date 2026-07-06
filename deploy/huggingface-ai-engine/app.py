"""
FASHIONISTAR AI Engine — ZeroGPU Gradio Application
=====================================================
Hosts all GPU-intensive AI/ML inference tasks for the FASHIONISTAR platform.

Architecture:
  - ZeroGPU: shared A100 GPU allocated on-demand per request
  - Gradio: API + web interface
  - FastAPI: REST API endpoints via gr.mount_gradio_app
  - Models: MediaPipe, SigLIP, CLIP, Sentence Transformers

Internal API: Used by fashionistar-celery-queues via Gradio Client
"""
import os
import json
import time
import logging
import base64
from io import BytesIO
from typing import Optional

import gradio as gr
import spaces  # ZeroGPU decorator
import numpy as np
from PIL import Image

# ── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("fashionistar.ai_engine")

# ── Environment ────────────────────────────────────────────────────────────────
HF_TOKEN = os.environ.get("HF_TOKEN", "")
INTERNAL_TOKEN = os.environ.get("INTERNAL_SERVICE_TOKEN", "fashionistar-internal-telemetry-2026")
PORT = int(os.environ.get("PORT", 7860))

# ── Lazy model loading (loaded once, cached in ZeroGPU) ────────────────────────
_mediapipe_pose = None
_siglip_model = None
_siglip_processor = None
_clip_model = None
_clip_processor = None


def _load_mediapipe():
    """Load MediaPipe Pose on first use."""
    global _mediapipe_pose
    if _mediapipe_pose is None:
        try:
            import mediapipe as mp
            mp_pose = mp.solutions.pose
            _mediapipe_pose = mp_pose.Pose(
                static_image_mode=True,
                model_complexity=2,
                enable_segmentation=True,
                min_detection_confidence=0.5,
            )
            logger.info("MediaPipe Pose loaded")
        except Exception as e:
            logger.error(f"MediaPipe load failed: {e}")
    return _mediapipe_pose


def _load_siglip():
    """Load SigLIP vision model."""
    global _siglip_model, _siglip_processor
    if _siglip_model is None:
        try:
            from transformers import AutoProcessor, AutoModel
            model_id = "google/siglip-base-patch16-224"
            _siglip_processor = AutoProcessor.from_pretrained(model_id)
            _siglip_model = AutoModel.from_pretrained(model_id)
            logger.info("SigLIP model loaded")
        except Exception as e:
            logger.error(f"SigLIP load failed: {e}")
    return _siglip_model, _siglip_processor


# ── ZeroGPU-decorated AI functions ────────────────────────────────────────────

@spaces.GPU
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

        # Decode image
        img_bytes = base64.b64decode(image_b64)
        img = Image.open(BytesIO(img_bytes)).convert("RGB")
        img_array = np.array(img)
        img_bgr = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)

        # Run MediaPipe Pose
        pose = _load_mediapipe()
        if pose is None:
            return {"error": "MediaPipe not available", "success": False}

        results = pose.process(cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB))

        if not results.pose_landmarks:
            return {"error": "No pose detected in image", "success": False}

        landmarks = results.pose_landmarks.landmark
        h_px, w_px = img_array.shape[:2]

        # Key landmark indices (MediaPipe)
        LEFT_SHOULDER = 11
        RIGHT_SHOULDER = 12
        LEFT_HIP = 23
        RIGHT_HIP = 24
        LEFT_ANKLE = 27
        RIGHT_ANKLE = 28
        LEFT_EAR = 7
        RIGHT_EAR = 8

        def px(idx):
            """Get landmark pixel coordinates."""
            lm = landmarks[idx]
            return np.array([lm.x * w_px, lm.y * h_px])

        # Pixel distances
        shoulder_px = np.linalg.norm(px(LEFT_SHOULDER) - px(RIGHT_SHOULDER))
        hip_px = np.linalg.norm(px(LEFT_HIP) - px(RIGHT_HIP))
        torso_px = np.mean([
            np.linalg.norm(px(LEFT_SHOULDER) - px(LEFT_HIP)),
            np.linalg.norm(px(RIGHT_SHOULDER) - px(RIGHT_HIP)),
        ])
        body_height_px = np.linalg.norm(
            (px(LEFT_ANKLE) + px(RIGHT_ANKLE)) / 2 - (px(LEFT_EAR) + px(RIGHT_EAR)) / 2
        )

        # Scale factor (px → cm)
        if body_height_px < 1:
            return {"error": "Cannot determine scale — ensure full body is visible", "success": False}

        px_per_cm = body_height_px / height_cm

        # Estimated circumferences (multiply width by π * circumference factor)
        shoulder_cm = (shoulder_px / px_per_cm) * 2.2  # front width × factor
        chest_cm = shoulder_cm * 0.95
        waist_cm = (hip_px / px_per_cm) * 1.8
        hip_cm = (hip_px / px_per_cm) * 2.1
        inseam_cm = (torso_px / px_per_cm) * 0.6

        measurements = {
            "success": True,
            "measurements": {
                "shoulder_cm": round(shoulder_cm, 1),
                "chest_cm": round(chest_cm, 1),
                "waist_cm": round(waist_cm, 1),
                "hip_cm": round(hip_cm, 1),
                "inseam_cm": round(inseam_cm, 1),
                "height_cm": round(height_cm, 1),
            },
            "confidence": round(results.pose_landmarks.landmark[LEFT_SHOULDER].visibility, 3),
            "model": "mediapipe-pose-v2",
        }
        logger.info(f"Measurements extracted: {measurements['measurements']}")
        return measurements

    except Exception as e:
        logger.error(f"Measurement extraction failed: {e}")
        return {"error": str(e), "success": False}


@spaces.GPU
def generate_fashion_embedding(image_b64: str) -> dict:
    """
    Generate SigLIP visual embedding for a fashion item image.
    
    Args:
        image_b64: Base64-encoded image
    
    Returns:
        dict with embedding vector and metadata
    """
    try:
        model, processor = _load_siglip()
        if model is None:
            return {"error": "SigLIP not available", "success": False}

        import torch

        img_bytes = base64.b64decode(image_b64)
        img = Image.open(BytesIO(img_bytes)).convert("RGB")

        inputs = processor(images=img, return_tensors="pt")
        with torch.no_grad():
            image_features = model.get_image_features(**inputs)
            # L2 normalize
            embedding = image_features[0].cpu().numpy()
            embedding = embedding / np.linalg.norm(embedding)

        return {
            "success": True,
            "embedding": embedding.tolist(),
            "dimension": len(embedding),
            "model": "google/siglip-base-patch16-224",
        }
    except Exception as e:
        logger.error(f"Embedding generation failed: {e}")
        return {"error": str(e), "success": False}


# ── Gradio Interface ───────────────────────────────────────────────────────────

def health_check() -> dict:
    """Health check endpoint."""
    return {
        "status": "ok",
        "service": "fashionistar-ai-engine",
        "gpu_available": True,
        "models": {
            "mediapipe": _mediapipe_pose is not None,
            "siglip": _siglip_model is not None,
        },
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def measurements_api(image: Image.Image, height_cm: float) -> str:
    """Gradio UI function for body measurements."""
    if image is None:
        return json.dumps({"error": "No image provided"})
    buffer = BytesIO()
    image.save(buffer, format="JPEG")
    img_b64 = base64.b64encode(buffer.getvalue()).decode()
    result = extract_body_measurements(img_b64, height_cm)
    return json.dumps(result, indent=2)


def embedding_api(image: Image.Image) -> str:
    """Gradio UI function for embeddings."""
    if image is None:
        return json.dumps({"error": "No image provided"})
    buffer = BytesIO()
    image.save(buffer, format="JPEG")
    img_b64 = base64.b64encode(buffer.getvalue()).decode()
    result = generate_fashion_embedding(img_b64)
    # Truncate embedding for display
    if result.get("success") and "embedding" in result:
        result["embedding_preview"] = result["embedding"][:8]
        result["embedding"] = f"[{result['dimension']} dimensions]"
    return json.dumps(result, indent=2)


# ── Build Gradio App ───────────────────────────────────────────────────────────

with gr.Blocks(
    title="FASHIONISTAR AI Engine",
    theme=gr.themes.Soft(primary_hue="purple"),
    css="""
    .header { text-align: center; margin-bottom: 20px; }
    .status { background: #1a1a2e; color: #e0e0e0; border-radius: 8px; padding: 10px; }
    """,
) as demo:

    gr.Markdown(
        """
        # 🤖 FASHIONISTAR AI Engine
        **ZeroGPU-powered AI inference for fashion intelligence**
        
        > Internal API — Used by fashionistar-celery-queues for background AI task processing
        """,
        elem_classes="header",
    )

    with gr.Tabs():
        # Tab 1: Body Measurements
        with gr.Tab("📏 Body Measurements"):
            gr.Markdown("Extract body measurements from a photo using MediaPipe Pose estimation.")
            with gr.Row():
                with gr.Column():
                    meas_image = gr.Image(label="Body Photo (full body, standing)", type="pil")
                    meas_height = gr.Slider(140, 220, value=170, label="Known Height (cm)")
                    meas_btn = gr.Button("📏 Extract Measurements", variant="primary")
                with gr.Column():
                    meas_output = gr.Code(label="Measurements JSON", language="json")
            meas_btn.click(measurements_api, inputs=[meas_image, meas_height], outputs=meas_output)

        # Tab 2: Fashion Embeddings
        with gr.Tab("🎨 Fashion Embeddings"):
            gr.Markdown("Generate SigLIP visual embeddings for fashion items.")
            with gr.Row():
                with gr.Column():
                    emb_image = gr.Image(label="Fashion Item Image", type="pil")
                    emb_btn = gr.Button("🎨 Generate Embedding", variant="primary")
                with gr.Column():
                    emb_output = gr.Code(label="Embedding JSON", language="json")
            emb_btn.click(embedding_api, inputs=[emb_image], outputs=emb_output)

        # Tab 3: Health Status
        with gr.Tab("💚 Health"):
            gr.Markdown("AI Engine service status")
            health_btn = gr.Button("Check Health", variant="secondary")
            health_output = gr.JSON(label="Health Status")
            health_btn.click(health_check, outputs=health_output)

    # Gradio API (for Celery worker to call via gr.Client)
    demo.queue(max_size=20)


# ── API endpoints via Gradio's built-in FastAPI ───────────────────────────────
app = demo.launch(
    server_name="0.0.0.0",
    server_port=PORT,
    share=False,
    show_error=True,
    prevent_thread_lock=True,
)


if __name__ == "__main__":
    demo.launch(
        server_name="0.0.0.0",
        server_port=PORT,
        share=False,
        show_error=True,
    )
