import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";
import { Loader2, MapPin, Search, Trophy } from "lucide-react";

import { formatApiError } from "../api/client";
import { fetchKeywordTracker } from "../api/keywords";
import { fetchMe } from "../api/onboarding";
import { fetchSuburbRanks } from "../api/ranks";
import type { MapPackPlace, SuburbRank } from "../api/types";
import { KeywordCompetitorsPanel } from "../components/keywords/KeywordCompetitorsPanel";
import { LeafletVisibilityMap } from "../components/map/LeafletVisibilityMap";
import { TopBar } from "../components/layout/TopBar";
import { Button } from "../components/ui/Button";
import { Card, CardHeader } from "../components/ui/Card";
import { MetricCard } from "../components/ui/MetricCard";
import { getStoredScanJobId, useActiveScanPolling } from "../hooks/useScanPolling";
import { parsePrimaryKeywords, scanKeywordFromPrimary } from "../lib/primaryKeywords";
import { useResearchedKeywords } from "../lib/researchedKeywords";
import { useAuthStore } from "../stores/authStore";
import { visibilityScoreFromSuburbs } from "../lib/scoring";

function fmtK(n: number) {
  if (n >= 1000) return `${(n / 1000).toFixed(1)}K`;
  return String(Math.round(n));
}

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

type KeywordOption = {
  keyword: string;
  source: "business_setup" | "published" | "researched" | "custom";
  label: string;
  mapsPosition?: number | null;
};

function sourceBadge(source: KeywordOption["source"]) {
  if (source === "business_setup") return "Setup";
  if (source === "published") return "Published";
  if (source === "researched") return "Researched";
  return null;
}

function isOurBusiness(title: string, businessName: string, businessUrl?: string | null) {
  const t = title.trim().toLowerCase();
  const n = businessName.trim().toLowerCase();
  if (!t || !n) return false;
  if (t.includes(n) || n.includes(t)) return true;
  if (businessUrl) {
    try {
      const host = new URL(businessUrl).hostname.replace(/^www\./, "").toLowerCase();
      if (host && t.includes(host.split(".")[0] ?? "")) return true;
    } catch {
      // ignore invalid URL
    }
  }
  return false;
}

