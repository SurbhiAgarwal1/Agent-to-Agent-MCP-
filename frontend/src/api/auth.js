import { apiClient } from "./client.js";

export async function loginApi(email, password) {
  return apiClient.post("/api/v1/auth/login", { email, password });
}

export async function registerApi(email, password, role = "HOSPITAL_STAFF", adminSignupKey = "") {
  return apiClient.post("/api/v1/auth/register", { email, password, role, admin_signup_key: adminSignupKey || undefined });
}

export async function getMeApi() {
  return apiClient.get("/api/v1/auth/me");
}
