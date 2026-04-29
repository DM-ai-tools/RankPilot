import { apiGet } from "./client";

export type ScoreBlock = { value: number; delta_4w: number | null };

export type DashboardScores = {
  seo_visibility: ScoreBlock;
  week_label: string;
};

export function fetchDashboardScores() {
  return apiGet<DashboardScores>("/api/v1/dashboard/scores");
}
