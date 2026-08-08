#!/usr/bin/env bash
# Ormodex ERP — daily Supabase Postgres backup (runs ON the VPS, dumps the
# REMOTE Supabase database — this VPS does not run its own Postgres server).
#
# Install:
#   sudo cp deploy/backup_db.sh /usr/local/bin/erp-backup-db.sh
#   sudo chmod 750 /usr/local/bin/erp-backup-db.sh
#   sudo chown erpapp:erpapp /usr/local/bin/erp-backup-db.sh
# Cron (as erpapp, via `sudo crontab -u erpapp -e`):
#   17 2 * * * /usr/local/bin/erp-backup-db.sh >> /var/www/erp/backend/logs/backup.log 2>&1
#
# Reads DATABASE_URL from the app's own .env so there is exactly one place
# the connection string lives.

set -euo pipefail

ENV_FILE="/var/www/erp/backend/.env"
BACKUP_DIR="/var/backups/erp-db"
RETENTION_DAYS=14
UPLOADS_DIR="/var/www/erp/backend/uploads"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"

if [[ ! -f "$ENV_FILE" ]]; then
    echo "ERROR: $ENV_FILE not found — cannot read DATABASE_URL." >&2
    exit 1
fi

DATABASE_URL="$(grep -E '^DATABASE_URL=' "$ENV_FILE" | head -n1 | cut -d= -f2-)"
if [[ -z "$DATABASE_URL" ]]; then
    echo "ERROR: DATABASE_URL is empty in $ENV_FILE." >&2
    exit 1
fi

# pg_dump doesn't understand the asyncpg driver prefix some tools add; strip
# it if present so this works whether DATABASE_URL is stored as
# postgresql:// or postgresql+asyncpg://.
PG_DUMP_URL="${DATABASE_URL/postgresql+asyncpg:\/\//postgresql://}"

mkdir -p "$BACKUP_DIR"

DUMP_FILE="$BACKUP_DIR/erp_db_${TIMESTAMP}.dump"
echo "[$(date -Iseconds)] Starting pg_dump -> $DUMP_FILE"

# Custom format (-Fc): compressed, supports pg_restore's selective/parallel
# restore — safer default than plain SQL for a database this size.
pg_dump "$PG_DUMP_URL" -Fc --no-owner --no-privileges -f "$DUMP_FILE"

echo "[$(date -Iseconds)] pg_dump complete: $(du -h "$DUMP_FILE" | cut -f1)"

# ── Uploaded files (products/logos/generated PDFs) — local disk on this VPS,
# not part of the Postgres dump, so back them up alongside it. ──────────────
if [[ -d "$UPLOADS_DIR" ]]; then
    UPLOADS_TAR="$BACKUP_DIR/erp_uploads_${TIMESTAMP}.tar.gz"
    tar -czf "$UPLOADS_TAR" -C "$(dirname "$UPLOADS_DIR")" "$(basename "$UPLOADS_DIR")"
    echo "[$(date -Iseconds)] Uploads archived: $(du -h "$UPLOADS_TAR" | cut -f1)"
fi

# ── Rotate: delete backups older than RETENTION_DAYS ────────────────────────
find "$BACKUP_DIR" -name 'erp_db_*.dump' -mtime "+${RETENTION_DAYS}" -delete
find "$BACKUP_DIR" -name 'erp_uploads_*.tar.gz' -mtime "+${RETENTION_DAYS}" -delete

echo "[$(date -Iseconds)] Backup cycle complete. Retained ${RETENTION_DAYS} days in $BACKUP_DIR."

# ── Optional off-VPS copy ───────────────────────────────────────────────────
# A local-disk-only backup does not protect against VPS loss/disk failure.
# Uncomment and configure ONE of these once you've decided where backups
# should live off-server:
#
#   # rclone (any remote: S3, Backblaze B2, Google Drive, etc.)
#   # rclone copy "$DUMP_FILE" remote:erp-backups/db/
#   # rclone copy "$UPLOADS_TAR" remote:erp-backups/uploads/
#
#   # rsync to a second host
#   # rsync -az "$DUMP_FILE" backup-host:/backups/erp-db/
