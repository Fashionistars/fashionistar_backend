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

from django.conf import settings

logger = logging.getLogger(__name__)


def _get_ollama_client():
    """Lazy import of Ollama client to avoid startup errors if not installed."""
    try:
        # pyrefly: ignore [missing-import]
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

    # ── G4 Fix: Public alias + size chart loader ──────────────────────────────

    def generate_size_recommendation(
        self,
        measurements: dict,
        product_info: dict,
    ) -> str:
        """
        Public method called by ai_router.py get_size_advice endpoint.

        Loads the product size chart from ProductVariant, determines the best
        size algorithmically, then generates a natural-language explanation.

        Args:
            measurements: dict of {bust, waist, hips, shoulder_width, height, ...} in cm
            product_info: dict with {name, category, size_chart} — size_chart may be
                          pre-populated by the router or loaded here from DB.

        Returns:
            Human-readable size recommendation string.
        """
        # If router didn't supply size chart, try loading from DB
        size_chart = product_info.get("size_chart") or []
        product_id = product_info.get("product_id")
        if not size_chart and product_id:
            try:
                size_chart = self.load_product_size_chart(product_id)
            except Exception as exc:
                logger.debug("[generate_size_recommendation] size chart load failed: %s", exc)

        # Determine best size algorithmically using bust/waist/hips cascade
        recommended_size = self._pick_best_size(measurements, size_chart)

        # Format size chart for prompt context
        size_chart_dict: dict[str, str] = {}
        for entry in size_chart:
            label = entry.get("size", "")
            ranges = []
            if entry.get("bust_min") and entry.get("bust_max"):
                ranges.append(f"bust {entry['bust_min']}-{entry['bust_max']}cm")
            if entry.get("waist_min") and entry.get("waist_max"):
                ranges.append(f"waist {entry['waist_min']}-{entry['waist_max']}cm")
            if entry.get("hips_min") and entry.get("hips_max"):
                ranges.append(f"hips {entry['hips_min']}-{entry['hips_max']}cm")
            size_chart_dict[label] = ", ".join(ranges) if ranges else "see vendor chart"

        product_specs = size_chart_dict or {
            k: v for k, v in product_info.items()
            if k not in ("name", "category", "product_id", "size_chart")
        }

        return self.generate_size_recommendation_reasoning(
            measurements=measurements,
            product_specs=product_specs,
            recommended_size=recommended_size or "—",
        )

    @staticmethod
    def load_product_size_chart(product_id: int | str) -> list[dict]:
        """
        Load size chart rows from ProductVariant for a given product_id.

        Returns a list of dicts, each representing one size option:
            [{"size": "M", "bust_min": 86, "bust_max": 92, "waist_min": 70, ...}, ...]

        Gracefully returns [] if the product has no size variants or DB is unavailable.
        """
        try:
            from django.apps import apps
            ProductVariant = apps.get_model("product", "ProductVariant")
            variants = (
                ProductVariant.objects
                .filter(product_id=product_id, is_active=True)
                .values(
                    "size",
                    "bust_min", "bust_max",
                    "waist_min", "waist_max",
                    "hips_min", "hips_max",
                    "shoulder_min", "shoulder_max",
                )
                .order_by("size")
            )
            return list(variants)
        except Exception as exc:
            logger.debug("[load_product_size_chart] product_id=%s failed: %s", product_id, exc)
            return []

    @staticmethod
    def _pick_best_size(measurements: dict, size_chart: list[dict]) -> str | None:
        """
        Algorithmic size selection from ProductVariant size chart.

        Priority cascade: bust → waist → hips → shoulder_width
        Returns the size label (e.g. "M") or None if no chart available.
        """
        if not size_chart:
            return None

        bust  = measurements.get("bust")
        waist = measurements.get("waist")
        hips  = measurements.get("hips")

        def _in_range(val, lo, hi) -> bool:
            if val is None or lo is None or hi is None:
                return False
            return float(lo) <= float(val) <= float(hi)

        # Score each variant by how many measurement dimensions fit
        best_size  = None
        best_score = -1

        for variant in size_chart:
            score = 0
            if _in_range(bust,  variant.get("bust_min"),  variant.get("bust_max")):
                score += 3  # Bust is most reliable for tops/dresses
            if _in_range(waist, variant.get("waist_min"), variant.get("waist_max")):
                score += 2
            if _in_range(hips,  variant.get("hips_min"),  variant.get("hips_max")):
                score += 2
            if score > best_score:
                best_score = score
                best_size  = variant.get("size")

        return best_size


