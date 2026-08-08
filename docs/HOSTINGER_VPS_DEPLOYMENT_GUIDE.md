# Hostinger VPS Deployment Guide (Ubuntu 24.04)

Deploy Ormodex ERP to a self-managed Hostinger VPS with Nginx, systemd,
Let's Encrypt, and GitHub Actions auto-deploy on push to `main`.

**This is an alternative to `docs/PRODUCTION_DEPLOYMENT_GUIDE.md`** (Railway +
Vercel). If you're moving from that setup, read the note in step 12 about not
running both deploy paths against the same domain at once. Everything here
uses the actual stack in this repo:

- Backend: FastAPI, entrypoint `backend/main.py` (`main:app`), served by
  Gunicorn + Uvicorn workers (`backend/gunicorn.conf.py`)
- Frontend: **Create React App via craco** (`frontend/package.json` — not
  Vite; `npm run build` runs `craco build`)
- Database: **Supabase-hosted Postgres**, reached over the network via the
  Supavisor transaction pooler (port 6543). This VPS does not run its own
  Postgres server — there is nothing to install or tune locally for the DB.
- Multi-tenancy: `tenant_id` columns + a `tenants` registry table already
  exist in the schema (see project memory: "Multi-tenant conversion",
  "Per-tenant settings"). This guide doesn't change app-level isolation —
  it only affects how the app is hosted. Nginx/systemd add no cross-tenant
  exposure since there's exactly one app instance per VPS, same as Railway.

```
Internet
   │  :443 (TLS via Let's Encrypt)
   ▼
┌─────────────────────────────────────────────┐
│  Nginx (host)                                │
│   /            → /var/www/erp/frontend/build │
│   /api/*       → 127.0.0.1:8001 (proxy)      │
└──────────────────────┬────────────────────────┘
                        │ 127.0.0.1 only
              ┌─────────▼─────────┐
              │ erp-backend.service│
              │ Gunicorn+Uvicorn   │  (systemd, auto-restart)
              └─────────┬─────────┘
                        │ asyncpg, Supavisor pooler :6543
              ┌─────────▼─────────┐
              │  Supabase Postgres │  (managed, remote — unchanged)
              └────────────────────┘
```

All commands below assume a **fresh Hostinger Ubuntu 24.04 VPS**. Run
server-provisioning steps as `root`; app steps as the `erpapp` user created
in step 2.

---

## 1. Point DNS at the VPS

In Hostinger's DNS panel (or wherever `yourdomain.com` is managed), add an
**A record** for the subdomain you'll use, e.g. `erp.yourdomain.com` →
`<VPS_PUBLIC_IP>`. DNS propagation can take a few minutes to a few hours —
kick this off first so it's ready by step 10 (Certbot needs it resolving
correctly).

## 2. First SSH connection + server provisioning

From your local machine:

```bash
ssh root@<VPS_PUBLIC_IP>
```

Accept the host key fingerprint prompt (type `yes`) and enter the root
password Hostinger emailed you. Once in:

```bash
# Optional but recommended: set a stronger root password immediately
passwd
```

Copy `deploy/setup_server.sh` from this repo onto the server (either `scp`
it up, or paste its contents into a file on the VPS directly), then run it:

```bash
# from your local machine, in the repo root
scp deploy/setup_server.sh root@<VPS_PUBLIC_IP>:/root/

# back on the VPS
ssh root@<VPS_PUBLIC_IP>
bash /root/setup_server.sh erp.yourdomain.com
```

This single script (see `deploy/setup_server.sh` for the full annotated
version) does, in order:

1. `apt-get update && apt-get upgrade -y` — updates the OS
2. Installs Python 3.12, Node.js 20 LTS, Git, Nginx, UFW, fail2ban,
   Certbot, `libpq-dev`/`postgresql-client` (for `pg_dump`/`psql` against
   the remote Supabase DB — no local Postgres server), build tools
3. Creates the `erpapp` system user and `/var/www/erp`
4. Configures UFW: **denies everything except SSH (22), HTTP (80), HTTPS
   (443)**
5. Enables `fail2ban` (SSH brute-force protection)
6. Enables `unattended-upgrades` for automatic security patches
7. Applies kernel/socket tuning for high concurrent-connection counts
8. Basic Nginx hardening (`server_tokens off`)

Verify the firewall came up correctly before moving on:

```bash
ufw status verbose
# Should show: 22/tcp ALLOW, 80/tcp ALLOW, 443/tcp ALLOW, default deny incoming
```

