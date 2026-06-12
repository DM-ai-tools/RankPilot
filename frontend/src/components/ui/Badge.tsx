import type { ReactNode } from "react";

const styles = {
  green: "bg-success/10 text-success",
  amber: "bg-warn/10 text-warn",
  red: "bg-danger/10 text-danger",
  blue: "bg-info/10 text-info",
  teal: "bg-teal-100 text-teal-800 ring-1 ring-teal-200/80",
  orange: "bg-brand-50 text-brand-700",
  pending: "bg-amber-100 text-amber-800 ring-1 ring-amber-300/70",
  published: "bg-emerald-100 text-emerald-800 ring-1 ring-emerald-300/70",
} as const;

type Tone = keyof typeof styles;

export function Badge({ tone, children, className = "" }: { tone: Tone; children: ReactNode; className?: string }) {
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-[11px] font-semibold ${styles[tone]} ${className}`}
    >
      {children}
    </span>
  );
}
