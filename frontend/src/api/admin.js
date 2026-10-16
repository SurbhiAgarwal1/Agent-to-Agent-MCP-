import { apiClient } from "./client.js";

export async function createUser(email, password, role) {
  return apiClient.post("/api/v1/auth/users", { email, password, role });
}

export async function listAuditLogs(limit = 50) {
  return apiClient.get(`/api/v1/auth/audit-logs?limit=${limit}`);
}

export async function grantHospitalMembership(userId, organizationId, membershipType = "STAFF") {
  return apiClient.post(`/api/v1/auth/users/${userId}/hospital-memberships`, {
    organization_id: organizationId,
    membership_type: membershipType,
  });
}

export async function grantBloodBankMembership(userId, organizationId, membershipType = "STAFF") {
  return apiClient.post(`/api/v1/auth/users/${userId}/blood-bank-memberships`, {
    organization_id: organizationId,
    membership_type: membershipType,
  });
}

export async function revokeHospitalMembership(membershipId) {
  return apiClient.delete(`/api/v1/auth/hospital-memberships/${membershipId}`);
}

export async function revokeBloodBankMembership(membershipId) {
  return apiClient.delete(`/api/v1/auth/blood-bank-memberships/${membershipId}`);
}