## 3. Generate a deploy SSH key (for GitHub Actions)

Still as root (or as `erpapp` — either works, this key is only ever used to
log in as `erpapp`):

```bash
sudo -u erpapp ssh-keygen -t ed25519 -f /home/erpapp/.ssh/erp_deploy_key -N ""
sudo -u erpapp bash -c 'cat /home/erpapp/.ssh/erp_deploy_key.pub >> /home/erpapp/.ssh/authorized_keys'
sudo -u erpapp chmod 600 /home/erpapp/.ssh/authorized_keys
cat /home/erpapp/.ssh/erp_deploy_key   # copy this PRIVATE key — you'll paste it into a GitHub secret in step 12
```

## 4. Scope sudo for the deploy user

`deploy/deploy.sh` needs to restart the backend service and reload Nginx,
but `erpapp` should not have broad sudo. Grant exactly those two commands:

```bash
sudo visudo -f /etc/sudoers.d/erpapp-deploy
```

Add this single line, then save:

```
erpapp ALL=(root) NOPASSWD: /usr/bin/systemctl restart erp-backend, /usr/bin/systemctl reload nginx, /usr/bin/systemctl is-active --quiet erp-backend, /usr/sbin/nginx -t
```

## 5. Clone the repo and do the first deploy

```bash
sudo -u erpapp -i
git clone https://github.com/<your-org>/<your-repo>.git /var/www/erp
cd /var/www/erp
```

If the repo is private, use a deploy key or PAT-based HTTPS URL here instead
— same as any other private-repo clone.

## 6. Backend: virtualenv, dependencies, `.env`

```bash
cd /var/www/erp/backend
python3.12 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
deactivate

mkdir -p logs uploads
cp /var/www/erp/deploy/backend.env.example .env
nano .env   # fill in every <placeholder> — see below for the required ones
chmod 600 .env
```

Required values you must fill in (everything else in the template has a
working default or is optional):

| Variable | Where to get it |
|---|---|
| `DATABASE_URL` | Supabase dashboard → Connect → **Transaction pooler** (port 6543) — the direct `:5432` host is IPv6-only and won't work here |
| `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY`, `SUPABASE_SECRET_KEY`, `SUPABASE_JWKS_URL` | Supabase dashboard → Project Settings → API |
| `JWT_SECRET` | `python3 -c "import secrets; print(secrets.token_urlsafe(64))"` |
| `SETTINGS_ENCRYPTION_KEY` | `python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` — back this up outside the VPS |
| `FRONTEND_URL` / `CORS_ORIGINS` | `https://erp.yourdomain.com` (your real domain) |
| `ADMIN_EMAIL` / `ADMIN_PASSWORD` | first-login admin bootstrap credentials |

Run migrations once, manually, to confirm the DB connection works before
wiring up the automated path:

```bash
source venv/bin/activate
alembic upgrade head
deactivate
```

## 7. Frontend: dependencies, `.env`, build

```bash
cd /var/www/erp/frontend
cp /var/www/erp/deploy/frontend.env.example .env
nano .env   # set REACT_APP_BACKEND_URL=https://erp.yourdomain.com
npm ci --legacy-peer-deps
CI=false npm run build
```

This produces `/var/www/erp/frontend/build` — the static files Nginx will
serve directly.

## 8. systemd service for FastAPI

Exit back to a root/sudo shell (`exit` out of the `erpapp` session, or open
a second SSH connection):

```bash
sudo cp /var/www/erp/deploy/erp-backend.service /etc/systemd/system/erp-backend.service
sudo systemctl daemon-reload
sudo systemctl enable --now erp-backend
sudo systemctl status erp-backend --no-pager
```

Check it's actually listening and healthy:

```bash
curl -fsS http://127.0.0.1:8001/health
# expect: {"status":"ok"} (or similar — see backend/server.py's /health handler)
journalctl -u erp-backend -n 50 --no-pager   # if it's not
```

## 9. Nginx site config (pre-SSL)

```bash
sudo cp /var/www/erp/deploy/nginx.erp.conf /etc/nginx/sites-available/erp.conf
sudo cp /var/www/erp/deploy/proxy_params_erp.conf /etc/nginx/proxy_params_erp.conf
sudo sed -i 's/erp.yourdomain.com/erp.YOURACTUALDOMAIN.com/' /etc/nginx/sites-available/erp.conf
sudo ln -s /etc/nginx/sites-available/erp.conf /etc/nginx/sites-enabled/erp.conf
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl reload nginx
```

