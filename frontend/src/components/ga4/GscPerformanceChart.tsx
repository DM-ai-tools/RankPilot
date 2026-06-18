import { useMemo, useState } from "react";

import type { GscPerformanceReport } from "../../api/ga4";

const CLICKS_COLOR = "#4285F4";
const IMPRESSIONS_COLOR = "#9334E6";
const CTR_COLOR = "#0F9D58";
const POSITION_COLOR = "#F4B400";

type MetricKey = "clicks" | "impressions" | "ctr" | "position";

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
      className={`flex min-w-[140px] flex-col rounded-lg border px-3 py-2 text-left transition ${
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

export function GscPerformanceChart({ data }: { data: GscPerformanceReport }) {
  const [active, setActive] = useState<Record<MetricKey, boolean>>({
    clicks: true,
    impressions: true,
    ctr: false,
    position: false,
  });
  const [hoverIdx, setHoverIdx] = useState<number | null>(null);

  const rows = data.rows ?? [];
  const totals = data.totals ?? { clicks: 0, impressions: 0, ctr: 0, position: 0 };

  const chart = useMemo(() => {
    const clicks = rows.map((r) => r.clicks);
    const impressions = rows.map((r) => r.impressions);
    const ctr = rows.map((r) => r.ctr * 100);
    const position = rows.map((r) => r.position);
    return {
      clicks,
      impressions,
      ctr,
      position,
      maxClicks: Math.max(...clicks, 1),
      maxImpressions: Math.max(...impressions, 1),
      maxCtr: Math.max(...ctr, 1),
      maxPosition: Math.max(...position, 1),
    };
  }, [rows]);

  const width = 900;
  const height = 180;
  const padL = 44;
  const padR = 44;
  const padT = 12;
  const padB = 28;
  const innerW = width - padL - padR;
  const innerH = height - padT - padB;

  const hover = hoverIdx != null && rows[hoverIdx] ? rows[hoverIdx] : null;
  const hoverX =
    hoverIdx != null && rows.length > 1
      ? padL + (hoverIdx / (rows.length - 1)) * innerW
      : padL;

  const toggle = (key: MetricKey) => setActive((s) => ({ ...s, [key]: !s[key] }));

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-2">
        <MetricPill
          label="Total clicks"
          value={fmtCompact(totals.clicks)}
          color={CLICKS_COLOR}
          active={active.clicks}
          onToggle={() => toggle("clicks")}
        />
        <MetricPill
          label="Total impressions"
          value={fmtCompact(totals.impressions)}
          color={IMPRESSIONS_COLOR}
          active={active.impressions}
          onToggle={() => toggle("impressions")}
        />
        <MetricPill
          label="Average CTR"
          value={`${(totals.ctr * 100).toFixed(1)}%`}
          color={CTR_COLOR}
          active={active.ctr}
          onToggle={() => toggle("ctr")}
        />
        <MetricPill
          label="Average position"
          value={totals.position.toFixed(1)}
          color={POSITION_COLOR}
          active={active.position}
          onToggle={() => toggle("position")}
        />
      </div>

      {!rows.length ? (
        <p className="text-sm text-rp-tlight">No Search Console performance data for this period.</p>
      ) : (
        <div className="relative overflow-x-auto rounded-lg border border-neutral-200 bg-white p-3">
          <svg
            viewBox={`0 0 ${width} ${height}`}
            className="w-full min-w-[640px]"
            onMouseLeave={() => setHoverIdx(null)}
          >
            {/* grid */}
            {[0, 0.25, 0.5, 0.75, 1].map((t) => {
              const y = padT + innerH * (1 - t);
              return (
                <line
                  key={t}
                  x1={padL}
                  x2={width - padR}
                  y1={y}
                  y2={y}
                  stroke="#E5E7EB"
                  strokeWidth={1}
                />
              );
            })}

            {/* left axis labels (clicks) */}
            {active.clicks && [0, 0.5, 1].map((t) => (
              <text
                key={`lc-${t}`}
                x={padL - 6}
                y={padT + innerH * (1 - t) + 4}
                textAnchor="end"
                fontSize={10}
                fill={CLICKS_COLOR}
              >
                {fmtCompact(chart.maxClicks * t)}
              </text>
            ))}

            {/* right axis labels (impressions) */}
            {active.impressions && [0, 0.5, 1].map((t) => (
              <text
                key={`ri-${t}`}
                x={width - padR + 6}
                y={padT + innerH * (1 - t) + 4}
                textAnchor="start"
                fontSize={10}
                fill={IMPRESSIONS_COLOR}
              >
                {fmtCompact(chart.maxImpressions * t)}
              </text>
            ))}

            <g transform={`translate(${padL}, ${padT})`}>
              {active.clicks && (
                <path
                  d={linePath(chart.clicks, innerW, innerH, chart.maxClicks)}
                  fill="none"
                  stroke={CLICKS_COLOR}
                  strokeWidth={2}
                />
              )}
              {active.impressions && (
                <path
                  d={linePath(chart.impressions, innerW, innerH, chart.maxImpressions)}
                  fill="none"
                  stroke={IMPRESSIONS_COLOR}
                  strokeWidth={2}
                />
              )}
              {active.ctr && (
                <path
                  d={linePath(chart.ctr, innerW, innerH, chart.maxCtr)}
                  fill="none"
                  stroke={CTR_COLOR}
                  strokeWidth={2}
                  strokeDasharray="4 3"
                />
              )}
              {active.position && (
                <path
                  d={linePath(chart.position, innerW, innerH, chart.maxPosition)}
                  fill="none"
                  stroke={POSITION_COLOR}
                  strokeWidth={2}
                  strokeDasharray="4 3"
                />
              )}

              {/* hover capture */}
              <rect
                x={0}
                y={0}
                width={innerW}
                height={innerH}
                fill="transparent"
                onMouseMove={(e) => {
                  const rect = (e.currentTarget as SVGRectElement).getBoundingClientRect();
                  const ratio = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
                  const idx = Math.round(ratio * (rows.length - 1));
                  setHoverIdx(idx);
                }}
              />

              {hoverIdx != null && (
                <>
                  <line
                    x1={(hoverIdx / Math.max(rows.length - 1, 1)) * innerW}
                    x2={(hoverIdx / Math.max(rows.length - 1, 1)) * innerW}
                    y1={0}
                    y2={innerH}
                    stroke="#9CA3AF"
                    strokeWidth={1}
                    strokeDasharray="4 4"
                  />
                  {active.clicks && (
                    <circle
                      cx={(hoverIdx / Math.max(rows.length - 1, 1)) * innerW}
                      cy={innerH - (chart.clicks[hoverIdx] / chart.maxClicks) * innerH}
                      r={4}
                      fill={CLICKS_COLOR}
                    />
                  )}
                  {active.impressions && (
                    <circle
                      cx={(hoverIdx / Math.max(rows.length - 1, 1)) * innerW}
                      cy={innerH - (chart.impressions[hoverIdx] / chart.maxImpressions) * innerH}
                      r={4}
                      fill={IMPRESSIONS_COLOR}
                    />
                  )}
                </>
              )}
            </g>

            {/* x-axis labels */}
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
              {active.clicks && (
                <div className="flex items-center justify-between gap-4">
                  <span className="flex items-center gap-1.5 text-neutral-600">
                    <span className="h-2 w-2 rounded-full" style={{ background: CLICKS_COLOR }} />
                    Clicks
                  </span>
                  <span className="font-semibold text-neutral-900">{hover.clicks}</span>
                </div>
              )}
              {active.impressions && (
                <div className="mt-1 flex items-center justify-between gap-4">
                  <span className="flex items-center gap-1.5 text-neutral-600">
                    <span className="h-2 w-2 rounded-full" style={{ background: IMPRESSIONS_COLOR }} />
                    Impressions
                  </span>
                  <span className="font-semibold text-neutral-900">{hover.impressions}</span>
                </div>
              )}
              {active.ctr && (
                <div className="mt-1 flex items-center justify-between gap-4">
                  <span className="text-neutral-600">CTR</span>
                  <span className="font-semibold text-neutral-900">{(hover.ctr * 100).toFixed(1)}%</span>
                </div>
              )}
              {active.position && (
                <div className="mt-1 flex items-center justify-between gap-4">
                  <span className="text-neutral-600">Position</span>
                  <span className="font-semibold text-neutral-900">{hover.position.toFixed(1)}</span>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
