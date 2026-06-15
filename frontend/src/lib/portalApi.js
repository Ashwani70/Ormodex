import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
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
  const token = localStorage.getItem("gew_portal_token");
  if (token) {
    config.headers = config.headers || {};
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

export function setPortalToken(token) {
  if (token) localStorage.setItem("gew_portal_token", token);
  else localStorage.removeItem("gew_portal_token");
}

export function getPortalToken() {
  return localStorage.getItem("gew_portal_token");
}

export default portalApi;
