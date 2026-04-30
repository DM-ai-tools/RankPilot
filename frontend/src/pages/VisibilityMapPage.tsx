import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { formatApiError } from "../api/client";
import { fetchMe } from "../api/onboarding";
import { fetchSuburbRanks } from "../api/ranks";
import { LeafletVisibilityMap } from "../components/map/LeafletVisibilityMap";
import { TopBar } from "../components/layout/TopBar";
import { Button } from "../components/ui/Button";
import { Card, CardHeader } from "../components/ui/Card";
import { MetricCard } from "../components/ui/MetricCard";
import { useAuthStore } from "../stores/authStore";
import { visibilityScoreFromSuburbs } from "../lib/scoring";

function fmtK(n: number) {
  if (n >= 1000) return `${(n / 1000).toFixed(1)}K`;
  return String(Math.round(n));
}

/* Rank badge matching mockup colour scheme */
function RankBadge({ rank }: { rank: number | null }) {
  const [bg, text] =
    rank == null           ? ["bg-[#F1F5F9]", "text-[#475569]"]
    : rank <= 3            ? ["bg-[#DCFCE7]", "text-[#15803D]"]
    : rank <= 10           ? ["bg-[#DBEAFE]", "text-[#1D4ED8]"]
    : rank <= 20           ? ["bg-[#FEF9C3]", "text-[#92400E]"]
    :                        ["bg-[#FEE2E2]", "text-[#B91C1C]"];

  return (
    <span
      className={`inline-flex items-center justify-center rounded-full px-2 py-0.5 text-[10px] font-bold ${bg} ${text}`}
    >
      {rank == null ? "—" : `#${rank}`}
    </span>
  );
}

