import { createContext, useContext, useEffect, useState, useCallback, useMemo } from "react";
import api from "@/lib/api";
import { setToken, clearToken } from "@/lib/tokenStore";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null); // null=loading, false=unauthenticated, object=user
  const [loading, setLoading] = useState(true);

  const fetchMe = useCallback(async () => {
    try {
      const { data } = await api.get("/auth/me");
      setUser(data);
    } catch (e) {
      setUser(false);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchMe();
  }, [fetchMe]);

  // useCallback so the handler identities are stable across renders — otherwise
  // they'd change every render, defeating the useMemo on the context value below
  // and re-rendering every useAuth() consumer (Layout, Sidebar, every page).
  const login = useCallback(async (email, password, opts = {}) => {
    const { rememberMe = false, companyCode, captchaToken, captchaAnswer } = opts;
    const { data } = await api.post("/auth/login", {
      email,
      password,
      remember_me: rememberMe,
      company_code: companyCode || undefined,
      captcha_token: captchaToken || undefined,
      captcha_answer: captchaAnswer || undefined,
    });
    // MFA-enabled accounts get a challenge token instead of a session; the
    // caller must follow up with completeMfaLogin(mfa_token, code).
    if (data.mfa_required) {
      return { mfaRequired: true, mfaToken: data.mfa_token };
    }
    if (data.access_token) {
      setToken(data.access_token);
    }
    setUser(data.user);
    return data.user;
  }, []);

  const completeMfaLogin = useCallback(async (mfaToken, code) => {
    const { data } = await api.post("/auth/login/mfa", {
      mfa_token: mfaToken,
      code,
    });
    if (data.access_token) {
      setToken(data.access_token);
    }
    setUser(data.user);
    return data.user;
  }, []);

  const changePassword = useCallback(async (currentPassword, newPassword) => {
    const { data } = await api.post("/auth/change-password", {
      current_password: currentPassword,
      new_password: newPassword,
    });
    if (data.access_token) {
      setToken(data.access_token);
    }
    // The fresh user no longer carries the reset flag, so the app un-gates.
    setUser(data.user);
    return data.user;
  }, []);

  const logout = useCallback(async () => {
    try {
      await api.post("/auth/logout");
    } catch {}
    clearToken();
    setUser(false);
  }, []);

  // Revokes every session for this account (all devices), not just this one.
  const logoutAll = useCallback(async () => {
    try {
      await api.post("/auth/logout-all");
    } catch {}
    clearToken();
    setUser(false);
  }, []);

  // True when the signed-in account must change its password before using the app.
  const mustChangePassword = !!(user && user.password_change_required);

  // Memoize the context value so consumers only re-render when something they
  // actually use (user/loading/flags) changes — not on every AuthProvider render.
  const value = useMemo(
    () => ({ user, loading, login, completeMfaLogin, changePassword, mustChangePassword, logout, logoutAll, refresh: fetchMe }),
    [user, loading, login, completeMfaLogin, changePassword, mustChangePassword, logout, logoutAll, fetchMe]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export const useAuth = () => useContext(AuthContext);
