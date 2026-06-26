import type { SuburbRanksResponse } from "./types";
import { apiGet } from "./client";

export function fetchSuburbRanks(keyword?: string) {
  const params = new URLSearchParams();
  const kw = (keyword ?? "").trim();
  if (kw) params.set("keyword", kw);
  const qs = params.toString();
  return apiGet<SuburbRanksResponse>(`/api/v1/ranks/suburbs${qs ? `?${qs}` : ""}`);
}
