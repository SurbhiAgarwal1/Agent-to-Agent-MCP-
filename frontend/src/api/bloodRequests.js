import { apiClient } from "./client.js";

export async function listBloodRequests() {
  return apiClient.get("/api/v1/blood-requests");
}

export async function getBloodRequest(id) {
  return apiClient.get(`/api/v1/blood-requests/${id}`);
}

export async function createBloodRequest(payload) {
  return apiClient.post("/api/v1/blood-requests", payload);
}

export async function updateBloodRequestStatus(id, status) {
  return apiClient.patch(`/api/v1/blood-requests/${id}/status`, { status });
}

export async function getRequestMatches(id) {
  return apiClient.get(`/api/v1/blood-requests/${id}/matches`);
}

export async function coordinateBloodRequest(id) {
  return apiClient.post(`/api/v1/blood-requests/${id}/coordinate`);
}

export async function orchestrateBloodRequest(id) {
  return apiClient.post(`/api/v1/blood-requests/${id}/orchestrate`);
}

export async function completeMatch(requestId, matchId) {
  return apiClient.post(
    `/api/v1/blood-requests/${requestId}/matches/${matchId}/complete`
  );
}

export async function rejectMatch(requestId, matchId, reason = null) {
  return apiClient.post(
    `/api/v1/blood-requests/${requestId}/matches/${matchId}/reject`,
    { reason }
  );
}

export async function processNlRequest(text) {
  return apiClient.post("/api/v1/nl-request", { text });
}
