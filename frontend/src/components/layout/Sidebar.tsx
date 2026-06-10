import { useQuery } from "@tanstack/react-query";
import {
  Building2,
  ClipboardList,
  FilePenLine,
  FileText,
  KeyRound,
  LayoutDashboard,
  LogOut,
  Map,
  MapPin,
  PanelLeft,
  PanelLeftClose,
  ShieldCheck,
  Star,
} from "lucide-react";
import type { ComponentType } from "react";
import { NavLink, useNavigate } from "react-router-dom";

import { fetchCitations } from "../../api/citations";
import { fetchMe } from "../../api/onboarding";
import { useAuthStore } from "../../stores/authStore";

const NAV_ITEMS: {
  to: string;
  label: string;
  icon: ComponentType<{ className?: string }>;
  badgeKey?: "citations";
}[] = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard },
  { to: "/map", label: "Maps Tracker", icon: Map },
  { to: "/content", label: "Content Engine", icon: FilePenLine },
  { to: "/gbp", label: "GBP Optimizer", icon: MapPin },
  { to: "/citations", label: "Citations", icon: ClipboardList, badgeKey: "citations" },
  { to: "/reviews", label: "Reviews", icon: Star },
  { to: "/ranks", label: "Keywords", icon: KeyRound },
  { to: "/reports", label: "Monthly Report", icon: FileText },
  { to: "/onboarding", label: "Business Setup", icon: Building2 },
];

function NavBadge({ count, collapsed }: { count: number; collapsed?: boolean }) {
  if (count <= 0) return null;
  if (collapsed) {
    return (
      <span className="absolute -right-0.5 -top-0.5 h-2 w-2 rounded-full bg-brand-500 ring-2 ring-[var(--ink-900)]" />
    );
  }
  return (
    <span className="ml-auto rounded-full bg-brand-500 px-1.5 py-0.5 text-[10px] font-bold tabular-nums text-white">
      {count}
    </span>
  );
}

type SidebarProps = {
  collapsed: boolean;
  onToggleCollapsed: () => void;
};

