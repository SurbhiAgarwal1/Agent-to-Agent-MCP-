import React, { createContext, useState, useEffect, useCallback } from "react";
import { loginApi, registerApi, getMeApi } from "../api/auth.js";
import { ApiError, SESSION_STORAGE_KEY } from "../api/client.js";

export const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [token, setToken] = useState(null);
  const [loading, setLoading] = useState(true);
  const [sessionExpiredMessage, setSessionExpiredMessage] = useState(null);

  // Restore an existing session. Only an invalid/expired token should clear it;
  // unrelated API failures must not silently log the user out.
  useEffect(() => {
    async function restoreSession() {
      try {
        const raw = sessionStorage.getItem(SESSION_STORAGE_KEY);
        if (!raw) return;

        const parsed = JSON.parse(raw);
        const savedToken = parsed?.token || parsed?.access_token;
        if (!savedToken) return;

        setToken(savedToken);
        try {
          const profile = await getMeApi();
          setUser(profile);
        } catch (err) {
          if (err instanceof ApiError && err.status === 401) {
            sessionStorage.removeItem(SESSION_STORAGE_KEY);
            setToken(null);
            setUser(null);
          } else {
            // Keep the token/session for transient 5xx/network/validation errors.
            setToken(savedToken);
          }
        }
      } catch {
        sessionStorage.removeItem(SESSION_STORAGE_KEY);
        setToken(null);
        setUser(null);
      } finally {
        setLoading(false);
      }
    }

    restoreSession();

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
    if (!accessToken) {
      throw new ApiError("Login response did not include an access token.", 500, result);
    }

    sessionStorage.setItem(
      SESSION_STORAGE_KEY,
      JSON.stringify({ token: accessToken, role: result.role, user_id: result.user_id })
    );
    setToken(accessToken);

    try {
      const profile = await getMeApi();
      setUser(profile);
      return profile;
    } catch (err) {
      // Do not leave a half-authenticated session behind if profile loading fails.
      sessionStorage.removeItem(SESSION_STORAGE_KEY);
      setToken(null);
      setUser(null);
      throw err;
    }
  }, []);

  const register = useCallback(
    async (email, password, role = "HOSPITAL_STAFF", adminSignupKey = "") => {
      setSessionExpiredMessage(null);
      await registerApi(email, password, role, adminSignupKey);
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
