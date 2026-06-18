import { apiGet } from "./client";

export type Ga4RangeKey = "week" | "month" | "quarter" | "half" | "year";

export const GA4_RANGE_LABELS: Record<Ga4RangeKey, string> = {
  week: "Last 7 days",
  month: "Last 30 days",
  quarter: "Last 90 days",
  half: "Last 6 months",
  year: "Last 12 months",
};

export type Ga4QueryDates = {
  range?: Ga4RangeKey;
  startDate?: string;
  endDate?: string;
};

export type Ga4PageFilter = {
  pages?: string[];
};

export type Ga4Row = Record<string, string | number>;

export type Ga4Report = {
  rows: Ga4Row[];
  totals: Record<string, Record<string, number>>;
  row_count: number;
  range?: string;
  compared?: boolean;
  start_date?: string;
  end_date?: string;
  filtered_pages?: string[];
  page_filter_active?: boolean;
};

export function todayIsoDate(): string {
  return new Date().toISOString().slice(0, 10);
}

export function daysAgoIsoDate(days: number): string {
  const d = new Date();
  d.setDate(d.getDate() - (days - 1));
  return d.toISOString().slice(0, 10);
}

export function formatGa4RangeLabel(dates: Ga4QueryDates): string {
  if (dates.startDate && dates.endDate) {
    return `${dates.startDate} – ${dates.endDate}`;
  }
  return GA4_RANGE_LABELS[dates.range ?? "month"];
}

function dateParams(
  dates: Ga4QueryDates,
  compare: boolean,
  extra?: Record<string, string | number | boolean>,
  pageFilter?: Ga4PageFilter,
) {
  const params = new URLSearchParams({ compare: String(compare) });
  if (dates.startDate && dates.endDate) {
    params.set("start_date", dates.startDate);
    params.set("end_date", dates.endDate);
  } else {
    params.set("range", dates.range ?? "month");
  }
  if (pageFilter?.pages?.length) {
    params.set("pages", pageFilter.pages.join(","));
  }
  if (extra) {
    Object.entries(extra).forEach(([k, v]) => params.set(k, String(v)));
  }
  return params.toString();
}

export type Ga4PageOption = {
  page: string;
  title?: string;
  clicks?: number;
  sessions?: number;
  source?: "gsc" | "ga4" | "both";
};

export type Ga4PageOptionsReport = {
  rows: Ga4PageOption[];
  row_count: number;
  range?: string;
  start_date?: string;
  end_date?: string;
  site_base_url?: string | null;
  warnings?: string[];
};

export const fetchGa4PageOptions = (dates: Ga4QueryDates, limit = 200): Promise<Ga4PageOptionsReport> =>
  apiGet(`/api/v1/ga4/page-options?${dateParams(dates, false, { limit })}`);

export const fetchGa4Overview = (
  dates: Ga4QueryDates,
  compare: boolean,
  pageFilter?: Ga4PageFilter,
): Promise<Ga4Report> => apiGet(`/api/v1/ga4/overview?${dateParams(dates, compare, undefined, pageFilter)}`);

export const fetchGa4Pages = (
  dates: Ga4QueryDates,
  compare: boolean,
  limit = 25,
  pageFilter?: Ga4PageFilter,
): Promise<Ga4Report> =>
  apiGet(`/api/v1/ga4/pages?${dateParams(dates, compare, { limit }, pageFilter)}`);

export const fetchGa4Channels = (
  dates: Ga4QueryDates,
  compare: boolean,
  pageFilter?: Ga4PageFilter,
): Promise<Ga4Report> => apiGet(`/api/v1/ga4/channels?${dateParams(dates, compare, undefined, pageFilter)}`);

export const fetchGa4Geo = (
  dates: Ga4QueryDates,
  compare: boolean,
  limit = 30,
  pageFilter?: Ga4PageFilter,
): Promise<Ga4Report> => apiGet(`/api/v1/ga4/geo?${dateParams(dates, compare, { limit }, pageFilter)}`);

export const fetchGa4Organic = (
  dates: Ga4QueryDates,
  compare: boolean,
  limit = 25,
  pageFilter?: Ga4PageFilter,
): Promise<Ga4Report> =>
  apiGet(`/api/v1/ga4/organic?${dateParams(dates, compare, { limit }, pageFilter)}`);

