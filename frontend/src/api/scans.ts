import { apiPostJson } from "./client";

export type ScanBody = { keyword?: string | null; radius_km?: number | null };

export type JobAccepted = { job_id: string; status: string };

export function enqueueMapsScan(body: ScanBody = {}) {
  return apiPostJson<JobAccepted, ScanBody>("/api/v1/scans/maps", body);
}
