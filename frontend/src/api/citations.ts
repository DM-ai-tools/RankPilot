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
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), 120_000);
  try {
    return await apiPostJson<SyncCitationsResponse>("/api/v1/citations/sync", {}, {
      signal: controller.signal,
    });
  } catch (err: unknown) {
    if (err instanceof DOMException && err.name === "AbortError") {
      throw new Error(
        "Citation sync timed out — directories are checked in parallel but some sites may be slow. Try Sync Now again.",
      );
    }
    throw err;
  } finally {
    window.clearTimeout(timer);
  }
}
