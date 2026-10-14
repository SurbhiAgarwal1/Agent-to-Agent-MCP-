import React from "react";

export function LoadingSpinner({ message = "Loading...", size = "md" }) {
  const sizeClasses = {
    sm: "16px",
    md: "28px",
    lg: "40px",
  };
  const dimension = sizeClasses[size] || sizeClasses.md;

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        padding: "2rem",
        gap: "0.75rem",
      }}
      role="status"
      aria-live="polite"
    >
      <div
        style={{
          width: dimension,
          height: dimension,
          border: "3px solid #e2e8f0",
          borderTopColor: "var(--color-primary)",
          borderRadius: "50%",
          animation: "spin 0.8s linear infinite",
        }}
      />
      {message && (
        <span style={{ fontSize: "0.875rem", color: "var(--color-text-muted)" }}>
          {message}
        </span>
      )}
      <style>{`
        @keyframes spin {
          0% { transform: rotate(0deg); }
          100% { transform: rotate(360deg); }
        }
      `}</style>
    </div>
  );
}

export default LoadingSpinner;
