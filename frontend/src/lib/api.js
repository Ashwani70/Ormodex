import axios from "axios";
import { getToken, setToken, clearToken } from "./tokenStore";

// `window.__GRAVITYONE_BACKEND_URL__` lets the desktop (Electron) build override
// the backend at runtime — the web build never sets it, so behaviour is unchanged.
const BACKEND_URL =
  (typeof window !== "undefined" && window.__GRAVITYONE_BACKEND_URL__) ||
  process.env.REACT_APP_BACKEND_URL ||
  "https://api.ormodex.com";
export const API = `${BACKEND_URL}/api`;

const api = axios.create({
  baseURL: API,
  withCredentials: true,
  // Bound every request so a hung/unreachable backend can never leave a promise
  // unsettled — otherwise a page's `.finally(() => setLoading(false))` never runs
  // and it sits on "LOADING..." forever. 30s is generous for slow report queries
  // but still guarantees the UI recovers (axios rejects with ECONNABORTED).
  timeout: 30000,
  headers: { "Content-Type": "application/json" },
});

// Read a non-httponly cookie by name (used for the CSRF double-submit token,
// which the backend deliberately sets readable-by-JS — see auth_utils.py's
// set_auth_cookies).
function readCookie(name) {
  const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`));
  return match ? decodeURIComponent(match[1]) : null;
}

// Attach Bearer token as a fallback when cookies are blocked, and echo the
// CSRF cookie back as a header on state-changing requests (log-only enforced
// server-side today — see server.py's csrf_check).
api.interceptors.request.use((config) => {
  const token = getToken();
  if (token) {
    config.headers = config.headers || {};
    config.headers.Authorization = `Bearer ${token}`;
  }
  const method = (config.method || "get").toUpperCase();
  if (method !== "GET" && method !== "HEAD") {
    const csrfToken = readCookie("csrf_token");
    if (csrfToken) {
      config.headers = config.headers || {};
      config.headers["X-CSRF-Token"] = csrfToken;
    }
  }
  if (config.data instanceof FormData && config.headers) {
    delete config.headers["Content-Type"];
  }
  return config;
});

// Automatically format error details to strings to prevent React rendering issues
// Also handle 401 Unauthorized errors by attempting to refresh the token
let isRefreshing = false;
let failedQueue = [];

const processQueue = (error, token = null) => {
  failedQueue.forEach((prom) => {
    if (error) {
      prom.reject(error);
    } else {
      prom.resolve(token);
    }
  });
  failedQueue = [];
};

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;

    if (error.response && error.response.data && error.response.data.detail) {
      error.response.data.detail = formatApiErrorDetail(error.response.data.detail, error);
    }

    if (error.response && error.response.status === 401 && !originalRequest._retry) {
      if (
        originalRequest.url.includes("/auth/login") ||
        originalRequest.url.includes("/auth/refresh") ||
        originalRequest.url.includes("/auth/logout")
      ) {
        return Promise.reject(error);
      }

      if (isRefreshing) {
        return new Promise((resolve, reject) => {
          failedQueue.push({ resolve, reject });
        })
          .then((token) => {
            originalRequest.headers.Authorization = `Bearer ${token}`;
            return api(originalRequest);
          })
          .catch((err) => {
            return Promise.reject(err);
          });
      }

      originalRequest._retry = true;
      isRefreshing = true;

      try {
        const { data } = await axios.post(
          `${API}/auth/refresh`,
          {},
          { withCredentials: true, timeout: 30000 }
        );
        const newToken = data.access_token;
        if (newToken) {
          setToken(newToken);
        }
        processQueue(null, newToken);

        originalRequest.headers.Authorization = `Bearer ${newToken}`;
        return api(originalRequest);
      } catch (refreshError) {
        processQueue(refreshError, null);
        clearToken();
        if (window.location.pathname !== "/login") {
          window.location.href = "/login";
        }
        return Promise.reject(refreshError);
      } finally {
        isRefreshing = false;
      }
    }

    return Promise.reject(error);
  }
);

export function formatApiErrorDetail(detail, error) {
  const err = error || (detail && (detail.isAxiosError || detail.message) ? detail : null);
  if (err) {
    if (!err.response) {
      if (err.code === "ECONNABORTED") return "Request timeout. Please try again.";
      return "Network error: Unable to reach the server.";
    }
    const status = err.response.status;
    const body = err.response.data;
    const innerDetail = body?.detail || body?.message;
    if (innerDetail) {
      return formatApiErrorDetail(innerDetail);
    }
    return `Error ${status}: Request failed`;
  }

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
