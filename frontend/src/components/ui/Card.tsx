import type { ReactNode } from "react";

/* Matches mockup .card: 10px radius, 1px border, white bg, bottom margin */
export function Card({ className = "", children }: { className?: string; children: ReactNode }) {
  return (
    <div
      className={`overflow-hidden rounded-card border border-rp-border bg-white shadow-card ${className}`}
    >
      {children}
    </div>
  );
}

/* Matches mockup .card-head: 12px 16px padding, flex space-between */
export function CardHeader({
  title,
  subtitle,
  right,
}: {
  title: string;
  subtitle?: string;
  right?: ReactNode;
}) {
  return (
    <div className="flex items-center justify-between border-b border-rp-border px-5 py-3.5">
      <div>
        <div className="text-[14px] font-semibold text-navy">{title}</div>
        {subtitle ? <div className="mt-0.5 text-[11px] text-rp-tlight">{subtitle}</div> : null}
      </div>
      {right}
    </div>
  );
}
