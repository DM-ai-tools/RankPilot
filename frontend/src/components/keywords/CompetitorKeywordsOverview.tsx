import { useQuery } from "@tanstack/react-query";
import { Check, Globe, Plus, Search, X } from "lucide-react";

import { formatApiError } from "../../api/client";
import {
  fetchCompetitorSiteKeywords,
  type SiteKeywordItem,
  type SiteKeywordsResponse,
} from "../../api/keywords";
import {
  addResearchedKeyword,
  removeResearchedKeyword,
  useResearchedKeywords,
} from "../../lib/researchedKeywords";
import { useSessionState } from "../../lib/useSessionState";
import { Button } from "../ui/Button";
import { Card } from "../ui/Card";
import { KeywordDataSourceBadge } from "./KeywordDataSourceBadge";

const COUNTRY_OPTIONS = [
  { code: "au", label: "Australia" },
  { code: "nz", label: "New Zealand" },
  { code: "us", label: "United States" },
  { code: "gb", label: "United Kingdom" },
];

function kdTone(kd: number | null): string {
  if (kd == null) return "text-rp-tlight";
  if (kd <= 10) return "text-[#22C55E]";
  if (kd <= 30) return "text-[#72C219]";
  if (kd <= 50) return "text-amber-600";
  return "text-red-600";
}

function positionTone(pos: number | null): string {
  if (pos == null) return "text-rp-tlight";
  if (pos <= 3) return "text-[#137333]";
  if (pos <= 10) return "text-[#72C219]";
  return "text-rp-tmid";
}

