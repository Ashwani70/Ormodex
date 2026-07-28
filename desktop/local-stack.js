// Owns the lifecycle of the two child processes that make up "local mode":
// an embedded Postgres instance and a spawned uvicorn running the real,
// unmodified FastAPI backend pointed at it. Only ever invoked when the
// resolved backend mode is "local" (see main.js's backendMode()).
//
// Both children are bound to 127.0.0.1 only — this is a single-user local
// ERP instance, not a LAN-reachable server.
const { app } = require("electron");
const path = require("path");
const fs = require("fs");
const http = require("http");
const { spawn } = require("child_process");
const log = require("./logger");
const { ensureSecrets, buildBackendEnv } = require("./local-env");

const isDev = !app.isPackaged;

let pg = null; // EmbeddedPostgres instance, once started
let backendProc = null; // uvicorn child process
let currentPort = null;
let starting = null; // in-flight start() promise, so concurrent callers await the same attempt

function pgDataDir() {
  return path.join(app.getPath("userData"), "pgdata");
}

// Resolves the backend source directory: the copy-backend.js build step's
// output (extraResources "backend" folder) in a packaged build, or the real
// backend/ directory one level up from the repo's desktop/ folder in dev.
function backendSourceDir() {
  if (isDev) return path.join(__dirname, "..", "backend");
  return path.join(process.resourcesPath, "backend");
}

// Resolves the bundled Python interpreter: desktop/scripts/bundle-python.js's
// output in a packaged build, or a dev-cache equivalent under
// desktop/runtime/ (produced by running `npm run build:python` locally once).
function pythonBinPath() {
  const base = isDev
    ? path.join(__dirname, "runtime", "python", `${process.platform}-${process.arch}`)
    : path.join(process.resourcesPath, "python");
  return process.platform === "win32"
    ? path.join(base, "python.exe")
    : path.join(base, "bin", "python3");
}

function pollHealth(url, { timeoutMs = 15000, intervalMs = 300 } = {}) {
  const deadline = Date.now() + timeoutMs;
  return new Promise((resolve) => {
    const attempt = () => {
      const req = http.request(
        { hostname: "127.0.0.1", port: currentPort, path: "/health", method: "GET", timeout: 2000 },
        (res) => {
          res.resume();
          if (res.statusCode && res.statusCode < 500) return resolve(true);
          retryOrGiveUp();
        }
      );
      req.on("error", retryOrGiveUp);
      req.on("timeout", () => { req.destroy(); retryOrGiveUp(); });
      req.end();
    };
    const retryOrGiveUp = () => {
      if (Date.now() >= deadline) return resolve(false);
      setTimeout(attempt, intervalMs);
    };
    attempt();
  });
}

async function startPostgres(secrets) {
  // Required lazily — this is a heavy native-binary package, no reason to
  // pay its require() cost when running in cloud mode. Ships as an ESM
  // default export (with a CJS interop wrapper), so the class is at
  // .default, not the module object itself.
  const EmbeddedPostgres = require("embedded-postgres").default;

  pg = new EmbeddedPostgres({
    databaseDir: pgDataDir(),
    user: "ormodex",
    password: secrets.dbPassword,
    port: secrets.dbPort,
    persistent: true,
  });

  const firstRun = !fs.existsSync(path.join(pgDataDir(), "PG_VERSION"));
  if (firstRun) {
    log.info("local-stack: initializing new Postgres data directory", { dir: pgDataDir() });
    await pg.initialise();
  }
  await pg.start();

  if (firstRun) {
    await pg.createDatabase("gravity_erp_local");
    log.info("local-stack: created gravity_erp_local database");
  }
}

// The bundled embeddable Python's `._pth` file pins sys.path to exactly the
// interpreter dir + site-packages (confirmed empirically) — unlike a normal
// Python install, it does NOT add the current working directory to
// sys.path, and does not honor PYTHONPATH either (the ._pth mechanism
// suppresses both). `python -m uvicorn server:app` therefore fails with
// "No module named 'server'" even with the right cwd. Bootstrapping via an
// inline `-c` script that explicitly inserts cwd onto sys.path before
// importing and running uvicorn programmatically sidesteps this entirely —
// no on-disk wrapper file needed, and identical behavior in dev vs packaged
// since backendSourceDir() varies but this snippet is generated fresh each
// time from that resolved path.
function bootstrapScript(port) {
  return (
    `import sys, uvicorn\n` +
    `sys.path.insert(0, ${JSON.stringify(backendSourceDir())})\n` +
    `uvicorn.run("server:app", host="127.0.0.1", port=${port})\n`
  );
}

async function startBackend(secrets) {
  const python = pythonBinPath();
  const cwd = backendSourceDir();
  const env = buildBackendEnv(secrets);

  if (!fs.existsSync(python)) {
    throw new Error(`Bundled Python interpreter not found at ${python}`);
  }
  if (!fs.existsSync(path.join(cwd, "server.py"))) {
    throw new Error(`Backend source not found at ${cwd}`);
  }

  backendProc = spawn(
    python,
    ["-c", bootstrapScript(secrets.backendPort)],
    { cwd, env, windowsHide: true }
  );

  backendProc.stdout.on("data", (buf) => log.info(`[local-backend] ${buf.toString().trim()}`));
  backendProc.stderr.on("data", (buf) => log.warn(`[local-backend] ${buf.toString().trim()}`));
  backendProc.on("exit", (code, signal) => {
    if (backendProc && !stopping) {
      log.error("local-stack: local backend exited unexpectedly", { code, signal });
    }
    backendProc = null;
  });

  currentPort = secrets.backendPort;
  const healthy = await pollHealth(`http://127.0.0.1:${secrets.backendPort}/health`);
  if (!healthy) {
    throw new Error("Local backend did not become healthy in time");
  }
}

let stopping = false;

async function start() {
  if (starting) return starting;
  starting = (async () => {
    log.info("local-stack: starting local Postgres + backend");
    const secrets = await ensureSecrets();
    await startPostgres(secrets);
    await startBackend(secrets);
    log.info("local-stack: local backend ready", { url: getLocalUrl() });
    return { ok: true, url: getLocalUrl() };
  })().catch((err) => {
    log.error("local-stack: failed to start", { message: err.message, stack: err.stack });
    return { ok: false, error: err.message };
  });
  const result = await starting;
  starting = null;
  return result;
}

async function stop() {
  stopping = true;
  try {
    if (backendProc) {
      const proc = backendProc;
      backendProc = null;
      let exited = false;
      proc.once("exit", () => { exited = true; });
      proc.kill("SIGTERM");
      await Promise.race([
        new Promise((resolve) => proc.once("exit", resolve)),
        new Promise((resolve) => setTimeout(resolve, 5000)),
      ]);
      if (!exited) {
        try { proc.kill("SIGKILL"); } catch { /* already gone */ }
      }
    }
    if (pg) {
      try {
        await pg.stop();
      } catch (err) {
        log.warn("local-stack: error stopping embedded Postgres", { message: err.message });
      }
      pg = null;
    }
    log.info("local-stack: stopped");
  } finally {
    stopping = false;
    currentPort = null;
  }
}

function isRunning() {
  return !!backendProc && !!currentPort;
}

function getLocalUrl() {
  return currentPort ? `http://127.0.0.1:${currentPort}` : null;
}

module.exports = { start, stop, isRunning, getLocalUrl };
