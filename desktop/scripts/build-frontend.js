// Builds the CRA frontend for desktop use and copies it into desktop/app/.
//
// Key differences from a web build:
//   • PUBLIC_URL="." so asset URLs are relative and work under file://
//   • env-config.js is injected before the React bundle so the app reads the
//     backend URL from Electron (window.__GRAVITYONE_BACKEND_URL__) at runtime
//     instead of a value baked in at build time.
//
// Run from desktop/:  npm run build:frontend   (also runs automatically before dist)

const { execSync } = require("child_process");
const fs = require("fs");
const path = require("path");

const DESKTOP_DIR = path.resolve(__dirname, "..");
const FRONTEND_DIR = path.resolve(DESKTOP_DIR, "..", "frontend");
const BUILD_DIR = path.join(FRONTEND_DIR, "build");
const OUT_DIR = path.join(DESKTOP_DIR, "app");

function rmrf(p) {
  fs.rmSync(p, { recursive: true, force: true });
}

function copyDir(src, dest) {
  fs.mkdirSync(dest, { recursive: true });
  for (const entry of fs.readdirSync(src, { withFileTypes: true })) {
    const s = path.join(src, entry.name);
    const d = path.join(dest, entry.name);
    if (entry.isDirectory()) copyDir(s, d);
    else fs.copyFileSync(s, d);
  }
}

console.log("▶ Building frontend for desktop (PUBLIC_URL=.)…");

// Reuse the existing dependency install; only build here. CI installs first.
execSync("npm run build", {
  cwd: FRONTEND_DIR,
  stdio: "inherit",
  env: {
    ...process.env,
    PUBLIC_URL: ".",
    // CRA treats warnings as errors in CI; keep the desktop build resilient.
    CI: "false",
  },
});

console.log("▶ Copying build → desktop/app …");
rmrf(OUT_DIR);
copyDir(BUILD_DIR, OUT_DIR);

// ── Inject runtime backend-URL config into index.html ────────────────
const ENV_SNIPPET = `
    <script>
      // Populated by Electron's preload bridge before the React bundle loads.
      // On the web (no bridge) this is a no-op and REACT_APP_BACKEND_URL wins.
      window.__GRAVITYONE_BOOTSTRAP__ = async function () {
        try {
          if (window.gravityone && window.gravityone.getConfig) {
            var cfg = await window.gravityone.getConfig();
            if (cfg && cfg.backendUrl) window.__GRAVITYONE_BACKEND_URL__ = cfg.backendUrl;
          }
        } catch (e) { /* ignore — fall back to default */ }
      };
    </script>`;

const indexPath = path.join(OUT_DIR, "index.html");
let html = fs.readFileSync(indexPath, "utf8");

// 1) Define the bootstrap FIRST — right after <head> — so it exists before the
//    loader script below (CRA emits the main bundle inside <head>, so order matters).
html = html.replace(/<head[^>]*>/, (m) => `${m}${ENV_SNIPPET}`);

// 2) The React bundle is loaded with `defer`. We must resolve the backend URL
//    *before* it runs, so make the bundle load only after bootstrap resolves.
//    Simplest reliable approach: block on the IPC call synchronously via an
//    inline await using top-level <script> ordering. CRA emits a single deferred
//    main bundle — we convert it to load on bootstrap completion.
html = html.replace(
  /<script defer="defer" src="([^"]+)"><\/script>/,
  (_m, src) =>
    `<script>window.__GRAVITYONE_BOOTSTRAP__().then(function(){` +
    `var s=document.createElement('script');s.src="${src}";document.body.appendChild(s);});</script>`
);

fs.writeFileSync(indexPath, html);

console.log("✓ Desktop frontend ready at desktop/app");
