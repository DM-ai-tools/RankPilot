import type { GbpActivityResponse } from "./types";
import { apiGet } from "./client";

export async function fetchGbpActivity(): Promise<GbpActivityResponse> {
  return apiGet<GbpActivityResponse>("/api/v1/gbp/activity");
}