# ══════════════════════════════════════════════════════════════════════════════
# GroqLLMEngine — Production LLM for HF Spaces (replaces Ollama on ZeroGPU)
# ══════════════════════════════════════════════════════════════════════════════

class GroqLLMEngine:
    """
    Interface to Groq API — ultra-fast LLM inference via Groq LPU chips.

    Why Groq instead of Ollama on HF Spaces:
      - Ollama requires a persistent daemon (incompatible with HF cold-start)
      - Groq free tier: 14,400 req/day, Llama-3.3-70B-Versatile
      - Response time: <200ms (faster than local 7B on CPU)
      - Zero infrastructure — one API key, works from any container

    API: https://console.groq.com/keys
    Free tier: 14,400 requests/day (Llama-3.3-70B-Versatile)
    Paid tier: pay-per-token with no rate limit

    Implements the same public interface as OllamaLLMEngine for drop-in use:
      llm.generate(system, prompt) -> str
      llm.is_available() -> bool

    Domain methods inherit from OllamaLLMEngine by delegation to share
    prompt templates (size recommendation, analytics insights, etc).
    """

    def __init__(self):
        self.enabled   = getattr(settings, "GROQ_ENABLED", True)
        self.api_key   = getattr(settings, "GROQ_API_KEY", "")
        self.model     = getattr(settings, "GROQ_MODEL",   "llama-3.3-70b-versatile")
        self._client   = None

    @property
    def client(self):
        if self._client is None:
            if not self.api_key:
                return None
            try:
                from groq import Groq
                self._client = Groq(api_key=self.api_key)
            except ImportError:
                logger.debug("groq package not installed — Groq LLM disabled")
            except Exception as exc:
                logger.warning("Failed to create Groq client: %s", exc)
        return self._client

    def is_available(self) -> bool:
        """True if GROQ_API_KEY is set and the groq package is installed."""
        if not self.enabled or not self.api_key:
            return False
        return self.client is not None

    def generate(
        self,
        system: str,
        prompt: str,
        temperature: float = 0.3,
        max_tokens: int    = 500,
    ) -> str:
        """
        Generate text using Groq API.
        Returns empty string if Groq is unavailable (graceful degradation).
        """
        if not self.enabled:
            return ""
        client = self.client
        if client is None:
            return ""
        try:
            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user",   "content": prompt},
                ],
                max_tokens=max_tokens,
                temperature=temperature,
            )
            return response.choices[0].message.content.strip()
        except Exception as exc:
            logger.warning("[GroqLLMEngine] generate failed: %s", exc)
            return ""

    # ── Delegate domain methods to OllamaLLMEngine (shared prompt templates) ──

    def generate_size_recommendation_reasoning(
        self, measurements: dict, product_specs: dict, recommended_size: str
    ) -> str:
        return OllamaLLMEngine.generate_size_recommendation_reasoning(
            self, measurements, product_specs, recommended_size  # type: ignore[arg-type]
        )

    def generate_platform_insights(self, analytics_data: dict) -> str:
        return OllamaLLMEngine.generate_platform_insights(self, analytics_data)  # type: ignore[arg-type]

    def generate_measurement_advice(self, measurements: dict, quality_score: float) -> str:
        return OllamaLLMEngine.generate_measurement_advice(self, measurements, quality_score)  # type: ignore[arg-type]

    def generate_size_recommendation(self, measurements: dict, product_info: dict) -> str:
        return OllamaLLMEngine.generate_size_recommendation(self, measurements, product_info)  # type: ignore[arg-type]

    @staticmethod
    def load_product_size_chart(product_id: int | str) -> list[dict]:
        return OllamaLLMEngine.load_product_size_chart(product_id)

    @staticmethod
    def _format_measurements(m: dict) -> str:
        return OllamaLLMEngine._format_measurements(m)

    @staticmethod
    def _format_product_specs(specs: dict) -> str:
        return OllamaLLMEngine._format_product_specs(specs)

    @staticmethod
    def _pick_best_size(measurements: dict, size_chart: list[dict]) -> str | None:
        return OllamaLLMEngine._pick_best_size(measurements, size_chart)


