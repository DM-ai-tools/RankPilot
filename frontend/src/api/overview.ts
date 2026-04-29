import type { DashboardOverview } from "./types";
import { apiGet } from "./client";

export function fetchDashboardOverview() {
  return apiGet<DashboardOverview>("/api/v1/dashboard/overview");
}
