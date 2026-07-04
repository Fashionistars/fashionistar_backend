---
title: FASHIONISTAR API Gateway
emoji: 👗
colorFrom: purple
colorTo: pink
sdk: docker
pinned: true
license: mit
app_port: 7860
short_description: FASHIONISTAR AI Fashion Platform — Django ASGI API
---

# 🎀 FASHIONISTAR AI — Django API Gateway

**Production ASGI Backend for the FASHIONISTAR AI Fashion Platform**

## API Endpoints

| Endpoint | Description |
|----------|-------------|
| `/api/v1/health/` | Health check |
| `/api/v1/products/` | Product catalogue |
| `/api/v1/measurements/` | AI body measurements |
| `/api/v1/orders/` | Order management |
| `/api/docs/` | OpenAPI Swagger UI |
| `/api/ninja/` | High-performance async endpoints |

## Tech Stack

- **Framework**: Django 6.0 LTS + Django Ninja (ASGI)
- **Server**: Gunicorn + UvicornWorker (3 workers)
- **Database**: Neon Serverless PostgreSQL 17
- **Cache/Queue**: Redis (Northflank)
- **Storage**: Cloudinary (media files)
- **Auth**: JWT + Google OAuth

## Status

- 🟢 **API**: Running on port 7860
- 🟢 **Celery Worker**: Hosted on Northflank
- 🟢 **Celery Beat**: Hosted on Northflank
