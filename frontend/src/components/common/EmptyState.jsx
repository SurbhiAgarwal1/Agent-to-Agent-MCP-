import React from "react";

export function EmptyState({ icon = "📋", title = "No records found", message, action }) {
  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        padding: "3rem 1.5rem",
        textAlign: "center",
        backgroundColor: "var(--color-bg)",
        borderRadius: "8px",
        border: "1px dashed var(--border-color)",
      }}
    >
      <div style={{ fontSize: "2rem", marginBottom: "0.75rem" }}>{icon}</div>
      <h4 style={{ fontSize: "1rem", fontWeight: 600, color: "var(--color-text-main)", marginBottom: "0.25rem" }}>
        {title}
      </h4>
      {message && (
        <p style={{ fontSize: "0.875rem", color: "var(--color-text-muted)", maxWidth: "380px", marginBottom: action ? "1rem" : 0 }}>
          {message}
        </p>
      )}
      {action && <div>{action}</div>}
    </div>
  );
}

export default EmptyState;
