// Downloads a redistributable Python runtime, installs the local-mode
// backend's dependencies into it, and places the result under
// desktop/runtime/python/<platform>-<arch>/ — the exact layout local-stack.js
// expects (see its pythonBinPath()).
//
// Pinned to 3.12.7 to match render.yaml's production PYTHON_VERSION exactly
// (read dynamically below, not hardcoded twice) — 3.12 has been out long
// enough that every native-extension dependency (asyncpg, bcrypt,
// cryptography, greenlet, pandas, numpy) has prebuilt wheels for it on every
// target platform, which is NOT yet guaranteed for newer Python releases.
// This is unrelated to whatever Python happens to be installed on the build
// machine — local-stack.js never touches system Python or PATH, only this
// bundled interpreter, so a version mismatch on the dev machine is harmless.
//
// Run from desktop/:  npm run build:python   (also runs automatically before dist/pack)
//
// Must be run natively on each target OS — cannot cross-bundle a Windows
// Python from a Linux CI runner and vice versa. desktop-release.yml already
// runs its build job natively per-OS (windows-latest/macos-latest/
// ubuntu-latest), so this just adds a step inside each existing job.
const { execFileSync } = require("child_process");
const fs = require("fs");
const https = require("https");
const path = require("path");

const DESKTOP_DIR = path.resolve(__dirname, "..");
const BACKEND_DIR = path.resolve(DESKTOP_DIR, "..", "backend");
const REQUIREMENTS = path.join(BACKEND_DIR, "requirements-desktop.txt");
const CACHE_DIR = path.join(DESKTOP_DIR, ".build-cache");
const OUT_ROOT = path.join(DESKTOP_DIR, "runtime", "python");

function readPinnedPythonVersion() {
  // Cross-check against render.yaml's PYTHON_VERSION rather than hardcoding
  // the same string in two files, so a future prod Python bump can't
  // silently desync the desktop bundle from prod without at least a diff
  // showing up here.
  const renderYamlPath = path.resolve(DESKTOP_DIR, "..", "render.yaml");
  const contents = fs.readFileSync(renderYamlPath, "utf8");
  const match = contents.match(/PYTHON_VERSION\s*\n\s*value:\s*([0-9.]+)/);
  if (!match) {
    throw new Error(`Could not find PYTHON_VERSION in ${renderYamlPath}`);
  }
  return match[1];
}

function download(url, destPath) {
  return new Promise((resolve, reject) => {
    fs.mkdirSync(path.dirname(destPath), { recursive: true });
    const file = fs.createWriteStream(destPath);
    https
      .get(url, (res) => {
        if (res.statusCode >= 300 && res.statusCode < 400 && res.headers.location) {
          file.close();
          fs.rmSync(destPath, { force: true });
          return resolve(download(res.headers.location, destPath));
        }
        if (res.statusCode !== 200) {
          reject(new Error(`Download failed (${res.statusCode}): ${url}`));
          return;
        }
        res.pipe(file);
        file.on("finish", () => file.close(resolve));
      })
      .on("error", reject);
  });
}

function targetKey() {
  return `${process.platform}-${process.arch}`;
}

function outDir() {
  return path.join(OUT_ROOT, targetKey());
}

