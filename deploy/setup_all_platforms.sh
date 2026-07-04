#!/usr/bin/env bash
# =============================================================================
# FASHIONISTAR — GitHub + Northflank + Hugging Face Setup Script
# =============================================================================
# This script:
#   1. Authenticates GitHub CLI with your PAT
#   2. Sets all required GitHub Secrets for CI/CD pipelines
#   3. Creates Northflank services via REST API
#   4. Pushes code to GitHub (triggers deployment pipelines)
#
# Usage:
#   export GITHUB_PAT="github_pat_..."
#   export NORTHFLANK_API_TOKEN="nf-..."
#   export HF_TOKEN="hf_..."
#   bash deploy/setup_all_platforms.sh
# =============================================================================

set -o errexit
set -o pipefail

# ── Credentials (Set via environment variables — DO NOT hardcode secrets) ─────
# Required: set these before running this script
: "${GITHUB_PAT:?ERROR: Set GITHUB_PAT environment variable before running}"
: "${NORTHFLANK_API_TOKEN:?ERROR: Set NORTHFLANK_API_TOKEN environment variable before running}"
: "${HF_TOKEN:?ERROR: Set HF_TOKEN environment variable before running}"

GITHUB_REPO="${GITHUB_REPO:-Fashionistars/fashionistar_backend}"
NORTHFLANK_PROJECT_ID="${NORTHFLANK_PROJECT_ID:-fashionistar}"
NORTHFLANK_TEAM_ID="${NORTHFLANK_TEAM_ID:-fashionistars-team}"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

log_info()    { echo -e "${GREEN}[✓] $*${NC}"; }
log_warn()    { echo -e "${YELLOW}[!] $*${NC}"; }
log_error()   { echo -e "${RED}[✗] $*${NC}"; }
log_section() { echo -e "\n${BOLD}${CYAN}══ $* ══${NC}"; }

# ═════════════════════════════════════════════════════════════════════════════
log_section "STEP 1: GitHub CLI Authentication"
# ═════════════════════════════════════════════════════════════════════════════

# Authenticate GitHub CLI with PAT
echo "$GITHUB_PAT" | gh auth login --with-token
log_info "GitHub CLI authenticated"

# Verify auth
gh auth status

# ═════════════════════════════════════════════════════════════════════════════
log_section "STEP 2: Set GitHub Repository Secrets"
# ═════════════════════════════════════════════════════════════════════════════

REPO="$GITHUB_REPO"

log_info "Setting HF_TOKEN secret..."
gh secret set HF_TOKEN --body "$HF_TOKEN" --repo "$REPO"

log_info "Setting NORTHFLANK_API_KEY secret..."
gh secret set NORTHFLANK_API_KEY --body "$NORTHFLANK_API_TOKEN" --repo "$REPO"

log_info "Setting NORTHFLANK_PROJECT_ID secret..."
gh secret set NORTHFLANK_PROJECT_ID --body "$NORTHFLANK_PROJECT_ID" --repo "$REPO"

log_info "Setting NORTHFLANK_TEAM_ID secret..."
gh secret set NORTHFLANK_TEAM_ID --body "$NORTHFLANK_TEAM_ID" --repo "$REPO"

log_info "All GitHub secrets set!"

# ═════════════════════════════════════════════════════════════════════════════
log_section "STEP 3: Get Northflank Project Details"
# ═════════════════════════════════════════════════════════════════════════════

# List current Northflank services
log_info "Listing current Northflank services..."
curl -s \
  -H "Authorization: Bearer ${NORTHFLANK_API_TOKEN}" \
  "https://api.northflank.com/v1/projects/${NORTHFLANK_PROJECT_ID}/services" \
  | python3 -c "import sys,json; data=json.load(sys.stdin); [print(f'  - {s[\"name\"]} ({s[\"status\"]})') for s in data.get('data',{}).get('services',[])]" 2>/dev/null || true

