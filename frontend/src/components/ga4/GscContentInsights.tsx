import { useMemo, useState } from "react";
import { ArrowDown, ArrowUp, Copy, ExternalLink } from "lucide-react";

import type { GscContentInsightRow, GscContentInsightsReport } from "../../api/ga4";

type InsightTab = "top" | "trending_up" | "trending_down";

const TABS: { id: InsightTab; label: string }[] = [
  { id: "top", label: "Top" },
  { id: "trending_up", label: "Trending up" },
  { id: "trending_down", label: "Trending down" },
];

function faviconUrl(pageUrl: string): string {
  try {
    const host = new URL(pageUrl).hostname;
    return `https://www.google.com/s2/favicons?domain=${encodeURIComponent(host)}&sz=64`;
  } catch {
    return "";
  }
}

function shortUrl(pageUrl: string): string {
  try {
    const u = new URL(pageUrl);
    const path = u.pathname === "/" ? "" : u.pathname;
    return `${u.hostname}${path}`;
  } catch {
    return pageUrl;
  }
}

function TrendBadge({ row }: { row: GscContentInsightRow }) {
  if (row.prev_clicks === 0 && row.clicks > 0) {
    return (
      <div className="flex flex-col items-end text-xs">
        <span className="flex items-center gap-0.5 font-semibold text-emerald-600">
          <ArrowUp className="h-3 w-3" />
          New
        </span>
        <span className="text-[10px] text-neutral-500">Previously: 0</span>
      </div>
    );
  }

  if (row.change_pct == null || row.change_clicks === 0) {
    return <span className="text-xs text-neutral-400">—</span>;
  }

  const up = row.change_clicks > 0;
  return (
    <span
      className={`flex items-center gap-0.5 text-xs font-semibold ${up ? "text-emerald-600" : "text-red-500"}`}
    >
      {up ? <ArrowUp className="h-3 w-3" /> : <ArrowDown className="h-3 w-3" />}
      {Math.abs(row.change_pct).toFixed(0)}%
    </span>
  );
}

function InsightRow({ row }: { row: GscContentInsightRow }) {
  const [copied, setCopied] = useState(false);
  const icon = faviconUrl(row.page);

  const copyUrl = async () => {
    try {
      await navigator.clipboard.writeText(row.page);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      /* ignore */
    }
  };

  return (
    <div className="group flex items-center gap-3 border-b border-neutral-100 py-3 last:border-b-0">
      <div className="flex h-12 w-12 shrink-0 items-center justify-center overflow-hidden rounded-md border border-neutral-200 bg-neutral-50">
        {icon ? (
          <img src={icon} alt="" className="h-6 w-6 object-contain" loading="lazy" />
        ) : (
          <span className="text-[10px] text-neutral-400">URL</span>
        )}
      </div>

      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-semibold text-neutral-900" title={row.title}>
          {row.title}
        </p>
        <div className="mt-0.5 flex items-center gap-1">
          <p className="truncate text-xs text-neutral-500" title={row.page}>
            {shortUrl(row.page)}
          </p>
          <div className="flex shrink-0 items-center gap-0.5 opacity-0 transition group-hover:opacity-100">
            <button
              type="button"
              onClick={copyUrl}
              className="rounded p-0.5 text-neutral-400 hover:bg-neutral-100 hover:text-neutral-700"
              title={copied ? "Copied" : "Copy URL"}
            >
              <Copy className="h-3.5 w-3.5" />
            </button>
            <a
              href={row.page}
              target="_blank"
              rel="noopener noreferrer"
              className="rounded p-0.5 text-neutral-400 hover:bg-neutral-100 hover:text-neutral-700"
              title="Open page"
            >
              <ExternalLink className="h-3.5 w-3.5" />
            </a>
          </div>
        </div>
      </div>

      <div className="flex shrink-0 items-center gap-4">
        <TrendBadge row={row} />
        <div className="min-w-[48px] text-right">
          <p className="text-sm font-bold text-neutral-900">{row.clicks}</p>
          <p className="text-[10px] text-neutral-500">Clicks</p>
        </div>
      </div>
    </div>
  );
}

export function GscContentInsights({ data }: { data: GscContentInsightsReport }) {
  const [tab, setTab] = useState<InsightTab>("trending_down");

  const rows = useMemo(() => {
    if (tab === "top") return data.top ?? [];
    if (tab === "trending_up") return data.trending_up ?? [];
    return data.trending_down ?? [];
  }, [data, tab]);

  const emptyLabel =
    tab === "top"
      ? "No page data for this period."
      : tab === "trending_up"
        ? "No pages gained clicks vs the previous period."
        : "No pages lost clicks vs the previous period.";

  return (
    <div>
      <div className="mb-4 flex flex-wrap gap-1 border-b border-neutral-200">
        {TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            onClick={() => setTab(t.id)}
            className={`-mb-px border-b-2 px-4 py-2 text-sm font-medium transition ${
              tab === t.id
                ? "border-[#1A73E8] text-[#1A73E8]"
                : "border-transparent text-neutral-600 hover:text-neutral-900"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {!rows.length ? (
        <p className="text-sm text-rp-tlight">{emptyLabel}</p>
      ) : (
        <div className="max-h-[480px] overflow-auto pr-1">
          {rows.map((row) => (
            <InsightRow key={row.page} row={row} />
          ))}
        </div>
      )}
    </div>
  );
}
