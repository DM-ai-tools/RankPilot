import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";

import { fetchJobStatus, type JobStatus } from "../api/jobs";

export type ScanProgress = {
  suburbs_checked: number;
  suburbs_total: number;
  found: number;
  rows_inserted: number;
  keyword?: string;
};

function parseProgress(job: JobStatus | undefined): ScanProgress | null {
  const raw = job?.result?.progress;
  if (!raw || typeof raw !== "object") return null;
  const p = raw as Record<string, unknown>;
  const total = Number(p.suburbs_total);
  const checked = Number(p.suburbs_checked);
  if (!Number.isFinite(total) || total <= 0) return null;
  return {
    suburbs_checked: Number.isFinite(checked) ? checked : 0,
    suburbs_total: total,
    found: Number(p.found) || 0,
    rows_inserted: Number(p.rows_inserted) || 0,
    keyword: typeof p.keyword === "string" ? p.keyword : undefined,
  };
}

const SCAN_JOB_STORAGE_KEY = "rankpilot_active_scan_job";
const SCAN_STALE_MS = 15 * 60 * 1000; // 15 minutes without updates => consider stuck

export function getStoredScanJobId(): string | null {
  try {
    return sessionStorage.getItem(SCAN_JOB_STORAGE_KEY);
  } catch {
    return null;
  }
}

export function storeScanJobId(jobId: string) {
  try {
    sessionStorage.setItem(SCAN_JOB_STORAGE_KEY, jobId);
  } catch {
    /* ignore */
  }
}

export function clearStoredScanJobId() {
  try {
    sessionStorage.removeItem(SCAN_JOB_STORAGE_KEY);
  } catch {
    /* ignore */
  }
}

/** Poll job status and refresh ranks/dashboard while a Maps scan runs. */
export function useActiveScanPolling(activeJobId: string | null) {
  const qc = useQueryClient();

  const jobQuery = useQuery({
    queryKey: ["job", activeJobId],
    queryFn: () => fetchJobStatus(activeJobId!),
    enabled: Boolean(activeJobId),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      if (status === "queued" || status === "running") return 4_000;
      return false;
    },
  });

  const status = jobQuery.data?.status;
  const isScanning = status === "queued" || status === "running";
  const progress = parseProgress(jobQuery.data);

  useEffect(() => {
    if (!jobQuery.data) return;
    const updatedAtMs = Date.parse(jobQuery.data.updated_at);
    const isStaleActiveJob =
      isScanning &&
      Number.isFinite(updatedAtMs) &&
      Date.now() - updatedAtMs > SCAN_STALE_MS;

    if (isStaleActiveJob) {
      // Worker was likely interrupted (dev reload/crash). Stop sticky "Scanning…" UI loop.
      clearStoredScanJobId();
      void qc.invalidateQueries({ queryKey: ["dashboard"] });
      void qc.invalidateQueries({ queryKey: ["ranks"] });
      void qc.invalidateQueries({ queryKey: ["opportunities"] });
      return;
    }

    if (isScanning) {
      void qc.invalidateQueries({ queryKey: ["ranks"] });
      void qc.invalidateQueries({ queryKey: ["dashboard"] });
      void qc.invalidateQueries({ queryKey: ["opportunities"] });
    }
    if (status === "succeeded" || status === "failed") {
      void qc.invalidateQueries({ queryKey: ["ranks"] });
      void qc.invalidateQueries({ queryKey: ["dashboard"] });
      void qc.invalidateQueries({ queryKey: ["opportunities"] });
      void qc.invalidateQueries({ queryKey: ["keywords"] });
      clearStoredScanJobId();
    }
  }, [jobQuery.data?.updated_at, isScanning, status, qc]);

  return {
    job: jobQuery.data,
    isScanning,
    progress,
    isLoading: jobQuery.isLoading,
    error: jobQuery.error,
  };
}
