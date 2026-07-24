# Installation Guide

How to install Ormodex ERP as an end user, on every currently-shipped platform.

> **Scope note:** this guide covers what actually ships today — Windows, macOS,
> Linux desktop installers and the installable Progressive Web App (PWA). Android
> and iOS native apps are not built yet (see `desktop/README.md` and the project's
> mobile-scope notes) — the PWA is the cross-platform mobile option in the
> meantime and installs from any modern mobile browser.

## Windows

1. Go to the [Download page](https://ormodex.com/download) (or your
   organization's internal link) and click **Download for Windows**.
2. Run `Ormodex-ERP-Setup.exe` (or the `.msi` if your IT department prefers
   MSI for group-policy deployment).
3. Windows SmartScreen may show **"Windows protected your PC"** the first time —
   this app is not yet code-signed (see `desktop/README.md § Code signing`).
   Click **More info → Run anyway** to proceed.
4. Follow the installer — choose the install location, whether to create a
   desktop shortcut (on by default), and finish.
5. Launch **Ormodex ERP** from the Start Menu or desktop shortcut.
6. On first launch you'll briefly see a splash screen while it checks your
   server connection, then the login screen.

**Uninstall:** Settings → Apps → Ormodex ERP → Uninstall (standard Windows flow;
the NSIS/MSI installer registers itself normally).

## macOS

1. Download `Ormodex-ERP.dmg` from the Download page.
2. Open the `.dmg` and drag **Ormodex ERP** into **Applications**.
3. On first launch, macOS Gatekeeper will warn the app is from an
   "unidentified developer" (not yet notarized). Right-click the app →
   **Open** → **Open** again in the confirmation dialog. This is only needed
   once.
4. Launch from Launchpad or Applications.

**Uninstall:** drag the app from Applications to Trash.

## Linux

Two package formats are provided:

- **`.AppImage`** — no installation needed. Make it executable and run it:
  ```bash
  chmod +x Ormodex-ERP.AppImage
  ./Ormodex-ERP.AppImage
  ```
- **`.deb`** (Debian/Ubuntu) — install with your package manager:
  ```bash
  sudo apt install ./Ormodex-ERP.deb
  ```
  then launch **Ormodex ERP** from your application menu.

**Uninstall:** `sudo apt remove ormodex-desktop` (deb), or simply delete the
AppImage file (AppImage).

## Progressive Web App (installable from any browser)

Works on Chrome, Edge, and Safari on desktop, and Chrome/Safari on
Android/iOS — no app store needed.

1. Open the ERP in your browser (e.g. `https://app.ormodex.com`).
2. **Desktop Chrome/Edge:** click the install icon (⊕) in the address bar, or
   the in-app **Install App** button if shown.
3. **Android Chrome:** tap the **⋮** menu → **Install app** / **Add to Home
   screen**.
4. **iOS Safari:** tap the **Share** icon → **Add to Home Screen**.

Once installed it behaves like a native app: its own icon, its own window
(no browser chrome), and works offline for pages you've already visited
(see `frontend/public/service-worker.js` for exactly what's cached).

## First login on any platform

Same credentials work everywhere — desktop, PWA, and browser all authenticate
against the same hosted backend. If your organization runs a private/on-prem
backend, the desktop app may ask you for the **ERP Server URL** on first run
(File menu → "ERP Server…" to change it later).

## Getting help

- In-app: **Help → Documentation** (desktop menu) or the Docs link on the
  marketing site.
- Logs for a support request: see `desktop/README.md § Logs & diagnostics`.
