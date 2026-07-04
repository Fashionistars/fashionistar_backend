---
title: FASHIONISTAR Celery Beat
emoji: ⏱️
colorFrom: purple
colorTo: red
sdk: docker
pinned: false
license: mit
app_port: 7860
short_description: FASHIONISTAR AI Fashion Platform — Celery Beat Scheduler
---

# ⏱️ FASHIONISTAR AI — Celery Beat Scheduler

**Periodic Task Scheduler for the FASHIONISTAR AI Fashion Platform**

## Operations Handled

- Triggers periodic cleanup of expired verification pings, locks, and logs.
- Triggers SMTP and SMS provider health verification audits.
- Schedules data aggregation, reporting pipelines, and cache warming.

## Deployment Constraints (Hugging Face)

- Runs a background health-check HTTP server on port 7860 to satisfy Space runtime constraints.
- Restarts gracefully if Celery Beat scheduler crashes.
- Uses CPU Basic instance (16GB RAM).
