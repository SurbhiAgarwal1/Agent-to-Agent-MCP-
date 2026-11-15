export function homeForRole(role) {
  const r = (role || "").toUpperCase();
  if (r === "USER") return "/donor";
  if (r === "BLOOD_BANK_STAFF") return "/bank";
  return "/dashboard";
}
