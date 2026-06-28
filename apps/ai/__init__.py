# apps/ai/__init__.py
"""
FASHIONISTAR AI Orchestration Engine.

This app is the central AI brain for the FASHIONISTAR platform.
It has READ access to all 24 Django apps via FashionistarDatabaseLayer.

Sub-systems:
  - Measurement Engine: MediaPipe Python server-side validation + anthropometric geometry
  - Recommendation Engine: marqo-FashionSigLIP + pgvector HNSW similarity search
  - Analytics Engine: LangGraph workflows + Ollama LLM for business intelligence
  - Ingestion Pipeline: Django signals → Celery → real-time AI data freshness

All heavy computation runs in Celery workers (never in the request/response cycle).
Django Ninja reads: /api/v1/ninja/ai/
DRF writes: /api/v1/measurements/scan/
"""
