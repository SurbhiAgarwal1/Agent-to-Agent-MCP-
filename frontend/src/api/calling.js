import { apiClient } from "./client.js";

/**
 * Dispatch an automated emergency voice call via CallingAgent.
 */
export async function dispatchVoiceCall(payload) {
  return apiClient.post("/api/v1/calling/dispatch", payload);
}

/**
 * Simulate / send DTMF touchtone carrier callback.
 */
export async function sendVoiceWebhook(payload) {
  return apiClient.post("/api/v1/calling/webhook", payload);
}

/**
 * Retrieve voice call logs for a specific blood request.
 */
export async function getCallLogs(requestId) {
  return apiClient.get(`/api/v1/calling/logs/${requestId}`);
}
