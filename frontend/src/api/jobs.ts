import { apiGet } from "./client";

export type JobStatus = {
  job_id: string;
  job_type: string;
  status: string;
  payload: Record<string, unknown>;
  result: Record<string, unknown> | null;
  error_message: string | null;
  created_at: string;
  updated_at: string;
};

export function fetchJobStatus(jobId: string) {
  return apiGet<JobStatus>(`/api/v1/jobs/${jobId}`);
}

/** Latest queued/running maps_scan for the signed-in client (404 when idle). */
export function fetchActiveScanJob() {
  return apiGet<JobStatus>("/api/v1/jobs/active/scan");
}

