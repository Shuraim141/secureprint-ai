import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

import { api, setUnauthorizedHandler, tokenStore } from "../services/api";

const AuthContext = createContext(null);

/** Holds the logged-in user. status: "loading" | "authenticated" | "anonymous". */
export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [status, setStatus] = useState(tokenStore.get() ? "loading" : "anonymous");

  const clearSession = useCallback(() => {
    tokenStore.clear();
    setUser(null);
    setStatus("anonymous");
  }, []);

  // The API client calls this when the server rejects our token (expired / revoked).
  useEffect(() => {
    setUnauthorizedHandler(clearSession);
    return () => setUnauthorizedHandler(null);
  }, [clearSession]);

  // Restore the session after a page reload by asking the backend who the token belongs to.
  useEffect(() => {
    if (!tokenStore.get()) return undefined;
    let cancelled = false;
    api
      .me()
      .then((profile) => {
        if (cancelled) return;
        setUser(profile);
        setStatus("authenticated");
      })
      .catch(() => {
        if (!cancelled) clearSession();
      });
    return () => {
      cancelled = true;
    };
  }, [clearSession]);

  const login = useCallback(async (username, password) => {
    const result = await api.login(username, password);
    tokenStore.set(result.access_token);
    try {
      const profile = await api.me();
      setUser(profile);
      setStatus("authenticated");
    } catch (error) {
      tokenStore.clear();
      throw error;
    }
  }, []);

  const logout = useCallback(async () => {
    try {
      await api.logout(); // revokes the token server-side and writes an audit record
    } catch {
      /* even if the server is unreachable, drop the local session */
    }
    clearSession();
  }, [clearSession]);

  const can = useCallback((permission) => Boolean(user?.permissions?.includes(permission)), [user]);

  const value = useMemo(
    () => ({ user, status, login, logout, can }),
    [user, status, login, logout, can],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside <AuthProvider>");
  return context;
}
