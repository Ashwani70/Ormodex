// Auto-update via electron-updater, backed by GitHub Releases (same repo the
// desktop-release.yml workflow already publishes installers to). Works for
// Windows (nsis) and Linux (AppImage) out of the box; macOS auto-update also
// requires the app to be signed+notarized (see desktop/README.md) — until then
// it silently no-ops on mac rather than nagging users with a broken updater.
const { autoUpdater } = require("electron-updater");
const { dialog } = require("electron");

let wired = false;

function setupAutoUpdate(mainWindow, log) {
  if (wired) return; // only one window drives the updater lifecycle
  wired = true;

  autoUpdater.logger = {
    info: (m) => log.info(String(m)),
    warn: (m) => log.warn(String(m)),
    error: (m) => log.error(String(m)),
  };
  autoUpdater.autoDownload = true;
  autoUpdater.autoInstallOnAppQuit = true;

  autoUpdater.on("update-available", (info) => {
    log.info("Update available", { version: info.version });
  });

  autoUpdater.on("update-not-available", () => log.info("No update available"));

  autoUpdater.on("error", (err) => log.error("Auto-update error", { message: err?.message }));

  autoUpdater.on("update-downloaded", async (info) => {
    log.info("Update downloaded, prompting restart", { version: info.version });
    const { response } = await dialog.showMessageBox(mainWindow, {
      type: "info",
      title: "Update ready",
      message: `Ormodex ERP ${info.version} has been downloaded.`,
      detail: "Restart now to apply the update, or it will install automatically the next time you quit.",
      buttons: ["Restart now", "Later"],
      defaultId: 0,
      cancelId: 1,
    });
    if (response === 0) autoUpdater.quitAndInstall();
  });

  // Check on launch, then every 4 hours while the app stays open — a business
  // ERP client is typically left running all day, so a boot-only check would
  // miss same-day hotfix releases.
  checkForUpdatesNow(log);
  setInterval(() => checkForUpdatesNow(log), 4 * 60 * 60 * 1000);
}

function checkForUpdatesNow(log) {
  autoUpdater.checkForUpdates().catch((err) => log.error("checkForUpdates failed", { message: err?.message }));
}

module.exports = { setupAutoUpdate, checkForUpdatesNow };
