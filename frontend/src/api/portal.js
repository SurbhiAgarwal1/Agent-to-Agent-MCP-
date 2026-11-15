import { apiClient } from "./client.js";

export const getPortalMe = () => apiClient.get("/api/v1/portal/me");

// Donor
export const listDonorNotifications = () => apiClient.get("/api/v1/portal/donor/notifications");
export const respondDonorNotification = (id, response) =>
  apiClient.post(`/api/v1/portal/donor/notifications/${id}/respond`, { response });
export const setDonorAvailability = (available) =>
  apiClient.patch("/api/v1/portal/donor/availability", { available });

// Blood bank
export const getBankInventory = () => apiClient.get("/api/v1/portal/bank/inventory");
export const saveBankInventory = (group, body) =>
  apiClient.put(`/api/v1/portal/bank/inventory/${encodeURIComponent(group)}`, body);
export const listBankNotifications = () => apiClient.get("/api/v1/portal/bank/notifications");
export const respondBankNotification = (id, body) =>
  apiClient.post(`/api/v1/portal/bank/notifications/${id}/respond`, body);

// Hospital staff
export const listHospitalAlerts = () => apiClient.get("/api/v1/hospital-alerts");
export const markHospitalAlertRead = (id) => apiClient.post(`/api/v1/hospital-alerts/${id}/read`);
export const getRequestResponses = (requestId) =>
  apiClient.get(`/api/v1/blood-requests/${requestId}/responses`);
