// Minimal file-based crash/error logger — no external dependency needed for a
// thin client. Writes JSON lines to userData/logs/main.log with automatic
// rotation so the file never grows unbounded across long-running installs.
const { app } = require("electron");
const path = require("path");
const fs = require("fs");

const MAX_BYTES = 2 * 1024 * 1024; // 2 MB before rotating

function logDir() {
  const dir = path.join(app.getPath("userData"), "logs");
  fs.mkdirSync(dir, { recursive: true });
  return dir;
}

function logFile() {
  return path.join(logDir(), "main.log");
}

function rotateIfNeeded() {
  try {
    const file = logFile();
    if (fs.existsSync(file) && fs.statSync(file).size > MAX_BYTES) {
      fs.renameSync(file, path.join(logDir(), "main.log.1"));
    }
  } catch {
    // best-effort — never let logging itself crash the app
  }
}

function write(level, message, extra) {
  try {
    rotateIfNeeded();
    const line = JSON.stringify({
      t: new Date().toISOString(),
      level,
      message,
      ...(extra !== undefined ? { extra } : {}),
    });
    fs.appendFileSync(logFile(), line + "\n");
  } catch {
    // ignore — logging must never throw into app lifecycle code
  }
  const consoleFn = level === "error" ? console.error : level === "warn" ? console.warn : console.log;
  consoleFn(`[${level}] ${message}`, extra ?? "");
}

module.exports = {
  info: (message, extra) => write("info", message, extra),
  warn: (message, extra) => write("warn", message, extra),
  error: (message, extra) => write("error", message, extra),
  filePath: logFile,
};
