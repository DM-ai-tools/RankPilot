import { useQuery } from "@tanstack/react-query";
import { HelpCircle, Search } from "lucide-react";
import { useEffect, useState } from "react";

import { formatApiError } from "../../api/client";
import { fetchKeywordOverview, type KeywordIdeaItem, type KeywordOverviewResponse } from "../../api/keywords";
import { Button } from "../ui/Button";
import { Card } from "../ui/Card";
import { KeywordDataSourceBadge } from "./KeywordDataSourceBadge";

const COUNTRY_OPTIONS = [
  { code: "au", label: "Australia" },
  { code: "nz", label: "New Zealand" },
  { code: "us", label: "United States" },
  { code: "gb", label: "United Kingdom" },
];

function KdGauge({ value }: { value: number | null | undefined }) {
  const kd = value ?? 0;
  const pct = Math.min(100, Math.max(0, kd)) / 100;
  const label = value == null ? "N/A" : `${kd}`;
  const sub =
    value == null
      ? ""
      : kd <= 10
        ? "Easy"
        : kd <= 30
          ? "Medium"
          : kd <= 50
            ? "Hard"
            : "Very Hard";
  const color =
    value == null ? "#94A3B8" : kd <= 10 ? "#22C55E" : kd <= 30 ? "#72C219" : kd <= 50 ? "#F59E0B" : "#EF4444";

  return (
    <div className="flex flex-col items-center">
      <svg viewBox="0 0 120 70" className="h-[72px] w-[120px]" aria-hidden>
        <path
          d="M 12 62 A 48 48 0 0 1 108 62"
          fill="none"
          stroke="#E8EDF3"
          strokeWidth="10"
          strokeLinecap="round"
        />
        <path
          d="M 12 62 A 48 48 0 0 1 108 62"
          fill="none"
          stroke={color}
          strokeWidth="10"
          strokeLinecap="round"
          strokeDasharray={`${pct * 151} 151`}
        />
      </svg>
      <div className="mt-1 text-center">
        <div className="text-[28px] font-extrabold leading-none text-navy">{label}</div>
        {sub ? <div className="text-[12px] font-semibold text-rp-tmid">{sub}</div> : null}
      </div>
    </div>
  );
}

function MiniBarChart({ values }: { values: number[] }) {
  const data = values.length > 0 ? values : [0, 0, 0, 0, 0, 0];
  const max = Math.max(...data, 1);
  return (
    <div className="flex h-14 items-end gap-0.5">
      {data.slice(-12).map((v, i) => (
        <div
          key={i}
          className="flex-1 rounded-sm bg-[#72C219]/70"
          style={{ height: `${Math.max(8, (v / max) * 100)}%` }}
          title={String(v)}
        />
      ))}
    </div>
  );
}

function MetricCard({
  title,
  children,
  footer,
}: {
  title: string;
  children: React.ReactNode;
  footer?: React.ReactNode;
}) {
  return (
    <div className="rounded-xl border border-rp-border bg-white p-4 shadow-card">
      <div className="mb-2 flex items-center gap-1 text-[11px] font-semibold text-rp-tmid">
        {title}
        <HelpCircle className="h-3 w-3 text-rp-tlight" />
      </div>
      {children}
      {footer ? <div className="mt-2 text-[10px] text-rp-tlight">{footer}</div> : null}
    </div>
  );
}