export function Sidebar({ collapsed, onToggleCollapsed }: SidebarProps) {
  const navigate = useNavigate();
  const token = useAuthStore((s) => s.accessToken);
  const setToken = useAuthStore((s) => s.setAccessToken);
  const me = useQuery({
    queryKey: ["me", token],
    queryFn: fetchMe,
    enabled: Boolean(token),
  });

  const citations = useQuery({
    queryKey: ["citations", token],
    queryFn: fetchCitations,
    enabled: Boolean(token),
  });

  const citationBadge = (citations.data?.items ?? []).filter((i) => i.drift_flag).length;
  const badgeMap = { citations: citationBadge };

  const businessUrl = me.data?.business_url?.trim() || null;

  const urlDerivedName = businessUrl
    ? businessUrl
        .replace(/^https?:\/\//, "")
        .replace(/^www\./, "")
        .split(".")[0]
        .replace(/-/g, " ")
    : null;

  function logout() {
    setToken(null);
    void navigate("/login", { replace: true });
  }

  return (
    <aside
      className={`sticky top-0 flex h-screen shrink-0 flex-col text-neutral-300 transition-[width] duration-200 ${
        collapsed ? "w-[4.5rem]" : "w-64"
      }`}
      style={{ backgroundColor: "var(--ink-900)" }}
    >
      {/* Brand + collapse toggle */}
      <div className={`border-b border-white/5 pb-4 pt-5 ${collapsed ? "px-2" : "px-4"}`}>
        <div className={`flex items-center ${collapsed ? "flex-col gap-2" : "gap-3"}`}>
          <div
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg shadow-sm"
            style={{ background: "linear-gradient(135deg, #7fbb43 0%, #4d8a20 100%)" }}
          >
            <ShieldCheck className="h-5 w-5 text-white" strokeWidth={2.25} />
          </div>
          {!collapsed ? (
            <div className="min-w-0 flex-1">
              <div className="text-[17px] font-extrabold tracking-tight text-white">
                Rank<span className="text-brand-400">Pilot</span>
              </div>
              <div className="text-[11px] text-neutral-500">Growth OS for local businesses</div>
            </div>
          ) : null}
          <button
            type="button"
            onClick={onToggleCollapsed}
            title={collapsed ? "Expand sidebar" : "Minimise sidebar"}
            aria-label={collapsed ? "Expand sidebar" : "Minimise sidebar"}
            className={`flex shrink-0 items-center justify-center rounded-md text-neutral-400 transition-colors hover:bg-ink-800 hover:text-white ${
              collapsed ? "h-8 w-8" : "h-8 w-8"
            }`}
          >
            {collapsed ? <PanelLeft className="h-4 w-4" /> : <PanelLeftClose className="h-4 w-4" />}
          </button>
        </div>
      </div>

      {/* Active business */}
      {!collapsed && businessUrl ? (
        <div
          className="mx-3 mt-3 rounded-lg border border-white/5 px-3 py-2.5"
          style={{ backgroundColor: "#16271e" }}
        >
          {urlDerivedName ? (
            <div className="truncate text-[13px] font-semibold capitalize text-white">{urlDerivedName}</div>
          ) : null}
          <div className="mt-0.5 truncate text-[11px] text-neutral-400">
            {businessUrl.replace(/^https?:\/\//, "")}
          </div>
        </div>
      ) : !collapsed && me.isLoading ? (
        <div className="mx-3 mt-3 rounded-lg border border-white/5 bg-ink-800 px-3 py-2.5">
          <div className="h-3 w-24 animate-pulse rounded bg-white/10" />
        </div>
      ) : null}

      {!collapsed ? (
        <div className="mt-4 px-4 pb-1 text-[11px] font-semibold uppercase tracking-[0.08em] text-neutral-500">
          SEO Features
        </div>
      ) : (
        <div className="mt-3" />
      )}

      <nav className={`flex flex-col gap-0.5 ${collapsed ? "px-1.5" : "px-2"}`}>
        {NAV_ITEMS.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === "/"}
            title={collapsed ? item.label : undefined}
            className={({ isActive }) =>
              [
                "relative flex items-center rounded-md text-sm font-medium transition-colors",
                collapsed ? "justify-center px-2 py-2.5" : "gap-3 px-3 py-2.5",
                isActive
                  ? "bg-brand-600 text-white shadow-sm"
                  : "text-neutral-400 hover:bg-ink-800 hover:text-white",
              ].join(" ")
            }
          >
            <item.icon className="h-4 w-4 shrink-0" />
            {!collapsed ? <span className="flex-1">{item.label}</span> : null}
            {item.badgeKey ? (
              <NavBadge count={badgeMap[item.badgeKey]} collapsed={collapsed} />
            ) : null}
          </NavLink>
        ))}
      </nav>

      <div className={`mt-auto border-t border-white/5 ${collapsed ? "px-2 py-3" : "px-3 py-3"}`}>
        <div
          className={`mb-3 flex flex-col items-center ${
            collapsed ? "gap-1 px-0 py-1" : "gap-1.5 rounded-lg border border-white/5 bg-ink-800/60 px-3 py-3"
          }`}
        >
          <img
            src="/Traffic-Radius-Logo.webp"
            alt="Traffic Radius"
            className={`object-contain opacity-95 ${
              collapsed ? "h-7 w-7 rounded" : "h-auto w-full max-w-[140px]"
            }`}
          />
          {!collapsed ? (
            <p className="text-center text-[10px] font-medium uppercase tracking-[0.06em] text-neutral-500">
              Powered by Traffic Radius
            </p>
          ) : null}
        </div>

        <button
          type="button"
          onClick={logout}
          title={collapsed ? "Sign out" : undefined}
          className={`inline-flex w-full items-center rounded-md text-left text-sm font-medium text-neutral-400 transition-colors hover:bg-ink-800 hover:text-white ${
            collapsed ? "justify-center px-2 py-2.5" : "gap-2.5 px-3 py-2"
          }`}
        >
          <LogOut className="h-4 w-4 shrink-0" />
          {!collapsed ? "Sign out" : null}
        </button>
      </div>
    </aside>
  );
}
