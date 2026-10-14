import React, { createContext, useState, useEffect, useCallback } from "react";
import { loginApi, registerApi, getMeApi } from "../api/auth.js";
import { SESSION_STORAGE_KEY } from "../api/client.js";

export const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [token, setToken] = useState(null);
  const [loading, setLoading] = useState(true);
  const [sessionExpiredMessage, setSessionExpiredMessage] = useState(null);

  // Restore session on mount
  useEffect(() => {
    async function restoreSession() {
      try {
        const raw = sessionStorage.getItem(SESSION_STORAGE_KEY);
        if (raw) {
          const parsed = JSON.parse(raw);
          if (parsed && (parsed.token || parsed.access_token)) {
            const savedToken = parsed.token || parsed.access_token;
            setToken(savedToken);
            // Fetch fresh user profile from backend
            try {
              const profile = await getMeApi();
              setUser(profile);
            } catch (err) {
              // Token invalid or expired
              sessionStorage.removeItem(SESSION_STORAGE_KEY);
              setToken(null);
              setUser(null);
            }
          }
        }
      } catch (e) {
        sessionStorage.removeItem(SESSION_STORAGE_KEY);
      } finally {
        setLoading(false);
      }
    }

    restoreSession();

    // Listen for auth expiration events from API client
    const handleExpired = () => {
      setToken(null);
      setUser(null);
      setSessionExpiredMessage("Your session has expired. Please sign in again.");
    };
    window.addEventListener("bdm:auth:expired", handleExpired);
    return () => window.removeEventListener("bdm:auth:expired", handleExpired);
  }, []);

  const login = useCallback(async (email, password) => {
    setSessionExpiredMessage(null);
    const result = await loginApi(email, password);
    const accessToken = result.access_token;
    sessionStorage.setItem(
      SESSION_STORAGE_KEY,
      JSON.stringify({ token: accessToken, role: result.role, user_id: result.user_id })
    );
    setToken(accessToken);

    // Fetch user profile with memberships
    const profile = await getMeApi();
    setUser(profile);
    return profile;
  }, []);

  const register = useCallback(
    async (email, password, role = "HOSPITAL_STAFF") => {
      setSessionExpiredMessage(null);
      await registerApi(email, password, role);
      // Auto login following registration
      return login(email, password);
    },
    [login]
  );

  const logout = useCallback(() => {
    sessionStorage.removeItem(SESSION_STORAGE_KEY);
    setToken(null);
    setUser(null);
    setSessionExpiredMessage(null);
  }, []);

  const clearExpiredMessage = useCallback(() => {
    setSessionExpiredMessage(null);
  }, []);

  const value = {
    user,
    token,
    isAuthenticated: !!token && !!user,
    loading,
    sessionExpiredMessage,
    clearExpiredMessage,
    login,
    register,
    logout,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
