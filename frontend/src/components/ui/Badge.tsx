import type { ReactNode } from "react";

const styles = {
  green: "bg-emerald-500/10 text-emerald-600",
  amber: "bg-amber-500/10 text-amber-700",
  red: "bg-red-500/10 text-red-600",
  blue: "bg-navy-mid/10 text-navy-mid",
  teal: "bg-teal/10 text-teal",
  orange: "bg-[#72C219]/12 text-[#72C219]",
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
