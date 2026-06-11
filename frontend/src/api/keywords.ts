import { apiGet } from "./client";

export type SuburbKeywordPhrase = {
  keyword: string;
  suburb: string;
  state?: string | null;
  avg_monthly_searches: number;
  competition?: string | null;
  difficulty?: number | null;
  opportunity_score?: number;
  traffic_potential?: number | null;
};

export type RelatedKeywordIdea = {
  keyword: string;
  suburb?: string | null;
  avg_monthly_searches: number;
  competition?: string | null;
  difficulty?: number | null;
  opportunity_score?: number;
  traffic_potential?: number | null;
};

export type KeywordCacheMeta = {
  from_cache?: boolean;
  cached_at?: string | null;
  cache_expires_at?: string | null;
};

export type SuburbKeywordResearch = {
  primary_keyword: string;
  metro_label: string;
  geo_label: string;
  location_scope?: "city" | "suburb";
  suburbs: string[];
  suburb_phrases: SuburbKeywordPhrase[];
  related_ideas: RelatedKeywordIdea[];
  top_keywords?: RelatedKeywordIdea[];
  source: string;
  message?: string | null;
} & KeywordCacheMeta;

export type KeywordLookupItem = {
  keyword: string;
  volume: number;
  difficulty: number | null;
  competition: string | null;
  traffic_potential: number | null;
  cpc_cents: number | null;
  opportunity_score: number;
};

export type KeywordLookupResponse = {
  country: string;
  keywords: KeywordLookupItem[];
  source: string;
  message?: string | null;
} & KeywordCacheMeta;

export const fetchSuburbKeywordResearch = (refresh = false): Promise<SuburbKeywordResearch> => {
  const params = new URLSearchParams();
  if (refresh) params.set("refresh", "true");
  const qs = params.toString();
  return apiGet<SuburbKeywordResearch>(`/api/v1/keywords/suburb-research${qs ? `?${qs}` : ""}`);
};

/** Ranked live Ahrefs keywords for GBP — prefers backend top_keywords list. */
export function pickTopAhrefsKeywords(
  data: SuburbKeywordResearch | undefined,
  limit = 30,
): RelatedKeywordIdea[] {
  if (Array.isArray(data?.top_keywords) && data.top_keywords.length > 0) {
    return data.top_keywords.slice(0, limit);
  }
  const phrases = Array.isArray(data?.suburb_phrases) ? data.suburb_phrases : [];
  const ideas = Array.isArray(data?.related_ideas) ? data.related_ideas : [];
  const merged: RelatedKeywordIdea[] = [
    ...phrases.map((p) => ({
      keyword: p.keyword,
      suburb: p.suburb,
      avg_monthly_searches: p.avg_monthly_searches,
      competition: p.competition,
      difficulty: p.difficulty,
      opportunity_score: p.opportunity_score,
      traffic_potential: p.traffic_potential,
    })),
    ...ideas,
  ];
  const seen = new Set<string>();
  const out: RelatedKeywordIdea[] = [];
  for (const item of merged) {
    const kw = (item?.keyword ?? "").trim();
    if (!kw) continue;
    const key = kw.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(item);
  }
  out.sort(
    (a, b) =>
      (b.opportunity_score ?? 0) - (a.opportunity_score ?? 0) ||
      (b.avg_monthly_searches ?? 0) - (a.avg_monthly_searches ?? 0),
  );
  return out.slice(0, limit);
}

export function formatKeywordVolume(vol: number | undefined): string {
  if (vol == null || vol <= 0) return "0–10/mo";
  if (vol < 10) return "0–10/mo";
  if (vol < 1000) return `${vol}/mo`;
  return `${(vol / 1000).toFixed(1)}k/mo`;
}

export const lookupKeywords = (
  q: string,
  country?: string,
  refresh = false,
): Promise<KeywordLookupResponse> => {
  const params = new URLSearchParams({ q });
  if (country) params.set("country", country);
  if (refresh) params.set("refresh", "true");
  return apiGet<KeywordLookupResponse>(`/api/v1/keywords/lookup?${params.toString()}`);
};

export type KeywordIdeaItem = {
  keyword: string;
  volume: number | null;
  volume_display: string;
  difficulty: number | null;
  competition: string | null;
};

export type KeywordOverviewMetrics = {
  keyword: string;
  volume: number | null;
  volume_display: string;
  difficulty: number | null;
  difficulty_label: string | null;
  difficulty_short: string;
  kd_description: string;
  traffic_potential: number | null;
  global_volume: number | null;
  volume_chart: number[];
  global_by_country: {
    country_code: string;
    country_name: string;
    volume: number;
    share_pct: number;
  }[];
};

