import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { formatApiError } from "../api/client";
import { fetchDashboardOverview } from "../api/overview";
import { fetchMe, patchMe } from "../api/onboarding";
import { fetchOpportunities } from "../api/opportunities";
import { fetchSuburbRanks } from "../api/ranks";
import { enqueueMapsScan } from "../api/scans";
import { LeafletVisibilityMap } from "../components/map/LeafletVisibilityMap";
import { TopBar } from "../components/layout/TopBar";
import { MetricCard } from "../components/ui/MetricCard";
import { Badge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { Card, CardHeader } from "../components/ui/Card";
import { useAuthStore } from "../stores/authStore";
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
          <circle cx="35" cy="35" r={r} fill="none" stroke="#DDE6D1" strokeWidth="6" />
          <circle
            cx="35" cy="35" r={r}
            fill="none"
            stroke="#2E8B7F"
            strokeWidth="6"
            strokeDasharray={`${(pct / 100) * circ} ${circ}`}
            strokeLinecap="round"
            transform="rotate(-90 35 35)"
          />
        </svg>
        <div className="absolute text-[16px] font-black text-navy">{Math.round(pct)}</div>
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
        primary_keyword:  kwInput.trim() || undefined,
      });
      const job = await enqueueMapsScan({
        keyword: profile.primary_keyword || null,
        radius_km: profile.search_radius_km ?? null,
      });
      return { profile, job };
    },
    onSuccess: (data) => {
      setUrlInput(data.profile.business_url || "");
      setKwInput(data.profile.primary_keyword || "");
      void qc.invalidateQueries({ queryKey: ["me"] });
      void qc.invalidateQueries({ queryKey: ["dashboard"] });
      void qc.invalidateQueries({ queryKey: ["ranks"] });
    },
  });

  const scan = useMutation({
    mutationFn: () =>
      enqueueMapsScan({
        keyword: kwInput.trim() || null,
        radius_km: me.data?.search_radius_km ?? null,
      }),
    onSuccess: () => {
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
          locationSource: me.data.business_location_source ?? null,
        }
      : null;

  const packPinCount = ranks.data?.map_competitors?.length ?? 0;
  const heatMapSubtitle = o
    ? `${o.metro_label} · "${o.keyword}"${packPinCount > 0 ? ` · ${packPinCount} competitor pin${packPinCount !== 1 ? "s" : ""} (Maps SERP)` : ""}`
    : "";

  const nearMiss = (opportunities.data?.items ?? [])
    .filter((op) => op.rank_position != null && op.rank_position >= 11 && op.rank_position <= 20)
    .sort((a, b) => (b.population ?? 0) - (a.population ?? 0))
    .slice(0, 3);

  /** Only when the saved profile has no website — not when /me failed or is still loading. */
  const showProfileQuickEdit =
    me.isSuccess && (!me.data.business_url || me.data.business_url.trim().length < 4);

  /* ── top-bar subtitle ──────────────────────────────────────── */
  const topBarSub = o
    ? `${o.metro_label} · "${o.keyword}" · ${st?.suburbs_total ?? 0} suburbs tracked`
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
              title="Queues a Google Maps local-pack check for each suburb via DataForSEO (minutes, not seconds). Updates ranks and per-state Google Ads search volumes stored on your grid."
              disabled={!token || scan.isPending || saveAndScan.isPending}
              onClick={() => void scan.mutate()}
            >
              {scan.isPending ? "Scanning…" : "Run Scan Now"}
            </Button>
          </>
        }
      />

      <div className="flex-1 overflow-y-auto bg-rp-light px-5 py-[18px]">

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
        {scan.isSuccess && !saveAndScan.isSuccess ? (
          <div className="mb-4 rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-2.5 text-xs text-emerald-800">
            Scan queued (job {scan.data.job_id}). The background worker picks up jobs about every 10 seconds; this page
            will update when ranks are written. If nothing changes after several minutes, check the API logs for
            DataForSEO errors.
          </div>
        ) : null}

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
                  Keyword
                </label>
                <input
                  type="text"
                  placeholder="e.g. plumber melbourne"
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
              <Link to="/onboarding" className="font-semibold text-[#72C219] hover:underline">
                onboarding
              </Link>.
            </p>
          </div>
        ) : null}

        {o ? (
          <>
            {/* ── 4 metric cards ─────────────────────────────────── */}
            <div className="mb-[14px] grid grid-cols-2 gap-3 xl:grid-cols-4">
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

              {/* 4. Monthly Searches */}
              <MetricCard
                label="Monthly Searches"
                value={fmtK(st?.monthly_searches ?? 0)}
                delta={st?.monthly_volume_note ?? "Run a Maps scan to load DataForSEO keyword volumes"}
              />
            </div>

            <div className="mb-[14px] rounded-[10px] border border-rp-border bg-white p-4">
              <div className="mb-2">
                <h3 className="text-[13px] font-bold text-navy">Business Details (Google)</h3>
              </div>
              <div className="grid gap-3 md:grid-cols-3">
                <div>
                  <div className="text-[10px] font-semibold uppercase tracking-wide text-rp-tlight">Company</div>
                  <div className="mt-1 text-[12px] font-semibold text-navy">
                    {o.business_profile?.name || me.data?.business_name || "Not found"}
                  </div>
                </div>
                <div>
                  <div className="text-[10px] font-semibold uppercase tracking-wide text-rp-tlight">Address</div>
                  <div className="mt-1 text-[12px] font-semibold text-navy">
                    {o.business_profile?.address || me.data?.business_address || "Not found"}
                  </div>
                </div>
                <div>
                  <div className="text-[10px] font-semibold uppercase tracking-wide text-rp-tlight">Phone</div>
                  <div className="mt-1 text-[12px] font-semibold text-navy">
                    {o.business_profile?.phone || me.data?.business_phone || "Not found"}
                  </div>
                </div>
              </div>
              {o.business_profile?.maps_url ? (
                <div className="mt-3 text-[12px]">
                  <a
                    href={o.business_profile.maps_url}
                    target="_blank"
                    rel="noreferrer"
                    className="font-semibold text-[#72C219] hover:underline"
                  >
                    Open Google Maps Location ↗
                  </a>
                </div>
              ) : null}
            </div>

            {/* ── 2-col: Actions Taken + Upcoming Actions ─────────── */}
            <div className="mb-[14px] grid gap-[14px] lg:grid-cols-2">
              {/* Actions Taken This Week */}
              <div className="overflow-hidden rounded-[10px] border border-rp-border bg-white">
                <div className="flex items-center gap-2 border-b border-rp-border px-4 py-3">
                  <h3 className="text-[13px] font-bold text-navy">Actions Taken This Week</h3>
                </div>
                {o.activity.length === 0 ? (
                  <div className="px-4 py-6 text-center text-[12px] text-rp-tlight">
                    No activity logged yet — run your first scan.
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
              </div>

              {/* Upcoming Actions (recommendations) */}
              <div className="overflow-hidden rounded-[10px] border border-rp-border bg-white">
                <div className="flex items-center gap-2 border-b border-rp-border px-4 py-3">
                  <h3 className="text-[13px] font-bold text-navy">⏰ Recommended Actions</h3>
                </div>
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
              </div>
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
                  title="Suburb Heat Map"
                  subtitle={heatMapSubtitle}
                  right={
                    <div className="flex items-center gap-2">
                      {g ? (
                        <div className="hidden flex-wrap items-center gap-x-2 gap-y-1 sm:flex">
                          {[
                            { label: "Top 3", c: "bg-emerald-500" },
                            { label: "Pack 4–10", c: "bg-amber-400" },
                            { label: "11–20", c: "bg-teal" },
                            { label: "NR", c: "bg-red-500" },
                          ].map((x) => (
                            <span key={x.label} className="flex items-center gap-1 text-[10px] text-rp-tlight">
                              <span className={`inline-block h-2.5 w-2.5 rounded-sm ${x.c}`} />
                              {x.label}
                            </span>
                          ))}
                          <span className="text-[10px] text-rp-tlight">· red marker = pack competitor</span>
                          <span className="text-[10px] text-rp-tlight">· blue marker = your business</span>
                        </div>
                      ) : null}
                      <Link to="/map">
                        <Button variant="outline" size="sm" type="button">
                          Full Map →
                        </Button>
                      </Link>
                    </div>
                  }
                />
                <div className="p-4">
                  <LeafletVisibilityMap
                    suburbs={ranks.data?.suburbs ?? []}
                    companyPoint={companyMapPoint}
                    competitorPins={ranks.data?.map_competitors ?? []}
                    heightClass="h-[300px]"
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
