import { Outlet } from "react-router-dom";

import { Sidebar } from "./Sidebar";

const GLOW =
  "radial-gradient(ellipse 80% 45% at 15% 0%, rgba(114,194,25,0.13) 0%, transparent 70%), " +
  "radial-gradient(ellipse 50% 40% at 88% 95%, rgba(114,194,25,0.07) 0%, transparent 70%)";

export function AppShell() {
  return (
    <div className="flex min-h-screen" style={{ backgroundColor: "#EDF4DD" }}>
      <Sidebar />
      <div className="flex min-h-0 min-w-0 flex-1 flex-col p-4">
        <div
          className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden rounded-card border border-rp-border shadow-app"
          style={{ backgroundImage: GLOW, backgroundColor: "#ffffff" }}
        >
          <Outlet />
        </div>
      </div>
    </div>
  );
}