At this point, `http://erp.yourdomain.com` should already serve the app over
plain HTTP (no SSL yet) — confirm this works before running Certbot:

```bash
curl -I http://erp.yourdomain.com
```

## 10. SSL with Let's Encrypt (Certbot)

```bash
sudo certbot --nginx -d erp.yourdomain.com --redirect --agree-tos -m you@yourdomain.com --no-eff-email
```

Certbot edits `/etc/nginx/sites-available/erp.conf` in place to add
`ssl_certificate`/`ssl_certificate_key` lines and the HTTP→HTTPS redirect
(the config already has the `/.well-known/acme-challenge/` location and
`return 301 https://...` block set up for this). Verify auto-renewal is
wired up:

```bash
sudo systemctl status certbot.timer --no-pager
sudo certbot renew --dry-run
```

Confirm HTTPS works end to end:

```bash
curl -I https://erp.yourdomain.com
curl -fsS https://erp.yourdomain.com/health
```

## 11. Backups + log rotation

```bash
sudo cp /var/www/erp/deploy/backup_db.sh /usr/local/bin/erp-backup-db.sh
sudo chmod 750 /usr/local/bin/erp-backup-db.sh
sudo chown erpapp:erpapp /usr/local/bin/erp-backup-db.sh

sudo crontab -u erpapp -e
# add this line:
# 17 2 * * * /usr/local/bin/erp-backup-db.sh >> /var/www/erp/backend/logs/backup.log 2>&1

sudo cp /var/www/erp/deploy/erp-backend.logrotate /etc/logrotate.d/erp-backend
sudo logrotate -d /etc/logrotate.d/erp-backend   # dry-run check
```

Run the backup script once by hand to confirm it works before trusting the
cron job:

```bash
sudo -u erpapp /usr/local/bin/erp-backup-db.sh
ls -lh /var/backups/erp-db/
```

By default backups stay on the VPS with 14-day retention. **This does not
protect against losing the VPS itself** — see the commented-out
`rclone`/`rsync` section at the bottom of `deploy/backup_db.sh` and decide
where an off-server copy should live (S3, Backblaze B2, a second host, etc.)
before you consider backups actually done.

## 12. GitHub Actions auto-deploy on push to `main`

The workflow is already committed at `.github/workflows/deploy-vps.yml`. It
runs the same test gate as the existing `deploy.yml`, then SSHes in and runs
`deploy/deploy.sh` (pull → install deps → migrate → rebuild frontend →
restart service → health check).

Add these secrets under **GitHub repo → Settings → Secrets and variables →
Actions → Secrets**:

| Secret | Value |
|---|---|
| `VPS_HOST` | your VPS IP, e.g. `187.127.219.89` |
| `VPS_SSH_USER` | `erpapp` |
| `VPS_SSH_KEY` | the **private** key printed in step 3 (`erp_deploy_key`, not `.pub`) |
| `VPS_SSH_PORT` | `22` (only needed if you changed the SSH port) |

> **If you're migrating off Railway/Vercel**: disable that path so a single
> push doesn't deploy twice to two different places. Railway/Vercel deploy
> via their own Git integration (not a workflow file you can just delete) —
> disconnect the repo from each project's dashboard, or at minimum point
> their production domains away from DNS once you've cut over. Keep
> `docs/PRODUCTION_DEPLOYMENT_GUIDE.md` as reference/rollback until you're
> confident in the VPS deploy.

Test it: push a trivial commit to `main` (or use **Actions → Deploy to
Hostinger VPS → Run workflow** for a manual trigger) and watch it run.

## 13. Performance notes for 500+ concurrent users

- **Gunicorn workers**: `backend/gunicorn.conf.py` defaults to `2 × CPU
  cores + 1`. This workload is I/O-bound (DB round-trips to Supabase, not
  local CPU work — same reasoning as `backend/Dockerfile`'s existing
  comment), and each worker serves many overlapping requests via asyncio —
  it is not one worker per concurrent browser tab. On a 2 vCPU Hostinger
  plan that's 5 workers; bump `WEB_CONCURRENCY` in `.env` if you scale the
  VPS up, and re-test under load before assuming a number is right.
- **Nginx**: `nginx.erp.conf` sets rate-limit zones (20 req/s general API,
  5 req/min on `/api/auth/login` specifically) and `keepalive 32` to the
  upstream to avoid re-handshaking a TCP connection per request.
