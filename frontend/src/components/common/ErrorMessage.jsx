import React from "react";
import { Button } from "./Button.jsx";

export function ErrorMessage({ message, onRetry, className = "" }) {
  if (!message) return null;

  return (
    <div className={`alert alert-danger ${className}`} role="alert">
      <div style={{ flex: 1 }}>
        <p style={{ fontWeight: 600, marginBottom: "0.25rem" }}>Notice</p>
        <p>{message}</p>
      </div>
      {onRetry && (
        <Button variant="secondary" size="sm" onClick={onRetry}>
          Try Again
        </Button>
      )}
    </div>
  );
}
