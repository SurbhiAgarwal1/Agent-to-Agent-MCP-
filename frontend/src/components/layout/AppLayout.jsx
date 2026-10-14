import React, { useEffect, useState } from "react";
import { Outlet } from "react-router-dom";
import { Navbar } from "./Navbar.jsx";
import { Sidebar } from "./Sidebar.jsx";
import { useAuth } from "../../hooks/useAuth.js";

export function AppLayout() {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const { sessionExpiredMessage, clearExpiredMessage } = useAuth();

  useEffect(() => {
    if (!sidebarOpen) return undefined;

    const handleKeyDown = (event) => {
      if (event.key === "Escape") {
        setSidebarOpen(false);
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [sidebarOpen]);

  return (
    <div style={{ display: "flex", flexDirection: "column", minHeight: "100vh" }}>
      <Navbar
        onToggleSidebar={() => setSidebarOpen((prev) => !prev)}
        isSidebarOpen={sidebarOpen}
      />

      {sessionExpiredMessage && (
        <div
          className="alert alert-warning"
          style={{ margin: "0.5rem 1.5rem 0", display: "flex", justifyContent: "space-between" }}
        >
          <span>{sessionExpiredMessage || 'Your session has expired. Please sign in again.'}</span>
          <button
            type="button"
            onClick={clearExpiredMessage}
            style={{ fontWeight: 600, color: "inherit", textDecoration: "underline" }}
          >
            Dismiss
          </button>
        </div>
      )}

      <div style={{ display: "flex", flex: 1 }}>
        <Sidebar isOpen={sidebarOpen} onClose={() => setSidebarOpen(false)} />
        <main
          style={{
            flex: 1,
            padding: "1.5rem",
            maxWidth: "1200px",
            width: "100%",
            margin: "0 auto",
          }}
        >
          <Outlet />
        </main>
      </div>
    </div>
  );
}

export default AppLayout;
