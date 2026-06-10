import type { ReactNode } from "react";

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
    <header className="sticky top-0 z-20 flex shrink-0 items-center justify-between gap-4 border-b border-neutral-200 bg-white/80 px-7 py-4 backdrop-blur-md">
      <div className="min-w-0 flex-1">
        <h1 className="text-2xl font-bold tracking-tight text-neutral-900">{title}</h1>
        {subtitle ? (
          <p className="mt-1 truncate text-sm text-neutral-500">{subtitle}</p>
        ) : null}
      </div>
      {actions ? <div className="flex shrink-0 items-center gap-2.5">{actions}</div> : null}
    </header>
  );
}
