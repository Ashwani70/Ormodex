// Single source of truth for the access token, used by both api.js (needs a
// synchronous read for the axios request interceptor) and AuthContext (writes
// on login/refresh/logout). Persists via secureStorage (encrypted-at-rest)
// but keeps an in-memory mirror so reading it never has to be async.
import { secureGet, secureSet, secureRemove } from "./secureStorage";

const STORAGE_KEY = "gew_access_token";

let memoryToken = null;
let hydrated = false;
// Resolves once the very first async read from encrypted storage completes,
// so callers that must not race the initial hydration (rare) can await it.
let hydratePromise = null;

function hydrate() {
  if (hydratePromise) return hydratePromise;
  hydratePromise = secureGet(STORAGE_KEY).then((value) => {
    memoryToken = value;
    hydrated = true;
    return value;
  });
  return hydratePromise;
}
hydrate();

export function getToken() {
  return memoryToken;
}

export function isHydrated() {
  return hydrated;
}

export async function waitForHydration() {
  return hydratePromise || hydrate();
}

export function setToken(value) {
  memoryToken = value;
  hydrated = true;
  if (value) secureSet(STORAGE_KEY, value);
  else secureRemove(STORAGE_KEY);
}

export function clearToken() {
  memoryToken = null;
  hydrated = true;
  secureRemove(STORAGE_KEY);
}
