import axios from "axios";
import { secureGet, secureSet, secureRemove } from "./secureStorage";

// Encrypted-at-rest mirror of the portal token, same approach as tokenStore.js
// for the internal realm. Kept in-memory for synchronous reads (the axios
// interceptor below can't await), seeded once at module load.
const PORTAL_TOKEN_KEY = "gew_portal_token";
let portalTokenMemory = null;
const portalTokenHydrated = secureGet(PORTAL_TOKEN_KEY).then((v) => { portalTokenMemory = v; });

// `window.__GRAVITYONE_BACKEND_URL__` lets the desktop (Electron) build override
// the backend at runtime — the web build never sets it, so behaviour is unchanged.
const BACKEND_URL =
  (typeof window !== "undefined" && window.__GRAVITYONE_BACKEND_URL__) ||
  process.env.REACT_APP_BACKEND_URL ||
  "http://localhost:8000";
export const PORTAL_API = `${BACKEND_URL}/api/portal`;

// A SEPARATE client from the internal `api` — its own baseURL and its own
// token key, so the portal (external) realm and the internal realm never share
// credentials in the browser.
const portalApi = axios.create({
  baseURL: PORTAL_API,
  withCredentials: true,
  headers: { "Content-Type": "application/json" },
});

portalApi.interceptors.request.use((config) => {
  if (portalTokenMemory) {
    config.headers = config.headers || {};
    config.headers.Authorization = `Bearer ${portalTokenMemory}`;
  }
  return config;
});

export function setPortalToken(token) {
  portalTokenMemory = token || null;
  if (token) secureSet(PORTAL_TOKEN_KEY, token);
  else secureRemove(PORTAL_TOKEN_KEY);
}

export function getPortalToken() {
  return portalTokenMemory;
}

// Awaited by callers that run at mount-time and must not race the async
// decrypt of the stored token (e.g. Portal.jsx deciding whether to even
// attempt loading a session on first paint).
export async function getPortalTokenAsync() {
  await portalTokenHydrated;
  return portalTokenMemory;
}

export default portalApi;
