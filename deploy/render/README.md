# Render.com Deployment Configuration

This directory contains the Render Blueprint specification for the FASHIONISTAR platform.

## Services Configured

1. **Django Web Service (`fashionistar-backend-free`)**
   - **Environment**: Python
   - **Build Command**: `pip install uv && uv sync && uv run python manage.py collectstatic --noinput`
   - **Start Command**: `./start.sh` or `./entrypoint.sh`
   - **Port**: 10000

2. **Celery Worker & Beat**
   - Fully documented within `render.yaml` for production-ready setups (using separate containers and resources).

## Deployment

To deploy on Render:
1. Log in to dashboard.render.com.
2. Click **New** → **Blueprint**.
3. Connect your GitHub repository.
4. Point to `deploy/render/render.yaml` as the blueprint file.
5. Fill in the required environment variables in the Render console.
