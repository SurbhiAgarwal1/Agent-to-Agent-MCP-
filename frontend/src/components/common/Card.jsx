import React from "react";

export function Card({ title, subtitle, action, actions, children, className = "", style = {} }) {
  const headerAction = action || actions;
  return (
    <div className={`card ${className}`} style={style}>
      {(title || subtitle || headerAction) && (
        <div
          style={{
            display: "flex",
            alignItems: "flex-start",
            justifyContent: "space-between",
            marginBottom: "1.25rem",
            paddingBottom: "0.75rem",
            borderBottom: "1px solid var(--border-color)",
          }}
        >
          <div>
            {title && (
              <h3 style={{ fontSize: "1.125rem", fontWeight: 600, color: "var(--color-text-main)" }}>
                {title}
              </h3>
            )}
            {subtitle && (
              <p style={{ fontSize: "0.875rem", color: "var(--color-text-muted)", marginTop: "0.15rem" }}>
                {subtitle}
              </p>
            )}
          </div>
          {headerAction && <div>{headerAction}</div>}
        </div>
      )}
      {children}
    </div>
  );
}

export default Card;
