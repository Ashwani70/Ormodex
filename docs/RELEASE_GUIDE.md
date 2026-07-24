# Release Guide

How to cut a new desktop release. Web/PWA deploys follow your normal hosting
pipeline (see `docs/DEPLOYMENT_GUIDE.md`) and aren't versioned/tagged the same
way.

## Desktop release checklist

1. **Bump the version** in `desktop/package.json` (`"version"`). Follow
   semver — patch for fixes, minor for new features, major for breaking
   changes to the desktop shell itself (rare, since it's a thin client).

2. **Update `NEXT_PUBLIC_APP_VERSION`** in the marketing site's environment if
   you want the Download page's displayed version to match (cosmetic only —
   the actual installers always carry the real `desktop/package.json`
   version regardless of this env var).

3. **Commit the version bump:**
   ```bash
   git add desktop/package.json
   git commit -m "chore: bump desktop version to X.Y.Z"
   git push
   ```

4. **Tag and push the tag** — this is what triggers the release build:
   ```bash
   git tag vX.Y.Z
   git push origin vX.Y.Z
   ```

5. **Watch the Actions run** (`Desktop Release` workflow). It:
   - Runs `pwa-check` first (fails fast if the web/PWA build is broken).
   - Builds Windows (`.exe` + `.msi`), macOS (`.dmg`), and Linux
     (`.AppImage` + `.deb`) in parallel.
   - Creates version-less "stable" aliases of each installer.
   - Publishes everything — including the `latest*.yml` auto-update feed
     files — to a **GitHub Release** for the tag.

6. **Verify the Release** once the workflow finishes:
   - All expected files are attached (5 platforms × versioned + aliased,
     plus 3 `latest*.yml` manifests).
   - Download and smoke-test at least one installer.
   - Confirm an **already-installed older version** picks up the update
     within a few minutes (auto-update checks run on launch — relaunch the
     old app to trigger an immediate check, or use **Help → Check for
     Updates…**).

7. **Announce** — the marketing site's download links
   (`releases/latest/download/...`) start serving the new version
   immediately; no website redeploy is needed.

## Manual / dry-run builds

Trigger the same workflow without a tag via **Actions → Desktop Release → Run
workflow** (workflow_dispatch). This builds and uploads artifacts (downloadable
from the workflow run page) but does **not** publish a GitHub Release or move
the "latest" auto-update pointer — safe to use for testing a change before
committing to a real version bump.

## Hotfix releases

Same steps as above with a patch version bump. Because the update check runs
every 4 hours while the app is open (not just on launch), most active users
get a hotfix within a few hours without needing to relaunch.

## Rolling back a bad release

See `docs/DEPLOYMENT_GUIDE.md § Rollback` — in short, delete or unpublish the
bad GitHub Release (specifically its `latest*.yml` files) so
`electron-updater` stops offering it, then cut a new patch release with the
fix.

## Code signing (not yet enabled)

Releases currently ship **unsigned**. Enabling signing doesn't change any of
the steps above — it only requires secrets to be present before the workflow
runs `electron-builder`:

- **Windows:** `CSC_LINK` (base64-encoded `.pfx`) + `CSC_KEY_PASSWORD` as
  repo/environment secrets, then remove the workflow's
  `CSC_IDENTITY_AUTO_DISCOVERY: "false"` override for the Windows job.
- **macOS:** an Apple Developer ID Application certificate, plus `APPLE_ID`
  and `APPLE_APP_SPECIFIC_PASSWORD` secrets for notarization (electron-builder
  notarizes automatically when these are present).

Both require an active paid developer account/certificate that only you can
provision — this repo is ready to consume them the moment they exist, but
provisioning them is outside what can be automated here.
