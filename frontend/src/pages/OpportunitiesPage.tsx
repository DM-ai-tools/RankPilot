import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { formatApiError } from "../api/client";
import { fetchOpportunities } from "../api/opportunities";
import { TopBar } from "../components/layout/TopBar";
import { Button } from "../components/ui/Button";
import { useAuthStore } from "../stores/authStore";

export function OpportunitiesPage() {
  const token = useAuthStore((s) => s.accessToken);
  const q = useQuery({
    queryKey: ["opportunities", token],
    queryFn: fetchOpportunities,
    enabled: Boolean(token),
  });

  const items = q.data?.items ?? [];

  return (
    <>
      <TopBar
        title="Near-miss suburbs & keywords"
        subtitle="SEO Feature 6 — gaps where you are off page 1; queue targeted content from Content queue"
        actions={
          <>
            <Button variant="outline" size="sm" type="button">
              Filter by type
            </Button>
            <Button size="sm" type="button">
              ✨ Auto-Fix All
            </Button>
          </>
        }
      />
      <div className="flex-1 overflow-y-auto bg-rp-light px-7 py-6">
        {!token ? (
          <p className="text-sm text-rp-tmid">
            <Link to="/login" className="font-semibold text-[#72C219] hover:underline">
              Sign in
            </Link>{" "}
            to load opportunities.
          </p>
        ) : q.isLoading ? (
          <p className="text-sm text-rp-tlight">Loading…</p>
        ) : q.isError ? (
          <p className="text-sm text-red-600">{formatApiError(q.error)}</p>
        ) : null}

        {items.length === 0 && token && !q.isLoading ? (
          <p className="text-sm text-rp-tlight">No opportunities — all suburbs are in the top-20 Maps pack or grid is empty.</p>
        ) : null}

        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {items.map((o) => (
            <div
              key={o.suburb_id}
              className="overflow-hidden rounded-xl border border-rp-border bg-white shadow-card"
            >
              <div className="bg-gradient-to-br from-navy to-navy-mid p-4 text-white">
                <div className="flex items-start justify-between">
                  <div>
                    <div className="text-[15px] font-bold">{o.suburb}</div>
                    <div className="mt-0.5 text-[11px] text-rp-tlight">
                      {o.postcode ? `Postcode ${o.postcode}` : "—"}
                    </div>
                  </div>
                  <span className="rounded-full bg-red-500/20 px-2.5 py-0.5 text-[10px] font-bold text-red-200">
                    {o.band === "beyond_pack" ? "Beyond top 20" : o.band === "page2" ? "Page 2+" : "Not ranking"}
                  </span>
                </div>
                {o.population != null ? (
                  <div className="mt-2.5 inline-block rounded-full bg-[#72C219]/25 px-2.5 py-1 text-[11px] font-bold text-orange-100">
                    Nearby market: ~{o.population.toLocaleString()} residents
                  </div>
                ) : null}
              </div>
              <div className="p-4">
                <div className="mb-2.5 flex items-center justify-between">
                  <span className="text-[11px] text-rp-tlight">Current rank</span>
                  <span className="text-[13px] font-bold text-red-500">
                    {o.rank_position == null ? "Not ranking" : `#${o.rank_position}`}
                  </span>
                </div>
                <div className="mb-3 rounded-lg bg-rp-light p-2.5 text-xs leading-relaxed text-rp-tmid">
                  <strong className="mb-0.5 block text-navy">💡 Recommended action</strong>
                  {o.recommended_action}
                </div>
                <div className="flex gap-1.5">
                  <Button size="sm" className="flex-1" type="button">
                    ✨ Generate Page
                  </Button>
                  <Button variant="outline" size="sm" type="button">
                    View Details
                  </Button>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </>
  );
}
