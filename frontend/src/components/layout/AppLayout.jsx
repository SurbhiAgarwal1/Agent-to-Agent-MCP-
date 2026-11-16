import React, { useEffect, useState } from "react";
import { Outlet } from "react-router-dom";
import { Navbar } from "./Navbar.jsx";
import { Sidebar } from "./Sidebar.jsx";
import { useAuth } from "../../hooks/useAuth.js";
import usePolling from "../../hooks/usePolling.js";
import { listDonorNotifications, listBankNotifications, listHospitalAlerts } from "../../api/portal.js";

function useBadges(role) {
  const fetcher = async () => {
    try {
      if (role === "USER") return { requests: ((await listDonorNotifications()).items || []).filter((n) => n.response_status === "pending").length };
      if (role === "BLOOD_BANK_STAFF") return { requests: ((await listBankNotifications()).items || []).filter((n) => n.response_status === "pending").length };
      if (role === "HOSPITAL_STAFF" || role === "ADMIN") return { alerts: Number((await listHospitalAlerts()).unread || 0) };
    } catch { /* badges are cosmetic */ }
    return {};
  };
  const { data } = usePolling(fetcher, 10000, [role]);
  return data || {};
}

export function AppLayout() {
  const [sidebarOpen, setSidebarOpen] = useState(() => window.innerWidth > 900); // open on desktop, closed on phones
  const { user, sessionExpiredMessage, clearExpiredMessage } = useAuth();
  const badges = useBadges(user?.role);

  useEffect(() => {
    if (!sidebarOpen) return undefined;
    const onKey = (event) => { if (event.key === "Escape" && window.innerWidth <= 900) setSidebarOpen(false); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [sidebarOpen]);

  return (
    <div className="bc-shell">
      <Sidebar isOpen={sidebarOpen} onClose={() => window.innerWidth <= 900 && setSidebarOpen(false)} badges={badges} />
      <div className="bc-main">
        <Navbar onToggleSidebar={() => setSidebarOpen((p) => !p)} isSidebarOpen={sidebarOpen} bell={(badges.requests || 0) + (badges.alerts || 0)} />
        {sessionExpiredMessage && (
          <div className="alert alert-warning" style={{ margin: "0.5rem 1.5rem 0", display: "flex", justifyContent: "space-between" }}>
            <span>{sessionExpiredMessage || "Your session has expired. Please sign in again."}</span>
            <button type="button" onClick={clearExpiredMessage} style={{ fontWeight: 600, color: "inherit", textDecoration: "underline" }}>Dismiss</button>
          </div>
        )}
        <main className="bc-content"><Outlet /></main>
      </div>
    </div>
  );
}

export default AppLayout;