- **Database**: you're on Supabase's Supavisor **transaction pooler**
  already (required, not optional — see `.env` comments) — it handles
  connection pooling on Supabase's side. Don't add a second local pooler
  (e.g. PgBouncer) in front of it unless you've specifically profiled a
  need; it's redundant with what Supavisor already does.
- **Static assets**: CRA fingerprints build output filenames, so
  `/static/*` is cached for 1 year immutably (see `nginx.erp.conf`) — the
  browser never re-fetches unchanged assets across deploys.
- **Load test before go-live**: none of the above numbers are guaranteed
  correct for your actual query patterns and VPS plan. Run a real load test
  (e.g. `k6` or `locust`) against a staging copy hitting representative
  endpoints (dashboard, invoice list, search) before trusting this to hold
  500 concurrent users, and watch `journalctl -u erp-backend -f` plus
  `htop` during the run.

---

## Deployment Verification Checklist

Run through this after the first deploy, and again after any infrastructure
change (not after every code push — the GitHub Actions health check already
covers that).

**Server & security**
- [ ] `ufw status verbose` shows only 22, 80, 443 allowed; default deny incoming
- [ ] `systemctl status fail2ban` is active
- [ ] `systemctl status unattended-upgrades` is active; `/etc/apt/apt.conf.d/20auto-upgrades` present
- [ ] `ssh erpapp@<host>` works with the deploy key; root password login still works as a fallback (or is disabled, if you've hardened further — not done by this guide)
- [ ] No unexpected open ports: `sudo ss -tulpn | grep LISTEN` shows only 22, 80, 443, and `127.0.0.1:8001` (backend, not publicly reachable)

**Application**
- [ ] `curl -fsS http://127.0.0.1:8001/health` returns healthy from the VPS itself
- [ ] `curl -fsS https://erp.yourdomain.com/health` returns healthy from the internet
- [ ] `https://erp.yourdomain.com` loads the React app in a browser, not a blank page or 502
- [ ] Login works with the `ADMIN_EMAIL`/`ADMIN_PASSWORD` set in `.env`
- [ ] Create/view a record in at least one module (e.g. a test Customer) to confirm the API round-trip and DB write both work
- [ ] Hard-refresh a deep link (e.g. `https://erp.yourdomain.com/invoices`) — should load the SPA, not 404 (confirms Nginx's `try_files` fallback)
- [ ] `systemctl status erp-backend` shows `active (running)`, not restarting in a loop (`journalctl -u erp-backend --since "10 min ago"`)

**TLS**
- [ ] `https://erp.yourdomain.com` shows a valid Let's Encrypt certificate (no browser warning)
- [ ] `http://erp.yourdomain.com` redirects to `https://`
- [ ] `sudo certbot renew --dry-run` succeeds
- [ ] `sudo systemctl status certbot.timer` is active (auto-renewal is scheduled)

**Multi-tenant isolation** (app-level, not infra — see project memory on
`tenant_id` enforcement)
- [ ] Logging in as users from two different tenants/companies shows only
      that tenant's data (customers, invoices, stock) — no cross-tenant leakage
- [ ] Confirm this on the deployed instance, not just in dev — infra changes
      don't alter app logic, but it's cheap to re-verify once during go-live

**CI/CD**
- [ ] Pushing a trivial commit to `main` triggers `.github/workflows/deploy-vps.yml` and it completes green
- [ ] The deployed commit hash matches `git rev-parse --short HEAD` on the VPS (`deploy.sh`'s last log line) and matches what you pushed
- [ ] A deliberately failing test blocks deployment (temporarily break a test, push to a branch, open a PR — confirm the `deploy` job never runs without `test-backend`/`test-frontend` passing)

**Backups**
- [ ] `sudo -u erpapp /usr/local/bin/erp-backup-db.sh` run manually succeeds and produces a `.dump` file in `/var/backups/erp-db/`
- [ ] The dump actually restores: `pg_restore --list <file>.dump` lists tables without error
- [ ] Cron entry exists: `sudo crontab -u erpapp -l`
- [ ] An off-VPS copy destination is configured (not just default local retention) — see step 11's note

**Logs**
- [ ] `sudo logrotate -d /etc/logrotate.d/erp-backend` dry-run shows no errors
- [ ] Nginx's own logrotate (`/etc/logrotate.d/nginx`, distro-provided) is present and unmodified

**Performance sanity**
- [ ] A basic load test (see step 13) completes without 5xx errors or unbounded response-time growth at your expected concurrent-user count
- [ ] `htop` during the load test shows Gunicorn workers busy but not swapping/OOM-killed (`dmesg | grep -i oom` after, to be sure)
