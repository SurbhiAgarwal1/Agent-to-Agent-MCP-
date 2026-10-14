// Centralized API client for the Blood Coordination Platform

const BASE_URL = import.meta.env.VITE_API_BASE_URL || "";
export const SESSION_STORAGE_KEY = "bdm_session";

export class ApiError extends Error {
  constructor(message, status, data) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.data = data;
  }
}

export class SessionExpiredError extends ApiError {
  constructor() {
    super("Your session has expired. Please log in again.", 401, null);
    this.name = "SessionExpiredError";
  }
}

/**
 * Format raw API error details into a human-readable string.
 */
export function formatErrorMessage(data, fallback = "An unexpected error occurred.") {
  if (!data) return fallback;
  const detail = data.detail || data.error;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail.map((d) => d.msg || d.message || JSON.stringify(d)).join("; ");
  }
  return fallback;
}

export function getStoredToken() {
  try {
    const raw = sessionStorage.getItem(SESSION_STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    return parsed?.token || parsed?.access_token || null;
  } catch {
    return null;
  }
}

/**
 * Core fetch wrapper with auth header injection and status handling.
 */
export async function apiRequest(endpoint, options = {}) {
  const url = endpoint.startsWith("http") ? endpoint : `${BASE_URL}${endpoint}`;
  const headers = {
    "Content-Type": "application/json",
    ...(options.headers || {}),
  };

  const token = getStoredToken();
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }

  let response;
  try {
    response = await fetch(url, {
      ...options,
      headers,
    });
  } catch (err) {
    throw new ApiError(
      "Unable to connect to the server. Please check your network connection.",
      0,
      null
    );
  }

  // Handle 401 Session Expiration
  if (response.status === 401) {
    sessionStorage.removeItem(SESSION_STORAGE_KEY);
    window.dispatchEvent(new CustomEvent("bdm:auth:expired"));
    throw new SessionExpiredError();
  }

  let data = null;
  const contentType = response.headers.get("content-type");
  if (contentType && contentType.includes("application/json")) {
    try {
      data = await response.json();
    } catch {
      data = null;
    }
  }

  if (!response.ok) {
    const msg = formatErrorMessage(
      data,
      `Request failed with status ${response.status}.`
    );
    throw new ApiError(msg, response.status, data);
  }

  return data;
}

export const apiClient = {
  get: (endpoint, headers) => apiRequest(endpoint, { method: "GET", headers }),
  post: (endpoint, body, headers) =>
    apiRequest(endpoint, {
      method: "POST",
      body: body ? JSON.stringify(body) : undefined,
      headers,
    }),
  patch: (endpoint, body, headers) =>
    apiRequest(endpoint, {
      method: "PATCH",
      body: body ? JSON.stringify(body) : undefined,
      headers,
    }),
  delete: (endpoint, headers) => apiRequest(endpoint, { method: "DELETE", headers }),
};
