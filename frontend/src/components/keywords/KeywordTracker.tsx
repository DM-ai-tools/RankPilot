/**
 * KeywordTracker — weekly rank monitoring for GBP post keywords.
 *
 * Shows a table of tracked keywords with:
 *  - Current Google organic rank
 *  - Current Google Maps pack rank
 *  - Search volume
 *  - Week-on-week change indicator
 *  - 12-week sparkline trend
 *
 * Users can also manually add/remove keywords and trigger a live re-check.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Activity, ArrowDown, ArrowUp, Minus, Plus, RefreshCw, Trash2, TrendingUp } from "lucide-react";
import { useState } from "react";

import { formatApiError } from "../../api/client";
import {
  addTrackedKeyword,
  fetchKeywordTracker,
  removeTrackedKeyword,
  triggerKeywordTrackerSync,
  type TrackedKeyword,
} from "../../api/keywords";

// ── Tiny sparkline SVG ────────────────────────────────────────────────────────

function Sparkline({ data, color = "#6366f1" }: { data: (number | null)[]; color?: string }) {
  const vals = data.filter((v): v is number => v !== null);
  if (vals.length < 2) {
    return <span className="text-xs text-gray-400 italic">—</span>;
  }
  // Invert: lower rank = better = higher on chart
  const min = Math.min(...vals);
  const max = Math.max(...vals);
  const range = max - min || 1;
  const W = 80;
  const H = 28;
  const step = W / (vals.length - 1);

  // points: x left-to-right = oldest-to-newest (data is newest-first, so reverse)
  const reversed = [...vals].reverse();
  const pts = reversed.map((v, i) => {
    const x = i * step;
    const y = H - ((v - min) / range) * (H - 4) - 2;
    return `${x},${y}`;
  });
  const poly = pts.join(" ");

  return (
    <svg width={W} height={H} className="overflow-visible">
      <polyline
        points={poly}
        fill="none"
        stroke={color}
        strokeWidth={1.8}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      {/* mark latest (last) point */}
      {pts.length > 0 && (
        <circle
          cx={parseFloat(pts[pts.length - 1].split(",")[0])}
          cy={parseFloat(pts[pts.length - 1].split(",")[1])}
          r={2.5}
          fill={color}
        />
      )}
    </svg>
  );
}

// ── Change badge ──────────────────────────────────────────────────────────────

function ChangeBadge({ change }: { change: number | null }) {
  if (change === null) return <span className="text-gray-400 text-xs">—</span>;
  if (change === 0)
    return (
      <span className="inline-flex items-center gap-0.5 text-xs text-gray-500">
        <Minus className="w-3 h-3" /> 0
      </span>
    );
  if (change > 0)
    return (
      <span className="inline-flex items-center gap-0.5 text-xs font-medium text-emerald-600">
        <ArrowUp className="w-3 h-3" /> +{change}
      </span>
    );
  return (
    <span className="inline-flex items-center gap-0.5 text-xs font-medium text-red-500">
      <ArrowDown className="w-3 h-3" /> {change}
    </span>
  );
}

// ── Rank cell ─────────────────────────────────────────────────────────────────