function IdeaColumn({
  title,
  items,
  emptyHint,
}: {
  title: string;
  items: KeywordIdeaItem[];
  emptyHint: string;
}) {
  return (
    <div className="min-h-[200px] rounded-xl border border-rp-border bg-white">
      <div className="border-b border-rp-border px-3 py-2.5 text-[12px] font-bold text-navy">{title}</div>
      <div className="max-h-[280px] overflow-y-auto p-2">
        {items.length === 0 ? (
          <p className="px-2 py-6 text-center text-[11px] text-rp-tlight">{emptyHint}</p>
        ) : (
          <ul className="space-y-0.5">
            {items.map((it) => (
              <li
                key={it.keyword}
                className="flex items-center justify-between gap-2 rounded-md px-2 py-1.5 hover:bg-rp-light"
              >
                <span className="truncate text-[11px] font-medium text-navy">{it.keyword}</span>
                <span className="shrink-0 text-[11px] font-semibold text-rp-tmid">{it.volume_display}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

type Props = {
  defaultKeyword?: string;
};

export function AhrefsKeywordOverview({ defaultKeyword = "" }: Props) {
  const [input, setInput] = useState(defaultKeyword);
  const [activeKeyword, setActiveKeyword] = useState("");
  const [country, setCountry] = useState("au");

  useEffect(() => {
    if (defaultKeyword && !activeKeyword) {
      setInput(defaultKeyword);
    }
  }, [defaultKeyword, activeKeyword]);

  const overviewQ = useQuery({
    queryKey: ["keywords", "overview", activeKeyword, country],
    queryFn: () => fetchKeywordOverview(activeKeyword, country),
    enabled: Boolean(activeKeyword.trim()),
    staleTime: 120_000,
    retry: 1,
  });

  const data: KeywordOverviewResponse | undefined = overviewQ.data;
  const loading = overviewQ.isFetching;
  const err = overviewQ.error;
  const m = data?.metrics;

  function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    const kw = input.trim();
    if (!kw) return;
    setActiveKeyword(kw);
  }

  return (
    <div className="space-y-4">
      <Card className="p-4">
        <form onSubmit={handleSearch} className="flex flex-wrap items-end gap-3">
          <div className="min-w-[240px] flex-1">
            <label className="mb-1 block text-[10px] font-bold uppercase tracking-wide text-rp-tlight">
              Keyword
            </label>
            <input
              className="w-full rounded-lg border border-rp-border bg-white px-3 py-2.5 text-[14px] font-semibold text-navy outline-none ring-[#72C219]/30 focus:ring-2"
              placeholder="e.g. commercial cleaning seo"
              value={input}
              onChange={(e) => setInput(e.target.value)}
            />
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
      </Card>

      {err ? (
        <p className="text-sm text-red-600">{formatApiError(err)}</p>
      ) : null}
      {data?.message ? (
        <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-[12px] text-amber-900">
          {data.message}
        </div>
      ) : null}

      {m && activeKeyword ? (
        <>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className="text-[18px] font-extrabold text-navy">
              Overview: <span className="text-rp-tmid">{data.keyword}</span>
            </h2>
            <span className="text-[11px] text-rp-tlight">
              {data.country_label} ({data.country}) · via Ahrefs
            </span>
          </div>

          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <MetricCard title="Keyword Difficulty" footer={m.kd_description}>
              <KdGauge value={m.difficulty} />
            </MetricCard>

            <MetricCard
              title="Search volume"
              footer={m.volume_chart.length ? "Last 12 months (Ahrefs)" : "Trend not available"}
            >
              <div className="text-[32px] font-extrabold leading-none text-navy">{m.volume_display}</div>
              <div className="mt-3">
                <MiniBarChart values={m.volume_chart} />
              </div>
            </MetricCard>

            <MetricCard title="Traffic potential" footer={m.traffic_potential == null ? "Trend not available" : undefined}>
              <div className="text-[32px] font-extrabold leading-none text-navy">
                {m.traffic_potential != null ? m.traffic_potential.toLocaleString() : "N/A"}
              </div>
              {m.traffic_potential == null ? (
                <div className="mt-3 opacity-40">
                  <MiniBarChart values={[0, 0, 0, 0, 0, 0]} />
                </div>
              ) : null}
            </MetricCard>

            <MetricCard title="Global search volume">
              <div className="text-[32px] font-extrabold leading-none text-navy">
                {m.global_volume != null ? m.global_volume.toLocaleString() : "N/A"}
              </div>
              {m.global_by_country.length > 0 ? (
                <ul className="mt-3 space-y-2">
                  {m.global_by_country.map((c) => (
                    <li key={c.country_code} className="text-[11px]">
                      <div className="flex justify-between font-semibold text-navy">
                        <span>{c.country_name}</span>
                        <span>{c.volume.toLocaleString()}</span>
                      </div>
                      <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-rp-light">
                        <div
                          className="h-full rounded-full bg-[#3B82F6]"
                          style={{ width: `${c.share_pct}%` }}
                        />
                      </div>
                      <div className="text-right text-[10px] text-rp-tlight">{c.share_pct}%</div>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="mt-2 text-[11px] text-rp-tlight">No global breakdown available.</p>
              )}
            </MetricCard>
          </div>

          <div>
            <h3 className="mb-3 text-[14px] font-bold text-navy">Keyword ideas</h3>
            <div className="grid gap-3 lg:grid-cols-2 xl:grid-cols-4">
              <IdeaColumn title="Terms match" items={data.terms_match} emptyHint="No matching terms found." />
              <IdeaColumn title="Questions" items={data.questions} emptyHint="No question keywords found." />
              <IdeaColumn
                title="Also rank for"
                items={data.also_rank_for}
                emptyHint="No related ranking keywords found."
              />
              <IdeaColumn
                title="Also talk about"
                items={data.also_talk_about}
                emptyHint="No co-mentioned topics found."
              />
            </div>
          </div>
        </>
      ) : null}

      {!loading && !m && !data?.message && activeKeyword ? (
        <p className="text-sm text-rp-tlight">No overview data returned for this keyword.</p>
      ) : null}
    </div>
  );
}
