// Copies backend/ source into desktop/backend-src/, which becomes an
// extraResources entry in the packaged app (see local-stack.js's
// backendSourceDir(), which reads from process.resourcesPath/backend there).
//
// This is a discrete copy step (rather than pointing electron-builder's
// extraResources "from" directly at ../backend) specifically so it can
// explicitly exclude .env, uploads/, __pycache__, and tests — guarding
// against a stray .env with real cloud DATABASE_URL/JWT_SECRET accidentally
// ending up inside a public installer.
//
// Run from desktop/:  npm run copy:backend   (also runs automatically before dist/pack)
const fs = require("fs");
const path = require("path");

const DESKTOP_DIR = path.resolve(__dirname, "..");
const BACKEND_DIR = path.resolve(DESKTOP_DIR, "..", "backend");
const OUT_DIR = path.join(DESKTOP_DIR, "backend-src");

// Directory names excluded anywhere in the tree.
const EXCLUDE_DIRS = new Set([
  "__pycache__", "tests", ".venv", "venv", "uploads", ".pytest_cache", ".mypy_cache",
]);
// Exact file names excluded at any level (secrets, and standalone dev
// utility scripts not needed at runtime).
const EXCLUDE_FILES = new Set([
  ".env", ".env.local", "test_db_conn.py", "update_admin_pwd.py",
]);
// File extensions excluded anywhere.
const EXCLUDE_EXTS = new Set([".pyc", ".pyo"]);

function shouldSkip(entryName, isDir) {
  if (isDir) return EXCLUDE_DIRS.has(entryName);
  if (EXCLUDE_FILES.has(entryName)) return true;
  return EXCLUDE_EXTS.has(path.extname(entryName));
}

function copyDir(src, dest) {
  fs.mkdirSync(dest, { recursive: true });
  for (const entry of fs.readdirSync(src, { withFileTypes: true })) {
    if (shouldSkip(entry.name, entry.isDirectory())) continue;
    const s = path.join(src, entry.name);
    const d = path.join(dest, entry.name);
    if (entry.isDirectory()) copyDir(s, d);
    else fs.copyFileSync(s, d);
  }
}

console.log("▶ Copying backend/ → desktop/backend-src/ (excluding .env, uploads/, tests, caches)…");
fs.rmSync(OUT_DIR, { recursive: true, force: true });
copyDir(BACKEND_DIR, OUT_DIR);

// Explicit safety check, not just reliance on the exclude list above — fail
// the build loudly if a .env somehow still made it through.
const leftoverEnv = fs.readdirSync(OUT_DIR).filter((f) => f === ".env" || f === ".env.local");
if (leftoverEnv.length) {
  console.error(`✗ Refusing to continue: found ${leftoverEnv.join(", ")} in ${OUT_DIR}`);
  process.exit(1);
}

console.log(`✓ Backend source ready at ${OUT_DIR}`);
