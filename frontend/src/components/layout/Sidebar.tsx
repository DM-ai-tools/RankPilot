import { useQuery } from "@tanstack/react-query";
import {
  ClipboardList,
  FilePenLine,
  FileText,
  KeyRound,
  LayoutDashboard,
  LogOut,
  Map,
  MapPin,
  Star,
} from "lucide-react";
import type { ComponentType } from "react";
import { NavLink, useNavigate } from "react-router-dom";

import { fetchContentQueue } from "../../api/contentQueue";
import { fetchCitations } from "../../api/citations";
import { fetchMe } from "../../api/onboarding";
import { useAuthStore } from "../../stores/authStore";

/* ─── nav configuration ─────────────────────────────────────── */
const NAV_ITEMS: {
  to: string;
  label: string;
  icon: ComponentType<{ className?: string }>;
  badgeKey?: "content" | "citations";
}[] = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard },
  { to: "/map", label: "Maps Tracker", icon: Map },
  { to: "/content", label: "Content Engine", icon: FilePenLine, badgeKey: "content" },
  { to: "/gbp", label: "GBP Optimizer", icon: MapPin },
  { to: "/citations", label: "Citations", icon: ClipboardList, badgeKey: "citations" },
  { to: "/reviews", label: "Reviews", icon: Star },
  { to: "/ranks", label: "Keywords", icon: KeyRound },
  { to: "/reports", label: "Monthly Report", icon: FileText },
];

function NavBadge({ count }: { count: number }) {
  if (count <= 0) return null;
  return (
    <span className="ml-auto rounded-full px-1.5 py-0.5 text-[9px] font-bold text-white shadow-sm" style={{ backgroundColor: "#72C219" }}>
      {count}
    </span>
  );
}

export function Sidebar() {
  const navigate  = useNavigate();
  const token     = useAuthStore((s) => s.accessToken);
  const setToken  = useAuthStore((s) => s.setAccessToken);
  const setNeedsOnboarding = useAuthStore((s) => s.setNeedsOnboarding);

  const me = useQuery({
    queryKey: ["me", token],
    queryFn: fetchMe,
    enabled: Boolean(token),
  });

  const cq = useQuery({
    queryKey: ["content-queue"],
    queryFn:  fetchContentQueue,
    enabled:  Boolean(token),
  });

  const citations = useQuery({
    queryKey: ["citations", token],
    queryFn:  fetchCitations,
    enabled:  Boolean(token),
  });

  const contentBadge   = (cq.data?.items ?? []).filter((i) => i.status === "pending").length;
  const citationBadge  = (citations.data?.items ?? []).filter((i) => i.drift_flag).length;
  const badgeMap       = { content: contentBadge, citations: citationBadge };

  const businessUrl  = me.data?.business_url?.trim() || null;

  /**
   * Derive a display name from the URL only.
   * e.g. "https://argfinance.com.au" → "argfinance"
   * We intentionally ignore `business_name` from the DB because it can hold
   * stale demo values ("BugCatchers AU") that don't match the current site.
   */
  const urlDerivedName = businessUrl
    ? businessUrl
        .replace(/^https?:\/\//, "")   // strip scheme
        .replace(/^www\./, "")          // strip www
        .split(".")[0]                  // take first label
        .replace(/-/g, " ")             // hyphen → space
    : null;

  function logout() {
    setToken(null);
    setNeedsOnboarding(true);
    void navigate("/login", { replace: true });
  }

  return (
    <aside className="sticky top-0 flex h-screen w-[228px] shrink-0 flex-col border-r border-white/10 bg-[#11161F]">

      {/* ── Brand ──────────────────────────────────────────── */}
      <div className="border-b border-white/10 px-4 pb-3 pt-4">
        <div className="text-[18px] font-extrabold tracking-tight text-white">
          Rank<span style={{ color: "#72C219" }}>Pilot</span>
        </div>
        <div className="mt-0.5 text-[10px] text-white/70">Growth OS for local businesses</div>
      </div>

      {/* ── Business card ─ matches .sidebar-biz ──────────── */}
      {businessUrl ? (
        <div className="mx-[10px] mb-1 mt-[10px] rounded-lg border border-white/40 bg-white/95 px-3 py-2">
          {urlDerivedName ? (
            <div className="truncate text-[12px] font-semibold capitalize text-navy">
              {urlDerivedName}
            </div>
          ) : null}
          <div className="mt-0.5 truncate text-[10px] text-rp-tlight">
            {businessUrl.replace(/^https?:\/\//, "")}
          </div>
        </div>
      ) : me.isLoading ? (
        <div className="mx-[10px] mb-1 mt-[10px] rounded-lg border border-white/40 bg-white/95 px-3 py-2">
          <div className="h-3 w-24 animate-pulse rounded bg-[#DDE6D1]" />
        </div>
      ) : null}

      {/* ── Nav section label ─────────────────────────────── */}
      <div className="mt-2 px-3 pb-1 text-[9px] font-bold uppercase tracking-[1.1px] text-white/70">
        SEO Features
      </div>

      {/* ── Nav items ─────────────────────────────────────── */}
      <nav className="flex flex-col gap-1 px-[6px]">
        {NAV_ITEMS.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === "/"}
            className={({ isActive }) =>
              [
                "group flex items-center gap-2.5 rounded-[9px] px-3 py-2 text-[12px] font-medium transition-colors",
                isActive
                  ? "text-white shadow-sm"
                  : "text-white/75 hover:bg-white/10 hover:text-white",
              ].join(" ")
            }
            style={({ isActive }: { isActive: boolean }) =>
              isActive
                ? { backgroundColor: "rgba(114,194,25,0.20)", outline: "1px solid rgba(114,194,25,0.50)", outlineOffset: "-1px" }
                : {}
            }
          >
            {({ isActive }: { isActive: boolean }) => (
              <>
                <span
                  className="flex h-[22px] w-[22px] shrink-0 items-center justify-center rounded-md transition-colors"
                  style={isActive ? { backgroundColor: "#72C219", color: "#fff" } : { backgroundColor: "rgba(255,255,255,0.10)", color: "rgba(255,255,255,0.75)" }}
                >
                  <item.icon className="h-3.5 w-3.5" />
                </span>
                <span className="flex-1">{item.label}</span>
                {item.badgeKey ? <NavBadge count={badgeMap[item.badgeKey]} /> : null}
              </>
            )}
          </NavLink>
        ))}
      </nav>

      {/* ── Bottom logout ──────────────────────────────────── */}
      <div className="mt-auto border-t border-white/10 px-4 py-3">
        <button
          type="button"
          onClick={logout}
          className="inline-flex w-full items-center gap-2 rounded-lg px-3 py-1.5 text-left text-[11px] font-semibold text-white/85 transition-colors hover:bg-white/10 hover:text-white"
        >
          <LogOut className="h-3.5 w-3.5" />
          Sign out
        </button>
      </div>
    </aside>
  );
}
