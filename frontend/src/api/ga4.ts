import { apiGet } from "./client";

export type Ga4RangeKey = "week" | "month" | "quarter" | "half" | "year";

export const GA4_RANGE_LABELS: Record<Ga4RangeKey, string> = {
  week: "Last 7 days",
  month: "Last 30 days",
  quarter: "Last 90 days",
  half: "Last 6 months",
  year: "Last 12 months",
};

export type Ga4Row = Record<string, string | number>;

export type Ga4Report = {
  rows: Ga4Row[];
  totals: Record<string, Record<string, number>>;
  row_count: number;
  range?: string;
  compared?: boolean;
};

function rangeParams(range: Ga4RangeKey, compare: boolean, extra?: Record<string, string | number | boolean>) {
  const params = new URLSearchParams({ range, compare: String(compare) });
  if (extra) {
    Object.entries(extra).forEach(([k, v]) => params.set(k, String(v)));
  }
  return params.toString();
}

export const fetchGa4Overview = (range: Ga4RangeKey, compare: boolean): Promise<Ga4Report> =>
  apiGet(`/api/v1/ga4/overview?${rangeParams(range, compare)}`);

export const fetchGa4Pages = (range: Ga4RangeKey, compare: boolean, limit = 25): Promise<Ga4Report> =>
  apiGet(`/api/v1/ga4/pages?${rangeParams(range, compare, { limit })}`);

export const fetchGa4Channels = (range: Ga4RangeKey, compare: boolean): Promise<Ga4Report> =>
  apiGet(`/api/v1/ga4/channels?${rangeParams(range, compare)}`);

export const fetchGa4Geo = (range: Ga4RangeKey, compare: boolean, limit = 30): Promise<Ga4Report> =>
  apiGet(`/api/v1/ga4/geo?${rangeParams(range, compare, { limit })}`);

export const fetchGa4Organic = (range: Ga4RangeKey, compare: boolean, limit = 25): Promise<Ga4Report> =>
  apiGet(`/api/v1/ga4/organic?${rangeParams(range, compare, { limit })}`);
