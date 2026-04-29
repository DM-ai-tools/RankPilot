import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Building2,
  CheckCircle2,
  CircleHelp,
  FilePenLine,
  FileText,
  PencilLine,
  Wrench,
} from "lucide-react";
import type { ReactNode } from "react";
import type { ComponentType } from "react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";

import { formatApiError } from "../api/client";
import {
  approveAll,
  fetchContentQueue,
  generateContent,
  purgeShellQueueItems,
  type ContentItem,
  updateItemStatus,
} from "../api/contentQueue";
import { MarkdownBody } from "../components/content/MarkdownBody";
import { TopBar } from "../components/layout/TopBar";
import { MetricCard } from "../components/ui/MetricCard";
import { Badge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { Card, CardHeader } from "../components/ui/Card";
import { derivePreviewDraft } from "../lib/contentPreviewDerived";
import { useAuthStore } from "../stores/authStore";

/* ── type & icon maps ────────────────────────────────────────── */
const TYPE_ICON: Record<string, ComponentType<{ className?: string }>> = {
  landing_page: FileText,
  gbp_description: Building2,
  blog_post: FilePenLine,
  faq: CircleHelp,
  schema: Wrench,
};

const STATUS_TONE: Record<string, "amber" | "green" | "teal" | "red" | "blue"> = {
  pending:   "amber",
  approved:  "green",
  published: "teal",
  rejected:  "red",
};

function statusLabel(status: string) {
  switch (status) {
    case "pending":   return "Generating…";
    case "approved":  return "Ready to Publish";
    case "published": return "Published ✓";
    case "rejected":  return "Rejected";
    default:          return status;
  }
}

function SignalPill({ ok, children }: { ok: boolean; children: ReactNode }) {
  if (ok) {
    return (
      <span className="inline-block max-w-[200px] truncate align-middle" title={String(children)}>
        <Badge tone="green" className="max-w-full">
          {children} ✓
        </Badge>
      </span>
    );
  }
  return (
    <span
      className="inline-flex max-w-[200px] truncate rounded-full border border-dashed border-rp-border bg-[#FAFBFC] px-2.5 py-0.5 text-[10px] font-medium text-rp-tlight"
      title={`${String(children)} — not found in this draft`}
    >
      {String(children)} — not in draft
    </span>
  );
}

function SectionLabel({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <div className={`text-[9px] font-bold uppercase tracking-[0.08em] text-rp-tlight ${className}`}>{children}</div>
  );
}

/* ── Content preview panel ───────────────────────────────────── */
function ContentPreview({ item }: { item: ContentItem }) {
  const body = item.body?.trim() ?? "";

  const derived = useMemo(
    () => derivePreviewDraft(body, item.title ?? "", item.word_count),
    [body, item.title, item.word_count]
  );

  const meta = [
    item.target_url ? `Target: ${item.target_url}` : null,
    item.generated_at ? `Generated: ${new Date(item.generated_at).toLocaleString()}` : null,
    item.published_at ? `Published: ${new Date(item.published_at).toLocaleString()}` : null,
  ].filter(Boolean);

  const { signals } = derived;

  return (
    <div className="space-y-4 p-4">
      {meta.length > 0 ? (
        <div className="flex flex-wrap gap-2">
          {meta.map((m) => (
            <span key={m} className="rounded-full bg-rp-light px-3 py-1 text-[11px] font-medium text-rp-tlight">
              {m}
            </span>
          ))}
        </div>
      ) : null}

      {body ? (
        <>
          <div>
            <SectionLabel>Signals (from this draft)</SectionLabel>
            <p className="mb-2 mt-1 text-[10px] text-rp-tlight">
              Pills update from headings, links, lists, FAQ sections, and JSON-LD blocks in the text — not from a fixed keyword list.
            </p>
            <div className="flex flex-wrap gap-1.5">
              <Badge tone="blue">Word count: {signals.wordCount.toLocaleString()}</Badge>
              <SignalPill ok={signals.hasH1Line}>Markdown H1</SignalPill>
              <SignalPill ok={signals.hasSubheadings}>H2+ sections</SignalPill>
              <SignalPill ok={signals.hasFaqBlock}>FAQ section</SignalPill>
              <SignalPill ok={signals.hasJsonLd}>JSON-LD block</SignalPill>
              <SignalPill ok={signals.hasRelativeLinks}>Relative links</SignalPill>
              <SignalPill ok={signals.hasList}>Lists</SignalPill>
              <SignalPill ok={signals.hasExternalLinks}>External links</SignalPill>
            </div>
          </div>

          <div className="rounded-lg border border-rp-border bg-white p-4 shadow-sm">
            <SectionLabel>Page title (H1)</SectionLabel>
            <h2 className="mt-1 text-[15px] font-bold leading-snug text-navy">{derived.pageTitle}</h2>

            {derived.introMd ? (
              <div className="mt-4 border-t border-rp-border pt-4">
                <SectionLabel>Opening paragraphs</SectionLabel>
                <div className="mt-2">
                  <MarkdownBody markdown={derived.introMd} />
                </div>
              </div>
            ) : (
              <p className="mt-2 text-[11px] italic text-rp-tlight">No separate opening block detected (optional).</p>
            )}
          </div>

          {(derived.faqMd || derived.jsonLdPretty) && (
            <div className="grid gap-3 md:grid-cols-2">
              <div className="rounded-lg border border-sky-200/80 bg-sky-50/40 p-3">
                <SectionLabel>FAQ section (preview)</SectionLabel>
                {derived.faqMd ? (
                  <div className="mt-2 max-h-[220px] overflow-y-auto pr-1">
                    <MarkdownBody markdown={derived.faqMd} />
                  </div>
                ) : (
                  <p className="mt-2 text-[11px] text-rp-tlight">No heading matched “FAQ” / “Frequently asked…” in this draft.</p>
                )}
              </div>
              <div className="rounded-lg border border-rp-border bg-[#1e293b] p-3">
                <SectionLabel className="!text-slate-400">Schema / JSON-LD (from draft)</SectionLabel>
                {derived.jsonLdPretty ? (
                  <pre className="mt-2 max-h-[220px] overflow-auto whitespace-pre-wrap break-words font-mono text-[10px] leading-relaxed text-slate-100">
                    {derived.jsonLdPretty}
                  </pre>
                ) : (
                  <p className="mt-2 text-[11px] text-slate-400">No fenced JSON-LD or ld+json script in this draft.</p>
                )}
              </div>
            </div>
          )}

          <div>
            <SectionLabel>Full draft (markdown)</SectionLabel>
            <div className="mt-2 max-h-[320px] overflow-y-auto rounded-lg border border-rp-border bg-[#FAFBFC] p-4">
              <MarkdownBody markdown={body} />
            </div>
          </div>
        </>
      ) : (
        <div className="rounded-lg border border-[#72C219]/20 bg-[#72C219]/5 p-4 text-[13px] text-rp-tmid">
          <p className="mb-1 font-semibold text-navy">No draft text saved yet</p>
          <p className="text-[12px]">
            Click <strong>Regenerate with AI</strong> to call Claude and replace this queue with fresh drafts.
          </p>
        </div>
      )}

      {item.notes && body ? (
        <div className="rounded-lg bg-rp-light px-3 py-2 text-[12px] text-rp-tlight">
          📝 {item.notes}
        </div>
      ) : null}
      {item.target_url && /^https?:\/\//i.test(item.target_url) ? (
        <div>
          <a
            href={item.target_url}
            target="_blank"
            rel="noreferrer"
            className="text-[12px] font-semibold text-[#72C219] hover:underline"
          >
            Open published WordPress page ↗
          </a>
        </div>
      ) : null}
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════ */
export function ContentQueuePage() {
  const token = useAuthStore((s) => s.accessToken);
  const qc    = useQueryClient();
  const shellPurgeDone = useRef(false);

  const q = useQuery({
    queryKey: ["content-queue"],
    queryFn:  fetchContentQueue,
    enabled:  Boolean(token),
  });

  /* auto-purge shell items */
  useEffect(() => {
    if (!token || shellPurgeDone.current || !q.isSuccess) return;
    const list = q.data?.items ?? [];
    if (!list.length) { shellPurgeDone.current = true; return; }
    const hasTitleOnly = list.some((it) => !it.body?.trim());
    if (!hasTitleOnly) { shellPurgeDone.current = true; return; }
    shellPurgeDone.current = true;
    void purgeShellQueueItems()
      .then(() => void qc.invalidateQueries({ queryKey: ["content-queue"] }))
      .catch(() => { shellPurgeDone.current = false; });
  }, [token, q.isSuccess, q.data?.items, qc]);

  const items        = q.data?.items ?? [];
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const selected     = items.find((i) => i.id === selectedId) ?? items[0] ?? null;

  const statusMut = useMutation({
    mutationFn: ({ id, status }: { id: string; status: string }) => updateItemStatus(id, status),
    onSuccess:  () => void qc.invalidateQueries({ queryKey: ["content-queue"] }),
  });

  const approveAllMut = useMutation({
    mutationFn: approveAll,
    onSuccess:  () => void qc.invalidateQueries({ queryKey: ["content-queue"] }),
  });

  const generateMut = useMutation({
    mutationFn: generateContent,
    onSuccess:  () => {
      setSelectedId(null);
      void qc.invalidateQueries({ queryKey: ["content-queue"] });
    },
  });

  /* derived counts for stat cards */
  const publishedCount = items.filter((i) => i.status === "published").length;
  const pendingCount   = items.filter((i) => i.status === "pending").length;
  const approvedCount  = items.filter((i) => i.status === "approved").length;

  return (
    <>
      <TopBar
        title="Auto-Content Engine"
        subtitle="AI-generated suburb pages, GBP descriptions, and SEO content"
        actions={
          <>
            <Button
              variant="outline"
              size="sm"
              type="button"
              disabled={generateMut.isPending}
              onClick={() => void generateMut.mutate()}
            >
              {generateMut.isPending ? "Writing…" : "Regenerate with AI"}
            </Button>
            <Button
              size="sm"
              type="button"
              disabled={pendingCount === 0 || approveAllMut.isPending}
              onClick={() => void approveAllMut.mutate()}
            >
              {approveAllMut.isPending
                ? "Approving…"
                : approveAllMut.isSuccess
                  ? `Approved ${approveAllMut.data.updated}`
                  : "+ Queue New Page"}
            </Button>
          </>
        }
      />

      <div className="flex-1 overflow-y-auto bg-rp-light px-5 py-[18px]">
        {!token ? (
          <p className="text-sm text-rp-tmid">
            <Link to="/login" className="font-semibold text-[#72C219] hover:underline">Sign in</Link>{" "}
            to view content queue.
          </p>
        ) : q.isLoading ? (
          <p className="text-sm text-rp-tlight">Loading…</p>
        ) : q.isError ? (
          <p className="text-sm text-red-600">{formatApiError(q.error)}</p>
        ) : null}

        {(statusMut.isError || generateMut.isError || approveAllMut.isError) ? (
          <div className="mb-3 rounded-lg border border-red-200 bg-red-50 px-4 py-2.5 text-xs text-red-700">
            {formatApiError(
              (statusMut.error ?? generateMut.error ?? approveAllMut.error) as Error
            )}
          </div>
        ) : null}
        {generateMut.isSuccess && !generateMut.data?.error ? (
          <div className="mb-3 rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-2.5 text-xs text-emerald-800">
            Saved {generateMut.data.generated} draft(s) with full text from Claude.
            {Array.isArray(generateMut.data.warnings) && generateMut.data.warnings.length > 0
              ? ` Partial: ${generateMut.data.warnings.join(" · ")}`
              : ""}
          </div>
        ) : null}
        {generateMut.isSuccess && generateMut.data?.error ? (
          <div className="mb-3 rounded-lg border border-amber-200 bg-amber-50 px-4 py-2.5 text-xs text-amber-800">
            Warning: {generateMut.data.error}
          </div>
        ) : null}

        <p className="mb-3 max-w-3xl text-[11px] leading-relaxed text-rp-tlight">
          <span className="font-semibold text-navy">Landing pages:</span> Publish sends the draft to your site as a
          real <strong>WordPress page</strong> (connect WordPress under Onboarding first).{" "}
          <span className="font-semibold text-navy">GBP descriptions</span> are not posted to WordPress — use
          &quot;Mark published&quot; to track that you copied them into Google Business Profile.
        </p>

        {/* ── 3 stat cards — matches mockup screen 4 ─────────── */}
        <div className="mb-[14px] grid grid-cols-3 gap-3">
          <MetricCard
            label="Pages Published"
            value={publishedCount}
            delta="this session"
          />
          <MetricCard
            label="In Queue"
            value={pendingCount + approvedCount}
            delta="waiting to publish"
          />
          <MetricCard
            label="Total Items"
            value={items.length}
            delta="in content queue"
          />
        </div>

        {/* ── Content Queue table + Preview ──────────────────── */}
        <div className="mb-[14px]">
          {/* Queue table */}
          <Card>
            <CardHeader
              title="Content Queue"
              right={
                pendingCount > 0 ? (
                  <Button
                    size="sm"
                    type="button"
                    disabled={approveAllMut.isPending}
                    onClick={() => void approveAllMut.mutate()}
                  >
                    <CheckCircle2 className="h-3.5 w-3.5" />
                    Approve All
                  </Button>
                ) : undefined
              }
            />
            {items.length === 0 && !q.isLoading ? (
              <div className="flex flex-col items-center justify-center gap-3 px-6 py-10 text-center">
                <div className="rounded-full bg-rp-light p-3 text-[#72C219]">
                  <FilePenLine className="h-5 w-5" />
                </div>
                <div className="text-[13px] font-semibold text-navy">No content yet</div>
                <p className="max-w-sm text-[12px] text-rp-tlight">
                  Click <strong>Regenerate with AI</strong> to call Claude — it will write suburb landing
                  pages for your top-ranked areas and a GBP description.
                </p>
                <Button
                  size="sm"
                  type="button"
                  disabled={generateMut.isPending}
                  onClick={() => void generateMut.mutate()}
                >
                  {generateMut.isPending ? "Writing…" : "Regenerate with AI"}
                </Button>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full border-collapse text-left">
                  <thead>
                    <tr className="border-b border-rp-border bg-rp-light text-[10px] font-bold uppercase tracking-wide text-rp-tlight">
                      <th className="px-4 py-2.5">Suburb Page</th>
                      <th className="px-4 py-2.5">Status</th>
                      <th className="px-4 py-2.5">Words</th>
                      <th className="px-4 py-2.5">Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {items.map((it) => {
                      const isSelected = (selectedId ?? items[0]?.id) === it.id;
                      const TypeIcon = TYPE_ICON[it.content_type] ?? FileText;
                      return (
                        <tr
                          key={it.id}
                          onClick={() => setSelectedId(it.id)}
                          className={`cursor-pointer border-b border-[#F0F4F8] hover:bg-[#FAFBFD] ${
                            isSelected ? "bg-[#72C219]/[0.03]" : ""
                          }`}
                        >
                          <td className="px-4 py-2.5">
                            <span className="mr-1.5 inline-flex h-5 w-5 items-center justify-center rounded-md bg-rp-light text-rp-tmid">
                              <TypeIcon className="h-3.5 w-3.5" />
                            </span>
                            <strong className="text-[12px] font-bold text-navy">
                              {it.title || it.content_type.replace("_", " ")}
                            </strong>
                          </td>
                          <td className="px-4 py-2.5">
                            <Badge tone={STATUS_TONE[it.status] ?? "amber"}>
                              {statusLabel(it.status)}
                            </Badge>
                          </td>
                          <td className="px-4 py-2.5 text-[12px] text-rp-tlight">
                            {it.word_count ?? "—"}
                          </td>
                          <td className="px-4 py-2.5">
                            {it.status === "approved" ? (
                              <button
                                type="button"
                                className="text-[11px] font-semibold text-[#72C219] hover:underline"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  void statusMut.mutate({ id: it.id, status: "published" });
                                }}
                              >
                                {it.content_type === "landing_page"
                                  ? "Publish to WordPress →"
                                  : "Mark published →"}
                              </button>
                            ) : it.status === "pending" ? (
                              <button
                                type="button"
                                className="text-[11px] font-semibold text-teal hover:underline"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  void statusMut.mutate({ id: it.id, status: "approved" });
                                }}
                              >
                                Approve →
                              </button>
                            ) : it.status === "published" ? (
                              <div className="flex flex-col gap-0.5">
                                <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-emerald-600">
                                  <CheckCircle2 className="h-3.5 w-3.5" />
                                  Live
                                </span>
                                {it.target_url && /^https?:\/\//i.test(it.target_url) ? (
                                  <a
                                    href={it.target_url}
                                    target="_blank"
                                    rel="noreferrer"
                                    className="text-[10px] font-semibold text-[#72C219] hover:underline"
                                    onClick={(e) => e.stopPropagation()}
                                  >
                                    View post ↗
                                  </a>
                                ) : null}
                              </div>
                            ) : (
                              <span className="text-[11px] text-rp-tlight">—</span>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        </div>

        {/* ── Content Preview ─────────────────────────────────── */}
        {selected ? (
          <Card>
            <CardHeader
              title={`Content Preview - "${selected.title || selected.content_type.replace("_", " ")}"`}
              right={
                selected.status !== "published" ? (
                  <Button
                    variant="outline"
                    size="sm"
                    type="button"
                    disabled={statusMut.isPending}
                    onClick={() => void statusMut.mutate({ id: selected.id, status: "approved" })}
                  >
                    <PencilLine className="h-3.5 w-3.5" />
                    Approve
                  </Button>
                ) : undefined
              }
            />
            <ContentPreview item={selected} />
          </Card>
        ) : null}
      </div>
    </>
  );
}
