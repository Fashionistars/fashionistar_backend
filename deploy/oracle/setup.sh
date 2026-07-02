#!/bin/bash
# ============================================================================
# FASHIONISTAR — Oracle Cloud VM Initial Setup Script
# ============================================================================
# Run this ONCE on a fresh Oracle Cloud VM.Standard.A1.Flex instance
# Target OS: Ubuntu 22.04 LTS (ARM64)
#
# Usage:
#   ssh ubuntu@<ORACLE_IP>
#   curl -fsSL https://raw.githubusercontent.com/FASHIONISTAR-CLOTHINGS/fashionistar_backend/main/deploy/oracle/setup.sh | bash
# ============================================================================

set -euo pipefail
export DEBIAN_FRONTEND=noninteractive

REPO_URL="https://github.com/FASHIONISTAR-CLOTHINGS/fashionistar_backend.git"
APP_DIR="/home/ubuntu/fashionistar_backend"

echo "============================================="
echo "  FASHIONISTAR Oracle Cloud VM Setup"
echo "  ARM64 / Ubuntu 22.04 LTS"
echo "============================================="

# ── Step 1: System Update ────────────────────────────────────────────────────
echo "📦 [1/12] Updating system packages..."
sudo apt-get update -qq
sudo apt-get upgrade -y -qq
sudo apt-get autoremove -y -qq

# ── Step 2: Core Dependencies ────────────────────────────────────────────────
echo "📦 [2/12] Installing core dependencies..."
sudo apt-get install -y -qq \
    curl \
    wget \
    git \
    htop \
    ufw \
    fail2ban \
    unzip \
    jq \
    certbot \
    python3-certbot-nginx \
    logrotate

# ── Step 3: Docker (ARM64 compatible) ───────────────────────────────────────
echo "🐳 [3/12] Installing Docker (ARM64)..."
if ! command -v docker &> /dev/null; then
    curl -fsSL https://get.docker.com | sh
    sudo usermod -aG docker ubuntu
    sudo systemctl enable docker
    sudo systemctl start docker
else
    echo "  Docker already installed: $(docker --version)"
fi

# ── Step 4: Docker Compose Plugin ────────────────────────────────────────────
echo "🐳 [4/12] Verifying Docker Compose..."
docker compose version || sudo apt-get install -y docker-compose-plugin

# ── Step 5: UFW Firewall Configuration ──────────────────────────────────────
echo "🔒 [5/12] Configuring UFW firewall..."
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow ssh           # Port 22
sudo ufw allow 80/tcp        # HTTP
sudo ufw allow 443/tcp       # HTTPS
sudo ufw allow 6379/tcp      # Redis (Northflank Celery workers connect here)
# WARNING: For extra security, restrict Redis port to Northflank IP ranges only:
# sudo ufw allow from <NORTHFLANK_IP_RANGE> to any port 6379
echo "y" | sudo ufw enable
sudo ufw status verbose

# ── Step 6: fail2ban (Brute force protection) ────────────────────────────────
echo "🔒 [6/12] Configuring fail2ban..."
sudo systemctl enable fail2ban
sudo systemctl start fail2ban

# ── Step 7: Log Directories ──────────────────────────────────────────────────
echo "📁 [7/12] Creating log directories..."
sudo mkdir -p /var/log/fashionistar/api
sudo mkdir -p /var/log/fashionistar/nginx
sudo mkdir -p /var/log/fashionistar/celery    # For reference (Celery logs on Northflank)
sudo chown -R ubuntu:ubuntu /var/log/fashionistar

