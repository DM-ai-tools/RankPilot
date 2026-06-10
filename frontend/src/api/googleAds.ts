import { apiGet, apiPostJson } from "./client";

export type GoogleAdsSetupStatus = {
  oauth_configured: boolean;
  developer_token_configured: boolean;
  login_customer_configured: boolean;
  connected: boolean;
  customer_id: string;
  customer_name: string;
};

export type GoogleAdsKeywordIdea = {
  keyword: string;
  avg_monthly_searches: number;
  competition: string | null;
  competition_index: number;
  low_top_of_page_bid_micros: number;
  high_top_of_page_bid_micros: number;
};

export type GoogleAdsKeywordIdeasResponse = GoogleAdsSetupStatus & {
  seed_keyword: string;
  metro_label: string;
  geo_target?: string;
  items: GoogleAdsKeywordIdea[];
  source?: string;
  message: string | null;
};

export type GoogleAdsCustomer = {
  customer_id: string;
  resource_name: string;
};

export const fetchGoogleAdsSetupStatus = (): Promise<GoogleAdsSetupStatus> =>
  apiGet<GoogleAdsSetupStatus>("/api/v1/google-ads/setup-status");

export const fetchGoogleAdsKeywordIdeas = (seed?: string): Promise<GoogleAdsKeywordIdeasResponse> => {
  const q = seed?.trim() ? `?seed=${encodeURIComponent(seed.trim())}` : "";
  return apiGet<GoogleAdsKeywordIdeasResponse>(`/api/v1/google-ads/keyword-ideas${q}`);
};

export const fetchGoogleAdsCustomers = (): Promise<{ items: GoogleAdsCustomer[] }> =>
  apiGet<{ items: GoogleAdsCustomer[] }>("/api/v1/integrations/google-ads/customers");

export const selectGoogleAdsCustomer = (body: { customer_id: string; customer_name?: string }) =>
  apiPostJson<{ selected: boolean; customer_id: string }, { customer_id: string; customer_name?: string }>(
    "/api/v1/integrations/google-ads/select-customer",
    body,
  );
