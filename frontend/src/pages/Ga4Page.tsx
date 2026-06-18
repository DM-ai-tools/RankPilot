import { useQuery } from "@tanstack/react-query";
import {
  ArrowDown,
  ArrowUp,
  BarChart2,
  Globe,
  MapPin,
  Minus,
  RefreshCw,
  Search,
  TrendingUp,
  Users,
} from "lucide-react";
import { useState } from "react";

import {
  GA4_RANGE_LABELS,
  type Ga4RangeKey,
  type Ga4Row,
  fetchGa4Channels,
  fetchGa4Geo,
  fetchGa4Organic,
  fetchGa4Overview,
  fetchGa4Pages,
} from "../api/ga4";
import { formatApiError } from "../api/client";
import { TopBar } from "../components/layout/TopBar";
import { Card } from "../components/ui/Card";
import { useAuthStore } from "../stores/authStore";

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmt(n: number | undefined | null, decimals = 0): string {
  if (n == null || isNaN(n)) return "—";
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return n.toFixed(decimals);
}

function fmtDur(seconds: number | undefined | null): string {
  if (seconds == null || isNaN(seconds)) return "—";
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  return `${m}m ${s}s`;
}

function fmtPct(n: number | undefined | null): string {
  if (n == null || isNaN(n)) return "—";
  return `${(n * 100).toFixed(1)}%`;
}

function pctChange(curr: number, prev: number): number | null {
  if (!prev) return null;
  return ((curr - prev) / prev) * 100;
}

function Delta({ curr, prev }: { curr: number; prev?: number }) {
  if (prev == null) return null;
  const diff = pctChange(curr, prev);
  if (diff == null) return <span className="text-rp-tlight text-xs">—</span>;
  const up = diff >= 0;
  return (
    <span className={`flex items-center gap-0.5 text-xs font-semibold ${up ? "text-emerald-600" : "text-red-500"}`}>
      {up ? <ArrowUp className="h-3 w-3" /> : <ArrowDown className="h-3 w-3" />}
      {Math.abs(diff).toFixed(1)}%
    </span>
  );
}

// ── Channel colours ───────────────────────────────────────────────────────────

const CHANNEL_COLORS: Record<string, string> = {
  "Organic Search": "#22c55e",
  "Paid Social": "#6366f1",
  "Direct": "#f59e0b",
  "Referral": "#06b6d4",
  "Organic Social": "#a78bfa",
  "Email": "#f472b6",
  "Unassigned": "#94a3b8",
  "AI": "#ff6b00",
};

function channelColor(name: string): string {
  return CHANNEL_COLORS[name] ?? "#94a3b8";
}

// ── Mini bar chart (inline SVG) ───────────────────────────────────────────────

function MiniBar({
  values,
  color = "#6366f1",
  height = 36,
}: {
  values: number[];
  color?: string;
  height?: number;
}) {
  if (!values.length) return null;
  const max = Math.max(...values, 1);
  const w = 100 / values.length;
  return (
    <svg viewBox={`0 0 100 ${height}`} preserveAspectRatio="none" className="w-full" style={{ height }}>
      {values.map((v, i) => {
        const h = (v / max) * height;
        return (
          <rect
            key={i}
            x={i * w + 0.5}
            y={height - h}
            width={w - 1}
            height={h}
            fill={color}
            opacity={0.75}
            rx="1"
          />
        );
      })}
    </svg>
  );
}

// ── Stat card ─────────────────────────────────────────────────────────────────

function StatCard({
  label,
  value,
  prev,
  sub,
  icon: Icon,
  color = "#6366f1",
}: {
  label: string;
  value: string;
  prev?: string;
  sub?: string;
  icon: React.ElementType;
  color?: string;
}) {
  return (
    <div className="rounded-xl border border-rp-border bg-white p-4 shadow-sm">
      <div className="mb-2 flex items-center justify-between">
        <span className="text-xs font-semibold uppercase tracking-wide text-rp-tlight">{label}</span>
        <span className="rounded-full p-1.5" style={{ background: color + "18" }}>
          <Icon className="h-4 w-4" style={{ color }} />
        </span>
      </div>
      <div className="text-2xl font-bold text-navy">{value}</div>
      {prev && (
        <div className="mt-1 flex items-center gap-2 text-xs text-rp-tlight">
          <span>prev {prev}</span>
        </div>
      )}
      {sub && <div className="mt-0.5 text-[11px] text-rp-tlight">{sub}</div>}
    </div>
  );
}

