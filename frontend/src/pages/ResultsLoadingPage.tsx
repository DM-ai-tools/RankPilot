import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import { fetchCitations } from "../api/citations";
import { fetchContentQueue } from "../api/contentQueue";
import { fetchIntegrationsStatus } from "../api/integrations";
import { fetchJobStatus } from "../api/jobs";
import { fetchDashboardOverview } from "../api/overview";
import { fetchOpportunities } from "../api/opportunities";
import { fetchSuburbRanks } from "../api/ranks";
import { useAuthStore } from "../stores/authStore";

/** After this, auto-redirect to dashboard if GSC+GA4 are ready (do not block on full Maps scan). */
const SCAN_AUTO_CONTINUE_MS = 90 * 1000;
/** "Slow scan" copy — informational only. */
const SCAN_SLOW_MESSAGE_MS = 3 * 60 * 1000;

function StatusRow({ label, ok, waitingText }: { label: string; ok: boolean; waitingText: string }) {
  return (
    <div className="flex items-center justify-between rounded-lg border border-rp-border bg-white px-3 py-2">
      <span className="text-[12px] font-semibold text-navy">{label}</span>
      <span className={`text-[11px] font-bold ${ok ? "text-emerald-600" : "text-amber-600"}`}>
        {ok ? "Connected" : waitingText}
      </span>
    </div>
  );
}

