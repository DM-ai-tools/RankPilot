import type { Opportunity } from "./types";
import { apiGet } from "./client";

export type OpportunitiesResponse = { items: Opportunity[] };

export function fetchOpportunities() {
  return apiGet<OpportunitiesResponse>("/api/v1/opportunities/");
}
