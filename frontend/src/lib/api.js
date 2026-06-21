import axios from "axios";

// `window.__GRAVITYONE_BACKEND_URL__` lets the desktop (Electron) build override
// the backend at runtime — the web build never sets it, so behaviour is unchanged.
const BACKEND_URL =
  (typeof window !== "undefined" && window.__GRAVITYONE_BACKEND_URL__) ||
  process.env.REACT_APP_BACKEND_URL ||
  "http://localhost:8000";
export const API = `${BACKEND_URL}/api`;

const api = axios.create({
  baseURL: API,
  withCredentials: true,
  headers: { "Content-Type": "application/json" },
});

// Attach Bearer token as a fallback when cookies are blocked
api.interceptors.request.use((config) => {
  const token = localStorage.getItem("gew_access_token");
  if (token) {
    config.headers = config.headers || {};
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

export function formatApiErrorDetail(detail) {
  if (detail == null) return "Something went wrong. Please try again.";
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail))
    return detail
      .map((e) => (e && typeof e.msg === "string" ? e.msg : JSON.stringify(e)))
      .filter(Boolean)
      .join(" ");
  if (detail && typeof detail.msg === "string") return detail.msg;
  return String(detail);
}

export default api;
