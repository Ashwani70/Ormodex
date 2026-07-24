# Rollback Guide

How to undo a bad production deploy, for each layer independently — a bad
frontend deploy and a bad backend deploy have different (and independent)
rollback paths since they're separate Railway services.

## Frontend or backend service (Railway)

Railway keeps deploy history per service:

1. Railway dashboard → the affected service → **Deployments** tab.
2. Find the last known-good deployment (before the bad one).
3. Click it → **Redeploy** (the exact wording/placement may vary slightly by
   Railway UI version, but every deployment has a redeploy/rollback action).

This redeploys the **exact previous image** — no rebuild, near-instant. Since
`deploy.yml` deploys backend and frontend as separate jobs, you can roll back
just the broken one without touching the other.

## Database migrations

Rolling back a migration is **not automatic** — `deploy.yml` runs
`alembic upgrade head` but there's no corresponding auto-downgrade step
(intentionally: an automatic downgrade on a production database is a
destructive-by-default footgun, not a safety feature).

To manually roll back one migration:
```bash
# From backend/, with DATABASE_URL pointed at production — do this
# deliberately, not as a reflexive "something broke" reaction.
alembic downgrade -1
```

**Before doing this, check whether the migration is actually reversible** —
read the specific migration file in `backend/alembic/versions/` for its
`downgrade()` function. Some migrations (adding a NOT NULL column with a
backfill, for example) have a `downgrade()` that drops the column entirely,
which loses any data written to it since the migration ran. If in doubt,
restore from the last `pg_dump` instead (see `docs/BACKUP_RECOVERY_GUIDE.md`)
rather than blind-downgrading against live data.

## When a deploy introduces a bad migration AND bad code together

Order matters for rollback, same as it does for the forward deploy:

1. Roll back the **backend service** to the previous image first (stops the
   bad code from running against whatever schema state exists).
2. Only then consider whether the migration itself needs reversing — often
   it doesn't, if the previous code version simply doesn't use the new
   column/table yet (additive migrations are usually safe to leave applied
   even after rolling back the code that was going to use them).
3. If the migration itself is the problem (e.g. it corrupted data during a
   backfill), restore from backup rather than attempting a downgrade on data
   that's already wrong.

## Verifying a rollback worked

Run through `docs/FINAL_VERIFICATION_CHECKLIST.md`'s login + dashboard +
one CRUD operation at minimum — don't consider a rollback "done" until you've
confirmed the app actually works, not just that the deploy succeeded.

## DNS / domain changes

Custom domain / CNAME changes aren't part of the normal deploy cycle and
don't have a "rollback" in the same sense — if you ever repoint
`api.mycompany.com` at a different Railway service and need to undo it,
just change the CNAME back. DNS propagation delay (minutes to an hour,
depending on TTL and registrar) applies in both directions.
