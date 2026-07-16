// Central place for env-driven URLs so buttons (Login, downloads) are configurable
// per environment without touching component code. Set these in .env.local / Vercel.

// Where the live ERP product app runs. The website's Login button deep-links to its
// /login route; Logout hits /logout. Defaults to local CRA dev server.
export const ERP_APP_URL =
  process.env.NEXT_PUBLIC_ERP_APP_URL || "http://localhost:3000";

export const ERP_LOGIN_URL = `${ERP_APP_URL.replace(/\/$/, "")}/login`;
export const ERP_SIGNUP_URL = `${ERP_APP_URL.replace(/\/$/, "")}/login`;
export const ERP_LOGOUT_URL = `${ERP_APP_URL.replace(/\/$/, "")}/logout`;

// GitHub repo that hosts the desktop releases (the desktop-release workflow
// publishes installers here). `latest/download/<asset>` always resolves to the
// newest release, so these links keep working across versions without edits.
const GH_REPO =
  process.env.NEXT_PUBLIC_GH_RELEASES_REPO || "Ashwani70/Ormodex-ERP";
const APP_VERSION = process.env.NEXT_PUBLIC_APP_VERSION || "2.4.0";
const ghAsset = (file) => `https://github.com/${GH_REPO}/releases/latest/download/${file}`;

// Desktop installer download URLs. These use the VERSION-LESS stable aliases the
// release workflow uploads alongside the versioned files, so the links never 404
// when the app version changes (no APP_VERSION coupling here).
// Stable names must match the aliases in .github/workflows/desktop-release.yml.
export const DOWNLOADS = {
  windows: {
    label: "Windows",
    sub: "Windows 10/11 · 64-bit · .exe",
    icon: "windows",
    url: process.env.NEXT_PUBLIC_DOWNLOAD_WINDOWS || ghAsset("Ormodex-ERP-Setup.exe"),
  },
  mac: {
    label: "macOS",
    sub: "Apple Silicon & Intel · .dmg",
    icon: "apple",
    url: process.env.NEXT_PUBLIC_DOWNLOAD_MAC || ghAsset("Ormodex-ERP.dmg"),
  },
  linux: {
    label: "Linux",
    sub: "Debian/Ubuntu & RPM · .AppImage",
    icon: "linux",
    url: process.env.NEXT_PUBLIC_DOWNLOAD_LINUX || ghAsset("Ormodex-ERP.AppImage"),
  },
};

export { APP_VERSION };