// ── Windows: official embeddable distribution ───────────────────────────
async function bundleWindows(version) {
  const zipUrl = `https://www.python.org/ftp/python/${version}/python-${version}-embed-amd64.zip`;
  const zipPath = path.join(CACHE_DIR, `python-${version}-embed-amd64.zip`);
  if (!fs.existsSync(zipPath)) {
    console.log(`▶ Downloading ${zipUrl}`);
    await download(zipUrl, zipPath);
  }

  const dest = outDir();
  fs.rmSync(dest, { recursive: true, force: true });
  fs.mkdirSync(dest, { recursive: true });

  // Requires either PowerShell's Expand-Archive (present on every supported
  // Windows/CI runner) or a bundled unzip — avoid a new npm dependency for
  // something the OS already provides.
  execFileSync(
    "powershell",
    ["-NoProfile", "-Command", `Expand-Archive -Path "${zipPath}" -DestinationPath "${dest}" -Force`],
    { stdio: "inherit" }
  );

  // The embeddable distribution ships WITHOUT pip and with `import site`
  // disabled by default (a `._pth` file pins sys.path to stdlib only) — a
  // known gotcha: third-party packages installed via pip are silently
  // invisible at runtime unless this file is edited to re-enable site
  // processing.
  const pthFiles = fs.readdirSync(dest).filter((f) => f.endsWith("._pth"));
  for (const pthFile of pthFiles) {
    const pthPath = path.join(dest, pthFile);
    let content = fs.readFileSync(pthPath, "utf8");
    content = content.replace(/^#\s*import site/m, "import site");
    fs.writeFileSync(pthPath, content);
  }

  // Bootstrap pip.
  const getPipPath = path.join(CACHE_DIR, "get-pip.py");
  if (!fs.existsSync(getPipPath)) {
    await download("https://bootstrap.pypa.io/get-pip.py", getPipPath);
  }
  const pythonExe = path.join(dest, "python.exe");
  execFileSync(pythonExe, [getPipPath, "--no-warn-script-location"], { stdio: "inherit" });

  console.log("▶ Installing backend dependencies…");
  execFileSync(
    pythonExe,
    ["-m", "pip", "install", "--no-warn-script-location", "-r", REQUIREMENTS],
    { stdio: "inherit" }
  );

  return pythonExe;
}

// ── macOS / Linux: python-build-standalone portable builds ──────────────
async function bundleUnix(version) {
  // indygreg/python-build-standalone publishes per-platform, fully
  // relocatable CPython tarballs — the closest Unix equivalent to Windows's
  // official embeddable zip (no first-class "embeddable" distribution exists
  // for macOS/Linux from python.org itself).
  const releaseTag = `${version}+20241016`; // pinned release matching 3.12.7; update if this tag is pulled
  const archMap = { x64: "x86_64", arm64: "aarch64" };
  const platformMap = {
    darwin: `${archMap[process.arch]}-apple-darwin`,
    linux: `${archMap[process.arch]}-unknown-linux-gnu`,
  };
  const target = platformMap[process.platform];
  if (!target) throw new Error(`Unsupported platform for bundle-python.js: ${process.platform}/${process.arch}`);

  const tarballName = `cpython-${version}+20241016-${target}-install_only.tar.gz`;
  const url = `https://github.com/indygreg/python-build-standalone/releases/download/20241016/${tarballName}`;
  const tarPath = path.join(CACHE_DIR, tarballName);
  if (!fs.existsSync(tarPath)) {
    console.log(`▶ Downloading ${url}`);
    await download(url, tarPath);
  }

  const dest = outDir();
  fs.rmSync(dest, { recursive: true, force: true });
  fs.mkdirSync(dest, { recursive: true });
  // python-build-standalone's "install_only" tarballs extract to a top-level
  // python/ dir — extract directly into dest so dest/bin/python3 exists.
  execFileSync("tar", ["-xzf", tarPath, "-C", dest, "--strip-components=1"], { stdio: "inherit" });

  const pythonBin = path.join(dest, "bin", "python3");
  console.log("▶ Installing backend dependencies…");
  execFileSync(pythonBin, ["-m", "pip", "install", "-r", REQUIREMENTS], { stdio: "inherit" });

  return pythonBin;
}

async function smokeTest(pythonBin) {
  console.log("▶ Smoke-testing bundled interpreter…");
  execFileSync(
    pythonBin,
    ["-c", "import fastapi, sqlalchemy, asyncpg, uvicorn, cryptography, bcrypt, pandas, numpy; print('OK')"],
    { stdio: "inherit" }
  );
}

async function main() {
  const version = readPinnedPythonVersion();
  console.log(`▶ Bundling Python ${version} for ${targetKey()}…`);
  fs.mkdirSync(CACHE_DIR, { recursive: true });

  const pythonBin =
    process.platform === "win32" ? await bundleWindows(version) : await bundleUnix(version);

  await smokeTest(pythonBin);
  console.log(`✓ Python runtime ready at ${outDir()}`);
}

main().catch((err) => {
  console.error("✗ bundle-python.js failed:", err.message);
  process.exit(1);
});
