import React from "react";

export function StatusBadge({ status }) {
  const norm = String(status || "").toUpperCase();

  const config = {
    PENDING: { label: "Pending", className: "badge-pending" },
    PROCESSING: { label: "Processing", className: "badge-processing" },
    PARTIALLY_FULFILLED: { label: "Partially Fulfilled", className: "badge-partially-fulfilled" },
    FULFILLED: { label: "Fulfilled", className: "badge-fulfilled" },
    CANCELLED: { label: "Cancelled", className: "badge-cancelled" },
    PROPOSED: { label: "Proposed", className: "badge-pending" },
    ACCEPTED: { label: "Reserved / Held", className: "badge-processing" },
    REJECTED: { label: "Rejected", className: "badge-cancelled" },
    COMPLETED: { label: "Delivered", className: "badge-fulfilled" },
  };

  const item = config[norm] || { label: status || "Unknown", className: "badge-pending" };

  return <span className={`badge ${item.className}`}>{item.label}</span>;
}

export default StatusBadge;