# ═════════════════════════════════════════════════════════════════════════════
log_section "STEP 4: Create Northflank Secret Group (fashionistar-secrets)"
# ═════════════════════════════════════════════════════════════════════════════

log_info "Creating/updating Northflank secret group with production env vars..."

# Read all env vars from production.env and format as JSON array
ENV_FILE="fashionistar_backend_production.env"
if [ -f "$ENV_FILE" ]; then
  SECRETS_JSON=$(python3 -c "
import json
secrets = []
with open('$ENV_FILE') as f:
    for line in f:
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if '=' in line:
            key, _, value = line.partition('=')
            key = key.strip()
            value = value.strip().strip('\"')
            secrets.append({'key': key, 'value': value})
print(json.dumps(secrets))
")
  
  # Create/update secret group
  RESPONSE=$(curl -s -w "\n%{http_code}" -X POST \
    -H "Authorization: Bearer ${NORTHFLANK_API_TOKEN}" \
    -H "Content-Type: application/json" \
    -d "{
      \"name\": \"fashionistar-secrets\",
      \"description\": \"FASHIONISTAR production environment variables\",
      \"secretType\": \"environment\",
      \"secrets\": {\"variables\": ${SECRETS_JSON}}
    }" \
    "https://api.northflank.com/v1/projects/${NORTHFLANK_PROJECT_ID}/secret-groups")

  HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
  BODY=$(echo "$RESPONSE" | head -n -1)
  
  if [ "$HTTP_CODE" -eq 200 ] || [ "$HTTP_CODE" -eq 201 ]; then
    log_info "Secret group created/updated (HTTP $HTTP_CODE)"
  else
    log_warn "Secret group response: HTTP $HTTP_CODE"
    log_warn "Body: $BODY"
    log_warn "The secret group may already exist — continuing..."
  fi
fi

# ═════════════════════════════════════════════════════════════════════════════
log_section "STEP 5: Create Northflank Celery Worker Service"
# ═════════════════════════════════════════════════════════════════════════════

log_info "Creating fashionistar-celery-worker service on Northflank..."

WORKER_RESPONSE=$(curl -s -w "\n%{http_code}" -X POST \
  -H "Authorization: Bearer ${NORTHFLANK_API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "fashionistar-celery-worker",
    "description": "FASHIONISTAR Celery Worker — AI/ML, notifications, webhooks",
    "billing": {"deploymentPlan": "nf-compute-10"},
    "deployment": {
      "buildpack": {
        "id": "dockerfile",
        "dockerfile": "/Dockerfile.celery",
        "context": "/",
        "buildArguments": {}
      },
      "internal": {
        "nfObjectId": "Fashionistars/fashionistar_backend",
        "branch": "main",
        "buildSHA": "latest"
      }
    },
    "ports": [],
    "runtimeEnvironment": {
      "from": [{"secretRef": {"id": "fashionistar-secrets"}}],
      "variables": [
        {"key": "CELERY_CONCURRENCY", "value": "4"},
        {"key": "CELERY_QUEUES", "value": "default,ai_tasks,measurements,analytics,notifications,webhooks"},
        {"key": "NORTHFLANK_SERVICE_ID", "value": "fashionistar-celery-worker"}
      ]
    }
  }' \
  "https://api.northflank.com/v1/projects/${NORTHFLANK_PROJECT_ID}/services/deployment")

WORKER_HTTP=$(echo "$WORKER_RESPONSE" | tail -n1)
WORKER_BODY=$(echo "$WORKER_RESPONSE" | head -n -1)

if [ "$WORKER_HTTP" -eq 200 ] || [ "$WORKER_HTTP" -eq 201 ]; then
  log_info "Celery worker service created (HTTP $WORKER_HTTP)"
else
  log_warn "Worker creation response: HTTP $WORKER_HTTP"
  log_warn "$WORKER_BODY"
fi

# ═════════════════════════════════════════════════════════════════════════════
log_section "STEP 6: Create Northflank Celery Beat Service"
# ═════════════════════════════════════════════════════════════════════════════

log_info "Creating fashionistar-celery-beat service on Northflank..."

BEAT_RESPONSE=$(curl -s -w "\n%{http_code}" -X POST \
  -H "Authorization: Bearer ${NORTHFLANK_API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "fashionistar-celery-beat",
    "description": "FASHIONISTAR Celery Beat — periodic task scheduler",
    "billing": {"deploymentPlan": "nf-compute-10"},
    "deployment": {
      "buildpack": {
        "id": "dockerfile",
        "dockerfile": "/Dockerfile.celery",
        "context": "/",
        "buildArguments": {}
      },
      "internal": {
        "nfObjectId": "Fashionistars/fashionistar_backend",
        "branch": "main",
        "buildSHA": "latest"
      }
    },
    "runtimeCommand": {"cmd": ["celery-beat"]},
    "runtimeEnvironment": {
      "from": [{"secretRef": {"id": "fashionistar-secrets"}}],
      "variables": [
        {"key": "NORTHFLANK_SERVICE_ID", "value": "fashionistar-celery-beat"}
      ]
    }
  }' \
  "https://api.northflank.com/v1/projects/${NORTHFLANK_PROJECT_ID}/services/deployment")

BEAT_HTTP=$(echo "$BEAT_RESPONSE" | tail -n1)
BEAT_BODY=$(echo "$BEAT_RESPONSE" | head -n -1)

if [ "$BEAT_HTTP" -eq 200 ] || [ "$BEAT_HTTP" -eq 201 ]; then
  log_info "Celery beat service created (HTTP $BEAT_HTTP)"
else
  log_warn "Beat creation response: HTTP $BEAT_HTTP"
  log_warn "$BEAT_BODY"
fi

# ═════════════════════════════════════════════════════════════════════════════
log_section "STEP 7: Push Code to GitHub (Triggers All CI/CD)"
# ═════════════════════════════════════════════════════════════════════════════

# Add and commit all new files
git add -A
git status

# Commit the new platform files
git commit -m "feat(deploy): multi-platform deployment architecture

- Dynamic entrypoint.sh (auto-detects HF/Northflank/Render/Oracle)  
- Dockerfile.production updated for Hugging Face Spaces (port 7860)
- Dockerfile.celery updated for Northflank workers
- deploy/huggingface/ — HF Spaces platform config
- deploy/northflank/ — Northflank service definitions
- .github/workflows/deploy-hf.yml — Hugging Face CI/CD pipeline" || true

# Push to GitHub main (triggers CI/CD pipelines)
git push origin main

log_info "Code pushed to GitHub! CI/CD pipelines are now triggered."

# ═════════════════════════════════════════════════════════════════════════════
log_section "✅ DEPLOYMENT INITIATED — Summary"
# ═════════════════════════════════════════════════════════════════════════════

echo ""
echo "  🤗 Hugging Face API:"
echo "     URL: https://fashionistar-fashionistar-api-v2.hf.space"
echo "     Health: https://fashionistar-fashionistar-api-v2.hf.space/api/v1/health/"
echo "     Status: https://huggingface.co/spaces/fashionistar/fashionistar-api-v2"
echo ""
echo "  🔷 Northflank Celery Worker:"
echo "     Dashboard: https://app.northflank.com/t/fashionistars-team/project/fashionistar"
echo "     Service: fashionistar-celery-worker"
echo ""
echo "  🔷 Northflank Celery Beat:"
echo "     Dashboard: https://app.northflank.com/t/fashionistars-team/project/fashionistar"
echo "     Service: fashionistar-celery-beat"
echo ""
echo "  🔁 GitHub Actions:"
echo "     CI/CD: https://github.com/$GITHUB_REPO/actions"
echo ""
