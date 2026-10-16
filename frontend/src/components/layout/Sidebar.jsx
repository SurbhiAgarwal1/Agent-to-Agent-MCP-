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

  const telemetry = [
    ["Grafana Dashboards", "📈", import.meta.env.VITE_GRAFANA_URL],
    ["Jaeger Traces", "🔍", import.meta.env.VITE_JAEGER_URL],
    ["Prometheus Status", "📊", import.meta.env.VITE_PROMETHEUS_URL],
  ];

  return (
    <>
      {isOpen && (
        <button
          type="button"
          className="mobile-backdrop"
          aria-label="Close navigation"
          onClick={onClose}
        />
      )}

      <aside
        id="app-sidebar"
        className={`sidebar ${isOpen ? "open" : "collapsed"}`}
        aria-label="Primary navigation"
        style={{
          width: "240px",
          backgroundColor: "var(--color-surface)",
          borderRight: "1px solid var(--color-border)",
          padding: "1.25rem 0.85rem",
          display: "flex",
          flexDirection: "column",
          justifyContent: "space-between",
          flexShrink: 0,
          overflow: "hidden",
          transition: "width 200ms ease-in-out, padding 200ms ease-in-out",
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
              <span>📊</span><span>Dashboard</span>
            </NavLink>

            {isHospitalStaff && (
              <>
                <NavLink to="/blood-requests" style={navLinkStyle} onClick={onClose} end>
                  <span>📋</span><span>Blood Requests</span>
                </NavLink>
                <NavLink to="/blood-requests/new" style={navLinkStyle} onClick={onClose}>
                  <span>🩸</span><span>Request Blood</span>
                </NavLink>
                <NavLink to="/notifications" style={navLinkStyle} onClick={onClose}>
                  <span>🔔</span><span>Notifications</span>
                </NavLink>
              </>
            )}

            <NavLink to="/profile" style={navLinkStyle} onClick={onClose}>
              <span>👤</span><span>Profile</span>
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
                <span>⚙️</span><span>Admin Overview</span>
              </NavLink>
              <NavLink to="/admin/users" style={navLinkStyle} onClick={onClose}>
                <span>👥</span><span>User Management</span>
              </NavLink>
              <NavLink to="/admin/memberships" style={navLinkStyle} onClick={onClose}>
                <span>🏥</span><span>Memberships</span>
              </NavLink>
              <NavLink to="/admin/audit-logs" style={navLinkStyle} onClick={onClose}>
                <span>📜</span><span>Audit Logs</span>
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
                Operations Telemetry
              </p>

              {telemetry.map(([label, icon, href]) =>
                href ? (
                  <a
                    key={label}
                    href={href}
                    target="_blank"
                    rel="noreferrer"
                    style={{ ...navLinkStyle({ isActive: false }), fontSize: "0.8rem" }}
                  >
                    <span>{icon}</span><span>{label} ↗</span>
                  </a>
                ) : (
                  <div
                    key={label}
                    style={{
                      ...navLinkStyle({ isActive: false }),
                      fontSize: "0.8rem",
                      cursor: "default",
                    }}
                    aria-disabled="true"
                  >
                    <span>{icon}</span><span>{label} — Not configured</span>
                  </div>
                )
              )}
            </div>
          )}
        </div>

        {isAdmin && (
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
              Agent Network
            </p>
            <p>A2A · MCP · System Operations</p>
          </div>
        )}
      </aside>

      <style>{`
        .mobile-backdrop {
          display: none;
        }

        @media (max-width: 768px) {
          .mobile-backdrop {
            display: block;
            position: fixed;
            inset: 57px 0 0 0;
            width: 100%;
            height: calc(100vh - 57px);
            border: 0;
            padding: 0;
            margin: 0;
            background: rgba(15, 23, 42, 0.4);
            z-index: 40;
            cursor: pointer;
          }

          .sidebar {
            position: fixed !important;
            top: 57px;
            bottom: 0;
            left: 0;
            width: 240px !important;
            padding: 1.25rem 0.85rem !important;
            transform: translateX(-100%);
            transition: transform 200ms ease-in-out;
            z-index: 45;
            overflow-y: auto !important;
            overflow-x: hidden;
          }

          .sidebar.open {
            transform: translateX(0);
          }

          .sidebar.collapsed {
            transform: translateX(-100%);
          }
        }

        @media (min-width: 769px) {
          .sidebar.collapsed {
            width: 0 !important;
            padding-left: 0 !important;
            padding-right: 0 !important;
            border-right-width: 0 !important;
          }
        }
      `}</style>
    </>
  );
}

export default Sidebar;
