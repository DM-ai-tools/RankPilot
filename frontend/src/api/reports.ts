import type { MonthlyReportsResponse } from "./types";
import { apiGet, apiGetBlob } from "./client";

export async function fetchMonthlyReports(): Promise<MonthlyReportsResponse> {
  return apiGet<MonthlyReportsResponse>("/api/v1/reports/monthly");
}

/** Download monthly report PDF (YYYY-MM). Returns blob + suggested filename. */
export async function downloadMonthlyReportPdf(monthYyyyMm: string): Promise<{ blob: Blob; filename: string }> {
  const month = monthYyyyMm.slice(0, 7);
  const { blob, filename } = await apiGetBlob(`/api/v1/reports/monthly/${month}/pdf`);
  return { blob, filename };
}