# Configure logrotate for API logs
sudo tee /etc/logrotate.d/fashionistar > /dev/null <<'EOF'
/var/log/fashionistar/api/*.log {
    daily
    rotate 14
    compress
    delaycompress
    missingok
    notifempty
    create 0644 ubuntu ubuntu
    postrotate
        docker kill --signal HUP fashionistar_api 2>/dev/null || true
    endscript
}

/var/log/fashionistar/nginx/*.log {
    daily
    rotate 14
    compress
    delaycompress
    missingok
    notifempty
    create 0644 ubuntu ubuntu
    postrotate
        docker kill --signal HUP fashionistar_nginx 2>/dev/null || true
    endscript
}
EOF

# ── Step 8: Clone Repository ─────────────────────────────────────────────────
echo "📥 [8/12] Cloning FASHIONISTAR backend repository..."
if [ -d "$APP_DIR" ]; then
    echo "  Repo already exists — pulling latest..."
    cd "$APP_DIR" && git pull origin main
else
    git clone "$REPO_URL" "$APP_DIR"
fi
cd "$APP_DIR"

# ── Step 9: Environment File ─────────────────────────────────────────────────
echo "⚙️  [9/12] Setting up .env.production..."
if [ ! -f "$APP_DIR/.env.production" ]; then
    cp "$APP_DIR/.env.production.example" "$APP_DIR/.env.production"
    echo ""
    echo "  ⚠️  ACTION REQUIRED: Edit .env.production with your actual secrets:"
    echo "       nano $APP_DIR/.env.production"
    echo ""
    echo "  Required variables:"
    echo "    DJANGO_SECRET_KEY=<64-char-random-string>"
    echo "    DATABASE_URL=postgres://USER:PASS@HOST:5432/fashionistar_prod"
    echo "    REDIS_PASSWORD=<strong-password>"
    echo "    CLOUDINARY_URL=cloudinary://KEY:SECRET@CLOUD_NAME"
    echo "    PAYSTACK_SECRET_KEY=sk_live_xxxxx"
    echo "    TWILIO_ACCOUNT_SID=ACxxxxxxxx"
    echo "    TWILIO_AUTH_TOKEN=xxxxxxxxxxxx"
    echo "    SENTRY_DSN=https://xxx@sentry.io/xxxxx"
    echo ""
else
    echo "  .env.production already exists — skipping."
fi

# ── Step 10: SSL Certificate ─────────────────────────────────────────────────
echo "🔐 [10/12] SSL Certificate setup..."
echo "  To obtain SSL certificate, run:"
echo "    sudo certbot --nginx -d api.fashionistar.net"
echo "  (Requires DNS A record pointing to this server first)"

# ── Step 11: Oracle Crontab (Keep-Alive + SSL Renewal) ───────────────────────
echo "⏰ [11/12] Configuring crontab..."
(crontab -l 2>/dev/null || echo "") | grep -v "fashionistar-keepalive\|certbot" | \
{ cat; \
    echo "# Oracle VM keep-alive (prevents idle reclamation > 7 days)";
    echo "*/4 * * * * /usr/bin/curl -sf http://127.0.0.1:8001/health/ > /dev/null 2>&1 # fashionistar-keepalive";
    echo "# SSL certificate auto-renewal";
    echo "0 3 * * * /usr/bin/certbot renew --quiet --post-hook 'docker compose -f $APP_DIR/docker-compose.production.yml restart nginx'";
    echo "# Nightly Docker image cleanup (free up disk space)";
    echo "0 4 * * * /usr/bin/docker image prune -f > /dev/null 2>&1";
} | crontab -
echo "  Crontab configured."

# ── Step 12: Start Services ───────────────────────────────────────────────────
echo "🚀 [12/12] Starting FASHIONISTAR services..."
cd "$APP_DIR"

# Pull latest images from GHCR
docker compose -f docker-compose.production.yml pull

# Start services (api, redis, nginx, keepalive)
docker compose -f docker-compose.production.yml up -d

echo ""
echo "============================================="
echo "  ✅ FASHIONISTAR Oracle VM Setup Complete!"
echo "============================================="
echo ""
echo "Next steps:"
echo "  1. Edit secrets:  nano $APP_DIR/.env.production"
echo "  2. Get SSL cert:  sudo certbot --nginx -d api.fashionistar.net"
echo "  3. Run migrations: docker compose -f $APP_DIR/docker-compose.production.yml exec api python manage.py migrate"
echo "  4. Health check:  curl http://localhost:8001/health/"
echo "  5. View API logs: docker compose -f $APP_DIR/docker-compose.production.yml logs -f api"
echo ""
echo "Log file locations:"
echo "  API logs:   /var/log/fashionistar/api/"
echo "  Nginx logs: /var/log/fashionistar/nginx/"
echo ""
echo "Redis endpoint for Northflank Celery workers:"
IP=$(curl -s ifconfig.me 2>/dev/null || echo "<ORACLE_PUBLIC_IP>")
echo "  CELERY_BROKER_URL=redis://:<REDIS_PASSWORD>@${IP}:6379/1"
echo "  (Add port 6379 to Oracle VCN Security List!)"
