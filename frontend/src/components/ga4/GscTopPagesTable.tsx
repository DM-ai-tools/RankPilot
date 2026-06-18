import { useState } from "react";
import { Copy, ExternalLink } from "lucide-react";

import type { GscTopPageRow } from "../../api/ga4";

function fmt(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return String(n);
}

function PageRow({ row }: { row: GscTopPageRow }) {
  const [copied, setCopied] = useState(false);

  const copyUrl = async () => {
    try {
      await navigator.clipboard.writeText(row.page);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      /* ignore */
    }
  };

  return (
    <tr className="group border-b border-neutral-100 hover:bg-[#FAFBFC]">
      <td className="py-2.5 pr-4">
        <div className="flex items-center gap-2">
          <a
            href={row.page}
            target="_blank"
            rel="noopener noreferrer"
            className="truncate text-sm text-[#1A73E8] hover:underline"
            title={row.page}
          >
            {row.page}
          </a>
          <div className="flex shrink-0 items-center gap-0.5 opacity-0 transition group-hover:opacity-100">
            <button
              type="button"
              onClick={copyUrl}
              className="rounded p-0.5 text-neutral-400 hover:bg-neutral-100 hover:text-neutral-700"
              title={copied ? "Copied" : "Copy URL"}
            >
              <Copy className="h-3.5 w-3.5" />
            </button>
            <a
              href={row.page}
              target="_blank"
              rel="noopener noreferrer"
              className="rounded p-0.5 text-neutral-400 hover:bg-neutral-100 hover:text-neutral-700"
              title="Open page"
            >
              <ExternalLink className="h-3.5 w-3.5" />
            </a>
          </div>
        </div>
      </td>
      <td className="py-2.5 pr-4 text-right text-sm font-semibold text-neutral-900">{fmt(row.clicks)}</td>
      <td className="py-2.5 text-right text-sm text-neutral-700">{fmt(row.impressions)}</td>
    </tr>
  );
}

export function GscTopPagesTable({ rows }: { rows: GscTopPageRow[] }) {
  if (!rows.length) {
    return <p className="text-sm text-rp-tlight">No page data for this period.</p>;
  }

  return (
    <div className="max-h-[480px] overflow-auto">
      <table className="w-full text-left">
        <thead className="sticky top-0 z-10 bg-white">
          <tr className="border-b border-neutral-200 text-xs font-semibold text-neutral-600">
            <th className="pb-2 pr-4">Top pages</th>
            <th className="pb-2 pr-4 text-right">Clicks</th>
            <th className="pb-2 text-right">Impressions</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <PageRow key={row.page} row={row} />
          ))}
        </tbody>
      </table>
    </div>
  );
}
