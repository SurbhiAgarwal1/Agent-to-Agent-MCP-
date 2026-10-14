import React from "react";

export function BloodGroupBadge({ bloodGroup, group }) {
  const value = bloodGroup || group || "—";
  return (
    <span className="badge badge-blood">
      {value}
    </span>
  );
}

export default BloodGroupBadge;
