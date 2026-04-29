import type { MonthlyReportsResponse } from "./types";
import { apiGet } from "./client";

export async function fetchMonthlyReports(): Promise<MonthlyReportsResponse> {
  return apiGet<MonthlyReportsResponse>("/api/v1/reports/monthly");
}
