import axios from "axios";
import { getToken, setToken, clearToken } from "./tokenStore";

// `window.__GRAVITYONE_BACKEND_URL__` lets the desktop (Electron) build override
// the backend at runtime — the web build never sets it, so behaviour is unchanged.
export const BACKEND_URL =
  (typeof window !== "undefined" && window.__GRAVITYONE_BACKEND_URL__) ||
  process.env.REACT_APP_BACKEND_URL ||
  "http://localhost:8000";
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

// Matches server.py's CSRF_MISMATCH_DETAIL — a 403 with this exact detail
// means the CSRF double-submit cookie went stale (e.g. rotated by a token
// refresh, see auth_utils.py's issue_csrf_cookie) rather than a real
// authorization failure, so it's safe to self-heal by fetching a fresh
// cookie and retrying once instead of surfacing a dead-end error.
const CSRF_MISMATCH_DETAIL = "CSRF token missing or invalid. Refreshing session — please retry.";

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;
    const rawDetail =
      error.response?.data?.detail ??
      error.response?.data?.message ??
      error.response?.data?.error;

    if (
      error.response &&
      error.response.status === 403 &&
      rawDetail === CSRF_MISMATCH_DETAIL &&
      originalRequest &&
      !originalRequest._csrfRetry
    ) {
      originalRequest._csrfRetry = true;
      try {
        await axios.get(`${API}/auth/csrf`, { withCredentials: true, timeout: 30000 });
        return api(originalRequest);
      } catch {
        // Fall through to normal error handling below (e.g. not logged in).
      }
    }

    const formattedDetail = formatApiErrorDetail(rawDetail, error);
    if (!error.response) {
      error.response = { data: { detail: formattedDetail } };
    } else if (!error.response.data || typeof error.response.data !== "object") {
      error.response.data = { detail: formattedDetail };
    } else {
      error.response.data.detail = formattedDetail;
    }

    if (error.response && error.response.status === 401 && !originalRequest._retry) {
      if (
        originalRequest.url &&
        (originalRequest.url.includes("/auth/login") ||
          originalRequest.url.includes("/auth/refresh") ||
          originalRequest.url.includes("/auth/logout"))
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
  if (detail && (detail.isAxiosError || detail.message || detail.response || detail.config)) {
    error = detail;
    detail =
      error.response?.data?.detail ??
      error.response?.data?.message ??
      error.response?.data?.error;
  }

  const err = error || (detail && (detail.isAxiosError || detail.message) ? detail : null);

  if (typeof detail === "string" && detail.trim()) return detail;

  if (Array.isArray(detail) && detail.length > 0) {
    const formattedArray = detail
      .map((e) => {
        if (!e) return "";
        if (typeof e === "string") return e;
        if (typeof e.msg === "string") return e.msg;
        if (typeof e.detail === "string") return e.detail;
        return JSON.stringify(e);
      })
      .filter(Boolean)
      .join(" ");
    if (formattedArray) return formattedArray;
  }

  if (detail && typeof detail.msg === "string" && detail.msg.trim()) return detail.msg;

  if (err) {
    if (!err.response) {
      if (err.code === "ECONNABORTED") return "Request timeout. Please try again.";
      return "Network error: Unable to reach the server.";
    }
    const status = err.response.status;
    const body = err.response.data;

    if (body) {
      const innerDetail = body.detail || body.message || body.error;
      if (innerDetail && innerDetail !== detail) {
        return formatApiErrorDetail(innerDetail, err);
      }
      if (typeof body === "string" && body.trim()) {
        const cleanText = body.replace(/<[^>]*>?/gm, "").trim();
        if (cleanText) return `Error ${status}: ${cleanText.slice(0, 120)}`;
      }
    }
    return `Error ${status}: Request failed`;
  }

  if (detail == null) return "Something went wrong. Please try again.";
  return String(detail);
}

export default api;
