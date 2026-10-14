import { apiClient } from "./client.js";

export async function loginApi(email, password) {
  return apiClient.post("/api/v1/auth/login", { email, password });
}

export async function registerApi(email, password, role = "HOSPITAL_STAFF") {
  return apiClient.post("/api/v1/auth/register", { email, password, role });
}

export async function getMeApi() {
  return apiClient.get("/api/v1/auth/me");
}
