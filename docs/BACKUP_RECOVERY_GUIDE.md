# Backup & Disaster Recovery Guide

## What needs backing up

1. **Database** (Supabase Postgres) — all business data: masters, vouchers,
   ledgers, HR, everything.
2. **Uploaded files** (Railway Volume at `/data/uploads`) — product images,
   company logos, letterheads, any generated PDFs saved to disk.
3. **Environment configuration** — the real `.env` values (secrets, API
   keys) are not stored anywhere except Railway's dashboard and wherever you
   separately vault them (see `docs/SECURITY_CHECKLIST.md`'s last item).
4. **Source code** — already backed up by virtue of being in GitHub; not a
   backup concern here beyond "don't force-push over history."

## 1. Database backups

### If you're on a paid Supabase plan
Supabase → Project Settings → Database → Backups. Daily automatic backups
are included (7-day point-in-time recovery on Pro and up — check your
specific plan's retention window). **This is the primary backup mechanism —
verify it's actually enabled for your project**, don't assume.

### If you're on the Supabase free tier
**No automatic backups are included.** Set up your own scheduled `pg_dump`:

```bash
# Add as a scheduled GitHub Actions workflow (or any cron runner you have),
# NOT from a Railway service — Railway containers are ephemeral and this
# needs to run on a schedule independent of deploys.
pg_dump "$DATABASE_URL" \
  --format=custom \
  --file="ormodex-erp-$(date +%Y%m%d-%H%M%S).dump"
```

Upload the resulting `.dump` file somewhere durable and OFF Supabase itself
(a separate S3/Backblaze/GCS bucket, or even a private GitHub Release asset
for a small DB) — a backup stored only inside the same Supabase project
doesn't protect you against losing the Supabase project itself.

A minimal scheduled workflow:

```yaml
# .github/workflows/db-backup.yml
name: Database Backup
on:
  schedule:
    - cron: "0 2 * * *"   # daily at 02:00 UTC
  workflow_dispatch:
jobs:
  backup:
    runs-on: ubuntu-latest
    steps:
      - name: Install postgresql-client
        run: sudo apt-get install -y postgresql-client
      - name: Dump database
        env:
          DATABASE_URL: ${{ secrets.DATABASE_URL }}
        run: pg_dump "$DATABASE_URL" --format=custom --file=backup.dump
      - name: Upload to storage
        # Plug in your actual off-Supabase destination here — e.g.
        # aws s3 cp, rclone, or actions/upload-artifact for short-term
        # retention only (GitHub Actions artifacts expire, not a real
        # long-term backup store on their own).
        run: echo "Wire this step to your actual backup destination"
```

(Not added as a live workflow in this repo since it needs a real backup
destination — S3 bucket, Backblaze B2, etc. — that only you can provision
and pay for. The template above is ready to complete once you pick one.)

## 2. File (upload) backups

The Railway Volume mounted at `/data/uploads` is durable across deploys and
restarts, but **Railway Volumes are not automatically backed up to a separate
location** — a Volume is redundant storage, not a backup. Two options:

- **Simplest:** periodically `railway run` a shell on the backend service
  and `tar czf` the uploads directory, download it, store it alongside your
  DB dumps.
- **Better long-term fix:** migrate `core/storage.py` to genuinely use
  Supabase Storage (an S3-compatible object store with its own durability)
  instead of local disk — this was evaluated during this deployment
  (see project memory on the storage-gap decision) and deferred in favor of
  the quicker Volume fix; revisit if file-loss risk becomes a real concern.

## 3. Restore procedures

### Restoring the database from a `pg_dump`
```bash
pg_restore --clean --if-exists --no-owner \
  --dbname="$DATABASE_URL" \
  backup.dump
```
Run this against a **fresh/staging** Supabase project first if at all
possible — never test a restore procedure for the first time against
production during an actual incident.

### Restoring from Supabase's own Point-in-Time Recovery (paid plans)
Supabase → Project Settings → Database → Backups → pick a timestamp →
Restore. This is a Supabase-managed operation; it restores in place (creates
a new project state at that point in time) — read Supabase's own
confirmation dialog carefully, as this affects the live project.

### Restoring uploaded files
Copy your last `tar` archive's contents back into the Railway Volume (via
`railway run` + `tar xzf`, or Railway's file-browser if available in your
plan). Cross-check against the database — a Bill referencing a PDF that no
longer exists just means "re-generate that PDF," not a hard failure, since
PDFs here are generated from data (see the PDF-redesign project memory), not
uploaded as the source of truth.

## 4. Disaster recovery scenarios

| Scenario | Recovery path |
|---|---|
| Bad deploy breaks the app | See `docs/ROLLBACK_GUIDE.md` — redeploy the previous Railway deployment, no data loss involved. |
| Accidental data deletion (user error, not infra failure) | Supabase PITR (paid plans) restore to just before the deletion, OR restore your latest `pg_dump` and manually re-apply any legitimate changes made after that dump — how much you lose depends entirely on dump frequency, which is why the schedule above matters. |
| Railway Volume lost/corrupted | Restore uploaded files from your last manual/scheduled `tar` backup (see §2). Business data in Postgres is unaffected — only files are at risk here. |
| Supabase project itself lost/deleted | Worst case, and why an OFF-Supabase `pg_dump` destination (§1) matters — restore into a brand-new Supabase project from your latest external dump, update `DATABASE_URL` in Railway, redeploy. |
| Railway account/project lost | Source code is safe in GitHub. Recreate the two services following `docs/PRODUCTION_DEPLOYMENT_GUIDE.md` from scratch, re-enter env vars from your password manager (see Security Checklist's last item), re-point DNS CNAMEs at the new Railway domains, restore the uploads Volume from your last backup. |

## 5. Recovery Time / Recovery Point targets

Not formally defined yet — a genuine business decision, not a technical one.
Before go-live, decide and write down:
- **RPO (Recovery Point Objective):** how much data loss is acceptable —
  directly determines your `pg_dump` schedule frequency (§1). Daily backups
  mean up to 24h of data loss in the worst case.
- **RTO (Recovery Time Objective):** how long the business can tolerate the
  ERP being down — determines whether you need a warm standby (not set up
  here) or whether "redeploy + restore, taking however long that takes" is
  acceptable.

This guide gives you the mechanics; the actual targets are a call for
whoever owns business continuity for your organization.
