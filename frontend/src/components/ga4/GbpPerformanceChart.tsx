import { useMemo, useState } from "react";

import type { GbpPerformanceReport } from "../../api/ga4";

const INTERACTIONS_COLOR = "#4285F4";
const CALLS_COLOR = "#1A73E8";
const WEBSITE_COLOR = "#9334E6";
const DIRECTIONS_COLOR = "#0F9D58";

type MetricKey = "interactions" | "calls" | "website_clicks" | "directions";

function fmtCompact(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return String(Math.round(n));
}

function fmtDateLabel(iso: string): string {
  const d = new Date(`${iso}T12:00:00`);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "short" });
}

function fmtAxisDate(iso: string): string {
  const d = new Date(`${iso}T12:00:00`);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString(undefined, { day: "2-digit", month: "short" });
}

function linePath(values: number[], width: number, height: number, max: number): string {
  if (!values.length) return "";
  const step = values.length > 1 ? width / (values.length - 1) : 0;
  return values
    .map((v, i) => {
      const x = i * step;
      const y = height - (max > 0 ? (v / max) * height : 0);
      return `${i === 0 ? "M" : "L"}${x},${y}`;
    })
    .join(" ");
}

function MetricPill({
  label,
  value,
  color,
  active,
  onToggle,
}: {
  label: string;
  value: string;
  color: string;
  active: boolean;
  onToggle: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onToggle}
      className={`flex min-w-[150px] flex-col rounded-lg border px-3 py-2 text-left transition ${
        active ? "border-transparent text-white shadow-sm" : "border-neutral-200 bg-white text-neutral-700"
      }`}
      style={active ? { backgroundColor: color } : undefined}
    >
      <span className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide opacity-90">
        <span
          className="inline-flex h-3.5 w-3.5 items-center justify-center rounded border text-[9px]"
          style={{
            borderColor: active ? "rgba(255,255,255,0.8)" : color,
            color: active ? "#fff" : color,
            background: active ? "rgba(255,255,255,0.15)" : "#fff",
          }}
        >
          {active ? "✓" : ""}
        </span>
        {label}
      </span>
      <span className="mt-1 text-xl font-bold leading-none">{value}</span>
    </button>
  );
}

