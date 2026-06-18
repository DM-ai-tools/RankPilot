import { useEffect, useMemo, useRef, useState } from "react";
import { Check, ChevronDown, Globe } from "lucide-react";

import { formatApiError } from "../../api/client";

function shortPageLabel(url: string): string {
  try {
    const u = new URL(url);
    const path = u.pathname === "/" ? u.hostname : u.pathname;
    return path.length > 48 ? `${path.slice(0, 45)}…` : path;
  } catch {
    return url.length > 48 ? `${url.slice(0, 45)}…` : url;
  }
}

function triggerLabel(selected: string[]): string {
  if (!selected.length) return "All pages (site-wide)";
  if (selected.length === 1) return shortPageLabel(selected[0]);
  return `${selected.length} pages selected`;
}

export function Ga4PageFilter({
  options,
  selected,
  onChange,
  loading,
  error,
  warnings,
}: {
  options: string[];
  selected: string[];
  onChange: (pages: string[]) => void;
  loading?: boolean;
  error?: unknown;
  warnings?: string[];
}) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const rootRef = useRef<HTMLDivElement>(null);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return options;
    return options.filter((p) => p.toLowerCase().includes(q));
  }, [options, search]);

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (e: MouseEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onPointerDown);
    return () => document.removeEventListener("mousedown", onPointerDown);
  }, [open]);

  const toggle = (page: string) => {
    if (selected.includes(page)) {
      onChange(selected.filter((p) => p !== page));
    } else {
      onChange([...selected, page]);
    }
  };

  const selectAll = () => {
    onChange([]);
    setOpen(false);
    setSearch("");
  };

  return (
    <div ref={rootRef} className="relative min-w-[220px] flex-1 sm:max-w-[320px]">
      <label className="mb-1.5 block text-[11px] font-semibold uppercase tracking-wide text-rp-tlight">
        Page selector
      </label>

      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="listbox"
        aria-expanded={open}
        className={`flex w-full items-center justify-between gap-2 rounded-lg border bg-white px-3 py-2 text-left text-xs font-medium transition-colors ${
          selected.length
            ? "border-[#6366f1] text-[#4338ca]"
            : "border-rp-border text-navy hover:border-neutral-300"
        }`}
      >
        <span className="flex min-w-0 items-center gap-2">
          <Globe className="h-3.5 w-3.5 shrink-0 text-rp-tlight" />
          <span className="truncate">{triggerLabel(selected)}</span>
        </span>
        <ChevronDown className={`h-4 w-4 shrink-0 text-rp-tlight transition ${open ? "rotate-180" : ""}`} />
      </button>

      {open && (
        <div className="absolute left-0 right-0 z-50 mt-1.5 overflow-hidden rounded-lg border border-rp-border bg-white shadow-xl sm:left-auto sm:right-auto sm:w-full">
          <div className="border-b border-rp-border bg-[#FAFBFC] px-3 py-2.5">
            <p className="text-xs font-semibold text-navy">Choose pages to filter</p>
            <p className="mt-0.5 text-[10px] text-rp-tlight">
              {loading
                ? "Loading pages…"
                : options.length
                  ? `${options.length} pages available · multi-select · GBP stays site-wide`
                  : "Multi-select supported. GBP overview stays site-wide."}
            </p>
          </div>

          <div className="border-b border-rp-border p-2">
            <input
              type="search"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search by URL or path…"
              className="w-full rounded-md border border-rp-border px-2.5 py-1.5 text-xs text-navy outline-none focus:border-[#6366f1]"
            />
          </div>

          <div className="max-h-[260px] overflow-auto p-1.5" role="listbox">
            <button
              type="button"
              onClick={selectAll}
              className={`mb-1 flex w-full items-center gap-2 rounded-md px-2.5 py-2 text-left text-xs transition ${
                !selected.length ? "bg-[#EEF2FF] font-semibold text-[#4338ca]" : "text-navy hover:bg-[#FAFBFC]"
              }`}
            >
              <span
                className={`flex h-4 w-4 shrink-0 items-center justify-center rounded-full border ${
                  !selected.length ? "border-[#6366f1] bg-[#6366f1] text-white" : "border-neutral-300"
                }`}
              >
                {!selected.length ? <Check className="h-3 w-3" /> : null}
              </span>
              All pages (site-wide)
            </button>

            {loading ? (
              <p className="px-2.5 py-3 text-xs text-rp-tlight">Loading pages from GA4 and Search Console…</p>
            ) : error ? (
              <p className="px-2.5 py-3 text-xs text-red-600">{formatApiError(error)}</p>
            ) : !options.length ? (
              <p className="px-2.5 py-3 text-xs text-rp-tlight">
                No pages found for this date range. Try a longer range, or connect GA4 / Search Console in Business
                Setup.
              </p>
            ) : !filtered.length ? (
              <p className="px-2.5 py-3 text-xs text-rp-tlight">No pages match your search.</p>
            ) : (
              filtered.map((page) => {
                const active = selected.includes(page);
                return (
                  <button
                    key={page}
                    type="button"
                    onClick={() => toggle(page)}
                    className={`mb-0.5 flex w-full items-start gap-2 rounded-md px-2.5 py-2 text-left text-xs transition ${
                      active ? "bg-[#EEF2FF] text-[#4338ca]" : "text-navy hover:bg-[#FAFBFC]"
                    }`}
                  >
                    <span
                      className={`mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded border ${
                        active ? "border-[#6366f1] bg-[#6366f1] text-white" : "border-neutral-300 bg-white"
                      }`}
                    >
                      {active ? <Check className="h-3 w-3" /> : null}
                    </span>
                    <span className="min-w-0">
                      <span className="block font-medium">{shortPageLabel(page)}</span>
                      <span className="mt-0.5 block truncate text-[10px] text-rp-tlight" title={page}>
                        {page}
                      </span>
                    </span>
                  </button>
                );
              })
            )}
          </div>

          {warnings && warnings.length > 0 && (
            <div className="border-t border-amber-200 bg-amber-50 px-3 py-2 text-[10px] text-amber-800">
              {warnings[0]}
            </div>
          )}

          {selected.length > 0 && (
            <div className="flex items-center justify-between border-t border-rp-border bg-[#FAFBFC] px-3 py-2">
              <span className="text-[10px] text-rp-tlight">{selected.length} page(s) selected</span>
              <button
                type="button"
                onClick={selectAll}
                className="text-[11px] font-semibold text-[#6366f1] hover:underline"
              >
                Reset to all pages
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
