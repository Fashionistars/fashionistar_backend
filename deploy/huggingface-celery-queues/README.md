---
title: FASHIONISTAR Celery Worker
emoji: ⚙️
colorFrom: purple
colorTo: indigo
sdk: docker
pinned: false
license: mit
app_port: 7860
short_description: FASHIONISTAR AI Fashion Platform — Celery Async Task Worker
---

# ⚙️ FASHIONISTAR AI — Celery Worker

**Background Async Task Processor for the FASHIONISTAR AI Fashion Platform**

## Queues Handled

| Queue | Description |
|-------|-------------|
| `default` | General asynchronous tasks |
| `ai_tasks` | AI/ML body measurement processing fallback |
| `measurements` | Body measurement computation and logs |
| `analytics` | Reporting, aggregation, and usage metrics |
| `notifications` | Transactional emails (Brevo/Zoho/Mailgun) and SMS (Twilio/Termii) |
| `webhooks` | Incoming Stripe & Cloudinary webhook reconciliation |

## Deployment Constraints (Hugging Face)

- Runs a background health-check HTTP server on port 7860 to satisfy Space runtime constraints.
- Restarts gracefully if Celery crashes.
- Uses CPU Basic instance (16GB RAM).
