import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useRef } from "react";
import { CheckCircle2 } from "lucide-react";

import { fetchCitations, syncCitations } from "../api/citations";
import { formatApiError } from "../api/client";
import { fetchMe } from "../api/onboarding";
import { useAuthStore } from "../stores/authStore";
import type { CitationRow } from "../api/types";
import { TopBar } from "../components/layout/TopBar";
import { Card, CardHeader } from "../components/ui/Card";
import { Badge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";

/* ── Status helpers ────────────────────────────────────────────── */
function statusTone(status: string, drift: boolean): "green" | "red" | "amber" | "blue" {
  if (status === "consistent" && !drift) return "green";
  if (status === "missing") return "red";
  if (drift || status === "inconsistent") return "amber";
  if (status === "fixing" || status === "queued") return "amber";
  return "blue";
}

function statusLabel(status: string, drift: boolean): string {
  if (status === "consistent" && !drift) return "Fixed ✓";
  if (status === "missing") return "Missing";
  if (drift) return "Needs manual fix";
  if (status === "inconsistent") return "Inconsistent";
  if (status === "fixing") return "Fixing…";
  if (status === "queued") return "Queued";
  return status;
}

/* ── KPI card ──────────────────────────────────────────────────── */
function SummaryCard({ label, value, color }: { label: string; value: number; color?: string }) {
  return (
    <div className="rounded-xl border border-rp-border bg-white px-5 py-4 shadow-card">
      <div className="text-[11px] font-semibold uppercase tracking-wide text-rp-tlight">{label}</div>
      <div className={`mt-1 text-[32px] font-extrabold leading-none ${color ?? "text-navy"}`}>{value}</div>
    </div>
  );
}

/* ── Per-field wrong/correct renderer ─────────────────────────── */
function WrongValueCell({ item, canonical: _canonical }: { item: CitationRow; canonical: string }) {
  if (item.status === "missing") {
    return <span className="text-red-500 italic">No listing found</span>;
  }

  const sn = item.scraped_nap;
  if (!sn) {
    return (
      <span className="italic text-rp-tlight">
        {item.drift_flag ? "Directory value differs" : "—"}
      </span>
    );
  }

  const rows: { field: string; value: string | null; ok: boolean }[] = [
    { field: "Name",    value: sn.name,    ok: sn.name_ok },
    { field: "Address", value: sn.address, ok: sn.address_ok },
    { field: "Phone",   value: sn.phone,   ok: sn.phone_ok },
  ].filter((r) => r.value);

  if (!rows.length) {
    return <span className="italic text-rp-tlight">{item.drift_flag ? "Directory value differs" : "—"}</span>;
  }

  return (
    <div className="space-y-0.5">
      {rows.map((r) => (
        <div key={r.field} className="flex items-center gap-1.5 text-[12px]">
          <span className="w-14 shrink-0 text-[10px] font-bold uppercase text-rp-tlight">{r.field}</span>
          {r.ok ? (
            <span className="text-emerald-700">{r.value}</span>
          ) : (
            <span className="text-red-500 line-through">{r.value}</span>
          )}
        </div>
      ))}
    </div>
  );
}

function CorrectValueCell({ item, canonicalName, canonicalAddr, canonicalPhone }: {
  item: CitationRow;
  canonicalName: string;
  canonicalAddr: string;
  canonicalPhone: string;
}) {
  if (item.status === "missing") {
    return <span className="text-emerald-700">Create listing with canonical NAP</span>;
  }

  const sn = item.scraped_nap;
  const rows: { field: string; correct: string; ok: boolean }[] = [
    { field: "Name",    correct: canonicalName,  ok: sn?.name_ok    ?? false },
    { field: "Address", correct: canonicalAddr,  ok: sn?.address_ok ?? false },
    { field: "Phone",   correct: canonicalPhone, ok: sn?.phone_ok   ?? false },
  ].filter((r) => r.correct && r.correct !== "Not found yet");

  if (!sn || !rows.length) {
    return (
      <span className="text-emerald-700 text-[12px]">
        {[canonicalName, canonicalAddr, canonicalPhone].filter(Boolean).join(" · ")}
      </span>
    );
  }

  // Only show rows where there's actually a mismatch to fix
  const toFix = rows.filter((r) => !r.ok);
  const toShow = toFix.length ? toFix : rows.slice(0, 1);

  return (
    <div className="space-y-0.5">
      {toShow.map((r) => (
        <div key={r.field} className="flex items-center gap-1.5 text-[12px] text-emerald-700">
          <CheckCircle2 className="h-3 w-3 shrink-0" />
          <span>{r.correct}</span>
        </div>
      ))}
    </div>
  );
}

/* ── Main page ─────────────────────────────────────────────────── */
export function CitationsPage() {
  const token = useAuthStore((s) => s.accessToken);
  const qc = useQueryClient();
  const syncTriggered = useRef(false);

  const me = useQuery({ queryKey: ["me", token], queryFn: fetchMe, enabled: Boolean(token) });
  const citations = useQuery({
    queryKey: ["citations", token],
    queryFn: fetchCitations,
    enabled: Boolean(token),
  });

  const syncMut = useMutation({
    mutationFn: syncCitations,
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ["citations", token] });
      await qc.invalidateQueries({ queryKey: ["me", token] });
    },
  });

  const latestCheckedAt = useMemo(() => {
    const stamps = (citations.data?.items ?? [])
      .map((x) => (x.last_checked ? new Date(x.last_checked).getTime() : 0))
      .filter((x) => Number.isFinite(x) && x > 0);
    return stamps.length ? new Date(Math.max(...stamps)) : null;
  }, [citations.data?.items]);

  useEffect(() => {
    if (!token || syncTriggered.current) return;
    if (!citations.isSuccess && !citations.isError) return;
    const items = citations.data?.items ?? [];
    const hasRecent = items.some((x) => {
      if (!x.last_checked) return false;
      return Date.now() - new Date(x.last_checked).getTime() < 24 * 60 * 60 * 1000;
    });
    syncTriggered.current = true;
    if (!items.length || !hasRecent) void syncMut.mutate();
  }, [token, citations.isSuccess, citations.isError, citations.data?.items, syncMut]);

  const items = citations.data?.items ?? [];
  const total       = items.length;
  const consistent  = items.filter((i) => i.status === "consistent" && !i.drift_flag).length;
  const bad         = items.filter((i) => i.status !== "consistent" || i.drift_flag).length;
  const fixedMonth  = items.filter((i) => i.status === "consistent").length;

  /* Split: inconsistencies in a separate table, consistent at bottom */
  const badItems  = items.filter((i) => i.status !== "consistent" || i.drift_flag);
  const goodItems = items.filter((i) => i.status === "consistent" && !i.drift_flag);

  const canonicalName  = me.data?.business_name?.trim()    || syncMut.data?.canonical?.name    || "Not set";
  const canonicalAddr  = me.data?.business_address?.trim() || syncMut.data?.canonical?.address || "Not found yet";
  const canonicalPhone = me.data?.business_phone?.trim()   || syncMut.data?.canonical?.phone   || "Not found yet";
  const canonicalSource = syncMut.data?.canonical?.source === "google_places"
    ? "Google Places API + Firecrawl scan"
    : syncMut.data?.canonical?.source === "firecrawl_website"
      ? "Website (Firecrawl) + directory scan"
      : "Profile + Firecrawl scan";

  return (
    <>
      <TopBar
        title="Citation & NAP Auditor"
        subtitle="Live directory consistency — Name, Address, Phone scraped from each listing"
        actions={
          <Button size="sm" type="button" disabled={syncMut.isPending} onClick={() => void syncMut.mutate()}>
            {syncMut.isPending ? "Syncing…" : "Sync Now"}
          </Button>
        }
      />
      <div className="flex-1 overflow-y-auto bg-rp-light px-7 py-6">

        {/* Status messages */}
        {syncMut.isPending && (
          <p className="mb-3 text-xs text-rp-tlight">Scraping {total || "8"} directories via Firecrawl…</p>
        )}
        {!syncMut.isPending && latestCheckedAt && (
          <p className="mb-3 text-xs text-rp-tlight">
            Last synced: {latestCheckedAt.toLocaleString("en-AU")}
          </p>
        )}
        {syncMut.isError && (
          <p className="mb-3 text-xs text-red-600">{formatApiError(syncMut.error)}</p>
        )}
        {syncMut.isSuccess && syncMut.data?.error && (
          <p className="mb-3 text-xs text-amber-700">{syncMut.data.error}</p>
        )}
        {syncMut.isSuccess && !syncMut.data?.error && (
          <p className="mb-3 text-xs text-emerald-700">
            Sync complete — checked {syncMut.data.updated} directories
            {syncMut.data.warnings?.length ? ` · ${syncMut.data.warnings.length} warning(s)` : ""}.
          </p>
        )}
        {(citations.isError || me.isError) && (
          <p className="mb-3 text-sm text-red-500">
            {formatApiError((citations.error ?? me.error) as Error)}
          </p>
        )}

        <div className="space-y-4">

          {/* ── KPI cards ──────────────────────────────────────── */}
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <SummaryCard label="Directories Scanned"   value={total} />
            <SummaryCard label="Consistent (Correct)"  value={consistent} color="text-emerald-600" />
            <SummaryCard label="Inconsistencies Found" value={bad}         color="text-red-500" />
            <SummaryCard label="Fixed This Month"      value={fixedMonth}  color="text-[#72C219]" />
          </div>

          {/* ── Canonical NAP ──────────────────────────────────── */}
          <Card>
            <CardHeader title="Correct Business Details (Canonical NAP)" />
            <div className="px-4 pt-1 text-[11px] text-rp-tlight">Source: {canonicalSource}</div>
            <div className="grid gap-3 p-4 md:grid-cols-3">
              {[
                { label: "Business Name (N)", value: canonicalName },
                { label: "Address (A)",       value: canonicalAddr },
                { label: "Phone (P)",         value: canonicalPhone },
              ].map((f) => (
                <div key={f.label} className="rounded-lg border border-emerald-200 bg-emerald-50 p-3">
                  <div className="text-[10px] font-bold uppercase text-emerald-700">{f.label}</div>
                  <div className="mt-1 text-[13px] font-semibold text-navy">{f.value}</div>
                </div>
              ))}
            </div>
            {(canonicalAddr === "Not found yet" || canonicalPhone === "Not found yet") && (
              <div className="px-4 pb-4 text-[12px] text-amber-700">
                Click <strong>Sync Now</strong> to fetch address &amp; phone from Google Places + Firecrawl.
              </div>
            )}
          </Card>

          {/* ── Inconsistencies table ──────────────────────────── */}
          <Card>
            <CardHeader
              title={`Inconsistencies Found — Action Required`}
              subtitle={`Canonical NAP: ${canonicalName} · ${canonicalAddr} · ${canonicalPhone}`}
            />
            <div className="overflow-x-auto">
              <table className="w-full border-collapse text-left">
                <thead>
                  <tr className="border-b border-rp-border bg-rp-light text-[11px] font-bold uppercase tracking-wide text-rp-tlight">
                    <th className="px-4 py-3 w-36">Directory</th>
                    <th className="px-4 py-3 w-20">Field</th>
                    <th className="px-4 py-3">Wrong Value Found</th>
                    <th className="px-4 py-3">Correct Value</th>
                    <th className="px-4 py-3 w-36">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {badItems.length === 0 ? (
                    <tr>
                      <td colSpan={5} className="px-4 py-8 text-center text-sm text-rp-tlight">
                        {total === 0
                          ? "No data yet — click Sync Now to run live directory checks."
                          : "All directories are consistent!"}
                      </td>
                    </tr>
                  ) : (
                    badItems.map((item) => {
                      const sn = item.scraped_nap;
                      const badFields = sn
                        ? [
                            !sn.name_ok    && sn.name    ? "Name"    : null,
                            !sn.address_ok && sn.address ? "Address" : null,
                            !sn.phone_ok   && sn.phone   ? "Phone"   : null,
                          ].filter(Boolean).join(", ") || "NAP"
                        : item.status === "missing" ? "Listing" : "NAP";

                      return (
                        <tr key={item.id} className="border-b border-[#F0F4F9] hover:bg-[#FAFBFD]">
                          <td className="px-4 py-3 text-[13px] font-semibold text-navy">{item.directory}</td>
                          <td className="px-4 py-3 text-[12px] text-rp-tmid">{badFields}</td>
                          <td className="px-4 py-3">
                            <WrongValueCell item={item} canonical={`${canonicalName} · ${canonicalAddr} · ${canonicalPhone}`} />
                          </td>
                          <td className="px-4 py-3">
                            <CorrectValueCell
                              item={item}
                              canonicalName={canonicalName}
                              canonicalAddr={canonicalAddr}
                              canonicalPhone={canonicalPhone}
                            />
                          </td>
                          <td className="px-4 py-3">
                            <Badge tone={statusTone(item.status, item.drift_flag)}>
                              {statusLabel(item.status, item.drift_flag)}
                            </Badge>
                          </td>
                        </tr>
                      );
                    })
                  )}
                </tbody>
              </table>
            </div>
          </Card>

          {/* ── Consistent listings (collapsed) ────────────────── */}
          {goodItems.length > 0 && (
            <Card>
              <CardHeader
                title={`Consistent Listings (${goodItems.length})`}
                subtitle="These directories have matching NAP data"
              />
              <div className="overflow-x-auto">
                <table className="w-full border-collapse text-left">
                  <thead>
                    <tr className="border-b border-rp-border bg-rp-light text-[11px] font-bold uppercase tracking-wide text-rp-tlight">
                      <th className="px-4 py-2">Directory</th>
                      <th className="px-4 py-2">Name</th>
                      <th className="px-4 py-2">Address</th>
                      <th className="px-4 py-2">Phone</th>
                      <th className="px-4 py-2">Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {goodItems.map((item) => {
                      const sn = item.scraped_nap;
                      return (
                        <tr key={item.id} className="border-b border-[#F0F4F9]">
                          <td className="px-4 py-2 text-[12px] font-semibold text-navy">{item.directory}</td>
                          <td className="px-4 py-2 text-[12px] text-emerald-700">
                            <span className="inline-flex items-center gap-1">
                              <CheckCircle2 className="h-3 w-3" />{sn?.name ?? canonicalName}
                            </span>
                          </td>
                          <td className="px-4 py-2 text-[12px] text-emerald-700">
                            <span className="inline-flex items-center gap-1">
                              <CheckCircle2 className="h-3 w-3" />{sn?.address ?? canonicalAddr}
                            </span>
                          </td>
                          <td className="px-4 py-2 text-[12px] text-emerald-700">
                            <span className="inline-flex items-center gap-1">
                              <CheckCircle2 className="h-3 w-3" />{sn?.phone ?? canonicalPhone}
                            </span>
                          </td>
                          <td className="px-4 py-2">
                            <Badge tone="green">Fixed ✓</Badge>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </Card>
          )}

        </div>
      </div>
    </>
  );
}
