import { apiDelete, apiGet, apiPostJson } from "./client";

export type IntegrationStatus = {
  connected: boolean;
  connected_at: string | null;
  extra: Record<string, string>;
};

export type IntegrationsStatusResponse = Record<string, IntegrationStatus>;

export type GoogleAuthUrlResponse = {
  url: string;
  type: string;
};

export type WordPressConnectRequest = {
  site_url: string;
  username: string;
  app_password: string;
};

export type WordPressConnectResponse = {
  connected: boolean;
  type: string;
  site: string;
  wp_user: string;
};

export type GscProperty = {
  property_id: string;
  property_name: string;
  property_type: string;
  permission_level: string;
};

export type Ga4Property = {
  property_id: string;
  property_name: string;
  account_name: string;
};

export type GbpProperty = {
  property_id: string;
  property_name: string;
  account_name: string;
  address?: string;
};

export const fetchIntegrationsStatus = (): Promise<IntegrationsStatusResponse> =>
  apiGet<IntegrationsStatusResponse>("/api/v1/integrations/status");

export const fetchGoogleAuthUrl = (type: "gsc" | "gbp" | "ga4"): Promise<GoogleAuthUrlResponse> =>
  apiGet<GoogleAuthUrlResponse>(`/api/v1/integrations/google/auth-url?type=${type}`);

export const connectWordPress = (body: WordPressConnectRequest): Promise<WordPressConnectResponse> =>
  apiPostJson<WordPressConnectResponse, WordPressConnectRequest>(
    "/api/v1/integrations/wordpress",
    body,
  );

export const disconnectIntegration = (type: string): Promise<{ disconnected: boolean; type: string }> =>
  apiDelete(`/api/v1/integrations/${type}`);

export const fetchGscProperties = (): Promise<{ items: GscProperty[] }> =>
  apiGet<{ items: GscProperty[] }>("/api/v1/integrations/gsc/properties");

export const selectGscProperty = (body: { property_id: string; property_name?: string }) =>
  apiPostJson<{ selected: boolean; property_id: string }, { property_id: string; property_name?: string }>(
    "/api/v1/integrations/gsc/select-property",
    body,
  );

export const fetchGa4Properties = (): Promise<{ items: Ga4Property[] }> =>
  apiGet<{ items: Ga4Property[] }>("/api/v1/integrations/ga4/properties");

export const selectGa4Property = (body: { property_id: string; property_name?: string }) =>
  apiPostJson<{ selected: boolean; property_id: string }, { property_id: string; property_name?: string }>(
    "/api/v1/integrations/ga4/select-property",
    body,
  );

export const fetchGbpProperties = (): Promise<{ items: GbpProperty[] }> =>
  apiGet<{ items: GbpProperty[] }>("/api/v1/integrations/gbp/properties");

export const selectGbpProperty = (body: { property_id: string; property_name?: string }) =>
  apiPostJson<{ selected: boolean; property_id: string }, { property_id: string; property_name?: string }>(
    "/api/v1/integrations/gbp/select-property",
    body,
  );