export type KeywordOverviewResponse = {
  keyword: string;
  country: string;
  country_label: string;
  metrics: KeywordOverviewMetrics | null;
  terms_match: KeywordIdeaItem[];
  questions: KeywordIdeaItem[];
  also_rank_for: KeywordIdeaItem[];
  also_talk_about: KeywordIdeaItem[];
  source: string;
  message?: string | null;
} & KeywordCacheMeta;

export const fetchKeywordOverview = (
  keyword: string,
  country?: string,
  refresh = false,
): Promise<KeywordOverviewResponse> => {
  const params = new URLSearchParams({ keyword });
  if (country) params.set("country", country);
  if (refresh) params.set("refresh", "true");
  return apiGet<KeywordOverviewResponse>(`/api/v1/keywords/overview?${params.toString()}`);
};

export type SiteKeywordItem = {
  keyword: string;
  volume: number | null;
  volume_display: string;
  difficulty: number | null;
  competition: string | null;
  best_position: number | null;
  traffic: number | null;
  ranking_url: string | null;
  opportunity_score: number;
};

export type SiteKeywordsResponse = {
  target: string;
  country: string;
  country_label: string;
  keywords: SiteKeywordItem[];
  source: string;
  message?: string | null;
} & KeywordCacheMeta;

export type SerpCompetitorItem = {
  position: number | null;
  domain: string;
  url: string;
  title: string | null;
  traffic: number | null;
  in_local_pack: boolean;
  local_pack_position: number | null;
};

export type KeywordSerpCompetitorsResponse = {
  keyword: string;
  country: string;
  competitors: SerpCompetitorItem[];
  source: string;
  message?: string | null;
} & KeywordCacheMeta;

/** Who ranks on Google for this keyword (Ahrefs SERP overview). */
export const fetchKeywordSerpCompetitors = (
  keyword: string,
  country?: string,
): Promise<KeywordSerpCompetitorsResponse> => {
  const params = new URLSearchParams({ keyword });
  if (country) params.set("country", country);
  return apiGet<KeywordSerpCompetitorsResponse>(
    `/api/v1/keywords/serp-competitors?${params.toString()}`,
  );
};

export type CompetitorGbpPost = {
  text: string;
  date: string | null;
  url: string | null;
  mentions_keyword: boolean;
};

export type CompetitorGbpPostsItem = {
  business_name: string;
  domain: string | null;
  organic_rank: number | null;
  maps_rank: number | null;
  in_local_pack: boolean;
  local_pack_position: number | null;
  posts_count: number;
  first_post_date: string | null;
  last_post_date: string | null;
  posts_per_month: number | null;
  keyword_mentions: number;
  top_terms: string[];
  recent_posts: CompetitorGbpPost[];
  note: string | null;
};

export type CompetitorGbpPostsResponse = {
  keyword: string;
  competitors: CompetitorGbpPostsItem[];
  competitor_source: "organic_serp" | "maps_scan" | string;
  source: string;
  message?: string | null;
} & KeywordCacheMeta;

export type SerpTargetForGbpPosts = {
  domain: string;
  title?: string | null;
  position?: number | null;
  in_local_pack?: boolean;
  local_pack_position?: number | null;
};

/** How competitors use GBP posts — pass SERP chips so the same rivals are analyzed. */
export const fetchCompetitorGbpPosts = (
  keyword: string,
  serpTargets?: SerpTargetForGbpPosts[],
): Promise<CompetitorGbpPostsResponse> => {
  const params = new URLSearchParams({ keyword });
  if (serpTargets && serpTargets.length > 0) {
    params.set("serp_targets", JSON.stringify(serpTargets.slice(0, 3)));
  }
  return apiGet<CompetitorGbpPostsResponse>(
    `/api/v1/keywords/competitor-gbp-posts?${params.toString()}`,
  );
};

/** Organic keywords a competitor website ranks for (Ahrefs Site Explorer). */
export const fetchCompetitorSiteKeywords = (
  target: string,
  country?: string,
  refresh = false,
): Promise<SiteKeywordsResponse> => {
  const params = new URLSearchParams({ target });
  if (country) params.set("country", country);
  if (refresh) params.set("refresh", "true");
  return apiGet<SiteKeywordsResponse>(`/api/v1/keywords/site-keywords?${params.toString()}`);
};
