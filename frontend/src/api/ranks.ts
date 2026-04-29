import type { SuburbRanksResponse } from "./types";
import { apiGet } from "./client";

export function fetchSuburbRanks() {
  return apiGet<SuburbRanksResponse>("/api/v1/ranks/suburbs");
}
