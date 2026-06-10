import { apiGet, apiPatchJson, apiPostJson } from "./client";

export type ClientProfile = {
  client_id: string;
  email: string;
  business_name: string;
  business_url: string;
  business_address?: string;
  business_phone?: string;
  tier: string;
  plan: string | null;
  primary_keyword: string;
  metro_label: string;
  location_scope?: "city" | "suburb";
  primary_suburb?: string;
  search_radius_km?: number;
  /** From GET /me — server geocoded for map. */
  business_lat?: number | null;
  business_lng?: number | null;
  business_location_source?: string | null;
};

export type OnboardingRequest = {
  business_name: string;
  business_url: string;
  business_address?: string;
  business_phone?: string;
  primary_keyword: string;
  metro_label: string;
  location_scope?: "city" | "suburb";
  primary_suburb?: string;
  search_radius_km?: number;
};

export type OnboardingResponse = {
  suburbs_seeded: number;
  metro_label: string;
  message: string;
};

/** Full profile including map pin (may call external geocoders — slower). */
export const fetchMe = (): Promise<ClientProfile> => apiGet<ClientProfile>("/api/v1/me");

/** Fast profile for login / routing — skips geocoding. */
export const fetchMeForAuth = (): Promise<ClientProfile> =>
  apiGet<ClientProfile>("/api/v1/me?include_map=false");

export type MePatch = { business_url: string; primary_keyword?: string };

export const patchMe = (body: MePatch): Promise<ClientProfile> =>
  apiPatchJson<ClientProfile, MePatch>("/api/v1/me", body);

export const saveOnboarding = (body: OnboardingRequest): Promise<OnboardingResponse> =>
  apiPostJson<OnboardingResponse, OnboardingRequest>("/api/v1/me/onboard", body);
