import { useQuery } from "@tanstack/react-query";
import { TrendingUp, TrendingDown, Minus, KeyRound } from "lucide-react";

import { fetchMe } from "../api/onboarding";
import { fetchSuburbRanks } from "../api/ranks";
import { TopBar } from "../components/layout/TopBar";
import { Card, CardHeader } from "../components/ui/Card";
import { useAuthStore } from "../stores/authStore";
import type { SuburbRank } from "../api/types";

/* ── rank badge colour ──────────────────────────────────────────── */
function rankColor(r: number | null): string {
  if (r == null)  return "text-rp-tlight";
  if (r <= 3)     return "text-emerald-600";
  if (r <= 10)    return "text-[#72C219]";
  if (r <= 20)    return "text-amber-500";
  return "text-red-500";
}

function rankBg(r: number | null): string {
  if (r == null)  return "bg-rp-light";
  if (r <= 3)     return "bg-emerald-50";
  if (r <= 10)    return "bg-[#72C219]/10";
  if (r <= 20)    return "bg-amber-50";
  return "bg-red-50";
}

function rankLabel(r: number | null): string {
  if (r == null) return "NR";
  return `#${r}`;
}

function rankIcon(r: number | null) {
  if (r == null) return <Minus className="h-3 w-3 text-rp-tlight" />;
  if (r <= 3)    return <TrendingUp className="h-3 w-3 text-emerald-600" />;
  if (r <= 10)   return <TrendingUp className="h-3 w-3 text-[#72C219]" />;
  return <TrendingDown className="h-3 w-3 text-red-400" />;
}

