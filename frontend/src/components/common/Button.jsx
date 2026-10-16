import React from "react";

export function Button({
  children,
  variant = "primary", // primary | secondary | danger | outline
  size = "md", // sm | md | lg
  type = "button",
  disabled = false,
  loading = false,
  onClick,
  className = "",
  style,
  ...props
}) {
  const variantClass = `btn-${variant}`;
  const sizeClass = size === "sm" ? "btn-sm" : size === "lg" ? "btn-lg" : "";

  return (
    <button
      type={type}
      disabled={disabled || loading}
      onClick={onClick}
      className={`btn ${variantClass} ${sizeClass} ${className}`}
      style={style}
      {...props}
    >
      {loading && (
        <span
          style={{
            display: "inline-block",
            width: "12px",
            height: "12px",
            border: "2px solid rgba(255,255,255,0.4)",
            borderTopColor: "currentColor",
            borderRadius: "50%",
            animation: "spin 0.7s linear infinite",
            marginRight: "6px",
          }}
        />
      )}
      {children}
    </button>
  );
}

export default Button;
