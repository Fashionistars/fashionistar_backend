# apps/ai/engines/recommendation_engine.py
"""
Fashion Recommendation Engine — marqo-FashionSigLIP + pgvector.

Technology:
  - Model: marqo-FashionSigLIP-B-16 (Apache 2.0, best fashion embeddings 2026)
  - Vector DB: pgvector HNSW index on existing PostgreSQL 17 (no new DB)
  - Similarity: Cosine distance, <50ms p95 at 100k+ products

Why marqo-FashionSigLIP over generic CLIP:
  - 57% improvement in fashion retrieval benchmark
  - Understands 7 fashion dimensions: descriptions, titles, colors,
    materials, categories, keywords, fine-grained details
  - Handles vocabulary mismatch (e.g., 'maxi dress' vs 'long gown')
  - Open source (Apache 2.0), no API costs

Performance:
  - CPU inference: ~1.5s per product (acceptable for batch embedding)
  - GPU inference: ~0.08s per product (if GPU available)
  - pgvector HNSW search: <50ms p95 regardless of collection size

Graceful degradation:
  If open_clip or torch are not installed, embedding generation returns None.
  The recommendation engine will fall back to text-only keyword search.
"""

from __future__ import annotations

import logging
from io import BytesIO

import numpy as np

logger = logging.getLogger(__name__)

# ── Singleton pattern for model loading ────────────────────────────────────────
_fashion_model = None
_fashion_preprocess = None
_fashion_tokenizer = None
_device = None


def _load_fashion_model():
    """
    Load marqo-FashionSigLIP model (singleton — loads once per Celery worker).
    Fails gracefully if open_clip/torch not installed.
    """
    global _fashion_model, _fashion_preprocess, _fashion_tokenizer, _device

    if _fashion_model is not None:
        return True

    try:
        import torch
        import open_clip

        _device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        logger.info("[FashionEngine] Loading marqo-FashionSigLIP on %s", _device)

        _fashion_model, _, _fashion_preprocess = open_clip.create_model_and_transforms(
            "ViT-B-16-SigLIP",
            pretrained="hf-hub:Marqo/marqo-FashionSigLIP",
        )
        _fashion_tokenizer = open_clip.get_tokenizer("ViT-B-16-SigLIP")
        _fashion_model.eval()
        _fashion_model.to(_device)

        logger.info("[FashionEngine] marqo-FashionSigLIP loaded successfully on %s", _device)
        return True
    except ImportError as exc:
        logger.warning("[FashionEngine] open_clip/torch not installed — fashion embeddings disabled: %s", exc)
        return False
    except Exception as exc:
        logger.error("[FashionEngine] Failed to load marqo-FashionSigLIP: %s", exc)
        return False


class FashionEmbeddingEngine:
    """
    Generates 512-dimensional fashion embeddings using marqo-FashionSigLIP.

    Usage:
        engine = FashionEmbeddingEngine()
        result = engine.embed_product(
            title="Floral Maxi Dress",
            description="Lightweight chiffon dress with a floral print...",
            image_bytes=open("dress.jpg", "rb").read(),
        )
        # result = {"image_vector": [...], "text_vector": [...], "combined_vector": [...]}
    """

    VECTOR_DIM = 512

    def __init__(self):
        self._available = _load_fashion_model()

    @property
    def is_available(self) -> bool:
        return self._available and _fashion_model is not None

    def embed_image(self, image_bytes: bytes) -> list[float] | None:
        """
        Generate 512-dim fashion embedding from a product image.

        Args:
            image_bytes: Raw image bytes (JPEG, PNG, WebP)

        Returns:
            512-element list of floats (L2-normalized), or None if unavailable
        """
        if not self.is_available:
            return None
        try:
            import torch
            from PIL import Image

            image = Image.open(BytesIO(image_bytes)).convert("RGB")
            image_tensor = _fashion_preprocess(image).unsqueeze(0).to(_device)

            with torch.no_grad(), torch.amp.autocast("cuda" if str(_device) == "cuda" else "cpu"):
                features = _fashion_model.encode_image(image_tensor)
                features = features / features.norm(dim=-1, keepdim=True)  # L2-normalize

            return features.cpu().squeeze().tolist()
        except Exception as exc:
            logger.warning("[FashionEngine] embed_image failed: %s", exc)
            return None

    def embed_text(self, text: str) -> list[float] | None:
        """
        Generate 512-dim fashion embedding from product title/description.

        The FashionSigLIP text encoder understands fashion vocabulary:
        colors, fabrics, silhouettes, occasions, garment types.

        Args:
            text: Product title + description (up to 77 tokens)

        Returns:
            512-element list of floats (L2-normalized), or None if unavailable
        """
        if not self.is_available:
            return None
        try:
            import torch

            # Truncate to fit within model's context window (77 tokens)
            text = text[:400]
            tokens = _fashion_tokenizer([text]).to(_device)

            with torch.no_grad(), torch.amp.autocast("cuda" if str(_device) == "cuda" else "cpu"):
                features = _fashion_model.encode_text(tokens)
                features = features / features.norm(dim=-1, keepdim=True)

            return features.cpu().squeeze().tolist()
        except Exception as exc:
            logger.warning("[FashionEngine] embed_text failed: %s", exc)
            return None

    def embed_product(
        self,
        title: str,
        description: str = "",
        image_bytes: bytes | None = None,
    ) -> dict[str, list[float] | None]:
        """
        Generate combined product embedding (image + text weighted average).

        Weighting:
          - Image available: 60% image + 40% text (visual primacy for fashion)
          - Image unavailable: 100% text

        Args:
            title:       Product title (e.g., "Floral Maxi Dress")
            description: Product description (up to 300 chars used)
            image_bytes: Raw primary image bytes (optional)

        Returns:
            {
                "image_vector":    [...] or None,
                "text_vector":     [...] or None,
                "combined_vector": [...],   # Always present if text available
            }
        """
        text = f"{title}. {description}".strip(". ")
        text_vec = self.embed_text(text)
        img_vec  = self.embed_image(image_bytes) if image_bytes else None

        if text_vec and img_vec:
            # 60% image + 40% text — visual primacy for fashion
            combined_arr = np.array(img_vec) * 0.6 + np.array(text_vec) * 0.4
            norm = np.linalg.norm(combined_arr)
            if norm > 0:
                combined_arr = combined_arr / norm
            combined = combined_arr.tolist()
        elif text_vec:
            combined = text_vec
        elif img_vec:
            combined = img_vec
        else:
            combined = None

        return {
            "image_vector":    img_vec,
            "text_vector":     text_vec,
            "combined_vector": combined,
        }

    def embed_measurement_query(self, measurements: dict) -> list[float] | None:
        """
        Embed user measurements as a text query for fashion similarity search.

        Converts measurement profile into natural language that the fashion
        embedding model can match against product descriptions.

        Example output text:
          "Fashion clothing for person: height 175cm, bust 88cm, waist 72cm,
           hips 95cm, shoulder width 38cm, inseam 82cm"
        """
        parts = ["Fashion clothing for person:"]
        field_map = [
            ("height",         "height"),
            ("bust",           "bust"),
            ("waist",          "waist"),
            ("hips",           "hips"),
            ("shoulder_width", "shoulder width"),
            ("inseam",         "inseam"),
            ("thigh",          "thigh"),
            ("arm_length",     "arm length"),
        ]
        for field_key, label in field_map:
            val = measurements.get(field_key)
            if val is not None:
                parts.append(f"{label} {val}cm")

        text = " ".join(parts)
        return self.embed_text(text)
