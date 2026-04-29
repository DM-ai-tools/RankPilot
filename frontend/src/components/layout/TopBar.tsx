import type { ReactNode } from "react";

/**
 * Matches the mockup `.topbar`:
 * padding:14px 20px, white bg, 1px bottom border, flex space-between.
 * Title: 16px/bold/navy. Right: flex items-center gap-10px.
 */
export function TopBar({
  title,
  subtitle,
  actions,
}: {
  title: string;
  subtitle?: string;
  actions?: ReactNode;
}) {
  return (
    <header className="flex shrink-0 items-center justify-between border-b border-rp-border bg-white px-6 py-4">
      <div>
        <h1 className="text-[18px] font-bold tracking-tight text-navy">{title}</h1>
        {subtitle ? (
          <p className="mt-1 text-[12px] text-rp-tlight">{subtitle}</p>
        ) : null}
      </div>
      {actions ? (
        <div className="flex items-center gap-2.5">{actions}</div>
      ) : null}
    </header>
  );
}
