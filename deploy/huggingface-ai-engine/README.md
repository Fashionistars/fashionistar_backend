---
title: FASHIONISTAR AI Engine
emoji: 🤖
colorFrom: purple
colorTo: pink
sdk: gradio
sdk_version: "5.37.0"
app_file: app.py
pinned: true
license: mit
short_description: ZeroGPU AI Engine — Fashion AI & Body Measurements
hardware: zero-gpu
---

# 🤖 FASHIONISTAR AI Engine

**ZeroGPU-powered AI/ML inference for the FASHIONISTAR Fashion Platform**

This space runs all GPU-intensive AI tasks:
- 📏 **Body Measurements** — MediaPipe + SigLIP pose estimation
- 🎨 **Fashion Embeddings** — CLIP/SigLIP image understanding  
- 🔍 **Visual Search** — Semantic fashion item lookup
- 🧠 **LLM Inference** — Llama 3.2 via Groq for style advice
- 📊 **Recommendation Engine** — AI-driven product recommendations

## API Endpoints

| Endpoint | Description |
|---|---|
| `POST /measurements` | Body measurement extraction from image |
| `POST /embeddings` | Fashion item embeddings |
| `POST /search` | Visual fashion search |
| `GET /health` | AI service health check |

## Architecture

```
fashionistar-api-v2 (CPU Docker)
         ↓ dispatches AI tasks
fashionistar-celery-queues (ZeroGPU Gradio)
         ↓ calls AI engine
fashionistar-ai-engine (ZeroGPU Gradio) ← THIS SPACE
```