export function VisibilityMapPage() {
  const token = useAuthStore((s) => s.accessToken);

  const q = useQuery({
    queryKey: ["ranks", "suburbs", token],
    queryFn:  fetchSuburbRanks,
    enabled:  Boolean(token),
  });
  const me = useQuery({
    queryKey: ["me", token],
    queryFn: fetchMe,
    enabled: Boolean(token),
  });

  const companyPoint =
    me.data?.business_lat != null &&
    me.data?.business_lng != null &&
    Number.isFinite(me.data.business_lat) &&
    Number.isFinite(me.data.business_lng)
      ? {
          lat: me.data.business_lat as number,
          lng: me.data.business_lng as number,
          label: me.data.business_name || "Your business",
          locationSource: me.data.business_location_source ?? null,
        }
      : null;

  const d = q.data;

  const mapScore = d?.suburbs?.length
    ? visibilityScoreFromSuburbs(d.suburbs)
    : (d?.visibility_score ?? 0);

  return (
    <>
      <TopBar
        title="Google Maps Rank Tracker"
        subtitle={
          d
            ? `"${d.keyword}" · ${d.metro_label} · ${d.suburbs.length} suburbs tracked`
            : token ? "Loading suburb grid…" : "Sign in to view rankings"
        }
        actions={
          <>
            <Button variant="outline" size="sm" type="button">
              ↓ Export CSV
            </Button>
          </>
        }
      />

      <div className="flex-1 overflow-y-auto bg-rp-light px-5 py-[18px]">

        {!token ? (
          <p className="text-sm text-rp-tmid">
            <Link to="/login" className="font-semibold text-[#72C219] hover:underline">Sign in</Link> to view this page.
          </p>
        ) : q.isLoading ? (
          <p className="text-sm text-rp-tlight">Loading…</p>
        ) : q.isError ? (
          <p className="text-sm text-red-600">{formatApiError(q.error)}</p>
        ) : null}

        {d ? (
          <>
            {/* ── 4 metric cards — matches mockup screen 3 ───────── */}
            <div className="mb-[14px] grid gap-3 xl:grid-cols-4" style={{ gridTemplateColumns: "160px 1fr 1fr 1fr" }}>
              {/* Visibility Score */}
              <div className="rounded-[10px] border border-rp-border bg-white p-[14px] text-center">
                <div className="mb-1.5 text-[10px] font-semibold uppercase tracking-[0.8px] text-rp-tlight">
                  Visibility Score
                </div>
                <div className="text-[44px] font-black leading-none text-teal">
                  {Math.round(mapScore)}
                </div>
                <div className="text-[10px] text-rp-tlight">/100</div>
                <div className="mt-1 text-[10px] font-semibold text-emerald-600">
                  {d.suburbs.length > 0 ? "From Maps pack ranks" : "—"}
                </div>
              </div>

              {/* Top 3 */}
              <MetricCard label="Top 3 — Highly Visible" value={d.top3_count}>
                <div>
                  <div className="text-[28px] font-extrabold leading-none text-emerald-500">
                    {d.top3_count}
                  </div>
                  <div className="mt-0.5 text-[10px] text-rp-tlight">suburbs ranking #1–3</div>
                  <div className="mt-2 h-2 overflow-hidden rounded-full bg-rp-border">
                    <div
                      className="h-full rounded-full bg-emerald-500"
                      style={{ width: `${d.suburbs.length ? (d.top3_count / d.suburbs.length) * 100 : 0}%` }}
                    />
                  </div>
                </div>
              </MetricCard>

              {/* Pack 4-10 */}
              <MetricCard label="Pack 4–10 — Visible">
                <div>
                  <div className="text-[28px] font-extrabold leading-none text-amber-500">
                    {d.page1_count}
                  </div>
                  <div className="mt-0.5 text-[10px] text-rp-tlight">suburbs ranking #4–10</div>
                  <div className="mt-2 h-2 overflow-hidden rounded-full bg-rp-border">
                    <div
                      className="h-full rounded-full bg-amber-400"
                      style={{ width: `${d.suburbs.length ? (d.page1_count / d.suburbs.length) * 100 : 0}%` }}
                    />
                  </div>
                </div>
              </MetricCard>

              {/* Not visible */}
              <MetricCard label="Not Visible">
                <div>
                  <div className="text-[28px] font-extrabold leading-none text-red-500">
                    {d.not_ranking_count}
                  </div>
                  <div className="mt-0.5 text-[10px] text-rp-tlight">suburbs not in top 20</div>
                  <div className="mt-2 h-2 overflow-hidden rounded-full bg-rp-border">
                    <div
                      className="h-full rounded-full bg-red-500"
                      style={{ width: `${d.suburbs.length ? (d.not_ranking_count / d.suburbs.length) * 100 : 0}%` }}
                    />
                  </div>
                </div>
              </MetricCard>
            </div>

            {/* ── Map + Suburb list ─────────────────────────────── */}
            <div className="grid gap-[14px] lg:grid-cols-[1fr_260px]">
              {/* Suburb Heat Map */}
              <Card>
                <CardHeader
                  title="Suburb Heat Map"
                  subtitle={
                    (d.map_competitors?.length ?? 0) > 0
                      ? `Circles = your suburb ranks · competitor pins (${d.map_competitors.length}) · blue marker = your business`
                      : "Circles = suburb ranks from last scan — run a new scan to store competitor pins (Google lat/lng via DataForSEO)"
                  }
                  right={
                    <div className="flex flex-wrap gap-2">
                      {[
                        ["bg-emerald-500", "Top 3"],
                        ["bg-amber-400",   "Pack 4–10"],
                        ["bg-teal",        "Pack 11–20"],
                        ["bg-red-500",     "Not visible"],
                      ].map(([c, l]) => (
                        <span key={l} className="flex items-center gap-1 text-[10px] text-rp-tlight">
                          <span className={`inline-block h-2.5 w-2.5 rounded-sm ${c}`} />
                          {l}
                        </span>
                      ))}
                    </div>
                  }
                />
                <div className="p-4">
                  <LeafletVisibilityMap
                    suburbs={d.suburbs}
                    companyPoint={companyPoint}
                    competitorPins={d.map_competitors ?? []}
                  />
                </div>
              </Card>

              {/* Suburb Rankings table */}
              <Card>
                <CardHeader title="Suburb Rankings" />
                <div className="max-h-[420px] overflow-y-auto">
                  <table className="w-full border-collapse text-left">
                    <thead>
                      <tr className="border-b border-rp-border bg-rp-light text-[10px] font-bold uppercase tracking-wide text-rp-tlight">
                        <th className="px-3 py-2">Suburb</th>
                        <th className="px-3 py-2 text-center">Rank</th>
                        <th className="px-3 py-2">Vol</th>
                      </tr>
                    </thead>
                    <tbody>
                      {d.suburbs.map((s) => (
                        <tr key={s.suburb_id} className="border-b border-[#F0F4F8] hover:bg-[#FAFBFD]">
                          <td className="px-3 py-2 text-[12px] font-semibold text-navy">
                            {s.suburb}
                          </td>
                          <td className="px-3 py-2 text-center">
                            <RankBadge rank={s.rank_position} />
                          </td>
                          <td className="px-3 py-2 text-[11px] text-rp-tlight">
                            {fmtK(s.monthly_volume_proxy)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </Card>
            </div>
          </>
        ) : null}
      </div>
    </>
  );
}
