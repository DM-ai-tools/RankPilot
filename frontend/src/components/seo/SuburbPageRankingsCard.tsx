import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowDown, ArrowUp, Minus, RefreshCw } from "lucide-react";

import { formatApiError } from "../../api/client";
import {
  fetchSuburbPageRankings,
  syncSuburbPageRankings,
  type SuburbPageRankingItem,
} from "../../api/seoWebsite";
import { Button } from "../ui/Button";
import { Card, CardHeader } from "../ui/Card";

function ChangeBadge({ change }: { change: number | null }) {
  if (change === null) return <span className="text-rp-tlight">—</span>;
  if (change === 0) {
    return (
      <span className="inline-flex items-center gap-0.5 text-[10px] text-rp-tmid">
        <Minus className="h-3 w-3" /> Same
      </span>
    );
  }
  if (change > 0) {
    return (
      <span className="inline-flex items-center gap-0.5 text-[10px] font-semibold text-[#137333]">
        <ArrowUp className="h-3 w-3" /> +{change}
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-0.5 text-[10px] font-semibold text-red-600">
      <ArrowDown className="h-3 w-3" /> {change}
    </span>
  );
}

function StatusBadge({ item }: { item: SuburbPageRankingItem }) {
  if (item.is_ranking) {
    return (
      <span className="rounded-full bg-[#E6F4EA] px-2 py-0.5 text-[10px] font-bold uppercase text-[#137333]">
        Ranking
      </span>
    );
  }
  return (
    <span className="rounded-full bg-[#FCE8E6] px-2 py-0.5 text-[10px] font-bold uppercase text-[#C5221F]">
      Not ranking
    </span>
  );
}

type Props = {
  enabled: boolean;
  token: string | null;
};

const RANKINGS_STALE_MS = 30 * 60_000;

export function SuburbPageRankingsCard({ enabled, token }: Props) {
  const qc = useQueryClient();

  const rankingsQ = useQuery({
    queryKey: ["suburb-page-rankings", token],
    queryFn: fetchSuburbPageRankings,
    enabled: enabled && Boolean(token),
    staleTime: RANKINGS_STALE_MS,
    gcTime: 60 * 60_000,
    refetchOnMount: false,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
  });

  const syncMut = useMutation({
    mutationFn: syncSuburbPageRankings,
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["suburb-page-rankings"] });
    },
  });

  const items = rankingsQ.data?.items ?? [];

  return (
    <Card>
      <CardHeader
        title="Published page rankings"
        subtitle="Google position for RankPilot-published pages only — last week vs this week"
        right={
          <Button
            size="sm"
            variant="outline"
            disabled={syncMut.isPending || rankingsQ.isLoading}
            onClick={() => void syncMut.mutate()}
          >
            <RefreshCw className={`mr-1 h-3 w-3 ${syncMut.isPending ? "animate-spin" : ""}`} />
            {syncMut.isPending ? "Checking…" : "Refresh rankings"}
          </Button>
        }
      />
      <div className="p-4">
        {rankingsQ.isLoading && !rankingsQ.data ? (
          <p className="text-sm text-rp-tlight">Loading rankings…</p>
        ) : rankingsQ.isError ? (
          <p className="text-sm text-red-600">{formatApiError(rankingsQ.error)}</p>
        ) : items.length === 0 ? (
          <p className="text-sm text-rp-tlight">
            No RankPilot-published suburb pages found yet. Click{" "}
            <strong>Refresh rankings</strong> to import them from WordPress, or publish a suburb page above.
          </p>
        ) : (
          <div className="max-h-[420px] overflow-auto rounded-md border border-rp-border">
            <table className="w-full min-w-[720px] border-collapse text-left text-[11px]">
              <thead className="sticky top-0 z-10 bg-rp-light text-[10px] font-bold uppercase text-rp-tlight shadow-[0_1px_0_0_#E5E7EB]">
                <tr>
                  <th className="px-3 py-2">Page</th>
                  <th className="px-3 py-2">Keyword</th>
                  <th className="px-3 py-2">Last week</th>
                  <th className="px-3 py-2">This week</th>
                  <th className="px-3 py-2">Change</th>
                  <th className="px-3 py-2">Status</th>
                </tr>
              </thead>
              <tbody>
                {items.map((item) => (
                  <tr key={item.history_id} className="border-t border-rp-border hover:bg-[#FAFBFD]">
                    <td className="px-3 py-2">
                      <div className="font-semibold text-navy">{item.title || item.slug}</div>
                      {item.page_url ? (
                        <a
                          href={item.page_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-[10px] text-rp-blue hover:underline"
                        >
                          /{item.slug}
                        </a>
                      ) : item.slug ? (
                        <div className="text-[10px] text-rp-tlight">/{item.slug}</div>
                      ) : null}
                      {item.suburb ? (
                        <div className="text-[10px] text-rp-tlight">{item.suburb}</div>
                      ) : null}
                    </td>
                    <td className="px-3 py-2">
                      <div className="text-rp-tmid">{item.keyword}</div>
                      {item.search_keywords && item.search_keywords.length > 1 ? (
                        <div className="text-[10px] text-rp-tlight">
                          Also checks: {item.search_keywords.slice(1).join(", ")}
                        </div>
                      ) : null}
                      {item.rank_note ? (
                        <div className="mt-0.5 text-[9px] text-amber-700">{item.rank_note}</div>
                      ) : null}
                    </td>
                    <td className="px-3 py-2 text-rp-tmid whitespace-nowrap">{item.last_week_label}</td>
                    <td className="px-3 py-2 font-semibold text-navy whitespace-nowrap">
                      {item.this_week_label}
                    </td>
                    <td className="px-3 py-2">
                      <ChangeBadge change={item.position_change} />
                    </td>
                    <td className="px-3 py-2">
                      <StatusBadge item={item} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {syncMut.isSuccess ? (
          <p className="mt-2 text-xs text-[#137333]">
            Rankings updated — checked {syncMut.data.checked} keyword
            {syncMut.data.checked === 1 ? "" : "s"}.
          </p>
        ) : null}
        {syncMut.isError ? (
          <p className="mt-2 text-xs text-red-600">{formatApiError(syncMut.error)}</p>
        ) : null}
        <p className="mt-3 text-[10px] text-rp-tlight">
          Checks Ahrefs SERP, Google Search Console (when connected), and live Google organic results
          for your published page URL. Rank checks use the page slug — your WordPress title can stay as-is.
        </p>
      </div>
    </Card>
  );
}
