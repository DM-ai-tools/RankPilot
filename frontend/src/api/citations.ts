import type { CitationsListResponse } from "./types";
import { apiGet, apiPostJson } from "./client";

export async function fetchCitations(): Promise<CitationsListResponse> {
  return apiGet<CitationsListResponse>("/api/v1/citations/directories");
}

export type SyncCitationsResponse = {
  updated: number;
  error?: string;
  warnings?: string[];
  canonical?: {
    name?: string;
    address?: string;
    phone?: string;
    source?: string;
  };
};

export async function syncCitations(): Promise<SyncCitationsResponse> {
  return apiPostJson("/api/v1/citations/sync", {});
}
