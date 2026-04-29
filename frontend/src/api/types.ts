export type ScoreBlock = { value: number; delta_4w: number | null };

export type DashboardOverview = {
  scores: { seo_visibility: ScoreBlock };
  week_label: string;
  keyword: string;
  metro_label: string;
  business_profile?: {
    name: string;
    address: string;
    phone: string;
    maps_url: string;
    source: string;
  } | null;
  stats: {
    visibility_score: number;
    visibility_delta: number | null;
    suburbs_ranked: number;
    suburbs_total: number;
    monthly_searches: number;
    monthly_volume_note?: string | null;
    missed_suburbs: number;
    missed_note: string | null;
  };
  gauge: {
    top3_count: number;
    page1_count: number;
    pack_11_20_count: number;
    not_ranking_count: number;
    top3_pct: number;
    page1_pct: number;
    pack_11_20_pct: number;
    not_ranking_pct: number;
  };
  activity: { icon: string; heading: string; detail: string; occurred_at: string }[];
  rank_wins: { suburb: string; before_rank: number | null; after_rank: number | null; change_label: string }[];
  recommendations: { icon: string; title: string; subtitle: string; priority: string }[];
};

export type SuburbRank = {
  suburb_id: string;
  suburb: string;
  state: string | null;
  postcode: string | null;
  lat: number | null;
  lng: number | null;
  population: number | null;
  rank_position: number | null;
  monthly_volume_proxy: number;
};

/** Maps local-pack listing from last DataForSEO scan (Google lat/lng). */
export type MapPackPlace = {
  title: string;
  lat: number;
  lng: number;
  rank: number | null;
  domain: string | null;
  url: string | null;
  address: string | null;
  suburb_context: string | null;
};

export type SuburbRanksResponse = {
  keyword: string;
  metro_label: string;
  suburbs: SuburbRank[];
  visibility_score: number;
  top3_count: number;
  page1_count: number;
  pack_11_20_count: number;
  not_ranking_count: number;
  map_competitors: MapPackPlace[];
};

export type ContentQueueItem = {
  id: string;
  content_type: string;
  title: string;
  status: string;
  approval_mode: string;
  word_count: number | null;
  generated_at: string | null;
  published_at: string | null;
  target_url: string | null;
};

export type Opportunity = {
  suburb_id: string;
  suburb: string;
  postcode: string | null;
  population: number | null;
  rank_position: number | null;
  band: string;
  recommended_action: string;
};

export type ScrapedNap = {
  name: string | null;
  address: string | null;
  phone: string | null;
  name_ok: boolean;
  address_ok: boolean;
  phone_ok: boolean;
};

export type CitationRow = {
  id: string;
  directory: string;
  status: string;
  drift_flag: boolean;
  last_checked: string | null;
  scraped_nap: ScrapedNap | null;
};

export type CitationsListResponse = {
  items: CitationRow[];
};

export type GbpActivityItem = {
  type: string;
  description: string;
  occurred_at: string;
};

export type GbpActivityResponse = {
  items: GbpActivityItem[];
};

export type MonthlyReport = {
  id: string;
  month: string;
  visibility_score_start: number | null;
  visibility_score_end: number | null;
  top3_start: number | null;
  top3_end: number | null;
  pages_published: number | null;
  citations_fixed: number | null;
  reviews_new: number | null;
  narrative_text: string | null;
  pdf_url: string | null;
};

export type MonthlyReportsResponse = {
  items: MonthlyReport[];
};

export type ReviewItemRow = {
  rating: number | null;
  review_text: string;
  timestamp: string | null;
  profile_name: string | null;
  time_ago: string | null;
};

export type ReviewsSummaryResponse = {
  business_title: string | null;
  reviews_total_google: number | null;
  average_rating: number | null;
  new_this_month: number;
  items_returned: number;
  reviews: ReviewItemRow[];
  fetched_at: string | null;
  message: string | null;
};

export type CompetitorVelocityItem = {
  title: string;
  domain: string | null;
  reviews_count: number | null;
  rating: number | null;
  estimated_monthly: number | null;
  is_client: boolean;
};

export type CompetitorVelocityResponse = {
  client_title: string | null;
  client_reviews_total: number | null;
  client_new_this_month: number;
  competitors: CompetitorVelocityItem[];
  note: string | null;
};
