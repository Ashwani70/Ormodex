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

APP_ROOT="/var/www/erp/Ormodex"
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
mkdir -p "$APP_ROOT/backend/logs"
sudo chown -R erpapp:erpapp "$APP_ROOT/backend/logs"
sudo find "$APP_ROOT/backend/logs" -type d -exec chmod 775 {} +
sudo find "$APP_ROOT/backend/logs" -type f -exec chmod 664 {} +

# Record the pre-restart main PID (if any) so the diagnostic dump below can
# tell "old process still draining" apart from "new process never started" —
# both look identical from curl's point of view but need different fixes.
OLD_MAIN_PID="$(sudo systemctl show erp-backend -p MainPID --value 2>/dev/null || echo 0)"

RESTART_T0=$(date +%s)
sudo systemctl restart erp-backend
# erp-backend.service has TimeoutStopSec=30 + KillMode=mixed: `restart` can
# block for up to 30s waiting for the OLD process to drain in-flight requests
# before the NEW one even starts. `is-active` only proves systemd forked a
# process — with Type=simple it has no idea whether Gunicorn's workers have
# actually finished booting (each one runs ~20-30s of idempotent schema-ensure
# / demo-seed / pool-warm work in the background — see server.py's lifespan/
# _run_startup_init — but the master binds the port immediately, before that
# finishes, specifically so this check doesn't have to wait for it).
sudo systemctl is-active --quiet erp-backend || {
    RESTART_ELAPSED=$(( $(date +%s) - RESTART_T0 ))
    echo "ERROR: erp-backend did not report active ${RESTART_ELAPSED}s after 'systemctl restart' (old MainPID was ${OLD_MAIN_PID})." >&2
    echo "--- systemctl status erp-backend ---" >&2
    sudo systemctl status erp-backend --no-pager -l >&2 || true
    echo "--- journalctl -u erp-backend -n 100 ---" >&2
    journalctl -u erp-backend -n 100 --no-pager >&2 || true
    exit 1
}

echo "== Reloading Nginx (picks up new frontend build, no downtime) =="
sudo nginx -t
sudo systemctl reload nginx

echo "== Health check =="
# Two layers, checked separately so a failure points at the right fix:
#   1. Is anything listening on 8001 at all? (process/bind problem — the
#      master itself never started, crashed, or is still mid-graceful-stop)
#   2. Does it answer HTTP correctly? (process is up and bound, but the ASGI
#      app itself is erroring — e.g. a bad migration, missing env var)
# Budget: worst case is TimeoutStopSec's 30s drain + a genuinely slow worker
# fork, so this allows up to 90s total (30 x 3s) rather than the previous 45s,
# which was tight enough that an unlucky graceful-shutdown could exhaust it on
# an otherwise-healthy deploy.
HEALTH_PASSED=false
PORT_SEEN_AT=""
for i in $(seq 1 30); do
    if [[ -z "$PORT_SEEN_AT" ]] && ss -tln 2>/dev/null | grep -q ':8001[[:space:]]'; then
        PORT_SEEN_AT=$i
        echo "Port 8001 is now bound (attempt $i) — waiting for /health to answer..."
    fi
    if curl -fsS --max-time 5 http://127.0.0.1:8001/health >/dev/null 2>&1; then
        HEALTH_PASSED=true
        break
    fi
    echo "Waiting for backend startup... ($i/30)"
    sleep 3
done

if [[ "$HEALTH_PASSED" != "true" ]]; then
    TOTAL_ELAPSED=$(( $(date +%s) - RESTART_T0 ))
    echo "ERROR: /health check failed post-deploy after ${TOTAL_ELAPSED}s total (restart + wait)." >&2
    if [[ -z "$PORT_SEEN_AT" ]]; then
        echo "DIAGNOSIS: port 8001 was NEVER observed listening — Gunicorn's master never bound it. Likely a startup-time crash (bad import, syntax error, missing dependency) rather than a slow worker." >&2
    else
        echo "DIAGNOSIS: port 8001 bound at attempt $PORT_SEEN_AT but /health still never answered — something accepts TCP connections but the ASGI app isn't responding correctly (check for an exception inside server.py's lifespan/startup path, or a worker stuck/crash-looping after bind)." >&2
    fi
    echo "" >&2
    echo "--- ss -tlnp (what's actually listening) ---" >&2
    ss -tlnp >&2 || true
    echo "" >&2
    echo "--- systemctl status erp-backend ---" >&2
    sudo systemctl status erp-backend --no-pager -l >&2 || true
    echo "" >&2
    echo "--- journalctl -u erp-backend -n 150 (since this restart) ---" >&2
    journalctl -u erp-backend -n 150 --no-pager >&2 || true
    echo "" >&2
    echo "--- gunicorn/uvicorn worker process tree ---" >&2
    pgrep -af gunicorn >&2 || echo "(no gunicorn processes found at all)" >&2
    echo "" >&2
    echo "--- disk space (a full disk silently breaks pip/npm/writes) ---" >&2
    df -h "$APP_ROOT" /data >&2 || true
    echo "" >&2
    echo "--- memory (MemoryMax=1536M in the unit — OOM kills look like a silent restart loop) ---" >&2
    free -h >&2 || true
    exit 1
fi
echo "Health check passed successfully! (port bound at attempt ${PORT_SEEN_AT:-unknown}, /health answered at attempt $i)"

echo "== Deploy complete: $(git rev-parse --short HEAD) =="
