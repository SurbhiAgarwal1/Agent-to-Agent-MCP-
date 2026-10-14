import React from "react";
import { NavLink } from "react-router-dom";
import { useAuth } from "../../hooks/useAuth.js";

export function Sidebar({ isOpen, onClose }) {
  const { user } = useAuth();
  const role = user?.role || "USER";

  const isHospitalStaff = role === "HOSPITAL_STAFF" || role === "ADMIN";
  const isAdmin = role === "ADMIN";

  const navLinkStyle = ({ isActive }) => ({
    display: "flex",
    alignItems: "center",
    gap: "0.75rem",
    padding: "0.6rem 0.85rem",
    borderRadius: "var(--radius-md)",
    fontSize: "0.875rem",
    fontWeight: isActive ? 600 : 500,
    color: isActive ? "var(--color-primary)" : "var(--color-text-secondary)",
    backgroundColor: isActive ? "var(--color-primary-subtle)" : "transparent",
    textDecoration: "none",
    transition: "background-color 150ms ease",
    marginBottom: "0.25rem",
  });

  return (
    <>
      {/* Mobile Backdrop */}
      {isOpen && (
        <div
          onClick={onClose}
          style={{
            position: "fixed",
            inset: 0,
            backgroundColor: "rgba(15, 23, 42, 0.4)",
            zIndex: 40,
            display: "none",
          }}
          className="mobile-backdrop"
        />
      )}

      <aside
        className={`sidebar ${isOpen ? "open" : ""}`}
        style={{
          width: "240px",
          backgroundColor: "var(--color-surface)",
          borderRight: "1px solid var(--color-border)",
          padding: "1.25rem 0.85rem",
          display: "flex",
          flexDirection: "column",
          justifyContent: "space-between",
          flexShrink: 0,
        }}
      >
        <div>
          <div style={{ marginBottom: "1.5rem" }}>
            <p
              style={{
                fontSize: "0.75rem",
                textTransform: "uppercase",
                letterSpacing: "0.06em",
                color: "var(--color-text-muted)",
                paddingLeft: "0.85rem",
                marginBottom: "0.5rem",
                fontWeight: 600,
              }}
            >
              Operations
            </p>
            <NavLink to="/dashboard" style={navLinkStyle} onClick={onClose} end>
              <span>📊</span>
              <span>Dashboard</span>
            </NavLink>

            {isHospitalStaff && (
              <>
                <NavLink to="/blood-requests" style={navLinkStyle} onClick={onClose} end>
                  <span>📋</span>
                  <span>Blood Requests</span>
                </NavLink>
                <NavLink to="/blood-requests/new" style={navLinkStyle} onClick={onClose}>
                  <span>🚨</span>
                  <span>Dispatch Request</span>
                </NavLink>
                <NavLink to="/notifications" style={navLinkStyle} onClick={onClose}>
                  <span>🔔</span>
                  <span>Notifications</span>
                </NavLink>
              </>
            )}

            <NavLink to="/profile" style={navLinkStyle} onClick={onClose}>
              <span>👤</span>
              <span>Profile</span>
            </NavLink>
          </div>

          {isAdmin && (
            <div style={{ marginBottom: "1.5rem" }}>
              <p
                style={{
                  fontSize: "0.75rem",
                  textTransform: "uppercase",
                  letterSpacing: "0.06em",
                  color: "var(--color-text-muted)",
                  paddingLeft: "0.85rem",
                  marginBottom: "0.5rem",
                  fontWeight: 600,
                }}
              >
                Administration
              </p>
              <NavLink to="/admin" style={navLinkStyle} onClick={onClose} end>
                <span>⚙️</span>
                <span>Admin Overview</span>
              </NavLink>
              <NavLink to="/admin/users" style={navLinkStyle} onClick={onClose}>
                <span>👥</span>
                <span>User Management</span>
              </NavLink>
              <NavLink to="/admin/memberships" style={navLinkStyle} onClick={onClose}>
                <span>🏥</span>
                <span>Memberships</span>
              </NavLink>
              <NavLink to="/admin/audit-logs" style={navLinkStyle} onClick={onClose}>
                <span>📜</span>
                <span>Audit Logs</span>
              </NavLink>

              <p
                style={{
                  fontSize: "0.7rem",
                  textTransform: "uppercase",
                  letterSpacing: "0.06em",
                  color: "var(--color-text-muted)",
                  paddingLeft: "0.85rem",
                  marginTop: "1.25rem",
                  marginBottom: "0.5rem",
                  fontWeight: 600,
                }}
              >
                Operations Telemetry (Loopback)
              </p>
              <a
                href="http://localhost:3001"
                target="_blank"
                rel="noreferrer"
                style={{ ...navLinkStyle({ isActive: false }), fontSize: "0.8rem" }}
              >
                <span>📈</span>
                <span>Grafana Dashboards ↗</span>
              </a>
              <a
                href="http://localhost:16686"
                target="_blank"
                rel="noreferrer"
                style={{ ...navLinkStyle({ isActive: false }), fontSize: "0.8rem" }}
              >
                <span>🔍</span>
                <span>Jaeger Traces ↗</span>
              </a>
              <a
                href="http://localhost:9090"
                target="_blank"
                rel="noreferrer"
                style={{ ...navLinkStyle({ isActive: false }), fontSize: "0.8rem" }}
              >
                <span>📊</span>
                <span>Prometheus Status ↗</span>
              </a>
            </div>
          )}
        </div>

        <div
          style={{
            padding: "0.75rem",
            backgroundColor: "var(--color-bg)",
            borderRadius: "var(--radius-md)",
            border: "1px solid var(--color-border)",
            fontSize: "0.75rem",
            color: "var(--color-text-muted)",
          }}
        >
          <p style={{ fontWeight: 600, color: "var(--color-text-secondary)" }}>
            A2A Coordination Engine
          </p>
          <p>Multi-Agent Protocol v1.0</p>
        </div>
      </aside>

      <style>{`
        @media (max-width: 768px) {
          .mobile-backdrop {
            display: block !important;
          }
          .sidebar {
            position: fixed !important;
            top: 57px;
            bottom: 0;
            left: 0;
            transform: translateX(-100%);
            transition: transform 200ms ease-in-out;
            z-index: 45;
          }
          .sidebar.open {
            transform: translateX(0);
          }
        }
      `}</style>
    </>
  );
}

export default Sidebar;