function MapsPackComparison({
  businessName,
  businessUrl,
  suburbs,
  mapCompetitors,
  trackedMapsPosition,
}: {
  businessName: string;
  businessUrl?: string | null;
  suburbs: SuburbRank[];
  mapCompetitors: MapPackPlace[];
  trackedMapsPosition: number | null;
}) {
  const suburbRanks = suburbs
    .map((s) => s.rank_position)
    .filter((r): r is number => r != null);
  const bestSuburbRank = suburbRanks.length ? Math.min(...suburbRanks) : null;
  const suburbsRanked = suburbRanks.length;

  const ourPack = mapCompetitors.find((c) =>
    isOurBusiness(c.title, businessName, businessUrl),
  );
  const ourMapsRank = bestSuburbRank ?? ourPack?.pack_rank_best ?? trackedMapsPosition;

  const competitors = mapCompetitors
    .filter((c) => !isOurBusiness(c.title, businessName, businessUrl))
    .slice(0, 8);

  return (
    <Card>
      <CardHeader
        title="Maps pack — you vs competitors"
        subtitle="Best suburb rank from heat map scan · pack listings seen across suburbs"
      />
      <div className="p-4">
        <div className="mb-3 flex flex-wrap items-center gap-3 rounded-lg border border-[#C2E0FF] bg-[#E8F4FF] px-3 py-2.5">
          <span className="text-[10px] font-bold uppercase tracking-wide text-[#0050A0]">
            Your business
          </span>
          <span className="text-[13px] font-semibold text-navy">{businessName || "Your business"}</span>
          <span className="inline-flex items-center gap-1 rounded-full bg-white px-2.5 py-0.5 text-[11px] font-bold text-[#0050A0]">
            <MapPin className="h-3 w-3" />
            {ourMapsRank != null ? `Best Maps rank #${ourMapsRank}` : "Not in top 20"}
          </span>
          {suburbsRanked > 0 && (
            <span className="text-[11px] text-[#0050A0]">
              visible in {suburbsRanked} of {suburbs.length} suburbs
            </span>
          )}
        </div>

        {competitors.length === 0 ? (
          <p className="text-[12px] text-rp-tlight">
            No competitor pack data yet — run a Maps scan for this keyword to populate the heat map.
          </p>
        ) : (
          <div className="max-h-[220px] overflow-y-auto">
            <table className="w-full border-collapse text-left">
              <thead>
                <tr className="border-b border-rp-border bg-rp-light text-[10px] font-bold uppercase tracking-wide text-rp-tlight">
                  <th className="px-3 py-2">#</th>
                  <th className="px-3 py-2">Business</th>
                  <th className="px-3 py-2 text-center">Best pack</th>
                  <th className="px-3 py-2 text-center">Suburbs seen</th>
                </tr>
              </thead>
              <tbody>
                {competitors.map((c) => (
                  <tr key={`${c.title}-${c.lat}`} className="border-b border-[#F0F4F8] hover:bg-[#FAFBFD]">
                    <td className="px-3 py-2">
                      <RankBadge rank={c.pack_rank_best ?? null} />
                    </td>
                    <td className="px-3 py-2 text-[12px] font-semibold text-navy">{c.title}</td>
                    <td className="px-3 py-2 text-center text-[11px] text-rp-tmid">
                      {c.pack_rank_best != null && c.pack_rank_worst != null && c.pack_rank_best !== c.pack_rank_worst
                        ? `#${c.pack_rank_best}–${c.pack_rank_worst}`
                        : c.pack_rank_best != null
                          ? `#${c.pack_rank_best}`
                          : "—"}
                    </td>
                    <td className="px-3 py-2 text-center text-[11px] text-rp-tlight">
                      {c.suburb_scan_count}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </Card>
  );
}

export function VisibilityMapPage() {
  const token = useAuthStore((s) => s.accessToken);
  const [searchParams] = useSearchParams();
  const [activeJobId] = useState<string | null>(() => getStoredScanJobId());
  const { isScanning, progress: scanProgress, job: scanJob } = useActiveScanPolling(activeJobId);
  const researched = useResearchedKeywords();

  const me = useQuery({
    queryKey: ["me", token],
    queryFn: fetchMe,
    enabled: Boolean(token),
  });

  const defaultKeyword = scanKeywordFromPrimary(me.data?.primary_keyword || "");
  const urlKeyword = (searchParams.get("keyword") || "").trim();
  const scanKeyword =
    (typeof scanJob?.payload?.keyword === "string" ? scanJob.payload.keyword : "") ||
    scanProgress?.keyword ||
    "";
  const [selectedKeyword, setSelectedKeyword] = useState("");
  const [customInput, setCustomInput] = useState("");

  useEffect(() => {
    if (urlKeyword) {
      setSelectedKeyword(urlKeyword);
      return;
    }
    if (isScanning && scanKeyword) {
      setSelectedKeyword(scanKeyword);
      return;
    }
    if (defaultKeyword && !selectedKeyword) {
      setSelectedKeyword(defaultKeyword);
    }
  }, [urlKeyword, isScanning, scanKeyword, defaultKeyword, selectedKeyword]);

  const activeKeyword = (selectedKeyword || customInput || defaultKeyword).trim();

  const trackerQ = useQuery({
    queryKey: ["keywords", "tracker", token],
    queryFn: fetchKeywordTracker,
    enabled: Boolean(token),
    staleTime: 60_000,
  });

  const keywordOptions = useMemo((): KeywordOption[] => {
    const seen = new Set<string>();
    const out: KeywordOption[] = [];
    const mapsByKw = new Map(
      (trackerQ.data ?? []).map((t) => [t.keyword.toLowerCase(), t.maps_position]),
    );

    const add = (keyword: string, source: KeywordOption["source"], label: string) => {
      const kw = keyword.trim();
      if (kw.length < 2) return;
      const key = kw.toLowerCase();
      if (seen.has(key)) return;
      seen.add(key);
      out.push({
        keyword: kw,
        source,
        label,
        mapsPosition: mapsByKw.get(key) ?? null,
      });
    };

    for (const kw of parsePrimaryKeywords(me.data?.primary_keyword || "")) {
      add(kw, "business_setup", "Business setup");
    }

    for (const t of trackerQ.data ?? []) {
      if (t.source === "gbp_post_published" || t.source === "suburb_page_published") {
        add(t.keyword, "published", "Published content");
      }
    }

    for (const r of researched) {
      add(r.keyword, "researched", "Keyword research");
    }

    return out;
  }, [me.data?.primary_keyword, trackerQ.data, researched]);

  const trackedForActive = (trackerQ.data ?? []).find(
    (t) => t.keyword.toLowerCase() === activeKeyword.toLowerCase(),
  );

  const q = useQuery({
    queryKey: ["ranks", "suburbs", token, activeKeyword],
    queryFn: () => fetchSuburbRanks(activeKeyword),
    enabled: Boolean(token) && Boolean(activeKeyword),
    refetchInterval: isScanning ? 5_000 : false,
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
          address: me.data.business_address ?? null,
          locationSource: me.data.business_location_source ?? null,
        }
      : null;

  const d = q.data;

  const profileRadiusKm = me.data?.search_radius_km ?? null;
  const activeScanRadiusKm =
    typeof scanJob?.payload?.radius_km === "number"
      ? scanJob.payload.radius_km
      : typeof scanJob?.payload?.radius_km === "string"
        ? Number(scanJob.payload.radius_km) || null
        : null;
  const apiRadiusKm = d?.search_radius_km ?? null;
  const displayRadiusKm = activeScanRadiusKm ?? apiRadiusKm ?? profileRadiusKm;

  const radiusLabel = displayRadiusKm
    ? displayRadiusKm <= 5
      ? `0–5 km (local block)`
      : displayRadiusKm <= 10
        ? `6–10 km (local)`
        : displayRadiusKm <= 15
          ? `11–15 km (suburb)`
          : displayRadiusKm <= 20
            ? `16–20 km (greater metro)`
            : displayRadiusKm <= 25
              ? `21–25 km (city-wide)`
              : displayRadiusKm <= 30
                ? `26–30 km (regional)`
                : `${displayRadiusKm} km (wide metro)`
    : null;

  const gridSuburbCount = d?.suburbs.length ?? 0;
  const fullGridCount = d?.grid_suburb_total ?? gridSuburbCount;
  const scanSuburbTotal = scanProgress?.suburbs_total ?? null;
  const suburbScopeLabel =
    isScanning && scanSuburbTotal != null && displayRadiusKm != null
      ? `${scanSuburbTotal} suburbs in ${displayRadiusKm} km scan`
      : gridSuburbCount > 0 && displayRadiusKm != null
        ? `${gridSuburbCount} suburbs · ${displayRadiusKm} km radius`
        : gridSuburbCount > 0
          ? `${gridSuburbCount} suburbs tracked`
          : "";

  const mapScore = d?.suburbs?.length
    ? visibilityScoreFromSuburbs(d.suburbs)
    : (d?.visibility_score ?? 0);

  const hasScanData = Boolean(d?.suburbs?.some((s) => s.rank_position != null));
  const suburbsWithPackData = Boolean(
    d?.map_competitors?.length || d?.suburbs?.some((s) => s.rank_position != null),
  );
  const scanPct =
    scanProgress && scanProgress.suburbs_total > 0
      ? Math.round((scanProgress.suburbs_checked / scanProgress.suburbs_total) * 100)
      : 0;

  const applyCustomKeyword = () => {
    const kw = customInput.trim();
    if (!kw) return;
    setSelectedKeyword(kw);
    setCustomInput("");
  };

  return (
    <>
      <TopBar
        title="Google Maps Rank Tracker"
        subtitle={
          d
            ? `"${d.keyword}" · ${d.metro_label}${suburbScopeLabel ? ` · ${suburbScopeLabel}` : ""}`
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

      <div className="page-scroll px-5 py-7">

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
            {isScanning && scanProgress ? (
              <div className="mb-[14px] flex items-center gap-3 rounded-lg border border-[#C2E0FF] bg-[#E8F4FF] px-4 py-3">
                <Loader2 className="h-4 w-4 shrink-0 animate-spin text-[#0050A0]" />
                <div className="min-w-0 flex-1">
                  <p className="text-[13px] font-semibold text-[#0050A0]">
                    Scanning &ldquo;{scanProgress.keyword || activeKeyword}&rdquo; —{" "}
                    {scanProgress.suburbs_checked} / {scanProgress.suburbs_total} suburbs ({scanPct}%)
                  </p>
                  <div className="mt-1.5 h-2 overflow-hidden rounded-full bg-white">
                    <div
                      className="h-full rounded-full bg-[#0050A0] transition-all duration-500"
                      style={{ width: `${scanPct}%` }}
                    />
                  </div>
                  <p className="mt-1 text-[11px] text-[#0050A0]/80">
                    Map refreshes every few seconds. This scan uses a{" "}
                    <strong>{displayRadiusKm ?? 25} km</strong> radius
                    {fullGridCount > gridSuburbCount
                      ? ` (${gridSuburbCount} suburbs in radius · ${fullGridCount} in full grid)`
                      : ""}
                    .
                  </p>
                </div>
              </div>
            ) : null}

            {/* Keyword picker */}
            <Card className="mb-[14px]">
              <CardHeader
                title="Keyword for heat map"
                subtitle="Default is your business setup keyword · pick a published keyword or enter a new one"
              />
              <div className="space-y-3 p-4">
                <div className="flex flex-wrap gap-1.5">
                  {keywordOptions.map((opt) => {
                    const active = opt.keyword.toLowerCase() === activeKeyword.toLowerCase();
                    const badge = sourceBadge(opt.source);
                    return (
                      <button
                        key={opt.keyword}
                        type="button"
                        onClick={() => setSelectedKeyword(opt.keyword)}
                        className={`inline-flex max-w-full items-center gap-1.5 rounded-full border px-2.5 py-1 text-left text-[11px] font-medium transition ${
                          active
                            ? "border-[#72C219] bg-[#72C219]/10 text-navy"
                            : "border-rp-border bg-white text-rp-tmid hover:border-[#72C219]/50"
                        }`}
                      >
                        {badge && (
                          <span
                            className={`shrink-0 rounded px-1 py-px text-[9px] font-bold uppercase ${
                              opt.source === "published"
                                ? "bg-emerald-100 text-emerald-700"
                                : opt.source === "business_setup"
                                  ? "bg-blue-100 text-blue-700"
                                  : "bg-amber-100 text-amber-700"
                            }`}
                          >
                            {badge}
                          </span>
                        )}
                        <span className="truncate">{opt.keyword}</span>
                        {opt.mapsPosition != null && (
                          <span className="shrink-0 text-[10px] text-rp-tlight">#{opt.mapsPosition}</span>
                        )}
                      </button>
                    );
                  })}
                </div>

                <div className="flex flex-wrap items-center gap-2">
                  <div className="relative min-w-[220px] flex-1">
                    <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-rp-tlight" />
                    <input
                      type="text"
                      value={customInput}
                      onChange={(e) => setCustomInput(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") applyCustomKeyword();
                      }}
                      placeholder="Type a keyword to rank on the map…"
                      className="w-full rounded-lg border border-rp-border py-2 pl-8 pr-3 text-[12px] text-navy outline-none focus:border-[#72C219]"
                    />
                  </div>
                  <Button variant="outline" size="sm" type="button" onClick={applyCustomKeyword}>
                    Apply keyword
                  </Button>
                  <Link
                    to={`/scan?keyword=${encodeURIComponent(activeKeyword)}`}
                    className="text-[11px] font-semibold text-[#72C219] hover:underline"
                  >
                    Run Maps scan →
                  </Link>
                </div>

                {!hasScanData && !isScanning && suburbsWithPackData && (
                  <p className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-[12px] text-slate-700">
                    Scan complete for <strong>&ldquo;{activeKeyword}&rdquo;</strong> —{" "}
                    <strong>{me.data?.business_name || "your business"}</strong> is not in the Google Maps
                    top 20 for this keyword in tracked suburbs (red dots = not visible). Competitor pins
                    on the map show who is ranking instead.
                  </p>
                )}

                {!hasScanData && !isScanning && !suburbsWithPackData && (
                  <p className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-[12px] text-amber-900">
                    No heat-map data for <strong>&ldquo;{activeKeyword}&rdquo;</strong> yet.
                    {" "}
                    <Link to={`/scan?keyword=${encodeURIComponent(activeKeyword)}`} className="font-semibold underline">
                      Run a Maps scan
                    </Link>
                    {" "}
                    to populate suburb rankings for this keyword.
                  </p>
                )}
              </div>
            </Card>

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
                  title={`Visibility Map${d.keyword ? ` – '${d.keyword}'` : ""}`}
                  subtitle={`${d.suburbs.length} suburbs${radiusLabel ? ` · ${radiusLabel}` : ""}`}
                />
                <div className="p-4">
                  <LeafletVisibilityMap
                    suburbs={d.suburbs}
                    companyPoint={companyPoint}
                    competitorPins={d.map_competitors}
                    radiusKm={displayRadiusKm}
                    radiusLabel={radiusLabel}
                    heightClass="h-[460px]"
                    scanProgress={scanProgress}
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

            {/* Competitor comparison */}
            <div className="mt-[14px] grid gap-[14px] lg:grid-cols-2">
              <MapsPackComparison
                businessName={me.data?.business_name || "Your business"}
                businessUrl={me.data?.business_url}
                suburbs={d.suburbs}
                mapCompetitors={d.map_competitors ?? []}
                trackedMapsPosition={trackedForActive?.maps_position ?? null}
              />
              <Card>
                <div className="p-4">
                  <p className="mb-2 flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-wide text-[#9A5B00]">
                    <Trophy className="h-3 w-3" />
                    Organic Google rankings
                  </p>
                  <KeywordCompetitorsPanel keyword={activeKeyword} />
                  {trackedForActive && (
                    <p className="mt-2 text-[11px] text-rp-tlight">
                      Your tracked rank: organic{" "}
                      {trackedForActive.organic_position != null
                        ? `#${trackedForActive.organic_position}`
                        : "—"}
                      {" · "}
                      Maps{" "}
                      {trackedForActive.maps_position != null
                        ? `#${trackedForActive.maps_position}`
                        : "—"}
                    </p>
                  )}
                </div>
              </Card>
            </div>
          </>
        ) : null}
      </div>
    </>
  );
}
