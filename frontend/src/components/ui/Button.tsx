import type { ButtonHTMLAttributes, ReactNode } from "react";

const variants = {
  primary:
    "border border-transparent bg-[var(--brand-600)] text-white shadow-sm hover:bg-brand-700 focus-visible:ring-2 focus-visible:ring-brand-300 disabled:border-neutral-200 disabled:bg-neutral-100 disabled:text-neutral-600 disabled:shadow-none disabled:hover:bg-neutral-100",
  navy:
    "border border-transparent bg-ink-900 text-white shadow-sm hover:bg-ink-800 focus-visible:ring-2 focus-visible:ring-neutral-300 disabled:border-neutral-200 disabled:bg-neutral-100 disabled:text-neutral-600 disabled:shadow-none disabled:hover:bg-neutral-100",
  outline:
    "border border-neutral-200 bg-white text-neutral-700 hover:bg-neutral-50 focus-visible:ring-2 focus-visible:ring-brand-300 disabled:border-neutral-200 disabled:bg-neutral-50 disabled:text-neutral-400 disabled:hover:bg-neutral-50",
  teal:
    "border border-transparent bg-success text-white shadow-sm hover:bg-success/90 focus-visible:ring-2 focus-visible:ring-success/40 disabled:border-neutral-200 disabled:bg-neutral-100 disabled:text-neutral-600 disabled:shadow-none disabled:hover:bg-neutral-100",
} as const;

type Variant = keyof typeof variants;

type Props = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: Variant;
  size?: "sm" | "md";
  children: ReactNode;
};

export function Button({ variant = "primary", size = "md", className = "", ...props }: Props) {
  const sz =
    size === "sm"
      ? "rounded-sm px-3 py-1.5 text-xs font-semibold"
      : "rounded-sm px-4 py-2.5 text-sm font-semibold";

  return (
    <button
      type="button"
      className={`inline-flex shrink-0 items-center justify-center gap-1.5 whitespace-nowrap transition-colors disabled:cursor-not-allowed ${variants[variant]} ${sz} ${className}`}
      {...props}
    />
  );
}
