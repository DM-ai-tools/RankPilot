import type { ReactNode } from "react";

interface MetricCardProps {
  label: string;
  value?: ReactNode;
  sub?: string;
  delta?: string;
  deltaUp?: boolean;
  deltaDown?: boolean;
  children?: ReactNode;
}

/**
 * Matches the `.metric-card` from the RankPilot mockup:
 * white card, 10px radius, 14px padding, 1px border.
 * Label: 10px/semibold/uppercase/letter-spaced.
 * Value: 24px/extrabold/navy.
 * Change: green (up) or red (down).
 */
export function MetricCard({ label, value, sub, delta, deltaUp, deltaDown, children }: MetricCardProps) {
  const deltaColor = deltaUp
    ? "text-emerald-600"
    : deltaDown
      ? "text-red-500"
      : "text-rp-tlight";

  return (
    <div className="rounded-[10px] border border-rp-border bg-white p-[14px]">
      <div className="mb-1.5 text-[10px] font-semibold uppercase tracking-[0.8px] text-rp-tlight">
        {label}
      </div>
      {children ?? (
        <>
          <div className="text-[24px] font-extrabold leading-none text-navy">
            {value}
          </div>
          {delta ? (
            <div className={`mt-1 text-[10px] font-semibold ${deltaColor}`}>{delta}</div>
          ) : null}
          {sub ? (
            <div className="mt-1 text-[10px] text-rp-tlight">{sub}</div>
          ) : null}
        </>
      )}
    </div>
  );
}
