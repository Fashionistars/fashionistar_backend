---
title: FASHIONISTAR API Gateway v1
emoji: 🎀
colorFrom: purple
colorTo: pink
sdk: docker
pinned: true
license: mit
app_port: 7860
short_description: FASHIONISTAR AI Fashion Platform — Django ASGI API Gateway
---

# 🎀 FASHIONISTAR AI — Django API Gateway (v1)

**Production ASGI Backend for the FASHIONISTAR AI Fashion Platform**

## Architecture

This space runs the **Django 6.0 LTS API Gateway** using:
- **Gunicorn** with **Uvicorn** async workers (ASGI)
- **Django Ninja** for async REST endpoints
- **Django REST Framework** for sync endpoints
- **PostgreSQL 17** (Neon Serverless, async psycopg)
- **Redis** (Aiven, for session cache + Celery broker)

## Companion Spaces

| Space | Role | Hardware |
|---|---|---|
| `fashionistar/fashionistar-api-v1` | **This space** — API Gateway | CPU (16GB) |
| `fashionistar/fashionistar-celery-beat` | Task scheduler | CPU (16GB) |
| `fashionistar/fashionistar-celery-queues` | AI task workers | ZeroGPU |
| `fashionistar/fashionistar-ai-engine` | ML models (MediaPipe, SigLIP) | ZeroGPU |

## Health Check

```
GET https://fashionistar-fashionistar-api-v1.hf.space/api/v1/health/
```

## API Documentation

```
GET https://fashionistar-fashionistar-api-v1.hf.space/api/docs/
```
