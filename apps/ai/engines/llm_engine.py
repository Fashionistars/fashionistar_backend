# apps/ai/engines/llm_engine.py
"""
Ollama LLM Engine — Self-hosted AI reasoning for FASHIONISTAR.

Zero cost. Full data privacy. No external APIs.

Setup:
  1. Install Ollama: https://ollama.ai/
  2. Pull a model: `ollama pull llama3.2:3b`  (CPU-friendly, 2GB RAM)
     Or for better quality: `ollama pull mistral:7b-instruct` (GPU)
  3. Set OLLAMA_HOST in settings (default: http://localhost:11434)
  4. Set OLLAMA_MODEL in settings (default: llama3.2:3b)

Models by use case:
  - Fast reasoning (CPU):     llama3.2:3b      ~2GB RAM
  - Better quality (CPU):     mistral:7b-instruct  ~5GB RAM
  - Best quality (GPU req):   llama3.1:8b      ~6GB VRAM
  - Text embeddings:          nomic-embed-text ~550MB RAM

Graceful degradation:
  If Ollama is not available, all methods return None / empty strings.
  The AI engine will still function — LLM features just produce no output.
"""

from __future__ import annotations

import logging
from typing import Any

from django.conf import settings

logger = logging.getLogger(__name__)


def _get_ollama_client():
    """Lazy import of Ollama client to avoid startup errors if not installed."""
    try:
        import ollama
        host = getattr(settings, "OLLAMA_HOST", "http://localhost:11434")
        return ollama.Client(host=host)
    except ImportError:
        logger.debug("ollama package not installed — LLM features disabled")
        return None
    except Exception as exc:
        logger.warning("Failed to create Ollama client: %s", exc)
        return None


