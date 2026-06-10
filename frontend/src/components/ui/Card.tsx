import type { ReactNode } from "react";

export function Card({ className = "", children }: { className?: string; children: ReactNode }) {
  return (
    <div
      className={`overflow-hidden rounded-lg border border-neutral-200 bg-white shadow-md ${className}`}
    >
      {children}
    </div>
  );
}

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
    <div className="flex items-center justify-between border-b border-neutral-200 px-6 py-4">
      <div>
        <div className="text-base font-bold text-neutral-900">{title}</div>
        {subtitle ? <div className="mt-0.5 text-xs text-neutral-500">{subtitle}</div> : null}
      </div>
      {right}
    </div>
  );
}
