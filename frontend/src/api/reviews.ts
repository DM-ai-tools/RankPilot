import type { CompetitorVelocityResponse, ReviewsSummaryResponse } from "./types";
import { apiGet } from "./client";

export function fetchReviewsSummary() {
  return apiGet<ReviewsSummaryResponse>("/api/v1/reviews/summary");
}

export function fetchCompetitorVelocity() {
  return apiGet<CompetitorVelocityResponse>("/api/v1/reviews/competitors");
}
