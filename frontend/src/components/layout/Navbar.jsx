import React from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../../hooks/useAuth.js";
import { useHospital } from "../../context/HospitalContext.jsx";
import { Button } from "../common/Button.jsx";

export function Navbar({ onToggleSidebar, isSidebarOpen = false }) {
  const { user, logout } = useAuth();
  const { hospitals, selectedHospitalId, selectHospital } = useHospital();
  const isHospitalStaff = user?.role === "HOSPITAL_STAFF" || user?.role === "ADMIN";

  return (
    <header
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        padding: "0.75rem 1.5rem",
        backgroundColor: "var(--color-surface)",
        borderBottom: "1px solid var(--color-border)",
        position: "sticky",
        top: 0,
        zIndex: 50,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: "1rem" }}>
        {onToggleSidebar && (
          <button
            type="button"
            onClick={onToggleSidebar}
            aria-label={isSidebarOpen ? "Close navigation" : "Open navigation"}
            aria-expanded={isSidebarOpen}
            aria-controls="app-sidebar"
            style={{
              padding: "0.4rem",
              borderRadius: "var(--radius-sm)",
              color: "var(--color-text-secondary)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            ☰
          </button>
        )}
        <Link
          to="/dashboard"
          style={{
            display: "flex",
            alignItems: "center",
            gap: "0.5rem",
            textDecoration: "none",
            color: "var(--color-text-primary)",
            fontWeight: 700,
            fontSize: "1.125rem",
          }}
        >
          <span style={{ fontSize: "1.25rem" }}>🩸</span>
          <span>Blood Coordination Platform</span>
        </Link>
      </div>

      <div style={{ display: "flex", alignItems: "center", gap: "1rem" }}>
        {/* Hospital Switcher for Hospital Staff & Admin */}
        {isHospitalStaff && hospitals.length > 0 && (
          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
            <span style={{ fontSize: "0.825rem", fontWeight: 600, color: "var(--color-text-secondary)" }}>
              🏥 Hospital:
            </span>
            <select
              value={selectedHospitalId}
              onChange={(e) => selectHospital(e.target.value)}
              style={{
                fontSize: "0.825rem",
                fontWeight: 600,
                padding: "0.35rem 0.65rem",
                borderRadius: "6px",
                border: "1px solid var(--color-border)",
                backgroundColor: "var(--color-bg)",
                color: "var(--color-text-primary)",
                maxWidth: "240px",
                cursor: "pointer",
                outline: "none",
              }}
              title="Select active hospital to manage blood requests"
            >
              {hospitals.map((h) => (
                <option key={h.hospital_id} value={h.hospital_id}>
                  {h.name}
                </option>
              ))}
            </select>
          </div>
        )}

        {user && (
          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", fontSize: "0.875rem" }}>
            <span style={{ color: "var(--color-text-secondary)", maxWidth: "160px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
              {user.email}
            </span>
            <span className="role-chip">{user.role?.replace("_", " ")}</span>
          </div>
        )}
        <Button variant="secondary" size="sm" onClick={logout}>
          Log out
        </Button>
      </div>
    </header>
  );
}

export default Navbar;