// ── Range + compare toolbar ───────────────────────────────────────────────────

function Toolbar({
  range,
  compare,
  onRange,
  onCompare,
}: {
  range: Ga4RangeKey;
  compare: boolean;
  onRange: (r: Ga4RangeKey) => void;
  onCompare: (c: boolean) => void;
}) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <div className="flex overflow-hidden rounded-lg border border-rp-border">
        {(Object.keys(GA4_RANGE_LABELS) as Ga4RangeKey[]).map((k) => (
          <button
            key={k}
            type="button"
            onClick={() => onRange(k)}
            className={`px-3 py-1.5 text-xs font-semibold transition-colors ${
              range === k
                ? "bg-navy text-white"
                : "bg-white text-rp-tmid hover:bg-[#F0F4FF]"
            }`}
          >
            {GA4_RANGE_LABELS[k].replace("Last ", "")}
          </button>
        ))}
      </div>
      <button
        type="button"
        onClick={() => onCompare(!compare)}
        className={`rounded-lg border px-3 py-1.5 text-xs font-semibold transition-colors ${
          compare
            ? "border-[#6366f1] bg-[#EEF2FF] text-[#6366f1]"
            : "border-rp-border bg-white text-rp-tmid hover:bg-[#F0F4FF]"
        }`}
      >
        {compare ? "Comparison: On" : "Compare to previous"}
      </button>
    </div>
  );
}

// ── Not connected banner ──────────────────────────────────────────────────────

function NotConnected({ error }: { error: unknown }) {
  const msg = formatApiError(error);
  const needsEnable = msg.includes("not enabled") || msg.includes("not been used") || msg.includes("Enable it");
  const needsReconnect = msg.includes("scope") || msg.includes("reconnect") || msg.includes("disconnect");
  const needsSetup = msg.includes("not connected") || msg.includes("No GA4 property") || msg.includes("property selected");

  return (
    <div className="rounded-xl border border-amber-200 bg-amber-50 p-5">
      <p className="font-semibold text-amber-800">
        {needsEnable ? "GA4 Data API not enabled in Google Cloud" :
         needsReconnect ? "GA4 needs to be reconnected" :
         needsSetup ? "GA4 not connected or property not selected" :
         "GA4 access error"}
      </p>
      <p className="mt-1 text-sm text-amber-700">{msg}</p>
      <div className="mt-3 flex flex-wrap gap-2">
        {needsEnable && (
          <a
            href="https://console.cloud.google.com/apis/library/analyticsdata.googleapis.com"
            target="_blank"
            rel="noopener noreferrer"
            className="rounded-md bg-amber-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-amber-700"
          >
            Enable GA4 Data API in Google Cloud →
          </a>
        )}
        <a
          href="/onboarding"
          className="rounded-md border border-amber-400 bg-white px-3 py-1.5 text-xs font-semibold text-amber-700 hover:bg-amber-50"
        >
          {needsReconnect ? "Reconnect GA4 in Business Setup" : "Go to Business Setup →"}
        </a>
      </div>
    </div>
  );
}

// ── Loading skeleton ──────────────────────────────────────────────────────────

function Skeleton({ rows = 5 }: { rows?: number }) {
  return (
    <div className="animate-pulse space-y-2">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="h-8 rounded-lg bg-gray-100" style={{ opacity: 1 - i * 0.1 }} />
      ))}
    </div>
  );
}

// ── Section wrapper ───────────────────────────────────────────────────────────

function SectionHeader({
  title,
  subtitle,
  icon: Icon,
}: {
  title: string;
  subtitle?: string;
  icon: React.ElementType;
}) {
  return (
    <div className="flex items-center gap-2 border-b border-neutral-200 px-5 py-3.5">
      <Icon className="h-4 w-4 text-rp-tlight shrink-0" />
      <div>
        <div className="text-sm font-bold text-neutral-900">{title}</div>
        {subtitle && <div className="text-[11px] text-neutral-500">{subtitle}</div>}
      </div>
    </div>
  );
}

