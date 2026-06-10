import type { ReactNode } from "react";

interface MetricCardProps {
  label: string;
  value?: ReactNode;
  sub?: string;
  delta?: string;
  deltaUp?: boolean;
  deltaDown?: boolean;
  children?: ReactNode;
  className?: string;
}

export function MetricCard({
  label,
  value,
  sub,
  delta,
  deltaUp,
  deltaDown,
  children,
  className = "",
}: MetricCardProps) {
  const deltaColor = deltaUp
    ? "text-success"
    : deltaDown
      ? "text-danger"
      : "text-neutral-500";

  return (
    <div className={`flex min-h-[148px] min-w-0 flex-col rounded-xl border border-neutral-200 bg-white p-5 shadow-sm ${className}`}>
      <div className="mb-2 text-[11px] font-semibold uppercase tracking-[0.06em] text-neutral-500">
        {label}
      </div>
      <div className="flex flex-1 flex-col justify-center">
        {children ?? (
          <>
            <div className="text-[28px] font-extrabold tabular-nums leading-none text-neutral-900">
              {value}
            </div>
            {delta ? (
              <div className={`mt-1.5 text-[11px] font-semibold ${deltaColor}`}>{delta}</div>
            ) : null}
            {sub ? <div className="mt-1 text-[11px] text-neutral-500">{sub}</div> : null}
          </>
        )}
      </div>
    </div>
  );
}
