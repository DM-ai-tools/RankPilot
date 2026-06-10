import type { CompetitorVelocityResponse, ReviewsSummaryResponse } from "./types";
import { apiGet } from "./client";

export function fetchReviewsSummary(refresh = false) {
  const qs = refresh ? "?refresh=true" : "";
  return apiGet<ReviewsSummaryResponse>(`/api/v1/reviews/summary${qs}`);
}

export function fetchCompetitorVelocity() {
  return apiGet<CompetitorVelocityResponse>("/api/v1/reviews/competitors");
}
