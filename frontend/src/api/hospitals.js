import { apiClient } from "./client.js";

export async function listHospitals() {
  return apiClient.get("/api/v1/hospitals");
}
