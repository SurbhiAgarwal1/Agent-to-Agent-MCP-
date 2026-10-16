import React from "react";

export function UrgencyBadge({ urgency }) {
  const norm = String(urgency || "MEDIUM").toUpperCase();

  const config = {
    LOW: { label: "Low", className: "badge-urgency-low" },
    MEDIUM: { label: "Medium", className: "badge-urgency-medium" },
    HIGH: { label: "High", className: "badge-urgency-high" },
    CRITICAL: { label: "Critical", className: "badge-urgency-critical" },
  };

  const item = config[norm] || config.MEDIUM;

  return <span className={`badge ${item.className}`}>{item.label}</span>;
}

export default UrgencyBadge;
