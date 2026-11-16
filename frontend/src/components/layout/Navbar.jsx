import React from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../../hooks/useAuth.js";

const BELL_TARGET = { HOSPITAL_STAFF: "/notifications", ADMIN: "/notifications", USER: "/donor/notifications", BLOOD_BANK_STAFF: "/bank/requests" };

export function Navbar({ onToggleSidebar, isSidebarOpen = false, bell = 0 }) {
  const { user, logout } = useAuth();
  const initial = (user?.email || "?").charAt(0).toUpperCase();
  return (
    <header className="bc-top">
      {onToggleSidebar && (
        <button type="button" onClick={onToggleSidebar} aria-label={isSidebarOpen ? "Close navigation" : "Open navigation"}
          aria-expanded={isSidebarOpen} aria-controls="app-sidebar" style={{ background: "none", border: 0, fontSize: "1.2rem", cursor: "pointer" }}>☰</button>
      )}
      <span className="spacer" />
      <Link to={BELL_TARGET[user?.role] || "/dashboard"} className="bc-bell" aria-label="Notifications">
        🔔{bell > 0 && <span className="dot">{bell}</span>}
      </Link>
      {user && (
        <div className="bc-user">
          <span className="bc-avatar" aria-hidden="true">{initial}</span>
          <span>{user.email}<small>{user.role?.replaceAll("_", " ")}</small></span>
        </div>
      )}
      <button type="button" className="bc-btn ghost sm" onClick={logout}>Log out</button>
    </header>
  );
}

export default Navbar;