function Section({
  title,
  subtitle,
  icon: Icon,
  children,
  loading,
  error,
}: {
  title: string;
  subtitle?: string;
  icon: React.ElementType;
  children: React.ReactNode;
  loading?: boolean;
  error?: unknown;
}) {
  return (
    <Card>
      <SectionHeader title={title} subtitle={subtitle} icon={Icon} />
      <div className="p-4">
        {error ? <NotConnected error={error} /> : loading ? <Skeleton /> : children}
      </div>
    </Card>
  );
}

// ── Pages table ───────────────────────────────────────────────────────────────

function PagesTable({ rows, compared }: { rows: Ga4Row[]; compared: boolean }) {
  if (!rows.length) return <p className="text-sm text-rp-tlight">No page data for this period.</p>;
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-xs">
        <thead>
          <tr className="border-b border-rp-border text-rp-tlight">
            <th className="pb-2 pr-4 font-semibold">#</th>
            <th className="pb-2 pr-4 font-semibold">Page</th>
            <th className="pb-2 pr-4 text-right font-semibold">Sessions</th>
            <th className="pb-2 pr-4 text-right font-semibold">Users</th>
            <th className="pb-2 pr-4 text-right font-semibold">Views</th>
            <th className="pb-2 pr-4 text-right font-semibold">Avg Duration</th>
            <th className="pb-2 text-right font-semibold">Bounce</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-rp-border">
          {rows.map((row, i) => {
            const path = String(row.pagePath || row.landingPage || "/");
            const title = String(row.pageTitle || "");
            const currSess = Number(row["sessions"] ?? row["sessions:current"] ?? 0);
            const prevSess = Number(row["sessions:previous"] ?? NaN);
            return (
              <tr key={`${path}-${i}`} className="hover:bg-[#FAFBFC]">
                <td className="py-2 pr-4 text-rp-tlight">{i + 1}</td>
                <td className="py-2 pr-4 max-w-[240px]">
                  <p className="truncate font-medium text-navy" title={path}>{path}</p>
                  {title && <p className="truncate text-[10px] text-rp-tlight" title={title}>{title}</p>}
                </td>
                <td className="py-2 pr-4 text-right font-semibold text-navy">
                  <div className="flex flex-col items-end gap-0.5">
                    <span>{fmt(currSess)}</span>
                    {compared && <Delta curr={currSess} prev={isNaN(prevSess) ? undefined : prevSess} />}
                  </div>
                </td>
                <td className="py-2 pr-4 text-right text-rp-tmid">{fmt(Number(row.activeUsers ?? 0))}</td>
                <td className="py-2 pr-4 text-right text-rp-tmid">{fmt(Number(row.screenPageViews ?? 0))}</td>
                <td className="py-2 pr-4 text-right text-rp-tmid">{fmtDur(Number(row.averageSessionDuration ?? 0))}</td>
                <td className="py-2 text-right text-rp-tmid">{fmtPct(Number(row.bounceRate ?? 0))}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

// ── Channels section ──────────────────────────────────────────────────────────

function ChannelsSection({ rows }: { rows: Ga4Row[]; compared?: boolean }) {
  if (!rows.length) return <p className="text-sm text-rp-tlight">No channel data.</p>;
  const totalSessions = rows.reduce((s, r) => s + Number(r.sessions ?? 0), 0);
  return (
    <div className="space-y-2">
      {rows.map((row, i) => {
        const channel = String(row.sessionDefaultChannelGrouping ?? "Unknown");
        const sess = Number(row.sessions ?? 0);
        const pct = totalSessions ? (sess / totalSessions) * 100 : 0;
        const color = channelColor(channel);
        return (
          <div key={`${channel}-${i}`} className="flex items-center gap-3">
            <div className="w-28 shrink-0 text-xs font-semibold text-navy truncate" title={channel}>{channel}</div>
            <div className="relative flex-1 rounded-full bg-gray-100" style={{ height: 10 }}>
              <div
                className="absolute left-0 top-0 h-full rounded-full transition-all"
                style={{ width: `${Math.min(pct, 100)}%`, background: color }}
              />
            </div>
            <div className="w-12 text-right text-xs font-bold text-navy">{fmt(sess)}</div>
            <div className="w-10 text-right text-[11px] text-rp-tlight">{pct.toFixed(1)}%</div>
          </div>
        );
      })}
    </div>
  );
}

// ── Geo table ─────────────────────────────────────────────────────────────────

function GeoTable({ rows }: { rows: Ga4Row[] }) {
  if (!rows.length) return <p className="text-sm text-rp-tlight">No location data.</p>;
  const maxSessions = Math.max(...rows.map((r) => Number(r.sessions ?? 0)), 1);
  return (
    <div className="space-y-2">
      {rows.slice(0, 20).map((row, i) => {
        const city = String(row.city ?? "Unknown");
        const region = String(row.region ?? "");
        const country = String(row.country ?? "");
        const sess = Number(row.sessions ?? 0);
        const users = Number(row.activeUsers ?? 0);
        const pct = (sess / maxSessions) * 100;
        return (
          <div key={`${city}-${i}`} className="flex items-center gap-3">
            <div className="flex w-40 shrink-0 flex-col">
              <span className="text-xs font-semibold text-navy truncate">{city}</span>
              <span className="text-[10px] text-rp-tlight truncate">{[region, country].filter(Boolean).join(", ")}</span>
            </div>
            <div className="relative flex-1 rounded-full bg-gray-100" style={{ height: 8 }}>
              <div
                className="absolute left-0 top-0 h-full rounded-full bg-[#FF6B00] transition-all"
                style={{ width: `${Math.min(pct, 100)}%` }}
              />
            </div>
            <div className="w-10 text-right text-xs font-bold text-navy">{fmt(sess)}</div>
            <div className="w-10 text-right text-[11px] text-rp-tlight">{fmt(users)} users</div>
          </div>
        );
      })}
    </div>
  );
}

// ── Overview trend chart ──────────────────────────────────────────────────────

function OverviewChart({ rows, metric, color }: { rows: Ga4Row[]; metric: string; color: string }) {
  const values = rows
    .filter((r) => r.dateRange === "current" || r.dateRange == null || !("dateRange" in r))
    .map((r) => Number(r[metric] ?? 0));
  if (!values.length) return null;
  return <MiniBar values={values} color={color} height={48} />;
}

// ── Main page ─────────────────────────────────────────────────────────────────

export function Ga4Page() {
  const token = useAuthStore((s) => s.accessToken);
  const [range, setRange] = useState<Ga4RangeKey>("month");
  const [compare, setCompare] = useState(false);

  const qk = [token, range, compare] as const;

  const overviewQ = useQuery({
    queryKey: ["ga4", "overview", ...qk],
    queryFn: () => fetchGa4Overview(range, compare),
    enabled: Boolean(token),
    staleTime: 5 * 60_000,
    retry: 1,
  });

  const pagesQ = useQuery({
    queryKey: ["ga4", "pages", ...qk],
    queryFn: () => fetchGa4Pages(range, compare, 25),
    enabled: Boolean(token),
    staleTime: 5 * 60_000,
    retry: 1,
  });

  const channelsQ = useQuery({
    queryKey: ["ga4", "channels", ...qk],
    queryFn: () => fetchGa4Channels(range, compare),
    enabled: Boolean(token),
    staleTime: 5 * 60_000,
    retry: 1,
  });

  const geoQ = useQuery({
    queryKey: ["ga4", "geo", ...qk],
    queryFn: () => fetchGa4Geo(range, compare, 30),
    enabled: Boolean(token),
    staleTime: 5 * 60_000,
    retry: 1,
  });

  const organicQ = useQuery({
    queryKey: ["ga4", "organic", ...qk],
    queryFn: () => fetchGa4Organic(range, compare, 25),
    enabled: Boolean(token),
    staleTime: 5 * 60_000,
    retry: 1,
  });

  const anyError = overviewQ.error ?? pagesQ.error ?? channelsQ.error;
  const totals = overviewQ.data?.totals?.current ?? {};
  const prevTotals = overviewQ.data?.totals?.previous ?? {};
  const overviewRows = overviewQ.data?.rows ?? [];

  return (
    <div className="min-h-screen bg-[#F7F8FC]">
      <TopBar title="GA4 Analytics" />

      <div className="mx-auto max-w-7xl space-y-5 px-4 pb-12 pt-6">
        {/* Header */}
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 className="text-xl font-bold text-navy">Google Analytics 4</h1>
            <p className="mt-0.5 text-sm text-rp-tlight">
              Traffic, page performance, channel mix and suburb-level geography — live from your GA4 property.
            </p>
          </div>
          <Toolbar range={range} compare={compare} onRange={setRange} onCompare={setCompare} />
        </div>

        {/* Global error */}
        {anyError && !overviewQ.isLoading && (
          <NotConnected error={anyError} />
        )}

        {/* ── KPI summary cards ── */}
        {!anyError && (
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
            <StatCard
              label="Active Users"
              value={fmt(Number(totals.activeUsers ?? 0))}
              prev={compare ? fmt(Number(prevTotals.activeUsers ?? 0)) : undefined}
              icon={Users}
              color="#6366f1"
            />
            <StatCard
              label="New Users"
              value={fmt(Number(totals.newUsers ?? 0))}
              prev={compare ? fmt(Number(prevTotals.newUsers ?? 0)) : undefined}
              icon={TrendingUp}
              color="#22c55e"
            />
            <StatCard
              label="Sessions"
              value={fmt(Number(totals.sessions ?? 0))}
              prev={compare ? fmt(Number(prevTotals.sessions ?? 0)) : undefined}
              icon={BarChart2}
              color="#f59e0b"
            />
            <StatCard
              label="Avg Duration"
              value={fmtDur(Number(totals.averageSessionDuration ?? 0))}
              icon={RefreshCw}
              color="#06b6d4"
              sub="per session"
            />
            <StatCard
              label="Bounce Rate"
              value={fmtPct(Number(totals.bounceRate ?? 0))}
              icon={Minus}
              color="#f43f5e"
              sub="of sessions"
            />
          </div>
        )}

        {/* ── Overview trend ── */}
        {!anyError && overviewRows.length > 0 && (
          <Card>
            <SectionHeader
              title="Traffic trend"
              subtitle={`${GA4_RANGE_LABELS[range]} · daily active users`}
              icon={TrendingUp}
            />
            <div className="grid grid-cols-1 gap-4 p-4 sm:grid-cols-3">
              <div>
                <p className="mb-1 text-xs font-semibold text-rp-tlight uppercase tracking-wide">Active Users</p>
                <OverviewChart rows={overviewRows} metric="activeUsers" color="#6366f1" />
              </div>
              <div>
                <p className="mb-1 text-xs font-semibold text-rp-tlight uppercase tracking-wide">Sessions</p>
                <OverviewChart rows={overviewRows} metric="sessions" color="#f59e0b" />
              </div>
              <div>
                <p className="mb-1 text-xs font-semibold text-rp-tlight uppercase tracking-wide">Page Views</p>
                <OverviewChart rows={overviewRows} metric="screenPageViews" color="#22c55e" />
              </div>
            </div>
          </Card>
        )}

        {/* ── Two-column: channels + geo ── */}
        <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
          <Section
            title="Traffic by channel"
            subtitle="Sessions by acquisition source"
            icon={BarChart2}
            loading={channelsQ.isLoading}
            error={channelsQ.error}
          >
            <ChannelsSection rows={channelsQ.data?.rows ?? []} compared={compare} />
          </Section>

          <Section
            title="Location / suburbs"
            subtitle="Top cities by sessions"
            icon={MapPin}
            loading={geoQ.isLoading}
            error={geoQ.error}
          >
            <GeoTable rows={geoQ.data?.rows ?? []} />
          </Section>
        </div>

        {/* ── Organic landing pages ── */}
        <Section
          title="Organic search landing pages"
          subtitle="Top pages that receive organic search traffic"
          icon={Search}
          loading={organicQ.isLoading}
          error={organicQ.error}
        >
          <PagesTable rows={organicQ.data?.rows ?? []} compared={compare} />
        </Section>

        {/* ── All pages ── */}
        <Section
          title="Page-level traffic"
          subtitle="All pages — sessions, users, views, duration, bounce rate"
          icon={Globe}
          loading={pagesQ.isLoading}
          error={pagesQ.error}
        >
          <PagesTable rows={pagesQ.data?.rows ?? []} compared={compare} />
        </Section>

        {/* Footer note */}
        <p className="text-center text-[11px] text-rp-tlight">
          Data sourced live from your GA4 property via the Google Analytics Data API.
          {compare && " Comparison = previous equivalent period."}
        </p>
      </div>
    </div>
  );
}