def get_llm_engine():
    """
    Factory: returns the best available LLM engine using a four-provider waterfall.

    Priority (fastest/most-capable first):
      1. SambaNovLLMEngine — if SAMBANOVA_API_KEY set
         └─ RDU chips: ~4,000 tok/s for Llama-3.3-70B. Fastest large-model inference.
         └─ Get key: https://cloud.sambanova.ai/apis (free $5 credit)

      2. CerebrasLLMEngine — if CEREBRAS_API_KEY set
         └─ WSE-3 chips: ~2,000 tok/s, 1,000,000 tokens/day free.
         └─ Best for high-volume batch tasks (analytics, measurement advice).
         └─ Get key: https://cloud.cerebras.ai/ (free, no credit card)

      3. GroqLLMEngine — if GROQ_API_KEY set
         └─ LPU chips: ~300 tok/s, <200ms TTFT, 14,400 req/day free.
         └─ Best for real-time interactive responses.
         └─ Get key: https://console.groq.com/keys

      4. OllamaLLMEngine — local dev / self-hosted fallback
         └─ No rate limits, no cost. Works on any GPU/CPU.
         └─ Install: https://ollama.com/

    All engines implement the same interface, so callers need zero changes.

    Example:
        llm = get_llm_engine()
        text = llm.generate(system="You are a fashion advisor.", prompt="Recommend a size for 90/72/96cm.")
        print(text)  # <-- works with any provider
    """
    # 1. SambaNova (fastest)
    samba_key = getattr(settings, "SAMBANOVA_API_KEY", "")
    if samba_key:
        engine = SambaNovLLMEngine()
        if engine.is_available():
            logger.info("[get_llm_engine] ✅ Using SambaNovLLMEngine (model: %s, ~4000 tok/s)", engine.model)
            return engine

    # 2. Cerebras (highest free throughput)
    cerebras_key = getattr(settings, "CEREBRAS_API_KEY", "")
    if cerebras_key:
        engine = CerebrasLLMEngine()
        if engine.is_available():
            logger.info("[get_llm_engine] ✅ Using CerebrasLLMEngine (model: %s, ~2000 tok/s)", engine.model)
            return engine

    # 3. Groq (lowest latency per request)
    groq_key = getattr(settings, "GROQ_API_KEY", "")
    if groq_key:
        engine = GroqLLMEngine()
        if engine.is_available():
            logger.info("[get_llm_engine] ✅ Using GroqLLMEngine (model: %s, ~300 tok/s)", engine.model)
            return engine

    # 4. Ollama (local dev, self-hosted, no rate limit)
    logger.debug("[get_llm_engine] No cloud API keys set — using OllamaLLMEngine (local)")
    return OllamaLLMEngine()


# ══════════════════════════════════════════════════════════════════════════════
# SambaNova LLM Engine — Fastest large model inference (RDU chips)
# ══════════════════════════════════════════════════════════════════════════════

class SambaNovLLMEngine:
    """
    Interface to SambaNova Cloud — world's fastest inference for large models.

    Why SambaNova:
      - RDU (Reconfigurable Data Unit) chips: optimized for agentic, long-context tasks
      - Llama-4 Maverick (400B MoE, 17B active) at >600 tok/s
      - Llama-3.3-70B at >4,000 tok/s  — 13x faster than Groq
      - OpenAI-compatible API (just change base_url + api_key)
      - Free tier: $5 signup credit (no credit card), then pay-per-token

    Get key: https://cloud.sambanova.ai/apis
    Models available: Meta-Llama-3.3-70B-Instruct, Meta-Llama-4-Maverick, etc.
    """

    BASE_URL = "https://api.sambanova.ai/v1"

    def __init__(self):
        self.enabled = getattr(settings, "SAMBANOVA_ENABLED", False)
        self.api_key = getattr(settings, "SAMBANOVA_API_KEY", "")
        self.model   = getattr(settings, "SAMBANOVA_MODEL", "Meta-Llama-3.3-70B-Instruct")
        self._client = None

    @property
    def client(self):
        if self._client is None and self.api_key:
            try:
                from openai import OpenAI
                self._client = OpenAI(api_key=self.api_key, base_url=self.BASE_URL)
            except ImportError:
                logger.debug("openai package not installed — SambaNova disabled")
            except Exception as exc:
                logger.warning("SambaNova client init failed: %s", exc)
        return self._client

    def is_available(self) -> bool:
        if not self.enabled or not self.api_key:
            return False
        return self.client is not None

    def generate(
        self,
        system: str,
        prompt: str,
        temperature: float = 0.3,
        max_tokens: int    = 500,
    ) -> str:
        if not self.enabled:
            return ""
        client = self.client
        if client is None:
            return ""
        try:
            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user",   "content": prompt},
                ],
                max_tokens=max_tokens,
                temperature=temperature,
            )
            return response.choices[0].message.content.strip()
        except Exception as exc:
            logger.warning("[SambaNovLLMEngine] generate failed: %s", exc)
            return ""

    # Shared domain methods (delegate to OllamaLLMEngine prompt templates)
    def generate_size_recommendation_reasoning(self, measurements, product_specs, recommended_size):
        return OllamaLLMEngine.generate_size_recommendation_reasoning(self, measurements, product_specs, recommended_size)  # type: ignore[arg-type]

    def generate_platform_insights(self, analytics_data):
        return OllamaLLMEngine.generate_platform_insights(self, analytics_data)  # type: ignore[arg-type]

    def generate_measurement_advice(self, measurements, quality_score):
        return OllamaLLMEngine.generate_measurement_advice(self, measurements, quality_score)  # type: ignore[arg-type]

    def generate_size_recommendation(self, measurements, product_info):
        return OllamaLLMEngine.generate_size_recommendation(self, measurements, product_info)  # type: ignore[arg-type]

    @staticmethod
    def load_product_size_chart(product_id): return OllamaLLMEngine.load_product_size_chart(product_id)
    @staticmethod
    def _format_measurements(m): return OllamaLLMEngine._format_measurements(m)
    @staticmethod
    def _format_product_specs(specs): return OllamaLLMEngine._format_product_specs(specs)
    @staticmethod
    def _pick_best_size(measurements, size_chart): return OllamaLLMEngine._pick_best_size(measurements, size_chart)