export function CompetitorKeywordsOverview() {
  const [input, setInput] = useSessionState("rp.ahrefsSite.input", "");
  const [activeTarget, setActiveTarget] = useSessionState("rp.ahrefsSite.target", "");
  const [country, setCountry] = useSessionState("rp.ahrefsSite.country", "au");
  const researched = useResearchedKeywords();
  const savedKeywords = new Set(researched.map((r) => r.keyword.toLowerCase()));

  const siteQ = useQuery({
    queryKey: ["keywords", "site-keywords", activeTarget, country],
    queryFn: () => fetchCompetitorSiteKeywords(activeTarget, country),
    enabled: Boolean(activeTarget.trim()),
    staleTime: 30 * 60_000,
    gcTime: 60 * 60_000,
    retry: 1,
  });

  const data: SiteKeywordsResponse | undefined = siteQ.data;
  const loading = siteQ.isFetching;
  const keywords = data?.keywords ?? [];

  function handleAnalyze(e: React.FormEvent) {
    e.preventDefault();
    const t = input.trim();
    if (!t) return;
    setActiveTarget(t);
  }

  const toggleSave = (item: SiteKeywordItem) => {
    if (savedKeywords.has(item.keyword.toLowerCase())) {
      removeResearchedKeyword(item.keyword);
    } else {
      addResearchedKeyword(item.keyword, item.volume);
    }
  };

  const addTopTen = () => {
    for (const item of keywords.slice(0, 10)) {
      addResearchedKeyword(item.keyword, item.volume);
    }
  };

  return (
    <div className="space-y-4">
      <Card className="p-4">
        <form onSubmit={handleAnalyze} className="flex flex-wrap items-end gap-3">
          <div className="min-w-[260px] flex-1">
            <label className="mb-1 block text-[10px] font-bold uppercase tracking-wide text-rp-tlight">
              Competitor website
            </label>
            <div className="relative">
              <Globe className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-rp-tlight" />
              <input
                className="w-full rounded-lg border border-rp-border bg-white py-2.5 pl-9 pr-3 text-[14px] font-semibold text-navy outline-none ring-[#72C219]/30 focus:ring-2"
                placeholder="e.g. competitor.com.au or https://www.competitor.com.au"
                value={input}
                onChange={(e) => setInput(e.target.value)}
              />
            </div>
          </div>
          <div>
            <label className="mb-1 block text-[10px] font-bold uppercase tracking-wide text-rp-tlight">
              Country
            </label>
            <select
              className="rounded-lg border border-rp-border bg-white px-3 py-2.5 text-[12px] text-navy"
              value={country}
              onChange={(e) => setCountry(e.target.value)}
            >
              {COUNTRY_OPTIONS.map((c) => (
                <option key={c.code} value={c.code}>
                  {c.label}
                </option>
              ))}
            </select>
          </div>
          <Button type="submit" disabled={loading || !input.trim()}>
            <Search className="h-4 w-4" />
            {loading ? "Loading…" : "Analyze"}
          </Button>
          {data?.source ? <KeywordDataSourceBadge source={data.source} /> : null}
        </form>
        <p className="mt-2 text-[11px] text-rp-tlight">
          Paste a competitor's website to see the organic keywords they rank for on Google (via Ahrefs).
          Click + on a keyword to use it in your Posts &amp; Content and Description generation.
        </p>
      </Card>

      {researched.length > 0 ? (
        <Card className="p-4">
          <div className="mb-2 flex items-center justify-between gap-2">
            <span className="text-[11px] font-bold uppercase tracking-wide text-rp-tlight">
              Saved research keywords ({researched.length})
            </span>
            <span className="text-[10px] text-rp-tlight">
              Available in the Posts &amp; Content and Description keyword pickers
            </span>
          </div>
          <div className="flex flex-wrap gap-1.5">
            {researched.map((r) => (
              <span
                key={r.keyword}
                className="inline-flex items-center gap-1 rounded-full border border-[#CEEAD6] bg-[#F6FFF8] px-2 py-0.5 text-[11px] font-medium text-[#137333]"
              >
                {r.keyword}
                <button
                  type="button"
                  title={`Remove "${r.keyword}"`}
                  onClick={() => removeResearchedKeyword(r.keyword)}
                  className="text-rp-tlight transition hover:text-red-600"
                >
                  <X className="h-3 w-3" />
                </button>
              </span>
            ))}
          </div>
        </Card>
      ) : null}

      {siteQ.error ? <p className="text-sm text-red-600">{formatApiError(siteQ.error)}</p> : null}
      {data?.message ? (
        <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-[12px] text-amber-900">
          {data.message}
        </div>
      ) : null}

      {data && keywords.length > 0 ? (
        <Card>
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-rp-border px-4 py-3">
            <div>
              <h2 className="text-[15px] font-extrabold text-navy">
                Organic keywords: <span className="text-rp-tmid">{data.target}</span>
              </h2>
              <p className="text-[11px] text-rp-tlight">
                {keywords.length} keywords · {data.country_label} ({data.country}) · via Ahrefs
                {data.from_cache ? " · cached" : ""}
              </p>
            </div>
            <Button type="button" size="sm" variant="outline" onClick={addTopTen}>
              + Save top 10 keywords
            </Button>
          </div>
          <div className="max-h-[520px] overflow-y-auto">
            <table className="w-full text-left">
              <thead className="sticky top-0 bg-rp-light">
                <tr className="text-[10px] font-bold uppercase tracking-wide text-rp-tlight">
                  <th className="px-4 py-2">Save</th>
                  <th className="px-2 py-2">Keyword</th>
                  <th className="px-2 py-2 text-right">Volume</th>
                  <th className="px-2 py-2 text-right">KD</th>
                  <th className="px-2 py-2 text-right">Position</th>
                  <th className="px-4 py-2 text-right">Traffic</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-rp-border">
                {keywords.map((item) => {
                  const saved = savedKeywords.has(item.keyword.toLowerCase());
                  return (
                    <tr key={item.keyword} className="hover:bg-[#F8FAFC]">
                      <td className="px-4 py-2">
                        <button
                          type="button"
                          title={
                            saved
                              ? "Saved — remove from Posts & Description keyword pickers"
                              : "Save to Posts & Description keyword pickers"
                          }
                          onClick={() => toggleSave(item)}
                          className={`flex h-5 w-5 items-center justify-center rounded border transition ${
                            saved
                              ? "border-[#34A853] bg-[#34A853] text-white"
                              : "border-rp-border bg-white text-rp-tlight hover:border-[#34A853] hover:text-[#34A853]"
                          }`}
                        >
                          {saved ? <Check className="h-3.5 w-3.5" /> : <Plus className="h-3.5 w-3.5" />}
                        </button>
                      </td>
                      <td className="max-w-[320px] px-2 py-2">
                        <span className="block truncate text-[12px] font-medium text-navy" title={item.keyword}>
                          {item.keyword}
                        </span>
                        {item.ranking_url ? (
                          <span className="block max-w-[320px] truncate text-[10px] text-rp-tlight" title={item.ranking_url}>
                            {item.ranking_url}
                          </span>
                        ) : null}
                      </td>
                      <td className="px-2 py-2 text-right text-[12px] font-semibold text-navy">
                        {item.volume_display}
                      </td>
                      <td className={`px-2 py-2 text-right text-[12px] font-semibold ${kdTone(item.difficulty)}`}>
                        {item.difficulty ?? "—"}
                      </td>
                      <td className={`px-2 py-2 text-right text-[12px] font-bold ${positionTone(item.best_position)}`}>
                        {item.best_position ? `#${item.best_position}` : "—"}
                      </td>
                      <td className="px-4 py-2 text-right text-[12px] text-rp-tmid">
                        {item.traffic != null ? item.traffic.toLocaleString() : "—"}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </Card>
      ) : null}

      {!loading && activeTarget && data && keywords.length === 0 && !data.message ? (
        <p className="text-sm text-rp-tlight">No organic keywords found for this website.</p>
      ) : null}
    </div>
  );
}
