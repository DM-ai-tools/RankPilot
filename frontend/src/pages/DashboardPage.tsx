import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { formatApiError } from "../api/client";
import { fetchDashboardOverview } from "../api/overview";
import { fetchMe, patchMe } from "../api/onboarding";
import { fetchOpportunities } from "../api/opportunities";
import { fetchSuburbRanks } from "../api/ranks";
import { formatKeywordVolume } from "../api/keywords";
import { enqueueMapsScan } from "../api/scans";
import { LeafletVisibilityMap } from "../components/map/LeafletVisibilityMap";
import { TopBar } from "../components/layout/TopBar";
import {
  getStoredScanJobId,
  storeScanJobId,
  useActiveScanPolling,
} from "../hooks/useScanPolling";
import { MetricCard } from "../components/ui/MetricCard";
import { Badge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { Card, CardHeader } from "../components/ui/Card";
import { useAuthStore } from "../stores/authStore";
import { normalizePrimaryKeywords, parsePrimaryKeywords, scanKeywordFromPrimary } from "../lib/primaryKeywords";
import { visibilityScoreFromSuburbs } from "../lib/scoring";

/* ── helpers ─────────────────────────────────────────────────── */
function fmtK(n: number) {
  if (n >= 1000) return `${(n / 1000).toFixed(1)}K`;
  return String(n);
}

function relTime(iso: string) {
  const ms = Date.now() - new Date(iso).getTime();
  const m  = Math.floor(ms / 60000);
  if (m < 2)  return "just now";
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

/* ── Visibility gauge ────────────────────────────────────────── */
function VisibilityGauge({ score }: { score: number }) {
  const pct = Math.min(100, Math.max(0, score));
  const r   = 28;
  const circ = 2 * Math.PI * r;
  return (
    <div className="flex flex-col items-center">
      <div className="relative flex items-center justify-center" style={{ width: 70, height: 70 }}>
        <svg width="70" height="70" viewBox="0 0 70 70">
          <circle cx="35" cy="35" r={r} fill="none" stroke="#e2e7df" strokeWidth="6" />
          <circle
            cx="35" cy="35" r={r}
            fill="none"
            stroke="#4d8a20"
            strokeWidth="6"
            strokeDasharray={`${(pct / 100) * circ} ${circ}`}
            strokeLinecap="round"
            transform="rotate(-90 35 35)"
          />
        </svg>
        <div className="absolute text-[16px] font-black tabular-nums text-neutral-900">{Math.round(pct)}</div>
      </div>
    </div>
  );
}

/* ── Activity / queue feed row ───────────────────────────────── */
function FeedRow({
  dot,
  title,
  meta,
}: {
  dot: "green" | "amber";
  title: string;
  meta: string;
}) {
  return (
    <div className="flex items-center gap-2.5 border-b border-[#F0F4F8] px-4 py-2.5 last:border-0">
      <div
        className={`h-2 w-2 shrink-0 rounded-full ${dot === "green" ? "bg-emerald-500" : "bg-amber-400"}`}
      />
      <div className="min-w-0 flex-1">
        <div className="truncate text-[12px] font-semibold text-navy">{title}</div>
        <div className="text-[10px] text-rp-tlight">{meta}</div>
      </div>
    </div>
  );
}

/* ── Near-miss card ──────────────────────────────────────────── */
function NearMissCard({
  label,
  rank,
  volume,
  action,
}: {
  label: string;
  rank: number;
  volume: number | null;
  action: string;
}) {
  return (
    <div className="flex-1 rounded-lg border border-rp-border bg-white px-[10px] py-[10px]">
      <div className="text-[12px] font-bold text-navy">{label}</div>
      <div className="mt-0.5 text-[10px] text-rp-tlight">
        Currently #{rank}{volume ? ` · ${fmtK(volume)} searches/mo` : ""}
      </div>
      <div className="mt-1 text-[10px] font-semibold text-amber-600">{action}</div>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════ */
export function DashboardPage() {
  const token = useAuthStore((s) => s.accessToken);
  const qc    = useQueryClient();
  const [urlInput, setUrlInput] = useState("");
  const [kwInput,  setKwInput]  = useState("");
  const [activeJobId, setActiveJobId] = useState<string | null>(() => getStoredScanJobId());
  const { isScanning, progress: scanProgress } = useActiveScanPolling(activeJobId);

  const me = useQuery({
    queryKey: ["me", token],
    queryFn:  fetchMe,
    enabled:  Boolean(token),
    staleTime: 45_000,
  });

  useEffect(() => {
    if (!me.data) return;
    setUrlInput(me.data.business_url || "");
    setKwInput(me.data.primary_keyword || "");
  }, [me.data?.client_id]);

  const overview = useQuery({
    queryKey: ["dashboard", "overview", token],
    queryFn:  fetchDashboardOverview,
    enabled:  Boolean(token),
    staleTime: 45_000,
  });

  const ranks = useQuery({
    queryKey: ["ranks", "suburbs", token],
    queryFn:  fetchSuburbRanks,
    enabled:  Boolean(token),
    staleTime: 45_000,
    refetchInterval: isScanning ? 5_000 : false,
  });

  const opportunities = useQuery({
    queryKey: ["opportunities", token],
    queryFn:  fetchOpportunities,
    enabled:  Boolean(token),
    staleTime: 45_000,
  });

  /* ── mutations ─────────────────────────────────────────────── */
  const saveAndScan = useMutation({
    mutationFn: async () => {
      const profile = await patchMe({
        business_url:     urlInput.trim(),
        primary_keyword:  normalizePrimaryKeywords(kwInput) || undefined,
      });
      const job = await enqueueMapsScan({
        keyword: scanKeywordFromPrimary(profile.primary_keyword || "") || null,
        radius_km: profile.search_radius_km ?? null,
      });
      return { profile, job };
    },
    onSuccess: (data) => {
      setUrlInput(data.profile.business_url || "");
      setKwInput(data.profile.primary_keyword || "");
      storeScanJobId(data.job.job_id);
      setActiveJobId(data.job.job_id);
      void qc.invalidateQueries({ queryKey: ["me"] });
      void qc.invalidateQueries({ queryKey: ["dashboard"] });
      void qc.invalidateQueries({ queryKey: ["ranks"] });
    },
  });

  const scan = useMutation({
    mutationFn: () =>
      enqueueMapsScan({
        keyword: scanKeywordFromPrimary(kwInput) || null,
        radius_km: me.data?.search_radius_km ?? null,
      }),
    onSuccess: (data) => {
      storeScanJobId(data.job_id);
      setActiveJobId(data.job_id);
      void qc.invalidateQueries({ queryKey: ["dashboard"] });
      void qc.invalidateQueries({ queryKey: ["ranks"] });
      void qc.invalidateQueries({ queryKey: ["me"] });
    },
  });

  /* ── derived values ────────────────────────────────────────── */
  const o   = overview.data;
  const g   = o?.gauge;
  const st  = o?.stats;

  const liveScore = ranks.data?.suburbs?.length
    ? visibilityScoreFromSuburbs(ranks.data.suburbs)
    : null;
  const gaugeScore = liveScore ?? o?.scores.seo_visibility.value ?? 0;

  const companyMapPoint =
    me.data?.business_lat != null &&
    me.data?.business_lng != null &&
    Number.isFinite(me.data.business_lat) &&
    Number.isFinite(me.data.business_lng)
      ? {
          lat: me.data.business_lat as number,
          lng: me.data.business_lng as number,
          label: me.data.business_name || "Your business",
          address: me.data.business_address ?? null,
          locationSource: me.data.business_location_source ?? null,
        }
      : null;

  const radiusKm = me.data?.search_radius_km ?? null;
  const radiusLabel = radiusKm
    ? radiusKm <= 5  ? `0–5 km (local block)`
    : radiusKm <= 10 ? `6–10 km (local)`
    : radiusKm <= 15 ? `11–15 km (suburb)`
    : radiusKm <= 20 ? `16–20 km (greater metro)`
    : radiusKm <= 25 ? `21–25 km (city-wide)`
    : `26–30 km (regional)`
    : null;


  const nearMiss = (opportunities.data?.items ?? [])
    .filter((op) => op.rank_position != null && op.rank_position >= 11 && op.rank_position <= 20)
    .sort((a, b) => (b.population ?? 0) - (a.population ?? 0))
    .slice(0, 3);

  /** Only when the saved profile has no website — not when /me failed or is still loading. */
  const showProfileQuickEdit =
    me.isSuccess && (!me.data.business_url || me.data.business_url.trim().length < 4);

  /* ── top-bar subtitle ──────────────────────────────────────── */
  const topBarSub = o
    ? `${o.metro_label} · ${parsePrimaryKeywords(o.keyword).slice(0, 3).join(" · ") || o.keyword} · ${st?.suburbs_total ?? 0} suburbs`
    : overview.isLoading ? "Loading…" : "";

  return (
    <>
      <TopBar
        title="Dashboard"
        subtitle={topBarSub}
        actions={
          <>
            {o?.activity?.[0]?.occurred_at ? (
              <span className="text-[11px] text-rp-tlight">
                Last scan: {relTime(o.activity[0].occurred_at)}
              </span>
            ) : null}
            <Button
              size="sm"
              type="button"
              className="min-w-[7.5rem]"
              title="Checks your Google Maps pack position in each suburb via DataForSEO (Ahrefs has no Maps rank API). Keyword volumes use Ahrefs when you view Keywords / the map."
              disabled={!token || scan.isPending || saveAndScan.isPending || isScanning}
              onClick={() => void scan.mutate()}
            >
              {isScanning
                ? scanProgress && scanProgress.suburbs_total > 0
                  ? `Scanning ${scanProgress.suburbs_checked}/${scanProgress.suburbs_total}…`
                  : "Scanning…"
                : scan.isPending
                  ? "Queuing…"
                  : "Scan Now"}
            </Button>
          </>
        }
      />

      <div className="page-scroll">

        {/* ── Status banners ───────────────────────────────────── */}
        {saveAndScan.isSuccess ? (
          <div className="mb-4 rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-2.5 text-xs text-emerald-800">
            Website saved and Maps scan queued (job {saveAndScan.data.job.job_id}). Refresh in a minute or two.
          </div>
        ) : null}
        {(saveAndScan.isError || scan.isError) ? (
          <div className="mb-4 rounded-lg border border-red-200 bg-red-50 px-4 py-2.5 text-xs text-red-700">
            {formatApiError((saveAndScan.isError ? saveAndScan.error : scan.error) as Error)}
          </div>
        ) : null}
        {scan.isSuccess && !saveAndScan.isSuccess ? null : null}

        {me.isError ? (
          <div className="mb-4 rounded-lg border border-red-200 bg-red-50 px-4 py-2.5 text-xs text-red-700">
            Profile could not be loaded ({formatApiError(me.error)}). Fix the API error above, then refresh. If you just
            pulled new code, restart the backend so the database column <code className="text-[10px]">search_radius_km</code>{" "}
            is applied on startup.
          </div>
        ) : null}
        {overview.isError ? (
          <p className="mb-4 text-sm text-red-600">{formatApiError(overview.error)}</p>
        ) : overview.isLoading ? (
          <p className="mb-4 text-sm text-rp-tlight">Loading dashboard…</p>
        ) : null}

        {/* ── Profile quick-edit: only when onboarding never saved a website URL ── */}
        {showProfileQuickEdit ? (
          <div className="mb-4 rounded-[10px] border border-rp-border bg-white px-4 py-3">
            <div className="mb-2 text-[12px] font-bold text-navy">Set up your business</div>
            <div className="grid gap-2 sm:grid-cols-[1fr_1fr_auto] sm:items-end">
              <div>
                <label className="mb-1 block text-[10px] font-semibold uppercase tracking-wide text-rp-tlight">
                  Website URL
                </label>
                <input
                  type="url"
                  placeholder="https://yourbusiness.com.au"
                  value={urlInput}
                  onChange={(e) => setUrlInput(e.target.value)}
                  className="w-full rounded-lg border border-rp-border px-3 py-1.5 text-[13px] text-navy outline-none focus:border-[#72C219]"
                />
              </div>
              <div>
                <label className="mb-1 block text-[10px] font-semibold uppercase tracking-wide text-rp-tlight">
                  Primary services
                </label>
                <input
                  type="text"
                  placeholder="e.g. plumber, electrician (comma-separated)"
                  value={kwInput}
                  onChange={(e) => setKwInput(e.target.value)}
                  className="w-full rounded-lg border border-rp-border px-3 py-1.5 text-[13px] text-navy outline-none focus:border-[#72C219]"
                />
              </div>
              <Button
                type="button"
                size="sm"
                disabled={!token || saveAndScan.isPending || urlInput.trim().length < 4}
                onClick={() => void saveAndScan.mutate()}
              >
                {saveAndScan.isPending ? "Saving…" : "Save & Scan"}
              </Button>
            </div>
            <p className="mt-1.5 text-[10px] text-rp-tlight">
              Metro / suburb grid comes from{" "}
              <Link to="/onboarding" className="font-semibold text-brand-600 hover:underline">
                onboarding
              </Link>.
            </p>
          </div>
        ) : null}

        {o ? (
          <>
            {/* ── 4 metric cards ─────────────────────────────────── */}
            <div className="mb-5 grid min-w-0 grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
              {/* 1. Visibility Score — with SVG gauge */}
              <MetricCard label="Visibility Score">
                <div className="flex flex-col items-center pt-1">
                  <VisibilityGauge score={gaugeScore} />
                  <div className="mt-1 text-[10px] font-semibold text-emerald-600">
                    {st?.visibility_delta != null
                      ? `↑ +${Math.round(st.visibility_delta)} this month`
                      : "Trend after 2+ scans"}
                  </div>
                </div>
              </MetricCard>

              {/* 2. Top-3 Suburbs */}
              <MetricCard
                label="Top-3 Suburbs"
                value={g?.top3_count ?? st?.suburbs_ranked ?? "—"}
                delta={`out of ${st?.suburbs_total ?? 0} tracked`}
              />

              {/* 3. Page 1 (pack 4–10) */}
              <MetricCard
                label="Pack 4–10 Suburbs"
                value={g?.page1_count ?? "—"}
                delta={g ? `${g.page1_pct.toFixed(0)}% of grid` : undefined}
              />

              {/* 4. Monthly Searches — per primary keyword */}
              <MetricCard label="Monthly Searches" className="xl:col-span-1">
                {(() => {
                  const rows =
                    st?.keyword_volumes?.length
                      ? st.keyword_volumes
                      : parsePrimaryKeywords(o?.keyword ?? me.data?.primary_keyword ?? "").map((kw) => ({
                          keyword: kw,
                          monthly_searches: 0,
                        }));
                  const total = rows.reduce((sum, row) => sum + (row.monthly_searches ?? 0), 0);
                  return (
                    <>
                      <div className="text-[28px] font-extrabold tabular-nums leading-none text-neutral-900">
                        {total > 0 ? fmtK(total) : rows.length ? "—" : fmtK(0)}
                      </div>
                      {rows.length > 0 ? (
                        <div className="mt-3 flex flex-col gap-1.5">
                          {rows.map((row) => (
                            <div
                              key={row.keyword}
                              className="flex items-center justify-between gap-2 rounded-md bg-brand-50 px-2 py-1"
                            >
                              <span className="min-w-0 truncate text-[11px] font-medium text-neutral-800" title={row.keyword}>
                                {row.keyword}
                              </span>
                              <span className="shrink-0 text-[11px] font-bold tabular-nums text-brand-700">
                                {formatKeywordVolume(row.monthly_searches)}
                              </span>
                            </div>
                          ))}
                        </div>
                      ) : null}
                      <div className="mt-auto pt-2 text-[10px] text-neutral-500">
                        {st?.monthly_volume_note ?? "Ahrefs · per keyword"}
                      </div>
                    </>
                  );
                })()}
              </MetricCard>
            </div>

            <Card className="mb-5">
              <CardHeader
                title="Business Details (Google)"
                subtitle="Live listing data from Google Places"
              />
              <div className="grid gap-4 p-6 md:grid-cols-3">
                <div>
                  <div className="text-[11px] font-semibold uppercase tracking-[0.06em] text-neutral-500">Company</div>
                  <div className="mt-1 text-sm font-semibold text-neutral-900">
                    {o.business_profile?.name || me.data?.business_name || "Not found"}
                  </div>
                </div>
                <div>
                  <div className="text-[11px] font-semibold uppercase tracking-[0.06em] text-neutral-500">Address</div>
                  <div className="mt-1 text-sm font-semibold text-neutral-900">
                    {o.business_profile?.address || me.data?.business_address || "Not found"}
                  </div>
                </div>
                <div>
                  <div className="text-[11px] font-semibold uppercase tracking-[0.06em] text-neutral-500">Phone</div>
                  <div className="mt-1 text-sm font-semibold tabular-nums text-neutral-900">
                    {o.business_profile?.phone || me.data?.business_phone || "Not found"}
                  </div>
                </div>
              </div>
              {o.business_profile?.maps_url ? (
                <div className="border-t border-neutral-200 px-6 py-3">
                  <a
                    href={o.business_profile.maps_url}
                    target="_blank"
                    rel="noreferrer"
                    className="text-sm font-semibold text-brand-600 hover:underline"
                  >
                    Open Google Maps Location ↗
                  </a>
                </div>
              ) : null}
            </Card>

            {/* ── 2-col: Actions Taken + Upcoming Actions ─────────── */}
            <div className="mb-5 grid gap-4 lg:grid-cols-2">
              <Card>
                <CardHeader title="Actions Taken This Week" subtitle="Recent GBP and content activity" />
                {o.activity.length === 0 ? (
                  <div className="px-4 py-6 text-center text-[12px] text-rp-tlight">
                    No GBP posts published this week yet — publish a post from the GBP tab to see it here.
                  </div>
                ) : (
                  o.activity.slice(0, 5).map((f) => (
                    <FeedRow
                      key={`${f.heading}-${f.occurred_at}`}
                      dot="green"
                      title={`${f.heading} — ${f.detail}`}
                      meta={`${f.icon} · ${relTime(f.occurred_at)}`}
                    />
                  ))
                )}
              </Card>

              <Card>
                <CardHeader title="Recommended Actions" subtitle="Prioritized next steps for your SEO" />
                {o.recommendations.length === 0 ? (
                  <div className="px-4 py-6 text-center text-[12px] text-rp-tlight">
                    No recommendations yet.
                  </div>
                ) : (
                  o.recommendations.slice(0, 5).map((a) => (
                    <FeedRow
                      key={a.title}
                      dot="amber"
                      title={a.title}
                      meta={`${a.icon} ${a.subtitle}`}
                    />
                  ))
                )}
              </Card>
            </div>

            {/* ── Near-miss alert ──────────────────────────────────── */}
            {nearMiss.length > 0 ? (
              <div
                className="mb-[14px] overflow-hidden rounded-[10px] border bg-[#FFFBEB]"
                style={{ borderColor: "#F59E0B" }}
              >
                <div className="border-b px-4 py-3" style={{ background: "#FFFBEB", borderColor: "#FDE68A" }}>
                  <h3 className="text-[13px] font-bold text-navy">
                    🎯 Near-Miss Opportunities ({nearMiss.length} suburb{nearMiss.length !== 1 ? "s" : ""} one push from Top 10)
                  </h3>
                </div>
                <div className="flex gap-[10px] px-4 py-3">
                  {nearMiss.map((op) => (
                    <NearMissCard
                      key={op.suburb_id}
                      label={`${o.keyword} ${op.suburb}`}
                      rank={op.rank_position!}
                      volume={op.population}
                      action={op.recommended_action}
                    />
                  ))}
                </div>
              </div>
            ) : null}

            {/* ── 2-col: Suburb Map + Rank Wins ────────────────────── */}
            <div className="grid gap-[14px] lg:grid-cols-[1fr_300px]">
              <Card>
                <CardHeader
                  title={`Visibility Map${o.keyword ? ` – '${o.keyword}'` : ""}`}
                  subtitle={`${ranks.data?.suburbs?.length ?? 0} suburbs${radiusLabel ? ` · ${radiusLabel}` : ""}`}
                  right={
                    <Link to="/map">
                      <Button variant="outline" size="sm" type="button">
                        Full Map →
                      </Button>
                    </Link>
                  }
                />
                <div className="p-4">
                  <LeafletVisibilityMap
                    suburbs={ranks.data?.suburbs ?? []}
                    companyPoint={companyMapPoint}
                    competitorPins={ranks.data?.map_competitors}
                    radiusKm={radiusKm}
                    radiusLabel={radiusLabel}
                    heightClass="h-[380px]"
                    scanProgress={scanProgress}
                  />
                </div>
              </Card>

              {/* Rank wins / gauge breakdown */}
              <div className="flex flex-col gap-[14px]">
                {/* Gauge breakdown */}
                <Card>
                  <CardHeader title="Visibility" subtitle={`Score · ${o.week_label}`} />
                  <div className="flex flex-col items-center px-4 py-3">
                    <div className="relative h-[90px] w-[90px]">
                      <svg className="-rotate-90" viewBox="0 0 36 36" width="90" height="90">
                        <circle cx="18" cy="18" r="15.9" fill="none" stroke="#DDE6D1" strokeWidth="3" />
                        <circle
                          cx="18" cy="18" r="15.9"
                          fill="none" stroke="#2E8B7F" strokeWidth="3"
                          strokeDasharray={`${(Math.min(100, gaugeScore) / 100) * 99.9} 99.9`}
                          strokeLinecap="round"
                        />
                      </svg>
                      <div className="absolute inset-0 flex flex-col items-center justify-center">
                        <span className="text-[24px] font-black text-navy">{Math.round(gaugeScore)}</span>
                        <span className="text-[10px] text-rp-tlight">/100</span>
                      </div>
                    </div>
                  </div>
                  {g ? (
                    <div className="space-y-2 px-4 pb-4">
                      {[
                        { label: "Top 3",     val: g.top3_count,       w: g.top3_pct,       c: "bg-emerald-500" },
                        { label: "Pack 4–10", val: g.page1_count,      w: g.page1_pct,      c: "bg-amber-400" },
                        { label: "Pack 11–20",val: g.pack_11_20_count, w: g.pack_11_20_pct, c: "bg-teal" },
                        { label: "Not visible",val:g.not_ranking_count,w: g.not_ranking_pct, c: "bg-red-500" },
                      ].map((p) => (
                        <div key={p.label}>
                          <div className="mb-1 flex justify-between text-[11px]">
                            <span className="text-rp-tlight">{p.label}</span>
                            <span className="font-semibold text-navy">{p.val}</span>
                          </div>
                          <div className="h-1.5 overflow-hidden rounded-full bg-rp-border">
                            <div className={`h-full rounded-full ${p.c}`} style={{ width: `${p.w}%` }} />
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : null}
                </Card>

                {/* Rank wins */}
                <Card>
                  <CardHeader title="This Week's Rank Wins" right={<Badge tone="green">Live</Badge>} />
                  {o.rank_wins.length === 0 ? (
                    <p className="px-4 py-4 text-[12px] text-rp-tlight">
                      Run a second scan to see rank-change deltas.
                    </p>
                  ) : (
                    <table className="w-full border-collapse text-[12px]">
                      <thead>
                        <tr className="border-b border-rp-border bg-rp-light text-[10px] font-bold uppercase text-rp-tlight">
                          <th className="px-3 py-2 text-left">Suburb</th>
                          <th className="px-3 py-2 text-center">Before</th>
                          <th className="px-3 py-2 text-center">Now</th>
                        </tr>
                      </thead>
                      <tbody>
                        {o.rank_wins.map((w) => (
                          <tr key={w.suburb} className="border-b border-[#F0F4F9] hover:bg-[#FAFBFD]">
                            <td className="px-3 py-2 font-semibold text-navy">{w.suburb}</td>
                            <td className="px-3 py-2 text-center text-rp-tlight">{w.before_rank ?? "—"}</td>
                            <td className="px-3 py-2 text-center font-bold text-emerald-600">{w.after_rank ?? "—"}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </Card>
              </div>
            </div>
          </>
        ) : null}
      </div>
    </>
  );
}
