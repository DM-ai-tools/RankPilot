import { useEffect, useState } from "react";
import { Outlet } from "react-router-dom";

import { Sidebar } from "./Sidebar";

const SIDEBAR_COLLAPSED_KEY = "rankpilot_sidebar_collapsed";

export function AppShell() {
  const [collapsed, setCollapsed] = useState(() => {
    try {
      return localStorage.getItem(SIDEBAR_COLLAPSED_KEY) === "1";
    } catch {
      return false;
    }
  });

  useEffect(() => {
    try {
      localStorage.setItem(SIDEBAR_COLLAPSED_KEY, collapsed ? "1" : "0");
    } catch {
      /* ignore */
    }
  }, [collapsed]);

  return (
    <div className="flex min-h-screen" style={{ backgroundColor: "var(--page)" }}>
      <Sidebar collapsed={collapsed} onToggleCollapsed={() => setCollapsed((v) => !v)} />
      <div className="flex min-h-0 min-w-0 flex-1 flex-col p-4 lg:p-6">
        <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden rounded-t-2xl bg-white shadow-lg ring-1 ring-neutral-200">
          <Outlet />
        </div>
      </div>
    </div>
  );
}
