import React, { useEffect } from "react";
import { Button } from "./Button.jsx";

export function Modal({
  isOpen,
  onClose,
  title,
  children,
  footer,
  confirmLabel = "Confirm",
  confirmVariant = "primary",
  onConfirm,
  confirmLoading = false,
}) {
  useEffect(() => {
    function handleKeyDown(e) {
      if (e.key === "Escape" && isOpen && onClose) {
        onClose();
      }
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  return (
    <div className="modal-overlay" onClick={onClose} role="dialog" aria-modal="true" aria-labelledby="modal-title">
      <div className="modal-content" onClick={(e) => e.stopPropagation()}>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            marginBottom: "1rem",
            paddingBottom: "0.5rem",
            borderBottom: "1px solid var(--border-color)",
          }}
        >
          <h3 id="modal-title" style={{ fontSize: "1.125rem", fontWeight: 600, margin: 0 }}>
            {title}
          </h3>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close modal"
            style={{ fontSize: "1.25rem", color: "var(--color-text-muted)", lineHeight: 1, background: 'none', border: 'none', cursor: 'pointer' }}
          >
            &times;
          </button>
        </div>

        <div style={{ marginBottom: "1.5rem", fontSize: "0.875rem", color: "var(--color-text-main)" }}>
          {children}
        </div>

        <div style={{ display: "flex", justifyContent: "flex-end", gap: "0.75rem" }}>
          {footer ? (
            footer
          ) : (
            <>
              <Button variant="outline" onClick={onClose} disabled={confirmLoading}>
                Cancel
              </Button>
              {onConfirm && (
                <Button variant={confirmVariant} onClick={onConfirm} loading={confirmLoading}>
                  {confirmLabel}
                </Button>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}

export default Modal;
