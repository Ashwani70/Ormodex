// Builds the environment block for the locally-spawned FastAPI/uvicorn
// process (see local-stack.js) and manages the one-time secrets that process
// needs to keep working across restarts.
//
// backend/core/auth_utils.py hard-requires JWT_SECRET (raises KeyError if
// unset) and backend/core/crypto.py degrades gracefully without
// SETTINGS_ENCRYPTION_KEY but silently stores secrets in plaintext — both are
// generated once here and persisted so restarting the local backend doesn't
// invalidate existing sessions or re-encrypt-as-plaintext previously
// encrypted settings.
const { app } = require("electron");
const crypto = require("crypto");
const fs = require("fs");
const path = require("path");
const net = require("net");

function secretsPath() {
  return path.join(app.getPath("userData"), "local-secrets.json");
}

function readSecrets() {
  try {
    return JSON.parse(fs.readFileSync(secretsPath(), "utf8"));
  } catch {
    return {};
  }
}

function writeSecrets(patch) {
  const next = { ...readSecrets(), ...patch };
  // Local-only secrets file — never touched by the human-edited config.json
  // and never uploaded/synced anywhere by this app.
  fs.writeFileSync(secretsPath(), JSON.stringify(next, null, 2), { mode: 0o600 });
  return next;
}

// Finds a free TCP port by binding to port 0 and reading back what the OS
// assigned, then immediately releasing it. There's a small unavoidable race
// between this check and the real listener binding later, but it's the
// standard best-effort approach absent a job-scheduler-level port lease.
function findFreePort() {
  return new Promise((resolve, reject) => {
    const srv = net.createServer();
    srv.unref();
    srv.on("error", reject);
    srv.listen(0, "127.0.0.1", () => {
      const { port } = srv.address();
      srv.close(() => resolve(port));
    });
  });
}

// Checks whether a specific port is still free (used to validate a
// previously-persisted port before reusing it — if something else has since
// taken it, callers should fall back to findFreePort() for a new one).
function isPortFree(port) {
  return new Promise((resolve) => {
    const srv = net.createServer();
    srv.once("error", () => resolve(false));
    srv.listen(port, "127.0.0.1", () => srv.close(() => resolve(true)));
  });
}

// Ensures dbPort/backendPort/jwtSecret/settingsEncryptionKey/dbPassword all
// exist, generating and persisting whichever are missing. Ports are re-picked
// if the previously persisted one is no longer free (e.g. another app took
// it while this one was closed) rather than failing to bind silently.
async function ensureSecrets() {
  let secrets = readSecrets();
  const patch = {};

  if (!secrets.jwtSecret) patch.jwtSecret = crypto.randomBytes(48).toString("base64");
  if (!secrets.settingsEncryptionKey) {
    // core/crypto.py's Fernet(key) requires EXACTLY the output shape of
    // cryptography.fernet.Fernet.generate_key(): 32 random bytes, base64
    // URL-safe alphabet ("-_" not "+/"), WITH "=" padding. Node's "base64url"
    // encoding uses the right alphabet but strips padding, which Fernet's
    // decoder does not reliably tolerate across versions — re-pad explicitly
    // rather than rely on decoder leniency.
    const unpadded = crypto.randomBytes(32).toString("base64url");
    patch.settingsEncryptionKey = unpadded + "=".repeat((4 - (unpadded.length % 4)) % 4);
  }
  if (!secrets.dbPassword) patch.dbPassword = crypto.randomBytes(24).toString("base64url");

  if (Object.keys(patch).length) secrets = writeSecrets(patch);

  const portPatch = {};
  if (!secrets.dbPort || !(await isPortFree(secrets.dbPort))) {
    portPatch.dbPort = await findFreePort();
  }
  if (!secrets.backendPort || !(await isPortFree(secrets.backendPort))) {
    portPatch.backendPort = await findFreePort();
  }
  if (Object.keys(portPatch).length) secrets = writeSecrets(portPatch);

  return secrets;
}

// Builds the full env block to pass to the spawned uvicorn child process.
// `secrets` is the object returned by ensureSecrets().
function buildBackendEnv(secrets) {
  const dbUrl =
    `postgresql+asyncpg://ormodex:${encodeURIComponent(secrets.dbPassword)}` +
    `@127.0.0.1:${secrets.dbPort}/gravity_erp_local`;

  return {
    ...process.env,
    ENV: "development", // enables server.py's dev-mode auto-DDL bootstrap + seeding
    DATABASE_URL: dbUrl,
    JWT_SECRET: secrets.jwtSecret,
    SETTINGS_ENCRYPTION_KEY: secrets.settingsEncryptionKey,
    LOCAL_STORAGE_DIR: path.join(app.getPath("userData"), "uploads"),
    // Reuses the existing CORS_ORIGINS env var mechanism already read by
    // server.py — allows the file://-loaded renderer's requests through.
    CORS_ORIGINS: "file://",
    // Deliberately NOT set: SUPABASE_*, RESEND_API_KEY, GST/e-way/AI provider
    // keys — all already optional/gated in the backend, so local mode simply
    // runs with those integrations inert rather than crashing.
  };
}

module.exports = { ensureSecrets, buildBackendEnv, secretsPath, findFreePort, isPortFree };
