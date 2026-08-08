#!/usr/bin/env bash
# Ormodex ERP — one-time Hostinger Ubuntu 24.04 VPS provisioning.
# Run as root (or via sudo) on a FRESH VPS. Idempotent where practical, but
# intended to be run once, top to bottom, per docs/HOSTINGER_VPS_DEPLOYMENT_GUIDE.md.
#
# What this does NOT do (deliberately, see the guide for these steps):
#   - Clone the repo / install app dependencies (deploy/deploy.sh does that)
#   - Issue the SSL certificate (needs DNS pointed at the VPS first)
#   - Write the real .env (secrets aren't safe to script/commit)

set -euo pipefail

APP_USER="erpapp"
APP_ROOT="/var/www/erp"
DOMAIN="${1:-}"

if [[ $EUID -ne 0 ]]; then
    echo "Run this as root: sudo bash setup_server.sh <your-domain>" >&2
    exit 1
fi

echo "== 1/10: System update =="
apt-get update -y
apt-get upgrade -y

echo "== 2/10: Core packages =="
apt-get install -y \
    build-essential \
    curl \
    git \
    nginx \
    ufw \
    fail2ban \
    unattended-upgrades \
    apt-listchanges \
    python3.12 \
    python3.12-venv \
    python3-pip \
    libpq-dev \
    postgresql-client \
    certbot \
    python3-certbot-nginx \
    logrotate \
    htop \
    ncdu

echo "== 3/10: Node.js 20 LTS (NodeSource) =="
if ! command -v node >/dev/null || [[ "$(node -v)" != v20* ]]; then
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
    apt-get install -y nodejs
fi
node -v
npm -v

echo "== 4/10: App user + directories =="
if ! id -u "$APP_USER" >/dev/null 2>&1; then
    useradd --create-home --shell /bin/bash "$APP_USER"
fi
mkdir -p "$APP_ROOT" "$APP_ROOT/backend/logs" "$APP_ROOT/backend/uploads"
chown -R "$APP_USER":"$APP_USER" "$APP_ROOT"

echo "== 5/10: UFW firewall (22, 80, 443 only) =="
ufw --force reset
ufw default deny incoming
ufw default allow outgoing
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable
ufw status verbose

echo "== 6/10: fail2ban (SSH brute-force protection) =="
systemctl enable --now fail2ban

echo "== 7/10: Unattended security upgrades =="
cat > /etc/apt/apt.conf.d/50unattended-upgrades.local <<'EOF'
Unattended-Upgrade::Allowed-Origins {
    "${distro_id}:${distro_codename}-security";
    "${distro_id}ESMApps:${distro_codename}-apps-security";
    "${distro_id}ESM:${distro_codename}-infra-security";
};
Unattended-Upgrade::Remove-Unused-Kernel-Packages "true";
Unattended-Upgrade::Remove-Unused-Dependencies "true";
Unattended-Upgrade::Automatic-Reboot "false";
EOF
cat > /etc/apt/apt.conf.d/20auto-upgrades <<'EOF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
APT::Periodic::AutocleanInterval "7";
EOF
systemctl enable --now unattended-upgrades

echo "== 8/10: Kernel/network tuning for many concurrent connections =="
cat > /etc/sysctl.d/99-erp-tuning.conf <<'EOF'
# Higher backlog + wider ephemeral port range for a Nginx+Gunicorn stack
# serving 500+ concurrent users.
net.core.somaxconn = 4096
net.ipv4.tcp_max_syn_backlog = 4096
net.ipv4.ip_local_port_range = 1024 65535
net.ipv4.tcp_fin_timeout = 15
net.ipv4.tcp_tw_reuse = 1
fs.file-max = 100000
EOF
sysctl --system

cat > /etc/security/limits.d/99-erp.conf <<EOF
$APP_USER soft nofile 65536
$APP_USER hard nofile 65536
EOF

echo "== 9/10: Nginx baseline hardening =="
sed -i 's/^\s*#\?\s*server_tokens.*/    server_tokens off;/' /etc/nginx/nginx.conf 2>/dev/null || true
grep -q "server_tokens off;" /etc/nginx/nginx.conf || sed -i '/http {/a \    server_tokens off;' /etc/nginx/nginx.conf
mkdir -p /var/www/certbot
nginx -t

echo "== 10/10: Done =="
echo
echo "Next steps (see docs/HOSTINGER_VPS_DEPLOYMENT_GUIDE.md from step 4 onward):"
echo "  1. Point DNS for ${DOMAIN:-<your-domain>} at this server's IP."
echo "  2. Deploy app code as the '$APP_USER' user (deploy/deploy.sh)."
echo "  3. Install deploy/nginx.erp.conf, then run certbot."
echo "  4. Install + enable the erp-backend systemd service."
