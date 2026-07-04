# FASHIONISTAR — Northflank Celery Services

## Service Definitions

This directory contains Northflank service configuration for FASHIONISTAR's background task workers.

### Services

| Service | Type | Purpose |
|---------|------|---------|
| `fashionistar-celery-worker` | Deployment Service | Celery task workers |
| `fashionistar-celery-beat` | Deployment Service | Celery Beat scheduler |

### Requirements

- Northflank Team: `fashionistars-team`
- Northflank Project: `fashionistar`
- GitHub Repo: `Fashionistars/fashionistar_backend`
- Dockerfile: `Dockerfile.celery`
- Secret Group: `fashionistar-secrets`

### Celery Queues

The worker handles these queues:
- `default` — General async tasks
- `ai_tasks` — AI/ML body measurement computation
- `measurements` — Body measurement processing
- `analytics` — Reporting & aggregation
- `notifications` — Email / SMS / Push
- `webhooks` — Incoming webhook processing

### Environment Variables

All production env vars are loaded from the `fashionistar-secrets` secret group.
Additional per-service vars:
- `CELERY_CONCURRENCY=4`
- `NORTHFLANK_SERVICE_ID=fashionistar-celery-worker`

### Dashboard

https://app.northflank.com/t/fashionistars-team/project/fashionistar
