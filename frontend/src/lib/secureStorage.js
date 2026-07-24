// Encrypted localStorage wrapper for the access token.
//
// Threat model: this defends against casual at-rest inspection of localStorage
// (browsing appdata files, a backup, another local process/extension skimming
// storage) — the token is AES-GCM encrypted with a key that itself lives in
// IndexedDB, not in the string you'd see if you opened localStorage directly.
// It does NOT defend against an attacker who already has arbitrary JS execution
// in this origin (XSS): at that point they can call the same decrypt function
// this module exposes. No client-side storage mechanism can fix that — the
// real mitigation for XSS is CSP + output encoding, which is a separate,
// already-existing concern (see core/security in the backend).
//
// The encryption key is generated once per browser profile as a non-extractable
// CryptoKey (Web Crypto refuses to ever hand back its raw bytes), cached in
// IndexedDB, and reused across sessions. If IndexedDB is unavailable (very old
// browser, privacy mode edge cases) this transparently falls back to plain
// localStorage so login never breaks.

const DB_NAME = "ormodex_secure";
const STORE_NAME = "keys";
const KEY_ID = "token-key";

let cachedKeyPromise = null;

function openDb() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, 1);
    req.onupgradeneeded = () => {
      if (!req.result.objectStoreNames.contains(STORE_NAME)) {
        req.result.createObjectStore(STORE_NAME);
      }
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

async function idbGet(key) {
  const db = await openDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, "readonly");
    const req = tx.objectStore(STORE_NAME).get(key);
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

async function idbSet(key, value) {
  const db = await openDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, "readwrite");
    tx.objectStore(STORE_NAME).put(value, key);
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}

async function getOrCreateKey() {
  if (cachedKeyPromise) return cachedKeyPromise;
  cachedKeyPromise = (async () => {
    const existing = await idbGet(KEY_ID).catch(() => null);
    if (existing) return existing;
    const key = await crypto.subtle.generateKey({ name: "AES-GCM", length: 256 }, false, ["encrypt", "decrypt"]);
    await idbSet(KEY_ID, key);
    return key;
  })();
  return cachedKeyPromise;
}

function supported() {
  return typeof indexedDB !== "undefined" && typeof crypto !== "undefined" && !!crypto.subtle;
}

const b64 = {
  encode: (buf) => btoa(String.fromCharCode(...new Uint8Array(buf))),
  decode: (str) => Uint8Array.from(atob(str), (c) => c.charCodeAt(0)),
};

export async function secureSet(storageKey, plainValue) {
  if (!supported()) {
    localStorage.setItem(storageKey, plainValue);
    return;
  }
  try {
    const key = await getOrCreateKey();
    const iv = crypto.getRandomValues(new Uint8Array(12));
    const encoded = new TextEncoder().encode(plainValue);
    const cipher = await crypto.subtle.encrypt({ name: "AES-GCM", iv }, key, encoded);
    localStorage.setItem(storageKey, JSON.stringify({ iv: b64.encode(iv), data: b64.encode(cipher), enc: 1 }));
  } catch {
    // Encryption unavailable for some reason — never block login over it.
    localStorage.setItem(storageKey, plainValue);
  }
}

export async function secureGet(storageKey) {
  const raw = localStorage.getItem(storageKey);
  if (!raw) return null;
  let parsed;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return raw; // legacy plaintext value from before this wrapper existed
  }
  if (!parsed || !parsed.enc) return raw;
  try {
    const key = await getOrCreateKey();
    const iv = b64.decode(parsed.iv);
    const data = b64.decode(parsed.data);
    const plain = await crypto.subtle.decrypt({ name: "AES-GCM", iv }, key, data);
    return new TextDecoder().decode(plain);
  } catch {
    return null; // key lost/rotated (e.g. profile data partially cleared) — force re-login
  }
}

export function secureRemove(storageKey) {
  localStorage.removeItem(storageKey);
}
