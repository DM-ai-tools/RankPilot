import { useQuery } from "@tanstack/react-query";
import {
  Check,
  ChevronDown,
  ChevronUp,
  ExternalLink,
  MapPin,
  Megaphone,
  Plus,
  Trophy,
} from "lucide-react";
import { useState } from "react";

import {
  fetchCompetitorGbpPosts,
  fetchCompetitorSiteKeywords,
  fetchKeywordSerpCompetitors,
  type CompetitorGbpPostsItem,
  type SerpCompetitorItem,
} from "../../api/keywords";
import {
  addResearchedKeyword,
  removeResearchedKeyword,
  useResearchedKeywords,
} from "../../lib/researchedKeywords";

function rankLabel(c: SerpCompetitorItem): string {
  if (c.position === 1) return "1st place";
  if (c.position === 2) return "2nd place";
  if (c.position === 3) return "3rd place";
  if (c.position != null) return `${c.position}th place`;
  if (c.in_local_pack) return "Maps pack";
  return "Ranking";
}

/** Expanded detail: how this competitor ranks + the keywords they use regularly. */
function CompetitorDetail({ item, keyword }: { item: SerpCompetitorItem; keyword: string }) {
  const researched = useResearchedKeywords();
  const saved = new Set(researched.map((r) => r.keyword.toLowerCase()));

  const siteQ = useQuery({
    queryKey: ["keywords", "site-keywords", item.domain, "panel"],
    queryFn: () => fetchCompetitorSiteKeywords(item.domain),
    staleTime: 30 * 60_000,
    gcTime: 60 * 60_000,
    retry: 1,
  });

  const topKeywords = (siteQ.data?.keywords ?? []).slice(0, 10);

  return (
    <div className="mt-2 rounded-lg border border-[#F3CFA4] bg-white p-3">
      {/* How they rank for this keyword */}
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="rounded-full bg-[#C25E00] px-2 py-0.5 text-[10px] font-bold text-white">
          {rankLabel(item)}
        </span>
        {item.position != null && (
          <span className="text-[11px] text-[#7A4700]">
            ranks <strong>#{item.position}</strong> on Google for “{keyword}”
          </span>
        )}
        {item.in_local_pack && (
          <span className="inline-flex items-center gap-1 rounded-full border border-[#C2E0FF] bg-[#E8F4FF] px-2 py-0.5 text-[10px] font-bold text-[#0050A0]">
            <MapPin className="h-3 w-3" />
            In Google Maps pack{item.local_pack_position ? ` · spot ${item.local_pack_position}` : ""}
          </span>
        )}
      </div>
      {item.title && (
        <p className="mt-1.5 text-[11px] text-rp-tmid">
          Ranking page: <span className="font-medium text-navy">{item.title}</span>{" "}
          <a
            href={item.url}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-0.5 text-[#1A73E8] hover:underline"
          >
            open <ExternalLink className="h-3 w-3" />
          </a>
        </p>
      )}

      {/* Keywords they use on a regular basis */}
      <p className="mt-3 text-[10px] font-bold uppercase tracking-wide text-[#9A5B00]">
        Keywords {item.domain} uses regularly
        <span className="ml-1 font-normal normal-case text-[#B88350]">
          · top organic keywords via Ahrefs · click + to use in your content
        </span>
      </p>
      {siteQ.isLoading ? (
        <p className="mt-1.5 text-[11px] text-[#B88350]">Loading their keywords…</p>
      ) : siteQ.isError ? (
        <p className="mt-1.5 text-[11px] text-[#B88350]">Could not load this competitor's keywords.</p>
      ) : topKeywords.length === 0 ? (
        <p className="mt-1.5 text-[11px] text-[#B88350]">No organic keywords found for this domain.</p>
      ) : (
        <div className="mt-1.5 space-y-1">
          {topKeywords.map((k) => {
            const isSaved = saved.has(k.keyword.toLowerCase());
            return (
              <div key={k.keyword} className="flex items-center gap-2 rounded px-1 py-0.5 hover:bg-[#FFF8F0]">
                <button
                  type="button"
                  title={
                    isSaved
                      ? "Saved — remove from Posts & Description keyword pickers"
                      : "Save to Posts & Description keyword pickers"
                  }
                  onClick={() =>
                    isSaved ? removeResearchedKeyword(k.keyword) : addResearchedKeyword(k.keyword, k.volume)
                  }
                  className={`flex h-4 w-4 shrink-0 items-center justify-center rounded border transition ${
                    isSaved
                      ? "border-[#34A853] bg-[#34A853] text-white"
                      : "border-rp-border bg-white text-rp-tlight hover:border-[#34A853] hover:text-[#34A853]"
                  }`}
                >
                  {isSaved ? <Check className="h-3 w-3" /> : <Plus className="h-3 w-3" />}
                </button>
                <span className="min-w-0 flex-1 truncate text-[11px] text-navy">{k.keyword}</span>
                {k.best_position != null && (
                  <span className="shrink-0 text-[10px] font-bold text-[#C25E00]">#{k.best_position}</span>
                )}
                <span className="w-14 shrink-0 text-right text-[10px] text-rp-tlight">
                  {k.volume_display}/mo
                </span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

function GbpPostsCompetitorCard({
  item,
  keyword,
}: {
  item: CompetitorGbpPostsItem;
  keyword: string;
}) {
  const [showPosts, setShowPosts] = useState(false);
  const researched = useResearchedKeywords();
  const saved = new Set(researched.map((r) => r.keyword.toLowerCase()));

  return (
    <div className="rounded-lg border border-[#F3CFA4] bg-white p-3">
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="text-[12px] font-bold text-navy">{item.business_name}</span>
        {item.organic_rank != null && (
          <span className="rounded-full bg-[#C25E00] px-2 py-0.5 text-[10px] font-bold text-white">
            #{item.organic_rank} organic
          </span>
        )}
        {item.in_local_pack && (
          <span className="inline-flex items-center gap-1 rounded-full border border-[#C2E0FF] bg-[#E8F4FF] px-2 py-0.5 text-[10px] font-bold text-[#0050A0]">
            <MapPin className="h-3 w-3" />
            Maps pack{item.local_pack_position ? ` #${item.local_pack_position}` : ""}
          </span>
        )}
        {item.organic_rank == null && item.maps_rank != null && !item.in_local_pack && (
          <span className="inline-flex items-center gap-1 rounded-full border border-[#C2E0FF] bg-[#E8F4FF] px-2 py-0.5 text-[10px] font-bold text-[#0050A0]">
            <MapPin className="h-3 w-3" />
            #{item.maps_rank} in Maps
          </span>
        )}
        {item.domain && <span className="text-[10px] text-rp-tlight">{item.domain}</span>}
      </div>

      {item.posts_count === 0 ? (
        <p className="mt-1.5 text-[11px] text-[#B88350]">
          {item.note ?? "No public GBP posts found."}
        </p>
      ) : (
        <>
          {/* Posting cadence / time frame */}
          <div className="mt-1.5 flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-rp-tmid">
            <span>
              <strong className="text-navy">{item.posts_count}</strong> posts found
            </span>
            {item.posts_per_month != null && (
              <span>
                ~<strong className="text-navy">{item.posts_per_month}</strong> posts/month
              </span>
            )}
            {item.last_post_date && (
              <span>
                last posted <strong className="text-navy">{item.last_post_date}</strong>
              </span>
            )}
            {item.first_post_date && item.last_post_date && item.first_post_date !== item.last_post_date && (
              <span className="text-rp-tlight">
                ({item.first_post_date} → {item.last_post_date})
              </span>
            )}
          </div>

          {/* Keyword usage */}
          <p className="mt-1.5 text-[11px]">
            {item.keyword_mentions > 0 ? (
              <span className="font-semibold text-[#137333]">
                ✓ Uses “{keyword}” in {item.keyword_mentions} of {item.posts_count} posts
              </span>
            ) : (
              <span className="text-rp-tlight">Doesn't mention “{keyword}” in recent posts</span>
            )}
          </p>

          {/* Terms they use regularly in posts */}
          {item.top_terms.length > 0 && (
            <>
              <p className="mt-2 text-[10px] font-bold uppercase tracking-wide text-[#9A5B00]">
                Terms they post with regularly
                <span className="ml-1 font-normal normal-case text-[#B88350]">· click + to use</span>
              </p>
              <div className="mt-1 flex flex-wrap gap-1">
                {item.top_terms.map((t) => {
                  const isSaved = saved.has(t.toLowerCase());
                  return (
                    <button
                      key={t}
                      type="button"
                      title={isSaved ? "Saved to your keyword pickers" : "Save to Posts & Description keyword pickers"}
                      onClick={() =>
                        isSaved ? removeResearchedKeyword(t) : addResearchedKeyword(t, null)
                      }
                      className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-medium transition ${
                        isSaved
                          ? "border-[#34A853] bg-[#E6F4EA] text-[#137333]"
                          : "border-[#F3CFA4] bg-[#FFF8F0] text-[#7A4700] hover:border-[#34A853] hover:bg-[#E6F4EA] hover:text-[#137333]"
                      }`}
                    >
                      {isSaved ? <Check className="h-2.5 w-2.5" /> : <Plus className="h-2.5 w-2.5" />}
                      {t}
                    </button>
                  );
                })}
              </div>
            </>
          )}

          {/* Recent posts with dates */}
          <button
            type="button"
            onClick={() => setShowPosts((v) => !v)}
            className="mt-2 inline-flex items-center gap-1 text-[11px] font-semibold text-[#1A73E8] hover:underline"
          >
            {showPosts ? "Hide their recent posts" : `View their recent posts (${item.recent_posts.length})`}
            {showPosts ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
          </button>
          {showPosts && (
            <div className="mt-1.5 space-y-1.5">
              {item.recent_posts.map((p, i) => (
                <div
                  key={i}
                  className={`rounded-md border px-2.5 py-2 text-[11px] leading-relaxed ${
                    p.mentions_keyword
                      ? "border-[#CEEAD6] bg-[#F6FFF8] text-navy"
                      : "border-rp-border bg-[#F8FAFC] text-rp-tmid"
                  }`}
                >
                  <div className="mb-0.5 flex items-center gap-2 text-[10px] text-rp-tlight">
                    {p.date && <span>📅 {p.date}</span>}
                    {p.mentions_keyword && (
                      <span className="font-bold text-[#137333]">contains “{keyword}”</span>
                    )}
                  </div>
                  {p.text}
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}

/** On-demand GBP post analysis for the same organic SERP competitors shown above. */
function CompetitorGbpPostsSection({
  keyword,
  serpCompetitors,
}: {
  keyword: string;
  serpCompetitors: SerpCompetitorItem[];
}) {
  const [enabled, setEnabled] = useState(false);
  const serpTargets = serpCompetitors.slice(0, 3).map((c) => ({
    domain: c.domain,
    title: c.title,
    position: c.position,
    in_local_pack: c.in_local_pack,
    local_pack_position: c.local_pack_position,
  }));

  const q = useQuery({
    queryKey: ["keywords", "competitor-gbp-posts", keyword, serpTargets.map((t) => t.domain).join(",")],
    queryFn: () => fetchCompetitorGbpPosts(keyword, serpTargets),
    enabled: enabled && serpTargets.length > 0,
    staleTime: 30 * 60_000,
    gcTime: 60 * 60_000,
    retry: 0,
  });

  const competitors = q.data?.competitors ?? [];

  return (
    <div className="mt-2 border-t border-[#FDE2C8] pt-2">
      {serpTargets.length === 0 ? (
        <p className="text-[11px] text-[#B88350]">
          Wait for organic competitors to load above, then analyze their GBP posts.
        </p>
      ) : !enabled ? (
        <button
          type="button"
          onClick={() => setEnabled(true)}
          className="inline-flex items-center gap-1.5 rounded-md border border-[#F3CFA4] bg-white px-2.5 py-1.5 text-[11px] font-semibold text-[#7A4700] transition hover:border-[#E8A04C] hover:bg-[#FFF3E2]"
        >
          <Megaphone className="h-3.5 w-3.5" />
          Analyze GBP posts for {serpTargets.map((t) => t.domain).join(", ")}
        </button>
      ) : q.isLoading ? (
        <p className="text-[11px] text-[#B88350]">
          Reading GBP posts for {serpTargets.map((t) => t.domain).join(", ")}… first run takes 1–2 min (cached 24h).
        </p>
      ) : q.isError ? (
        <p className="text-[11px] text-[#B88350]">Competitor GBP post analysis unavailable right now.</p>
      ) : competitors.length === 0 ? (
        <p className="text-[11px] text-[#B88350]">
          {q.data?.message ?? "No competitor data returned."}
        </p>
      ) : (
        <div className="space-y-2">
          <p className="flex flex-wrap items-center gap-1.5 text-[10px] font-bold uppercase tracking-wide text-[#9A5B00]">
            <Megaphone className="h-3 w-3" />
            GBP posts — same competitors as the chips above
            {q.data?.competitor_source === "maps_scan" && (
              <span className="font-normal normal-case text-amber-700">
                (fallback: Maps scan list — not the organic chips)
              </span>
            )}
            {q.data?.message && (
              <span className="font-normal normal-case text-[#B88350]">· {q.data.message}</span>
            )}
          </p>
          {competitors.map((c) => (
            <GbpPostsCompetitorCard key={c.business_name} item={c} keyword={keyword} />
          ))}
        </div>
      )}
    </div>
  );
}

/**
 * "Who ranks for this keyword" card shown beside generated posts /
 * descriptions — overview only, never injected into the content.
 * Click a competitor to see how they rank and which keywords they use.
 */
export function KeywordCompetitorsPanel({ keyword }: { keyword?: string | null }) {
  const kw = (keyword ?? "").trim();
  const [openDomain, setOpenDomain] = useState<string | null>(null);

  const q = useQuery({
    queryKey: ["keywords", "serp-competitors", kw],
    queryFn: () => fetchKeywordSerpCompetitors(kw),
    enabled: Boolean(kw),
    staleTime: 30 * 60_000,
    gcTime: 60 * 60_000,
    retry: 1,
  });

  if (!kw) return null;

  const competitors = q.data?.competitors ?? [];
  const openItem = competitors.find((c) => c.domain === openDomain) ?? null;

  return (
    <div className="rounded-lg border border-[#FDE2C8] bg-[#FFF8F0] px-3 py-2.5">
      <p className="flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-wide text-[#9A5B00]">
        <Trophy className="h-3 w-3" />
        Organic Google rankings for “{kw}”
        <span className="font-normal normal-case text-[#B88350]">
          · websites on page 1 (Ahrefs) · click a chip for keyword details
        </span>
      </p>

      {q.isLoading ? (
        <p className="mt-1.5 text-[11px] text-[#B88350]">Checking who ranks for this keyword…</p>
      ) : q.isError ? (
        <p className="mt-1.5 text-[11px] text-[#B88350]">Competitor lookup unavailable right now.</p>
      ) : competitors.length === 0 ? (
        <p className="mt-1.5 text-[11px] text-[#B88350]">
          {q.data?.message ?? "No competitors found ranking for this keyword."}
        </p>
      ) : (
        <>
          <div className="mt-1.5 flex flex-wrap gap-1.5">
            {competitors.slice(0, 8).map((c) => {
              const isOpen = openDomain === c.domain;
              return (
                <button
                  key={c.domain}
                  type="button"
                  title={c.title ?? c.url}
                  onClick={() => setOpenDomain(isOpen ? null : c.domain)}
                  className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-medium transition ${
                    isOpen
                      ? "border-[#C25E00] bg-[#FFF3E2] text-[#7A4700]"
                      : "border-[#F3CFA4] bg-white text-[#7A4700] hover:border-[#E8A04C] hover:bg-[#FFF3E2]"
                  }`}
                >
                  <span className="font-bold text-[#C25E00]">
                    #{c.position ?? c.local_pack_position ?? "–"}
                  </span>
                  {c.domain}
                  {c.in_local_pack && <MapPin className="h-3 w-3 text-[#0050A0]" />}
                  {isOpen ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
                </button>
              );
            })}
          </div>
          {openItem && <CompetitorDetail item={openItem} keyword={kw} />}
        </>
      )}

      <CompetitorGbpPostsSection keyword={kw} serpCompetitors={competitors} />
    </div>
  );
}