function RankCell({ pos, emptyLabel = "—" }: { pos: number | null; emptyLabel?: string }) {
  if (pos === null) return <span className="text-gray-400 text-sm">{emptyLabel}</span>;
  const color =
    pos <= 3
      ? "bg-emerald-100 text-emerald-700"
      : pos <= 10
        ? "bg-blue-100 text-blue-700"
        : pos <= 20
          ? "bg-amber-100 text-amber-700"
          : "bg-gray-100 text-gray-600";
  return (
    <span className={`inline-block px-1.5 py-0.5 rounded text-xs font-semibold ${color}`}>
      #{pos}
    </span>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

export function KeywordTracker() {
  const qc = useQueryClient();
  const [newKw, setNewKw] = useState("");
  const [adding, setAdding] = useState(false);
  const [expandedKw, setExpandedKw] = useState<string | null>(null);

  const {
    data: keywords = [],
    isLoading,
    error,
  } = useQuery({
    queryKey: ["keyword-tracker"],
    queryFn: fetchKeywordTracker,
    staleTime: 5 * 60 * 1000,
  });

  const syncMutation = useMutation({
    mutationFn: (force: boolean) => triggerKeywordTrackerSync(force),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["keyword-tracker"] }),
  });

  const addMutation = useMutation({
    mutationFn: (kw: string) => addTrackedKeyword(kw),
    onSuccess: () => {
      setNewKw("");
      setAdding(false);
      qc.invalidateQueries({ queryKey: ["keyword-tracker"] });
    },
  });

  const removeMutation = useMutation({
    mutationFn: (kw: string) => removeTrackedKeyword(kw),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["keyword-tracker"] }),
  });

  const handleSync = (force: boolean) => syncMutation.mutate(force);

  const publishedKeywords = keywords.filter((k) => k.source === "gbp_post_published");
  const otherKeywords = keywords.filter((k) => k.source !== "gbp_post_published");

  const sourceBadge = (source: string) => {
    if (source === "gbp_post_published") {
      return (
        <span className="inline-block rounded px-1.5 py-0.5 text-xs font-semibold bg-emerald-100 text-emerald-800 ring-1 ring-emerald-300/70">
          Live on GBP
        </span>
      );
    }
    if (source === "gbp_post") {
      return (
        <span className="inline-block rounded px-1.5 py-0.5 text-xs bg-indigo-100 text-indigo-700">
          GBP draft
        </span>
      );
    }
    return (
      <span className="inline-block rounded px-1.5 py-0.5 text-xs bg-gray-100 text-gray-600">
        Manual
      </span>
    );
  };

  const renderKeywordRows = (items: TrackedKeyword[]) =>
    items.map((kw) => {
      const isExpanded = expandedKw === kw.keyword;
      const organicHistory = kw.history.map((h) => h.organic_position);
      const mapsHistory = kw.history.map((h) => h.maps_position);
      const isPublished = kw.source === "gbp_post_published";

      return (
        <>
          <tr
            key={kw.keyword}
            className={`hover:bg-gray-50 cursor-pointer ${
              isPublished ? "bg-emerald-50/40" : ""
            }`}
            onClick={() => setExpandedKw(isExpanded ? null : kw.keyword)}
          >
            <td className="px-4 py-2.5 font-medium text-gray-900 max-w-[220px]">
              <span className="truncate block">{kw.keyword}</span>
              {kw.rank_note && (
                <span className="mt-0.5 block text-[10px] font-normal leading-snug text-amber-700">
                  {kw.rank_note}
                </span>
              )}
            </td>
            <td className="px-4 py-2.5 text-center">
              <RankCell
                pos={kw.organic_position}
                emptyLabel={kw.search_volume != null && kw.last_checked ? "N/R" : "—"}
              />
            </td>
            <td className="px-4 py-2.5 text-center">
              <ChangeBadge change={kw.organic_change} />
            </td>
            <td className="px-4 py-2.5 text-center">
              <RankCell
                pos={kw.maps_position}
                emptyLabel={kw.last_checked ? "N/R" : "—"}
              />
            </td>
            <td className="px-4 py-2.5 text-center">
              <ChangeBadge change={kw.maps_change} />
            </td>
            <td className="px-4 py-2.5 text-center text-gray-600">
              {kw.search_volume != null
                ? kw.search_volume >= 1000
                  ? `${(kw.search_volume / 1000).toFixed(1)}k`
                  : String(kw.search_volume)
                : "—"}
            </td>
            <td className="px-4 py-2.5 text-center">
              <Sparkline data={organicHistory} color={isPublished ? "#059669" : "#6366f1"} />
            </td>
            <td className="px-4 py-2.5 text-center">{sourceBadge(kw.source)}</td>
            <td className="px-4 py-2.5 text-right text-gray-400 text-xs whitespace-nowrap">
              {lastChecked(kw)}
            </td>
            <td className="px-4 py-2.5 text-right">
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  removeMutation.mutate(kw.keyword);
                }}
                disabled={removeMutation.isPending}
                className="p-1 text-gray-400 hover:text-red-500 rounded transition-colors"
                title="Stop tracking"
              >
                <Trash2 className="w-3.5 h-3.5" />
              </button>
            </td>
          </tr>

          {isExpanded && (
            <tr key={`${kw.keyword}-exp`} className="bg-indigo-50/40">
              <td colSpan={10} className="px-6 py-4">
                <div className="grid grid-cols-2 gap-6">
                  <div>
                    <p className="text-xs font-semibold text-gray-700 mb-2 uppercase tracking-wide">
                      Organic position — weekly history
                    </p>
                    {organicHistory.some((v) => v !== null) ? (
                      <table className="text-xs w-full">
                        <thead>
                          <tr className="text-gray-500">
                            <th className="text-left pb-1">Week</th>
                            <th className="text-center pb-1">Organic</th>
                            <th className="text-center pb-1">Maps</th>
                          </tr>
                        </thead>
                        <tbody>
                          {kw.history.map((h) => (
                            <tr key={h.week} className="border-t border-indigo-100">
                              <td className="py-0.5 text-gray-500">{h.week}</td>
                              <td className="py-0.5 text-center">
                                <RankCell pos={h.organic_position} />
                              </td>
                              <td className="py-0.5 text-center">
                                <RankCell pos={h.maps_position} />
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    ) : (
                      <p className="text-xs text-gray-400 italic">
                        No history yet — sync to start tracking.
                      </p>
                    )}
                  </div>

                  <div>
                    <p className="text-xs font-semibold text-gray-700 mb-2 uppercase tracking-wide">
                      Maps position trend
                    </p>
                    <div className="flex items-end gap-4">
                      <Sparkline data={mapsHistory} color="#10b981" />
                      <div className="space-y-1 text-xs text-gray-600">
                        <div>
                          <span className="text-gray-400">Current organic:</span>{" "}
                          <strong>
                            {kw.organic_position !== null ? `#${kw.organic_position}` : "—"}
                          </strong>
                        </div>
                        <div>
                          <span className="text-gray-400">Current Maps:</span>{" "}
                          <strong>
                            {kw.maps_position !== null ? `#${kw.maps_position}` : "—"}
                          </strong>
                        </div>
                        <div>
                          <span className="text-gray-400">Volume:</span>{" "}
                          <strong>
                            {kw.search_volume !== null ? kw.search_volume.toLocaleString() : "—"}
                            /mo
                          </strong>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </td>
            </tr>
          )}
        </>
      );
    });

  const handleAdd = () => {
    const kw = newKw.trim();
    if (!kw) return;
    addMutation.mutate(kw);
  };

  const lastChecked = (kw: TrackedKeyword) => {
    if (!kw.last_checked) return "never";
    const d = new Date(kw.last_checked);
    const diff = Date.now() - d.getTime();
    const hrs = Math.round(diff / 3_600_000);
    if (hrs < 1) return "just now";
    if (hrs < 24) return `${hrs}h ago`;
    const days = Math.round(hrs / 24);
    return `${days}d ago`;
  };

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-2">
          <TrendingUp className="w-5 h-5 text-indigo-500" />
          <div>
            <h2 className="text-base font-semibold text-gray-900">Keyword Rank Tracker</h2>
            <p className="text-xs text-gray-500">
              Keywords from your published GBP posts are tracked here — check organic &amp; Maps rank weekly
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => handleSync(false)}
            disabled={syncMutation.isPending}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-700 disabled:opacity-50 transition-colors"
          >
            <RefreshCw className={`w-4 h-4 ${syncMutation.isPending ? "animate-spin" : ""}`} />
            {syncMutation.isPending ? "Checking…" : "Sync & Check ranks"}
          </button>
          <button
            onClick={() => handleSync(true)}
            disabled={syncMutation.isPending}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md border border-gray-300 text-gray-700 text-sm hover:bg-gray-50 disabled:opacity-50 transition-colors"
            title="Force re-check even if already checked today"
          >
            Force refresh
          </button>
        </div>
      </div>

      {syncMutation.isError && (
        <p className="text-sm text-red-600">{formatApiError(syncMutation.error)}</p>
      )}
      {syncMutation.isSuccess && (
        <p className="text-sm text-emerald-600">
          {syncMutation.data.added_keywords > 0
            ? `✓ Added ${syncMutation.data.added_keywords} new keyword(s) from your GBP posts. `
            : ""}
          Checked {syncMutation.data.checked} keyword(s).
        </p>
      )}

      {/* Add keyword */}
      <div className="flex items-center gap-2">
        {adding ? (
          <>
            <input
              autoFocus
              value={newKw}
              onChange={(e) => setNewKw(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") handleAdd();
                if (e.key === "Escape") {
                  setAdding(false);
                  setNewKw("");
                }
              }}
              placeholder="e.g. marketing agency sydney"
              className="flex-1 max-w-sm border border-gray-300 rounded-md px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />
            <button
              onClick={handleAdd}
              disabled={addMutation.isPending || !newKw.trim()}
              className="px-3 py-1.5 rounded-md bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-700 disabled:opacity-50"
            >
              {addMutation.isPending ? "Adding…" : "Add"}
            </button>
            <button
              onClick={() => {
                setAdding(false);
                setNewKw("");
              }}
              className="px-3 py-1.5 text-sm text-gray-500 hover:text-gray-700"
            >
              Cancel
            </button>
          </>
        ) : (
          <button
            onClick={() => setAdding(true)}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md border border-dashed border-gray-300 text-gray-600 text-sm hover:border-indigo-400 hover:text-indigo-600 transition-colors"
          >
            <Plus className="w-4 h-4" /> Add keyword manually
          </button>
        )}
      </div>

      {/* Table */}
      {isLoading ? (
        <div className="flex items-center gap-2 py-8 justify-center text-gray-500 text-sm">
          <Activity className="w-4 h-4 animate-pulse" /> Loading tracked keywords…
        </div>
      ) : error ? (
        <p className="text-sm text-red-600">{formatApiError(error)}</p>
      ) : keywords.length === 0 ? (
        <div className="py-10 text-center text-gray-500 text-sm space-y-2">
          <p className="font-medium">No keywords tracked yet</p>
          <p>
            Click <strong>Sync &amp; Check ranks</strong> to pull keywords from your published GBP posts
            (e.g. <em>SEO services Melbourne</em>), or add one manually above.
          </p>
        </div>
      ) : (
        <div className="space-y-4">
          {publishedKeywords.length > 0 && (
            <div className="overflow-x-auto rounded-xl border border-emerald-200">
              <div className="border-b border-emerald-200 bg-emerald-50 px-4 py-2 text-xs font-semibold uppercase tracking-wide text-emerald-800">
                Published GBP keywords ({publishedKeywords.length})
              </div>
              <table className="min-w-full text-sm">
                <thead className="bg-gray-50 border-b border-gray-200">
                  <tr>
                    <th className="px-4 py-2.5 text-left font-medium text-gray-600 w-48">Keyword</th>
                    <th className="px-4 py-2.5 text-center font-medium text-gray-600">Organic rank</th>
                    <th className="px-4 py-2.5 text-center font-medium text-gray-600">Δ week</th>
                    <th className="px-4 py-2.5 text-center font-medium text-gray-600">Maps rank</th>
                    <th className="px-4 py-2.5 text-center font-medium text-gray-600">Δ week</th>
                    <th className="px-4 py-2.5 text-center font-medium text-gray-600">Volume</th>
                    <th className="px-4 py-2.5 text-center font-medium text-gray-600">Organic trend (12w)</th>
                    <th className="px-4 py-2.5 text-center font-medium text-gray-600">Source</th>
                    <th className="px-4 py-2.5 text-right font-medium text-gray-600">Last checked</th>
                    <th className="px-4 py-2.5" />
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">{renderKeywordRows(publishedKeywords)}</tbody>
              </table>
            </div>
          )}

          {otherKeywords.length > 0 && (
            <div className="overflow-x-auto rounded-xl border border-gray-200">
              {publishedKeywords.length > 0 && (
                <div className="border-b border-gray-200 bg-gray-50 px-4 py-2 text-xs font-semibold uppercase tracking-wide text-gray-600">
                  Other tracked keywords ({otherKeywords.length})
                </div>
              )}
              <table className="min-w-full text-sm">
                <thead className="bg-gray-50 border-b border-gray-200">
                  <tr>
                    <th className="px-4 py-2.5 text-left font-medium text-gray-600 w-48">Keyword</th>
                    <th className="px-4 py-2.5 text-center font-medium text-gray-600">Organic rank</th>
                    <th className="px-4 py-2.5 text-center font-medium text-gray-600">Δ week</th>
                    <th className="px-4 py-2.5 text-center font-medium text-gray-600">Maps rank</th>
                    <th className="px-4 py-2.5 text-center font-medium text-gray-600">Δ week</th>
                    <th className="px-4 py-2.5 text-center font-medium text-gray-600">Volume</th>
                    <th className="px-4 py-2.5 text-center font-medium text-gray-600">Organic trend (12w)</th>
                    <th className="px-4 py-2.5 text-center font-medium text-gray-600">Source</th>
                    <th className="px-4 py-2.5 text-right font-medium text-gray-600">Last checked</th>
                    <th className="px-4 py-2.5" />
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">{renderKeywordRows(otherKeywords)}</tbody>
              </table>
            </div>
          )}
        </div>
      )}

      <p className="text-xs text-gray-400">
        Organic rank = your website position (Ahrefs) · Maps rank = your GBP in Google Maps (DataForSEO live
        check at your primary suburb) · Publishing a GBP post auto-tracks its keyword and checks ranks
      </p>
    </div>
  );
}