export function GbpPerformanceChart({ data }: { data: GbpPerformanceReport }) {
  const [active, setActive] = useState<Record<MetricKey, boolean>>({
    interactions: true,
    calls: false,
    website_clicks: false,
    directions: false,
  });
  const [hoverIdx, setHoverIdx] = useState<number | null>(null);

  const rows = data.rows ?? [];
  const totals = data.totals ?? {
    interactions: 0,
    calls: 0,
    website_clicks: 0,
    directions: 0,
  };

  const chart = useMemo(() => {
    const interactions = rows.map((r) => r.interactions);
    const calls = rows.map((r) => r.calls);
    const website = rows.map((r) => r.website_clicks);
    const directions = rows.map((r) => r.directions);
    return {
      interactions,
      calls,
      website_clicks: website,
      directions,
      maxInteractions: Math.max(...interactions, 1),
      maxCalls: Math.max(...calls, 1),
      maxWebsite: Math.max(...website, 1),
      maxDirections: Math.max(...directions, 1),
    };
  }, [rows]);

  const metricConfig: Record<
    MetricKey,
    { label: string; color: string; max: (c: typeof chart) => number; values: (c: typeof chart) => number[] }
  > = {
    interactions: {
      label: "Interactions",
      color: INTERACTIONS_COLOR,
      max: (c) => c.maxInteractions,
      values: (c) => c.interactions,
    },
    calls: { label: "Calls", color: CALLS_COLOR, max: (c) => c.maxCalls, values: (c) => c.calls },
    website_clicks: {
      label: "Website clicks",
      color: WEBSITE_COLOR,
      max: (c) => c.maxWebsite,
      values: (c) => c.website_clicks,
    },
    directions: {
      label: "Directions",
      color: DIRECTIONS_COLOR,
      max: (c) => c.maxDirections,
      values: (c) => c.directions,
    },
  };

  const width = 900;
  const height = 180;
  const padL = 44;
  const padR = 20;
  const padT = 12;
  const padB = 28;
  const innerW = width - padL - padR;
  const innerH = height - padT - padB;

  const hover = hoverIdx != null && rows[hoverIdx] ? rows[hoverIdx] : null;
  const hoverX =
    hoverIdx != null && rows.length > 1 ? padL + (hoverIdx / (rows.length - 1)) * innerW : padL;

  const toggle = (key: MetricKey) => setActive((s) => ({ ...s, [key]: !s[key] }));
  const activeKeys = (Object.keys(active) as MetricKey[]).filter((k) => active[k]);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-2">
        <MetricPill
          label="Profile interactions"
          value={fmtCompact(totals.interactions)}
          color={INTERACTIONS_COLOR}
          active={active.interactions}
          onToggle={() => toggle("interactions")}
        />
        <MetricPill
          label="Calls"
          value={fmtCompact(totals.calls)}
          color={CALLS_COLOR}
          active={active.calls}
          onToggle={() => toggle("calls")}
        />
        <MetricPill
          label="Website clicks"
          value={fmtCompact(totals.website_clicks)}
          color={WEBSITE_COLOR}
          active={active.website_clicks}
          onToggle={() => toggle("website_clicks")}
        />
        <MetricPill
          label="Directions"
          value={fmtCompact(totals.directions)}
          color={DIRECTIONS_COLOR}
          active={active.directions}
          onToggle={() => toggle("directions")}
        />
      </div>

      {!rows.length ? (
        <p className="text-sm text-rp-tlight">No Business Profile activity for this period.</p>
      ) : (
        <div className="relative overflow-x-auto rounded-lg border border-neutral-200 bg-white p-3">
          <svg
            viewBox={`0 0 ${width} ${height}`}
            className="w-full min-w-[640px]"
            onMouseLeave={() => setHoverIdx(null)}
          >
            {[0, 0.25, 0.5, 0.75, 1].map((t) => {
              const y = padT + innerH * (1 - t);
              return (
                <line key={t} x1={padL} x2={width - padR} y1={y} y2={y} stroke="#E5E7EB" strokeWidth={1} />
              );
            })}

            <g transform={`translate(${padL}, ${padT})`}>
              {activeKeys.map((key) => {
                const cfg = metricConfig[key];
                const max = cfg.max(chart);
                const vals = cfg.values(chart);
                return (
                  <path
                    key={key}
                    d={linePath(vals, innerW, innerH, max)}
                    fill="none"
                    stroke={cfg.color}
                    strokeWidth={key === "interactions" ? 2.5 : 2}
                    strokeDasharray={key === "interactions" ? undefined : "4 3"}
                  />
                );
              })}

              <rect
                x={0}
                y={0}
                width={innerW}
                height={innerH}
                fill="transparent"
                onMouseMove={(e) => {
                  const rect = (e.currentTarget as SVGRectElement).getBoundingClientRect();
                  const ratio = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
                  setHoverIdx(Math.round(ratio * (rows.length - 1)));
                }}
              />

              {hoverIdx != null && activeKeys.length > 0 && (
                <line
                  x1={(hoverIdx / Math.max(rows.length - 1, 1)) * innerW}
                  x2={(hoverIdx / Math.max(rows.length - 1, 1)) * innerW}
                  y1={0}
                  y2={innerH}
                  stroke="#9CA3AF"
                  strokeWidth={1}
                  strokeDasharray="4 4"
                />
              )}
            </g>

            {rows.map((row, i) => {
              if (rows.length > 14 && i % Math.ceil(rows.length / 7) !== 0 && i !== rows.length - 1) return null;
              const x = padL + (i / Math.max(rows.length - 1, 1)) * innerW;
              return (
                <text key={row.date} x={x} y={height - 6} textAnchor="middle" fontSize={10} fill="#6B7280">
                  {fmtAxisDate(row.date)}
                </text>
              );
            })}
          </svg>

          {hover && (
            <div
              className="pointer-events-none absolute z-10 min-w-[180px] rounded-lg border border-neutral-200 bg-white px-3 py-2 text-xs shadow-lg"
              style={{
                left: `clamp(12px, ${(hoverX / width) * 100}%, calc(100% - 200px))`,
                top: 12,
              }}
            >
              <div className="mb-2 font-semibold text-neutral-900">{fmtDateLabel(hover.date)}</div>
              {(Object.keys(metricConfig) as MetricKey[]).map((key) => (
                <div key={key} className="mt-1 flex items-center justify-between gap-4">
                  <span className="flex items-center gap-1.5 text-neutral-600">
                    <span className="h-2 w-2 rounded-full" style={{ background: metricConfig[key].color }} />
                    {metricConfig[key].label}
                  </span>
                  <span className="font-semibold text-neutral-900">{hover[key]}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
