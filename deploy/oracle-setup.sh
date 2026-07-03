#!/usr/bin/env bash
# ============================================================================
# FASHIONISTAR — Oracle Cloud VM Initial Setup Script
# ============================================================================
# Run this script ONCE after provisioning a fresh Oracle Cloud ARM64 VM:
#   chmod +x deploy/oracle-setup.sh
#   ssh ubuntu@YOUR_ORACLE_IP 'bash -s' < deploy/oracle-setup.sh
#
# What this does:
#   1. Updates Ubuntu
#   2. Installs Docker + Docker Compose
#   3. Installs Nginx + Certbot
#   4. Configures UFW firewall
#   5. Clones the repository
#   6. Sets up systemd auto-start on reboot
# ============================================================================

set -euo pipefail

REPO_URL="https://github.com/FASHIONISTAR-CLOTHINGS/fashionistar_backend.git"
APP_DIR="/home/ubuntu/fashionistar_backend"
DOMAIN="api.fashionistar.net"

echo "======================================================"
echo "  FASHIONISTAR Oracle Cloud Production Setup"
echo "  Target: VM.Standard.A1.Flex (ARM64 / Ubuntu 22.04)"
echo "======================================================"

# ── 1. System Update ──────────────────────────────────────────────────────────
echo "[1/8] Updating system packages..."
sudo apt-get update -qq
sudo apt-get upgrade -y -qq
sudo apt-get install -y -qq \
    curl \
    wget \
    git \
    htop \
    unzip \
    ca-certificates \
    gnupg \
    lsb-release

# ── 2. Install Docker ─────────────────────────────────────────────────────────
echo "[2/8] Installing Docker (ARM64 compatible)..."
if ! command -v docker &> /dev/null; then
    curl -fsSL https://get.docker.com | sh
    sudo usermod -aG docker ubuntu
    sudo systemctl enable docker
    sudo systemctl start docker
    echo "✅ Docker installed"
else
    echo "✅ Docker already installed ($(docker --version))"
fi

# Install Docker Compose v2 plugin
sudo apt-get install -y -qq docker-compose-plugin
echo "✅ Docker Compose installed ($(docker compose version))"

# ── 3. Install Nginx + Certbot ────────────────────────────────────────────────
echo "[3/8] Installing Nginx + Certbot..."
sudo apt-get install -y -qq nginx certbot python3-certbot-nginx
sudo systemctl enable nginx
echo "✅ Nginx installed"

# ── 4. Configure UFW Firewall ─────────────────────────────────────────────────
echo "[4/8] Configuring UFW firewall..."
sudo ufw --force reset
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow 22/tcp comment "SSH"
sudo ufw allow 80/tcp comment "HTTP (Let's Encrypt + redirect)"
sudo ufw allow 443/tcp comment "HTTPS API"
# Redis port — ONLY enable this if Northflank workers need direct Redis access
# sudo ufw allow from NORTHFLANK_IP to any port 6379 comment "Redis (Northflank only)"
sudo ufw --force enable
sudo ufw status verbose
echo "✅ Firewall configured"

# ── 5. Oracle iptables fix (OCI blocks traffic by default at OS level too) ────
echo "[5/8] Configuring iptables for Oracle Cloud..."
sudo iptables -I INPUT -p tcp --dport 80 -j ACCEPT
sudo iptables -I INPUT -p tcp --dport 443 -j ACCEPT
sudo iptables-save | sudo tee /etc/iptables/rules.v4 > /dev/null 2>&1 || true
echo "✅ iptables configured"

# ── 6. Clone Repository ───────────────────────────────────────────────────────
echo "[6/8] Cloning FASHIONISTAR repository..."
if [ -d "$APP_DIR" ]; then
    echo "Directory exists, pulling latest..."
    cd "$APP_DIR" && git pull origin main
else
    git clone "$REPO_URL" "$APP_DIR"
fi
echo "✅ Repository ready at $APP_DIR"

# ── 7. Set up systemd service for auto-start ──────────────────────────────────
echo "[7/8] Setting up systemd auto-start service..."
sudo tee /etc/systemd/system/fashionistar.service > /dev/null <<EOF
[Unit]
Description=FASHIONISTAR Production Stack
Requires=docker.service
After=docker.service network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=$APP_DIR
ExecStart=/usr/bin/docker compose -f docker-compose.production.yml up -d
ExecStop=/usr/bin/docker compose -f docker-compose.production.yml down
TimeoutStartSec=300
User=ubuntu
Group=ubuntu

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable fashionistar
echo "✅ systemd service configured (auto-starts on reboot)"

# ── 8. SSL Certificate setup ──────────────────────────────────────────────────
echo "[8/8] SSL Certificate setup..."
echo ""
echo "================================================"
echo "MANUAL STEP REQUIRED: Get SSL Certificate"
echo "================================================"
echo "Run the following command (after DNS is propagated):"
echo ""
echo "  sudo certbot --nginx -d ${DOMAIN} --non-interactive --agree-tos -m admin@fashionistar.net"
echo ""
echo "Then set up auto-renewal:"
echo "  echo '0 12 * * * /usr/bin/certbot renew --quiet' | sudo crontab -"
echo ""

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo "======================================================"
echo "  ✅ Oracle Cloud Setup Complete!"
echo "======================================================"
echo ""
echo "Next steps:"
echo "  1. Upload .env.production to $APP_DIR/.env.production"
echo "  2. Point DNS: ${DOMAIN} → $(curl -s ifconfig.me)"
echo "  3. Get SSL cert: sudo certbot --nginx -d ${DOMAIN}"
echo "  4. Start stack: cd $APP_DIR && docker compose -f docker-compose.production.yml up -d"
echo "  5. Run migrations: docker compose -f docker-compose.production.yml exec api python manage.py migrate"
echo "  6. Verify: curl https://${DOMAIN}/health/"
echo ""
echo "Oracle VM Public IP: $(curl -s ifconfig.me)"
echo ""

# Note: Log out and back in for docker group to take effect
echo "⚠️  IMPORTANT: Log out and back in for docker permissions to apply"
