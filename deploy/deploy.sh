#!/usr/bin/env bash
# Ormodex ERP — application deploy/update script.
# Runs AS the erpapp user on the VPS. Used both for the first manual deploy
# and by GitHub Actions (.github/workflows/deploy-vps.yml) on every push to
# main via `ssh erpapp@vps bash /var/www/erp/deploy/deploy.sh`.
#
# Assumes:
#   - /var/www/erp is already a git clone of this repo (first-time setup
#     clones it manually, see docs/HOSTINGER_VPS_DEPLOYMENT_GUIDE.md step 5).
#   - /var/www/erp/backend/.env and /var/www/erp/frontend/.env already exist
#     (this script never writes secrets).
#   - erp-backend.service is already installed (systemctl restart, not enable).

set -euo pipefail

APP_ROOT="/var/www/erp"
BRANCH="${DEPLOY_BRANCH:-main}"

cd "$APP_ROOT"

echo "== Pulling latest ($BRANCH) =="
git fetch origin "$BRANCH"
git reset --hard "origin/$BRANCH"

echo "== Backend: install deps + migrate =="
cd "$APP_ROOT/backend"
if [[ ! -d venv ]]; then
    python3.12 -m venv venv
fi
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
alembic upgrade head
deactivate

echo "== Frontend: install deps + build =="
cd "$APP_ROOT/frontend"
npm ci --legacy-peer-deps
CI=false npm run build

echo "== Restarting backend service =="
sudo systemctl restart erp-backend
sleep 2
sudo systemctl is-active --quiet erp-backend || {
    echo "ERROR: erp-backend failed to start after deploy. Check: journalctl -u erp-backend -n 100" >&2
    exit 1
}

echo "== Reloading Nginx (picks up new frontend build, no downtime) =="
sudo nginx -t
sudo systemctl reload nginx

echo "== Health check =="
sleep 1
curl -fsS http://127.0.0.1:8001/health || {
    echo "ERROR: /health check failed post-deploy." >&2
    exit 1
}

echo "== Deploy complete: $(git rev-parse --short HEAD) =="