export function ResultsLoadingPage() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [params] = useSearchParams();
  const token = useAuthStore((s) => s.accessToken);
  const setNeedsOnboarding = useAuthStore((s) => s.setNeedsOnboarding);
  const jobId = params.get("job");

  const integrations = useQuery({
    queryKey: ["integrations-status", token],
    queryFn: fetchIntegrationsStatus,
    enabled: Boolean(token),
    refetchInterval: 3000,
  });

  const job = useQuery({
    queryKey: ["job-status", jobId, token],
    queryFn: () => fetchJobStatus(jobId ?? ""),
    enabled: Boolean(token && jobId),
    refetchInterval: (q) => (q.state.data?.status === "succeeded" || q.state.data?.status === "failed" ? false : 3000),
  });

  const gscConnected = Boolean(integrations.data?.gsc?.connected);
  const ga4Connected = Boolean(integrations.data?.ga4?.connected);
  const gscPropertySelected = Boolean(integrations.data?.gsc?.extra?.selected_property);
  const ga4PropertySelected = Boolean(integrations.data?.ga4?.extra?.selected_property);
  const scanDone = job.data?.status === "succeeded";
  const scanFailed = job.data?.status === "failed";
  const scanPending = Boolean(
    jobId && job.data?.status && job.data.status !== "succeeded" && job.data.status !== "failed",
  );
  const [nowTick, setNowTick] = useState(() => Date.now());
  useEffect(() => {
    if (!scanPending) return;
    const id = window.setInterval(() => setNowTick(Date.now()), 5_000);
    return () => window.clearInterval(id);
  }, [scanPending]);
  const scanElapsedMs = useMemo(() => {
    if (!job.data?.created_at) return 0;
    const started = new Date(job.data.created_at).getTime();
    if (Number.isNaN(started)) return 0;
    return nowTick - started;
  }, [job.data?.created_at, nowTick]);

  /** Maps job still running but long enough we should not block the whole UX on it. */
  const scanPastAutoContinue = scanPending && scanElapsedMs > SCAN_AUTO_CONTINUE_MS;
  const scanShowSlowBanner = scanPending && scanElapsedMs > SCAN_SLOW_MESSAGE_MS;

  const integrationsReady =
    gscConnected && ga4Connected && gscPropertySelected && ga4PropertySelected;

  /** Auto-leave this page once integrations are done and the scan finished, failed, or hit the soft timeout. */
  const readyForDashboard = useMemo(
    () =>
      integrationsReady &&
      (scanDone || scanFailed || scanPastAutoContinue),
    [integrationsReady, scanDone, scanFailed, scanPastAutoContinue],
  );

  /** Manual "Continue" as soon as GSC+GA4 are wired — Maps can still be running in the background. */
  const allowManualDashboard = integrationsReady;

  useEffect(() => {
    if (!readyForDashboard) return;
    let cancelled = false;
    const warm = async () => {
      await Promise.all([
        qc.fetchQuery({ queryKey: ["dashboard", "overview", token], queryFn: fetchDashboardOverview }),
        qc.fetchQuery({ queryKey: ["ranks", "suburbs", token], queryFn: fetchSuburbRanks }),
        qc.fetchQuery({ queryKey: ["opportunities", token], queryFn: fetchOpportunities }),
        qc.fetchQuery({ queryKey: ["content-queue", token], queryFn: fetchContentQueue }),
        qc.fetchQuery({ queryKey: ["citations", token], queryFn: fetchCitations }),
      ]);
      if (cancelled) return;
      setNeedsOnboarding(false);
      void navigate("/", { replace: true });
    };
    void warm();
    return () => {
      cancelled = true;
    };
  }, [navigate, qc, readyForDashboard, setNeedsOnboarding, token]);

  if (!token) {
    void navigate("/login", { replace: true });
    return null;
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-rp-light px-4 py-10">
      <div className="w-full max-w-[620px] rounded-2xl border border-rp-border bg-white p-8 shadow-card">
        <div className="mb-5 flex items-center gap-3">
          <div className="h-9 w-9 animate-spin rounded-full border-4 border-rp-border border-t-orange" />
          <div>
            <h1 className="text-[18px] font-extrabold text-navy">Preparing your SEO dashboard</h1>
            <p className="text-[12px] text-rp-tlight">
              Connecting integrations, processing SERP scan, and loading your results.
            </p>
          </div>
        </div>

        <div className="space-y-2.5">
          <StatusRow label="Google Search Console OAuth" ok={gscConnected} waitingText="Waiting..." />
          <StatusRow label="GSC Property Selected" ok={gscPropertySelected} waitingText="Select property..." />
          <StatusRow label="Google Analytics 4 OAuth" ok={ga4Connected} waitingText="Waiting..." />
          <StatusRow label="GA4 Property Selected" ok={ga4PropertySelected} waitingText="Select property..." />
          <StatusRow
            label="Maps SERP Scan"
            ok={scanDone}
            waitingText={
              scanFailed
                ? "Failed"
                : !jobId
                  ? "Missing job id"
                  : scanPastAutoContinue
                    ? "Still running (you can open dashboard)"
                    : "Running..."
            }
          />
        </div>

        {scanFailed ? (
          <div className="mt-4 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-[12px] text-red-700">
            Scan failed: {job.data?.error_message || "Unknown error"}.
          </div>
        ) : null}

        {!jobId ? (
          <div className="mt-4 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-[12px] text-amber-700">
            No scan job id found. Please run the scan again from onboarding.
          </div>
        ) : null}

        {scanShowSlowBanner && !scanFailed ? (
          <div className="mt-4 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-[12px] text-amber-800">
            The Maps scan can take many minutes (DataForSEO checks each suburb). After about 90 seconds we still move
            you on if Google integrations are ready — refresh the dashboard later for full suburb ranks.
          </div>
        ) : null}

        <div className="mt-6 flex justify-end gap-2">
          <button
            type="button"
            className="rounded-md border border-rp-border px-3 py-2 text-[12px] font-semibold text-rp-tmid hover:bg-rp-light"
            onClick={() => void navigate("/onboarding", { replace: true })}
          >
            Back to Onboarding
          </button>
          <button
            type="button"
            className="rounded-md px-3 py-2 text-[12px] font-semibold text-white disabled:opacity-50"
            style={{ backgroundColor: "#72C219" }}
            disabled={!allowManualDashboard}
            onClick={() => {
              setNeedsOnboarding(false);
              void navigate("/", { replace: true });
            }}
          >
            Continue to Dashboard
          </button>
        </div>
      </div>
    </div>
  );
}

