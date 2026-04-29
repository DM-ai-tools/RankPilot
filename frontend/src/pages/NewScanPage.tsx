import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CircleAlert, CircleCheck } from "lucide-react";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { formatApiError } from "../api/client";
import { fetchMe } from "../api/onboarding";
import { enqueueMapsScan } from "../api/scans";
import { TopBar } from "../components/layout/TopBar";
import { Button } from "../components/ui/Button";
import { Card, CardHeader } from "../components/ui/Card";
import { useAuthStore } from "../stores/authStore";

const AU_METROS = [
  "Melbourne, VIC",
  "Sydney, NSW",
  "Brisbane, QLD",
  "Perth, WA",
  "Adelaide, SA",
];

const RADIUS_OPTIONS = [
  { km: 10, label: "10 km",  hint: "~15 suburbs" },
  { km: 25, label: "25 km",  hint: "~35 suburbs ✓" },
  { km: 50, label: "50 km",  hint: "~60 suburbs" },
  { km: 0,  label: "Custom", hint: "Enter km" },
];

type Step = 1 | 2 | 3 | 4;

function StepBar({ current }: { current: Step }) {
  const steps: { num: number; title: string; sub: string }[] = [
    { num: 1, title: "Business", sub: "Verify URL" },
    { num: 2, title: "Keywords", sub: "Configure scan" },
    { num: 3, title: "Location", sub: "Set radius" },
    { num: 4, title: "Review",   sub: "Confirm & run" },
  ];
  return (
    <div className="mb-6 flex overflow-hidden rounded-xl border border-rp-border bg-white">
      {steps.map((s) => {
        const done   = s.num < current;
        const active = s.num === current;
        return (
          <div
            key={s.num}
            className={`flex flex-1 items-center gap-3 border-r border-rp-border px-5 py-4 last:border-r-0 ${
              done ? "bg-emerald-50" : active ? "bg-[#72C219]/5" : ""
            }`}
          >
            <div
              className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-xs font-bold ${
                done   ? "bg-emerald-500 text-white" :
                active ? "bg-[#72C219] text-white"      :
                         "bg-rp-border text-rp-tlight"
              }`}
            >
              {done ? "✓" : s.num}
            </div>
            <div>
              <div className="text-xs font-semibold text-navy">{s.title}</div>
              <div className="text-[11px] text-rp-tlight">{s.sub}</div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

export function NewScanPage() {
  const navigate = useNavigate();
  const qc       = useQueryClient();
  const token    = useAuthStore((s) => s.accessToken);

  const profile = useQuery({
    queryKey: ["me"],
    queryFn:  fetchMe,
    enabled:  Boolean(token),
  });

  const prof = profile.data;
  const [step,        setStep]        = useState<Step>(1);
  const [businessUrl, setBusinessUrl] = useState("");
  const [keyword,     setKeyword]     = useState("");
  const [metro,       setMetro]       = useState("Melbourne, VIC");
  const [radiusKm,    setRadiusKm]    = useState(25);
  const [customKm,    setCustomKm]    = useState("");

  // Pre-fill once when profile data arrives
  useEffect(() => {
    if (!prof) return;
    if (prof.business_url)    setBusinessUrl(prof.business_url);
    if (prof.primary_keyword) setKeyword(prof.primary_keyword);
    if (prof.metro_label)     setMetro(prof.metro_label);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [prof?.client_id]);           // run once per client, not on every field change

  const domain = (() => {
    try {
      const u = businessUrl.startsWith("http") ? businessUrl : `https://${businessUrl}`;
      return new URL(u).hostname.replace(/^www\./, "");
    } catch { return businessUrl || ""; }
  })();

  const effectiveRadius  = radiusKm === 0 ? (Number(customKm) || 25) : radiusKm;
  const approxSuburbs    = effectiveRadius <= 10 ? "~15" : effectiveRadius <= 25 ? "~25" : "~40";
  const estimatedCostAUD = ((effectiveRadius <= 10 ? 15 : effectiveRadius <= 25 ? 35 : 60) * 0.001).toFixed(2);

  const scan = useMutation({
    mutationFn: () => enqueueMapsScan({ keyword, radius_km: effectiveRadius }),
    onSuccess:  () => {
      void qc.invalidateQueries({ queryKey: ["ranks"] });
      void qc.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });

  if (profile.isLoading) {
    return (
      <>
        <TopBar title="Run a New Scan" subtitle="Loading your profile…" />
        <div className="flex-1 bg-rp-light px-7 py-10">
          <p className="text-sm text-rp-tlight">Loading…</p>
        </div>
      </>
    );
  }

  return (
    <>
      <TopBar
        title="Run a New Scan"
        subtitle={`${prof?.business_name ?? "Your business"} — Google Maps visibility scan`}
      />
      <div className="mx-auto max-w-[760px] flex-1 overflow-y-auto bg-rp-light px-7 py-6">
        <StepBar current={step} />

        {/* ── Step 1: Business URL ─────────────────────────────────────── */}
        {step === 1 && (
          <Card>
            <CardHeader title="Verify Business URL" subtitle="Step 1 of 4" />
            <div className="space-y-4 p-5">
              <div>
                <label className="mb-1.5 block text-xs font-semibold text-navy">
                  Business Website URL
                </label>
                <input
                  type="text"
                  value={businessUrl}
                  onChange={(e) => setBusinessUrl(e.target.value)}
                  placeholder="e.g. bugcatchers.com.au"
                  className="w-full rounded-lg border-[1.5px] border-rp-border px-3.5 py-2.5 text-sm text-navy outline-none focus:border-[#72C219]"
                />
                <p className="mt-1 text-[11px] text-rp-tlight">
                  We match this domain against Google Maps results to find your rank position.
                </p>
              </div>

              {domain && (
                <div className="flex items-center gap-2 rounded-lg border-[1.5px] border-emerald-500 bg-emerald-50 px-3.5 py-2.5 text-[13px] font-medium text-emerald-700">
                  <CircleCheck className="h-4 w-4 shrink-0" />
                  <span>
                    <strong>{domain}</strong>
                    {prof?.business_name ? ` — ${prof.business_name}` : ""}
                    {prof?.metro_label   ? ` · ${prof.metro_label}`   : ""}
                  </span>
                </div>
              )}

              <div className="rounded-lg border border-navy/10 bg-navy/[0.04] px-4 py-3 text-[12px] text-rp-tmid">
                <strong>How ranking works:</strong> RankPilot searches{" "}
                <em>{keyword || prof?.primary_keyword || "your keyword"}</em> in Google Maps for each suburb,
                then checks if <strong>{domain || "your domain"}</strong> appears in results and at what position.
              </div>
            </div>
            <div className="flex justify-end border-t border-rp-border px-5 py-4">
              <Button disabled={!businessUrl} onClick={() => setStep(2)}>
                Continue → Configure Keyword
              </Button>
            </div>
          </Card>
        )}

        {/* ── Step 2: Keyword + Metro ───────────────────────────────────── */}
        {step === 2 && (
          <Card>
            <CardHeader title="Business & Keyword Setup" subtitle="Step 2 of 4" />
            <div className="space-y-4 p-5">
              {/* Confirmed URL */}
              <div>
                <label className="mb-1 block text-xs font-semibold text-navy">Business Website URL</label>
                <div className="flex items-center gap-2 rounded-lg border-[1.5px] border-emerald-500 bg-emerald-50 px-3.5 py-2.5 text-[13px] font-medium text-emerald-700">
                  <CircleCheck className="h-4 w-4 shrink-0" />
                  <span className="flex-1">{domain}{prof?.business_name ? ` — ${prof.business_name}` : ""}</span>
                  <button type="button" className="text-[11px] text-[#72C219] hover:underline" onClick={() => setStep(1)}>
                    Change
                  </button>
                </div>
              </div>

              {/* Keyword */}
              <div>
                <label className="mb-1.5 block text-xs font-semibold text-navy">Primary Keyword</label>
                <input
                  type="text"
                  value={keyword}
                  onChange={(e) => setKeyword(e.target.value)}
                  placeholder="e.g. pest control, plumber, electrician"
                  className="w-full rounded-lg border-[1.5px] border-rp-border px-3.5 py-2.5 text-sm text-navy outline-none focus:border-[#72C219]"
                />
                <p className="mt-1 text-[11px] text-rp-tlight">
                  {keyword
                    ? <>We will search <em>"{keyword}"</em> in Google Maps for each suburb.</>
                    : "Enter the service keyword you most want to rank for."}
                  {" "}Use your most commercially valuable search term.
                </p>
              </div>

              {/* Metro */}
              <div>
                <label className="mb-1.5 block text-xs font-semibold text-navy">City / Metro Area</label>
                <select
                  value={metro}
                  onChange={(e) => setMetro(e.target.value)}
                  className="w-full rounded-lg border-[1.5px] border-rp-border px-3.5 py-2.5 text-sm text-navy outline-none focus:border-[#72C219]"
                >
                  {AU_METROS.map((m) => (
                    <option key={m} value={m}>{m}</option>
                  ))}
                </select>
              </div>
            </div>
            <div className="flex items-center justify-between border-t border-rp-border px-5 py-4">
              <Button variant="outline" onClick={() => setStep(1)}>← Back</Button>
              <Button disabled={!keyword.trim()} onClick={() => setStep(3)}>
                Continue → Set Radius
              </Button>
            </div>
          </Card>
        )}

        {/* ── Step 3: Radius ────────────────────────────────────────────── */}
        {step === 3 && (
          <Card>
            <CardHeader title="Search Radius" subtitle="Step 3 of 4" />
            <div className="space-y-4 p-5">
              <p className="text-[13px] text-rp-tmid">
                We scan suburbs within this radius of <strong>{metro.split(",")[0]}</strong> CBD.
              </p>
              <div className="grid grid-cols-4 gap-2.5">
                {RADIUS_OPTIONS.map((r) => {
                  const sel = r.km === 0 ? radiusKm === 0 : radiusKm === r.km;
                  return (
                    <button
                      key={r.km}
                      type="button"
                      onClick={() => setRadiusKm(r.km)}
                      className={`rounded-lg border-[1.5px] p-3 text-center transition-colors ${
                        sel ? "border-[#72C219] bg-[#72C219]/[0.06]" : "border-rp-border hover:border-[#72C219]/50"
                      }`}
                    >
                      <div className={`text-[15px] font-bold ${sel ? "text-[#72C219]" : "text-rp-tmid"}`}>{r.label}</div>
                      <div className={`mt-0.5 text-[10px] ${sel ? "text-[#72C219]" : "text-rp-tlight"}`}>{r.hint}</div>
                    </button>
                  );
                })}
              </div>
              {radiusKm === 0 && (
                <div>
                  <label className="mb-1 block text-xs font-semibold text-navy">Custom radius (km)</label>
                  <input
                    type="number" min="5" max="200"
                    value={customKm}
                    onChange={(e) => setCustomKm(e.target.value)}
                    placeholder="e.g. 35"
                    className="w-40 rounded-lg border-[1.5px] border-rp-border px-3 py-2 text-sm text-navy outline-none focus:border-[#72C219]"
                  />
                </div>
              )}
              <div className="flex gap-2 rounded-lg border border-navy/10 bg-navy/[0.04] px-4 py-3 text-[13px] text-rp-tmid">
                <CircleAlert className="mt-0.5 h-4 w-4 shrink-0 text-teal" />
                <span>
                  This scan checks <strong>{approxSuburbs} suburbs</strong> around{" "}
                  <strong>{metro.split(",")[0]}</strong> for{" "}
                  <strong>"{keyword}"</strong>. Results ready in <strong>3–5 min</strong>.
                </span>
              </div>
            </div>
            <div className="flex items-center justify-between border-t border-rp-border px-5 py-4">
              <Button variant="outline" onClick={() => setStep(2)}>← Back</Button>
              <Button onClick={() => setStep(4)}>Continue → Review</Button>
            </div>
          </Card>
        )}

        {/* ── Step 4: Review & Run ──────────────────────────────────────── */}
        {step === 4 && (
          <Card>
            <CardHeader title="Review & Run Scan" subtitle="Step 4 of 4 — confirm then launch" />
            <div className="space-y-3 p-5">
              {[
                { label: "Business URL",  value: domain },
                { label: "Keyword",       value: keyword },
                { label: "Metro",         value: metro },
                { label: "Radius",        value: `${effectiveRadius} km (${approxSuburbs} suburbs)` },
              ].map((row) => (
                <div key={row.label} className="flex items-center justify-between rounded-lg bg-rp-light px-4 py-2.5">
                  <span className="text-[11px] font-bold uppercase tracking-wide text-rp-tlight">{row.label}</span>
                  <span className="text-[13px] font-bold text-navy">{row.value}</span>
                </div>
              ))}

              <div className="rounded-lg border border-navy/10 bg-navy/[0.04] px-4 py-3 text-[12px] text-rp-tmid">
                RankPilot calls <strong>DataForSEO Maps API</strong> for each suburb,
                matches <strong>{domain}</strong> in results, and writes rank positions to your database.
                Dashboard updates automatically when the scan completes.
              </div>

              {scan.isError && (
                <p className="text-sm text-red-600">{formatApiError(scan.error)}</p>
              )}

              {scan.isSuccess && (
                <div className="rounded-lg border border-emerald-500/25 bg-emerald-50 px-4 py-4">
                  <p className="text-[13px] font-bold text-emerald-800">
                    Scan queued successfully. Job ID:{" "}
                    <code className="rounded bg-white px-1.5 py-0.5 text-navy">{scan.data.job_id}</code>
                  </p>
                  <p className="mt-1 text-[12px] text-emerald-700">
                    Worker picks up jobs every 30 s. Rankings appear on the dashboard in 3–5 minutes.
                  </p>
                  <button
                    type="button"
                    onClick={() => void navigate("/")}
                    className="mt-3 text-sm font-bold text-[#72C219] hover:underline"
                  >
                    Go to Dashboard →
                  </button>
                </div>
              )}
            </div>
            <div className="flex items-center justify-between border-t border-rp-border px-5 py-4">
              <Button variant="outline" onClick={() => setStep(3)} disabled={scan.isPending || scan.isSuccess}>
                ← Back
              </Button>
              {!scan.isSuccess && (
                <Button disabled={scan.isPending} onClick={() => void scan.mutate()}>
                  {scan.isPending ? "Queuing scan…" : "🔄 Run Scan Now"}
                </Button>
              )}
            </div>
          </Card>
        )}

        <p className="mt-3 flex flex-wrap items-center gap-1.5 px-1 text-[11px] text-rp-tlight">
          Estimated scan cost:{" "}
          <span className="font-bold text-navy">~AUD ${estimatedCostAUD}</span>
          <span>·</span>
          <span>Consumed from your DataForSEO balance</span>
        </p>
      </div>
    </>
  );
}