export type Ga4KeywordRow = {
  keyword: string;
  clicks: number;
  impressions: number;
  ctr: number;
  position: number;
  volume?: number;
  volume_display?: string;
  difficulty?: number | null;
  traffic_potential?: number | null;
  prev_clicks?: number;
  prev_impressions?: number;
  prev_position?: number;
};

export type Ga4KeywordsReport = {
  rows: Ga4KeywordRow[];
  row_count: number;
  range?: string;
  compared?: boolean;
  gsc_site?: string;
  volume_source?: "ahrefs" | "none" | "ahrefs_error";
  start_date?: string;
  end_date?: string;
  filtered_pages?: string[];
  page_filter_active?: boolean;
};

export const fetchGa4Keywords = (
  dates: Ga4QueryDates,
  compare: boolean,
  limit = 30,
  pageFilter?: Ga4PageFilter,
): Promise<Ga4KeywordsReport> =>
  apiGet(`/api/v1/ga4/keywords?${dateParams(dates, compare, { limit }, pageFilter)}`);

export type GscPerformanceTotals = {
  clicks: number;
  impressions: number;
  ctr: number;
  position: number;
};

export type GscPerformanceDay = {
  date: string;
  clicks: number;
  impressions: number;
  ctr: number;
  position: number;
};

export type GscPerformanceReport = {
  totals: GscPerformanceTotals;
  prev_totals?: GscPerformanceTotals;
  rows: GscPerformanceDay[];
  row_count: number;
  range?: string;
  compared?: boolean;
  gsc_site?: string;
  start_date?: string;
  end_date?: string;
  filtered_pages?: string[];
  page_filter_active?: boolean;
};

export const fetchGscPerformance = (
  dates: Ga4QueryDates,
  compare: boolean,
  pageFilter?: Ga4PageFilter,
): Promise<GscPerformanceReport> =>
  apiGet(`/api/v1/ga4/gsc-performance?${dateParams(dates, compare, undefined, pageFilter)}`);

export type GscContentInsightRow = {
  page: string;
  title: string;
  clicks: number;
  prev_clicks: number;
  change_clicks: number;
  change_pct: number | null;
  impressions: number;
  ctr: number;
  position: number;
};

export type GscContentInsightsReport = {
  top: GscContentInsightRow[];
  trending_up: GscContentInsightRow[];
  trending_down: GscContentInsightRow[];
  range?: string;
  gsc_site?: string;
  start_date?: string;
  end_date?: string;
  prev_start_date?: string;
  prev_end_date?: string;
  filtered_pages?: string[];
  page_filter_active?: boolean;
};

export const fetchGscContentInsights = (
  dates: Ga4QueryDates,
  limit = 20,
  pageFilter?: Ga4PageFilter,
): Promise<GscContentInsightsReport> =>
  apiGet(`/api/v1/ga4/gsc-insights?${dateParams(dates, false, { limit }, pageFilter)}`);

export type GscTopPageRow = {
  page: string;
  clicks: number;
  impressions: number;
  ctr: number;
  position: number;
};

export type GscTopPagesReport = {
  rows: GscTopPageRow[];
  row_count: number;
  range?: string;
  gsc_site?: string;
  start_date?: string;
  end_date?: string;
  filtered_pages?: string[];
  page_filter_active?: boolean;
};

export const fetchGscTopPages = (
  dates: Ga4QueryDates,
  limit = 25,
  pageFilter?: Ga4PageFilter,
): Promise<GscTopPagesReport> =>
  apiGet(`/api/v1/ga4/gsc-pages?${dateParams(dates, false, { limit }, pageFilter)}`);

export type GbpPerformanceTotals = {
  interactions: number;
  calls: number;
  website_clicks: number;
  directions: number;
  messages: number;
  bookings: number;
  menus: number;
};

export type GbpPerformanceDay = {
  date: string;
  interactions: number;
  calls: number;
  website_clicks: number;
  directions: number;
  messages: number;
  bookings: number;
  menus: number;
};

export type GbpPerformanceReport = {
  totals: GbpPerformanceTotals;
  prev_totals?: GbpPerformanceTotals;
  rows: GbpPerformanceDay[];
  row_count: number;
  range?: string;
  compared?: boolean;
  location?: string;
  start_date?: string;
  end_date?: string;
};

export const fetchGbpPerformance = (dates: Ga4QueryDates, compare: boolean): Promise<GbpPerformanceReport> =>
  apiGet(`/api/v1/ga4/gbp-performance?${dateParams(dates, compare)}`);