# ══════════════════════════════════════════════════════════════════════════════
# Cerebras LLM Engine — Highest token throughput (WSE-3 chips)
# ══════════════════════════════════════════════════════════════════════════════

class CerebrasLLMEngine:
    """
    Interface to Cerebras Cloud — highest raw token throughput in 2026.

    Why Cerebras:
      - WSE-3 (Wafer Scale Engine): world's largest chip, optimized for AI
      - Llama-3.3-70B at ~2,000 tok/s — massive throughput for batch tasks
      - OpenAI-compatible API (just change base_url)
      - Free tier: 1,000,000 tokens/day (no credit card required)
      - Ideal for batch embedding tasks and long-context analytics

    Get key: https://cloud.cerebras.ai/
    Models: llama-3.3-70b, llama3.1-8b, llama-4-scout-17b-16e-instruct
    """

    BASE_URL = "https://api.cerebras.ai/v1"

    def __init__(self):
        self.enabled = getattr(settings, "CEREBRAS_ENABLED", False)
        self.api_key = getattr(settings, "CEREBRAS_API_KEY", "")
        self.model   = getattr(settings, "CEREBRAS_MODEL", "llama-3.3-70b")
        self._client = None

    @property
    def client(self):
        if self._client is None and self.api_key:
            try:
                from openai import OpenAI
                self._client = OpenAI(api_key=self.api_key, base_url=self.BASE_URL)
            except ImportError:
                logger.debug("openai package not installed — Cerebras disabled")
            except Exception as exc:
                logger.warning("Cerebras client init failed: %s", exc)
        return self._client

    def is_available(self) -> bool:
        if not self.enabled or not self.api_key:
            return False
        return self.client is not None

    def generate(
        self,
        system: str,
        prompt: str,
        temperature: float = 0.3,
        max_tokens: int    = 500,
    ) -> str:
        if not self.enabled:
            return ""
        client = self.client
        if client is None:
            return ""
        try:
            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user",   "content": prompt},
                ],
                max_tokens=max_tokens,
                temperature=temperature,
            )
            return response.choices[0].message.content.strip()
        except Exception as exc:
            logger.warning("[CerebrasLLMEngine] generate failed: %s", exc)
            return ""

    # Shared domain methods
    def generate_size_recommendation_reasoning(self, measurements, product_specs, recommended_size):
        return OllamaLLMEngine.generate_size_recommendation_reasoning(self, measurements, product_specs, recommended_size)  # type: ignore[arg-type]

    def generate_platform_insights(self, analytics_data):
        return OllamaLLMEngine.generate_platform_insights(self, analytics_data)  # type: ignore[arg-type]

    def generate_measurement_advice(self, measurements, quality_score):
        return OllamaLLMEngine.generate_measurement_advice(self, measurements, quality_score)  # type: ignore[arg-type]

    def generate_size_recommendation(self, measurements, product_info):
        return OllamaLLMEngine.generate_size_recommendation(self, measurements, product_info)  # type: ignore[arg-type]

    @staticmethod
    def load_product_size_chart(product_id): return OllamaLLMEngine.load_product_size_chart(product_id)
    @staticmethod
    def _format_measurements(m): return OllamaLLMEngine._format_measurements(m)
    @staticmethod
    def _format_product_specs(specs): return OllamaLLMEngine._format_product_specs(specs)
    @staticmethod
    def _pick_best_size(measurements, size_chart): return OllamaLLMEngine._pick_best_size(measurements, size_chart)
