import React from "react";
import { NavLink } from "react-router-dom";
import { useAuth } from "../../hooks/useAuth.js";

const GRAFANA = import.meta.env.VITE_GRAFANA_URL || "http://localhost:3001";
const JAEGER = import.meta.env.VITE_JAEGER_URL || "http://localhost:16686";
const PROMETHEUS = import.meta.env.VITE_PROMETHEUS_URL || "http://localhost:9090";

const ROLE_LABEL = {
  HOSPITAL_STAFF: "Hospital Staff", BLOOD_BANK_STAFF: "Blood Bank Staff", USER: "Donor Portal", ADMIN: "Admin Console",
};

const MENU = {
  HOSPITAL_STAFF: [
    ["/dashboard", "▦", "Dashboard", true], ["/blood-requests/new", "🩸", "Blood Request"], ["/blood-requests", "📋", "Request Details", true],
    ["/pharmacy", "💊", "Pharmacy & Medicine"], ["/notifications", "🔔", "Notifications", false, "alerts"], ["/profile", "👤", "Profile"],
  ],
  BLOOD_BANK_STAFF: [
    ["/bank", "▦", "Dashboard", true], ["/bank/inventory", "🧊", "Inventory"], ["/bank/requests", "📋", "Blood Requests", false, "requests"],
    ["/bank/donations", "🤝", "Donations"], ["/pharmacy", "💊", "Pharmacy"], ["/profile", "👤", "Profile"],
  ],
  USER: [
    ["/donor", "▦", "Dashboard", true], ["/donor/notifications", "🔔", "Notifications", false, "requests"],
    ["/donor/history", "🕘", "Donation History"], ["/profile", "👤", "Profile"],
  ],
  ADMIN: [
    ["/admin", "▦", "Dashboard", true], ["/blood-requests", "📋", "Blood Requests", true], ["/admin/memberships", "🏥", "Hospitals & Banks"],
    ["/admin/users", "👥", "Users & Roles"], ["/admin/audit-logs", "📜", "System Logs"], ["/admin/agents", "🤖", "Agent Console"],
    ["/blood-requests/new", "🩸", "Raise Request"],
  ],
};

export function Sidebar({ isOpen, onClose, badges = {} }) {
  const { user } = useAuth();
  const role = user?.role || "USER";
  const items = MENU[role] || MENU.USER;
  const link = ([to, icon, label, end, badge]) => (
    <NavLink key={to + label} to={to} end={Boolean(end)} onClick={onClose} className={({ isActive }) => `bc-nav${isActive ? " active" : ""}`}>
      <span className="ico" aria-hidden="true">{icon}</span><span>{label}</span>
      {badge && badges[badge] > 0 && <span className="bc-badge">{badges[badge]}</span>}
    </NavLink>
  );
  const ext = (href, icon, label) => (
    <a key={label} href={href} target="_blank" rel="noreferrer" className="bc-nav"><span className="ico" aria-hidden="true">{icon}</span><span>{label} ↗</span></a>
  );
  return (
    <aside id="app-sidebar" className={`bc-side sidebar ${isOpen ? "open" : "collapsed"}`} aria-label="Primary navigation">
      <span className="bc-brand"><span aria-hidden="true">🩸</span><span>Blood<b>Connect</b></span></span>
      <div className="bc-role">{ROLE_LABEL[role] || "Member"}</div>
      {items.map(link)}
      {role === "ADMIN" && (
        <>
          <div className="bc-group">Operations Telemetry</div>
          {ext(GRAFANA, "📈", "Grafana Dashboards")}
          {ext(JAEGER, "🔍", "Jaeger Traces")}
          {ext(PROMETHEUS, "📊", "Prometheus Status")}
        </>
      )}
      {isOpen && <button type="button" className="mobile-backdrop" aria-label="Close navigation" onClick={onClose} style={{ display: "none" }} />}
    </aside>
  );
}

export default Sidebar;