/* ── Main page ─────────────────────────────────────────────────── */
export function RanksPage() {
  const token = useAuthStore((s) => s.accessToken);
  const me = useQuery({ queryKey: ["me", token], queryFn: fetchMe, enabled: Boolean(token) });
  const ranks = useQuery({
    queryKey: ["ranks", "suburbs", token],
    queryFn: fetchSuburbRanks,
    enabled: Boolean(token),
  });

  const kw      = ranks.data?.keyword || me.data?.primary_keyword || "";
  const metro   = ranks.data?.metro_label || me.data?.metro_label || "";
  const radius  = me.data?.search_radius_km ?? 25;
  const suburbs = ranks.data?.suburbs ?? [];

  const ranked     = suburbs.filter((s) => s.rank_position != null).length;
  const top3       = suburbs.filter((s) => s.rank_position != null && s.rank_position <= 3).length;
  const pack4to10  = suburbs.filter((s) => s.rank_position != null && s.rank_position > 3 && s.rank_position <= 10).length;
  const notRanking = suburbs.filter((s) => s.rank_position == null).length;
  const total      = suburbs.length;

  const sorted = [...suburbs].sort((a, b) => {
    if (a.rank_position == null && b.rank_position == null) return a.suburb.localeCompare(b.suburb);
    if (a.rank_position == null) return 1;
    if (b.rank_position == null) return -1;
    return a.rank_position - b.rank_position;
  });

  const noData = !ranks.isLoading && suburbs.length === 0;

  return (
    <>
      <TopBar
        title="Keywords"
        subtitle={
          kw
            ? `Maps pack: "${kw}"${metro ? ` · ${metro}` : ""} · ${radius} km radius`
            : "Run a scan to populate keyword rankings"
        }
      />
      <div className="flex-1 overflow-y-auto bg-rp-light px-7 py-6">

        {/* ── KPI cards ─────────────────────────────────────────── */}
        <div className="mb-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {[
            { label: "Keyword",         value: kw || "—",                   desc: "Primary service phrase" },
            { label: "Top 3 (Pack)",    value: total ? String(top3) : "—",  desc: "In Google Maps 3-pack" },
            { label: "Pack 4–10",       value: total ? String(pack4to10) : "—", desc: "On first page" },
            { label: "Not Ranking",     value: total ? String(notRanking) : "—", desc: "Outside top 20" },
          ].map((s) => (
            <div key={s.label} className="rounded-xl border border-rp-border bg-white px-5 py-4 shadow-card">
              <div className="text-[11px] font-semibold uppercase tracking-wide text-rp-tlight">{s.label}</div>
              <div className="mt-1 truncate text-[24px] font-extrabold leading-none text-navy">{s.value}</div>
              <div className="mt-0.5 text-[10px] text-rp-tlight">{s.desc}</div>
            </div>
          ))}
        </div>

        {/* ── Suburb rank table ──────────────────────────────────── */}
        <Card>
          <CardHeader
            title={`Suburb Rankings — "${kw || "keyword not set"}"`}
            subtitle={
              total
                ? `${ranked} of ${total} suburbs ranked · search radius ${radius} km`
                : "No scan data yet"
            }
          />

          {ranks.isLoading && (
            <div className="px-6 py-10 text-center text-sm text-rp-tlight">Loading rankings…</div>
          )}

          {noData && (
            <div className="flex flex-col items-center gap-3 px-6 py-12 text-center">
              <div className="rounded-full bg-rp-light p-4" style={{ color: "#72C219" }}>
                <KeyRound className="h-6 w-6" />
              </div>
              <div className="text-sm font-semibold text-navy">No scan data yet</div>
              <p className="max-w-sm text-xs leading-relaxed text-rp-tlight">
                Click <strong>Run Scan Now</strong> on the dashboard to start a Maps pack check
                for each suburb in your grid. Results appear here in 3–5 minutes.
              </p>
              {!kw && (
                <p className="max-w-xs text-xs text-amber-700">
                  Also make sure you have a <strong>primary keyword</strong> set in your profile (e.g. "seo agency").
                </p>
              )}
            </div>
          )}

          {sorted.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full border-collapse text-left">
                <thead>
                  <tr className="border-b border-rp-border bg-rp-light text-[11px] font-bold uppercase tracking-wide text-rp-tlight">
                    <th className="px-4 py-3 w-10">#</th>
                    <th className="px-4 py-3">Suburb</th>
                    <th className="px-4 py-3">State</th>
                    <th className="px-4 py-3 text-center">Maps Rank</th>
                    <th className="px-4 py-3 text-right">Monthly Searches</th>
                    <th className="px-4 py-3">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {sorted.map((s: SuburbRank, i) => (
                    <tr key={s.suburb_id} className="border-b border-[#F0F4F9] hover:bg-[#FAFBFD]">
                      <td className="px-4 py-2.5 text-[11px] text-rp-tlight">{i + 1}</td>
                      <td className="px-4 py-2.5">
                        <div className="text-[13px] font-semibold text-navy">{s.suburb}</div>
                        {s.postcode && <div className="text-[10px] text-rp-tlight">{s.postcode}</div>}
                      </td>
                      <td className="px-4 py-2.5 text-[12px] text-rp-tmid">{s.state ?? "—"}</td>
                      <td className="px-4 py-2.5 text-center">
                        <span
                          className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[12px] font-bold ${rankColor(s.rank_position)} ${rankBg(s.rank_position)}`}
                        >
                          {rankIcon(s.rank_position)}
                          {rankLabel(s.rank_position)}
                        </span>
                      </td>
                      <td className="px-4 py-2.5 text-right text-[12px] font-semibold text-navy">
                        {s.monthly_volume_proxy > 0
                          ? s.monthly_volume_proxy.toLocaleString()
                          : <span className="text-rp-tlight">—</span>}
                      </td>
                      <td className="px-4 py-2.5 text-[11px]">
                        {s.rank_position == null ? (
                          <span className="rounded-full bg-red-50 px-2 py-0.5 text-red-500">Not ranking</span>
                        ) : s.rank_position <= 3 ? (
                          <span className="rounded-full bg-emerald-50 px-2 py-0.5 text-emerald-700">Top 3 Pack</span>
                        ) : s.rank_position <= 10 ? (
                          <span className="rounded-full px-2 py-0.5 font-medium" style={{ backgroundColor: "rgba(114,194,25,0.12)", color: "#4a8a0f" }}>Pack 4–10</span>
                        ) : (
                          <span className="rounded-full bg-amber-50 px-2 py-0.5 text-amber-700">Pack 11–20</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>

      </div>
    </>
  );
}
