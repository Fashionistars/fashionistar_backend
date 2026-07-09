# apps/ai/engines/__init__.py
"""
AI Engine modules — clean public exports.

Multi-Provider LLM (auto-selected via get_llm_engine()):
    SambaNovLLMEngine  ← Fastest: ~4,000 tok/s RDU chips (SAMBANOVA_API_KEY)
    CerebrasLLMEngine  ← Throughput: ~2,000 tok/s WSE-3, 1M tok/day free (CEREBRAS_API_KEY)
    GroqLLMEngine      ← Latency: ~300 tok/s LPU, <200ms TTFT (GROQ_API_KEY)
    OllamaLLMEngine    ← Local dev fallback, no rate limits

ZeroGPU (HF Spaces):
    from apps.ai.engines.zerogpu_engine import (
        initialize_models, extract_body_measurements,
        generate_fashion_embedding, generate_llm_response, health_check
    )

Server-side validation (Django):
    from apps.ai.engines.measurement_engine import MeasurementEngine
    from apps.ai.engines.llm_engine import get_llm_engine
    from apps.ai.engines.recommendation_engine import generate_product_embedding
"""

from apps.ai.engines.llm_engine import (
    OllamaLLMEngine,
    GroqLLMEngine,
    SambaNovLLMEngine,
    CerebrasLLMEngine,
    get_llm_engine,
)

__all__ = [
    "OllamaLLMEngine",
    "GroqLLMEngine",
    "SambaNovLLMEngine",
    "CerebrasLLMEngine",
    "get_llm_engine",
]