class OllamaLLMEngine:
    """
    Interface to the self-hosted Ollama LLM service.

    All methods degrade gracefully if Ollama is unavailable.
    Use OLLAMA_ENABLED = False in settings to disable entirely.

    Usage:
        llm = OllamaLLMEngine()
        text = llm.generate(
            system="You are a fashion expert.",
            prompt="Recommend a size for someone with bust 90cm."
        )
    """

    def __init__(self):
        self.enabled = getattr(settings, "OLLAMA_ENABLED", True)
        self.model   = getattr(settings, "OLLAMA_MODEL",   "llama3.2:3b")
        self.embed_model = getattr(settings, "OLLAMA_EMBED_MODEL", "nomic-embed-text")
        self._client = None

    @property
    def client(self):
        if self._client is None:
            self._client = _get_ollama_client()
        return self._client

    def is_available(self) -> bool:
        """Check if Ollama is reachable. Uses a lightweight ping."""
        if not self.enabled:
            return False
        try:
            client = self.client
            if client is None:
                return False
            client.list()  # Lists available models — fast ping
            return True
        except Exception:
            return False

    def generate(
        self,
        system: str,
        prompt: str,
        temperature: float = 0.3,
        max_tokens: int = 500,
    ) -> str:
        """
        Generate text using the Ollama LLM.

        Returns empty string if Ollama is unavailable (graceful degradation).

        Args:
            system: System prompt defining the LLM's role
            prompt: User prompt
            temperature: 0.0-1.0 (lower = more deterministic, better for size advice)
            max_tokens: Maximum response length

        Returns:
            Generated text string, or "" if unavailable
        """
        if not self.enabled:
            return ""

        try:
            client = self.client
            if client is None:
                return ""

            response = client.chat(
                model=self.model,
                messages=[
                    {"role": "system",  "content": system},
                    {"role": "user",    "content": prompt},
                ],
                options={
                    "temperature": temperature,
                    "num_predict":  max_tokens,
                },
            )
            return response.get("message", {}).get("content", "").strip()
        except Exception as exc:
            logger.warning("[OllamaLLMEngine] generate failed: %s", exc)
            return ""

    def embed(self, text: str) -> list[float] | None:
        """
        Generate text embeddings using nomic-embed-text via Ollama.

        Used for RAG: embed user queries to retrieve similar content.
        Returns None if unavailable.
        """
        if not self.enabled:
            return None

        try:
            client = self.client
            if client is None:
                return None

            response = client.embeddings(
                model=self.embed_model,
                prompt=text,
            )
            return response.get("embedding")
        except Exception as exc:
            logger.warning("[OllamaLLMEngine] embed failed: %s", exc)
            return None

    # ── Domain-specific generation methods ────────────────────────────────────

    def generate_size_recommendation_reasoning(
        self,
        measurements: dict,
        product_specs: dict,
        recommended_size: str,
    ) -> str:
        """
        Generate a human-readable explanation for the recommended size.

        Shown to the customer in the UI. Example output:
        "We recommend size M because your bust measurement (88cm) fits
        comfortably within the M range (86-92cm), and your waist (72cm)
        is true-to-size for this garment's M cut."
        """
        system = (
            "You are a professional fashion stylist and sizing expert. "
            "Always be friendly, concise, and specific. "
            "Never recommend the customer measure themselves — we already have their data. "
            "Focus on why the specific size fits best."
        )
        prompt = f"""
A customer has these body measurements:
{self._format_measurements(measurements)}

This product's size chart:
{self._format_product_specs(product_specs)}

We are recommending size: {recommended_size}

In 2-3 sentences, explain specifically why {recommended_size} is the best fit.
Reference specific measurements from their profile. Be warm and confident.
"""
        return self.generate(system, prompt, temperature=0.3, max_tokens=200)

    def generate_platform_insights(self, analytics_data: dict) -> str:
        """
        Generate business intelligence insights from platform analytics data.
        Used by the AnalyticsWorkflow for admin dashboard.
        """
        system = (
            "You are a senior fashion e-commerce business analyst. "
            "Provide clear, actionable insights. "
            "Be specific with numbers. Keep insights concise."
        )
        prompt = f"""
Analyse this FASHIONISTAR platform data and provide exactly 5 numbered actionable insights:

Platform Data:
{analytics_data}

Format: numbered list, each insight on its own line, max 2 sentences each.
"""
        return self.generate(system, prompt, temperature=0.4, max_tokens=600)

    def generate_measurement_advice(self, measurements: dict, quality_score: float) -> str:
        """
        Generate advice for the user after their AI body scan.
        Encourages corrections for low-quality measurements.
        """
        system = (
            "You are a helpful fashion measurement assistant. "
            "Be encouraging and specific. Never alarm the user."
        )

        if quality_score >= 0.8:
            prompt = f"""
A customer just completed their AI body scan with {int(quality_score * 100)}% confidence.
Their measurements: {self._format_measurements(measurements)}

In 2 sentences, congratulate them and highlight 1 key measurement that will help them shop.
"""
        else:
            prompt = f"""
A customer completed their AI body scan with {int(quality_score * 100)}% confidence (lower than ideal).
Their measurements: {self._format_measurements(measurements)}

In 2 sentences, encourage them and suggest 1 specific thing to improve accuracy next time
(e.g., better lighting, standing straighter, wearing fitted clothing).
"""
        return self.generate(system, prompt, temperature=0.4, max_tokens=150)

    # ── Formatting helpers ─────────────────────────────────────────────────────

    @staticmethod
    def _format_measurements(m: dict) -> str:
        lines = []
        field_names = {
            "bust": "Bust", "waist": "Waist", "hips": "Hips",
            "shoulder_width": "Shoulder Width", "inseam": "Inseam",
            "arm_length": "Arm Length", "thigh": "Thigh",
            "height": "Height", "weight_kg": "Weight",
        }
        for key, label in field_names.items():
            if m.get(key) is not None:
                unit = "kg" if key == "weight_kg" else "cm"
                lines.append(f"  {label}: {m[key]}{unit}")
        return "\n".join(lines) if lines else "  No measurements available"

    @staticmethod
    def _format_product_specs(specs: dict) -> str:
        if not specs:
            return "  No size chart available"
        lines = [f"  {size}: {details}" for size, details in specs.items()]
        return "\n".join(lines)
