import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Globe,
  Image,
  KeyRound,
  Megaphone,
  MapPin,
  Palette,
  Search,
  ShieldCheck,
  Sparkles,
  Trash2,
  Upload,
  Wrench,
  X,
} from "lucide-react";
import { Component, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";

import { formatApiError } from "../api/client";
import { fetchSuburbKeywordResearch, formatKeywordVolume, pickTopAhrefsKeywords } from "../api/keywords";
import { mergeResearchedIntoIdeas, useResearchedKeywords } from "../lib/researchedKeywords";
import { fetchMeForAuth } from "../api/onboarding";
import {
  deleteGbpPhoto,
  deleteGbpPost,
  downloadGbpPostsXlsx,
  fetchGbpOverview,
  generateGbpDescription,
  generateGbpPhoto,
  generateGbpPostDirections,
  generateGbpPosts,
  publishGbpPhoto,
  saveGbpBrandKit,
  saveGbpDescriptionDraft,
  scheduleAllGbpPosts,
  syncGbpPosts,
  updateGbpDescription,
  updateGbpPost,
  uploadGbpBrandLogo,
  uploadGbpPhoto,
  gbpListingDescription,
  type GbpBrandKit,
  type GbpOverview,
  type GbpPhoto,
  type GbpPostsExportOptions,
  type GbpQueueItem,
  type KeywordAuditItem,
} from "../api/gbp";
import { AhrefsKeywordOverview } from "../components/keywords/AhrefsKeywordOverview";
import { CompetitorKeywordsOverview } from "../components/keywords/CompetitorKeywordsOverview";
import { KeywordCompetitorsPanel } from "../components/keywords/KeywordCompetitorsPanel";
import { TopBar } from "../components/layout/TopBar";
import { Badge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { Card, CardHeader } from "../components/ui/Card";
import { useAuthStore } from "../stores/authStore";

const TABS = [
  { id: "overview", label: "Overview", icon: ShieldCheck },
  { id: "posts", label: "Posts & Content", icon: Megaphone },
  { id: "description", label: "Description & Keywords", icon: KeyRound },
  { id: "keywords", label: "Keyword Research", icon: Search },
  { id: "ahrefs", label: "Ahrefs Overview", icon: Globe },
  { id: "photos", label: "Photos", icon: Image },
  { id: "brandkit", label: "Brand Kit", icon: Palette },
  { id: "services", label: "Services & Categories", icon: Wrench },
] as const;

type TabId = (typeof TABS)[number]["id"];

const GBP_POST_CHAR_LIMIT = 1500;

function asArray<T>(value: unknown): T[] {
  return Array.isArray(value) ? value : [];
}

class TabErrorBoundary extends Component<
  { label: string; children: ReactNode },
  { error: Error | null }
> {
  state: { error: Error | null } = { error: null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  render() {
    if (this.state.error) {
      return (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          <strong>{this.props.label}</strong> could not load: {this.state.error.message}
        </div>
      );
    }
    return this.props.children;
  }
}

function statusBadge(status: string) {
  const tones: Record<string, "green" | "amber" | "red" | "teal" | "blue"> = {
    pending: "amber",
    approved: "green",
    published: "green",
    rejected: "red",
    removed_on_gbp: "red",
    archived: "teal",
    scheduled: "blue",
    draft: "blue",
  };
  return <Badge tone={tones[status] ?? "blue"}>{status.replace(/_/g, " ")}</Badge>;
}

function formatGbpHistoryDate(iso?: string) {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("en-AU", { dateStyle: "short", timeStyle: "short" });
}

// ── Overview Tab ──────────────────────────────────────────────────────────────

function OverviewTab({ d }: { d: GbpOverview }) {
  const score = d.health_score ?? 0;
  const scoreColor =
    score >= 80 ? "#34A853" : score >= 50 ? "#FBBC04" : "#EA4335";

  return (
    <div className="space-y-4">
      <div className="grid gap-4 sm:grid-cols-3">
        <Card>
          <div className="p-4 text-center">
            <div className="text-3xl font-black" style={{ color: scoreColor }}>
              {score}
            </div>
            <div className="mt-1 text-xs text-rp-tlight">GBP Health Score</div>
          </div>
        </Card>
        <Card>
          <div className="p-4 text-center">
            <div className="text-3xl font-black text-navy">{d.photo_count ?? 0}</div>
            <div className="mt-1 text-xs text-rp-tlight">Photos</div>
          </div>
        </Card>
        <Card>
          <div className="p-4 text-center">
            <div className="text-3xl font-black text-navy">
              {d.posts?.filter((p) => p.status === "published").length ?? 0}
            </div>
            <div className="mt-1 text-xs text-rp-tlight">Posts published</div>
          </div>
        </Card>
      </div>

      {d.keyword_gaps && d.keyword_gaps.length > 0 && (
        <Card>
          <CardHeader title="Keyword gaps" subtitle="Missing from your GBP listing" />
          <div className="flex flex-wrap gap-2 p-4">
            {d.keyword_gaps.map((g) => (
              <span
                key={g}
                className="rounded-full border border-red-200 bg-red-50 px-2 py-0.5 text-[11px] text-red-700"
              >
                {g}
              </span>
            ))}
          </div>
        </Card>
      )}

      {d.categories && d.categories.length > 0 && (
        <Card>
          <CardHeader title="Categories" subtitle="From your Google listing" />
          <div className="flex flex-wrap gap-2 p-4">
            {d.categories.map((c) => (
              <span
                key={c}
                className="rounded-full bg-rp-light px-2 py-0.5 text-[11px] text-navy"
              >
                {c}
              </span>
            ))}
          </div>
        </Card>
      )}

      {d.website_uri && (
        <Card>
          <div className="px-4 py-3 text-xs text-rp-tlight">
            Website on listing:{" "}
            <a href={d.website_uri} target="_blank" rel="noreferrer" className="text-teal underline">
              {d.website_uri}
            </a>
          </div>
        </Card>
      )}
    </div>
  );
}

// ── Posts Tab ─────────────────────────────────────────────────────────────────

function PostsTab({
  d,
  token,
  onGenerate,
  onApprove,
  onPublish,
  onSaveDraft,
  onSyncPosts,
  onDeletePost,
  onScheduleAll,
  onDownloadExcel,
  scheduleAllPending,
  exportPending,
  busy,
  saveDraftPending,
  syncPostsPending,
}: {
  d: GbpOverview;
  token: string | null;
  onGenerate: (count: number, prompts: string) => void;
  onApprove: (id: string, body: string, scheduledFor?: string) => void;
  onPublish: (id: string, body: string) => void;
  onSaveDraft: (id: string, body: string) => void;
  onSyncPosts: () => void;
  onDeletePost: (id: string) => void;
  onScheduleAll: (mode: "daily" | "range", start?: string, end?: string) => void;
  onDownloadExcel: (opts: GbpPostsExportOptions) => void;
  scheduleAllPending: boolean;
  exportPending: boolean;
  busy: boolean;
  saveDraftPending: boolean;
  syncPostsPending: boolean;
}) {
  const qc = useQueryClient();
  const currentDraft = d.weekly_post ?? d.posts?.find((p) => p.status === "pending");
  const [selectedPostId, setSelectedPostId] = useState<string | null>(null);
  const [editBody, setEditBody] = useState("");
  const [prompts, setPrompts] = useState<string[]>(Array(10).fill(""));
  const [postCount, setPostCount] = useState(1);
  const [promptGenCount, setPromptGenCount] = useState(1);
  const [selectedPromptKws, setSelectedPromptKws] = useState<string[]>([]);
  const [keywordPreview, setKeywordPreview] = useState<string | null>(null);
  const [activePromptIdx, setActivePromptIdx] = useState(0);
  const [scheduleDate, setScheduleDate] = useState("");
  const [batchMode, setBatchMode] = useState<"daily" | "range">("daily");
  const [batchStart, setBatchStart] = useState("");
  const [batchEnd, setBatchEnd] = useState("");
  const [exportDateFrom, setExportDateFrom] = useState("");
  const [exportDateTo, setExportDateTo] = useState("");
  const [selectedExportIds, setSelectedExportIds] = useState<string[]>([]);

  const todayStr = new Date().toISOString().slice(0, 10);
  const allPosts = asArray<GbpQueueItem>(d.posts);

  const postGeneratedDate = (p: GbpQueueItem) =>
    p.generated_at ? new Date(p.generated_at).toISOString().slice(0, 10) : "";

  const matchesExportDate = (p: GbpQueueItem) => {
    const gen = postGeneratedDate(p);
    if (!gen) return !exportDateFrom && !exportDateTo;
    if (exportDateFrom && gen < exportDateFrom) return false;
    if (exportDateTo && gen > exportDateTo) return false;
    return true;
  };

  const exportCandidates = useMemo(() => {
    let list = allPosts.filter(matchesExportDate);
    if (selectedExportIds.length > 0) {
      const picked = new Set(selectedExportIds);
      list = list.filter((p) => picked.has(p.id));
    }
    return list;
  }, [allPosts, exportDateFrom, exportDateTo, selectedExportIds]);

  const toggleExportPost = (id: string) =>
    setSelectedExportIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id],
    );

  const selectAllForExport = () => {
    setSelectedExportIds(allPosts.filter(matchesExportDate).map((p) => p.id));
  };

  const clearExportSelection = () => setSelectedExportIds([]);

  const handleDownloadExcel = () => {
    const hasFilter =
      selectedExportIds.length > 0 || Boolean(exportDateFrom) || Boolean(exportDateTo);
    if (hasFilter && exportCandidates.length === 0) {
      window.alert("No posts match your selection or date range.");
      return;
    }
    const opts: GbpPostsExportOptions = {};
    if (exportDateFrom) opts.dateFrom = exportDateFrom;
    if (exportDateTo) opts.dateTo = exportDateTo;
    if (selectedExportIds.length > 0) opts.postIds = selectedExportIds;
    onDownloadExcel(opts);
  };

  const exportLabel = (() => {
    if (exportPending) return "Preparing…";
    if (selectedExportIds.length > 0 || exportDateFrom || exportDateTo) {
      return `⬇ Download Excel (${exportCandidates.length})`;
    }
    return `⬇ Download Excel (${allPosts.length})`;
  })();
  // Posts that can still be scheduled / rescheduled (not yet live on Google).
  const schedulablePosts = d.posts?.filter((p) => p.status === "pending" || p.status === "approved") ?? [];

  const ahrefsQ = useQuery({
    queryKey: ["keywords", "suburb-research", "gbp-batch"],
    queryFn: () => fetchSuburbKeywordResearch(),
    staleTime: 120_000,
  });
  const researchedKws = useResearchedKeywords();
  const ahrefsKeywords = useMemo(
    () => mergeResearchedIntoIdeas(researchedKws, pickTopAhrefsKeywords(ahrefsQ.data, 30)),
    [ahrefsQ.data, researchedKws],
  );

  const refreshKeywords = useMutation({
    mutationFn: () => fetchSuburbKeywordResearch(true),
    onSuccess: (data) => {
      qc.setQueryData(["keywords", "suburb-research", "gbp-batch"], data);
      qc.setQueryData(["keywords", "suburb-research", "desc-tab"], data);
    },
  });

  const togglePromptKw = (kw: string) =>
    setSelectedPromptKws((prev) =>
      prev.includes(kw) ? prev.filter((k) => k !== kw) : [...prev, kw],
    );

  const generateDirections = useMutation({
    mutationFn: () =>
      generateGbpPostDirections(promptGenCount, selectedPromptKws),
    onSuccess: (data) => {
      const next = [...prompts];
      for (let i = 0; i < data.prompts.length; i++) {
        next[i] = data.prompts[i]?.slot ?? "";
      }
      setPrompts(next);
      setPostCount(data.count);
      setActivePromptIdx(0);
    },
  });

  const draft =
    (selectedPostId ? d.posts?.find((p) => p.id === selectedPostId) : null) ?? currentDraft ?? null;
  const isCurrentDraft = Boolean(draft && currentDraft && draft.id === currentDraft.id);
  const isEditable = Boolean(draft && draft.status === "pending" && isCurrentDraft);
  // Any post that isn't already live on Google can be edited and acted on.
  const canEditBody = Boolean(draft) && draft?.status !== "published";
  const canAct = canEditBody;
  const isAlreadyPublished = draft?.status === "published";
  const overLimit = editBody.trim().length > GBP_POST_CHAR_LIMIT;

  useEffect(() => { setSelectedPostId(null); }, [currentDraft?.id]);

  const loadedDraftIdRef = useRef<string | null>(null);
  useEffect(() => {
    const id = draft?.id ?? null;
    // A different post (newly generated or selected) → always show ITS body.
    if (id !== loadedDraftIdRef.current) {
      loadedDraftIdRef.current = id;
      setEditBody(draft?.body ?? "");
      setScheduleDate(draft?.scheduled_for?.slice(0, 10) ?? "");
      return;
    }
    // Same post refetched in the background → keep unsaved edits, else sync.
    setEditBody((prev) => {
      const saved = (draft?.body ?? "").trim();
      if (prev.trim() && prev.trim() !== saved) return prev;
      return draft?.body ?? "";
    });
  }, [draft?.id, draft?.body]);

  const photoUrl = draft?.photo_id
    ? `/api/v1/gbp/photos/${draft.photo_id}/file`
    : null;

  const charCount = editBody.trim().length;

  return (
    <div className="space-y-4">
      <KeywordPreviewModal keyword={keywordPreview} onClose={() => setKeywordPreview(null)} />
      {/* Location scope banner */}
      {d.location_scope && (
        <div
          className={`flex items-center gap-2 rounded-lg border px-4 py-2.5 text-[12px] ${
            d.location_scope === "city"
              ? "border-[#C2E0FF] bg-[#E8F4FF] text-[#0050A0]"
              : "border-[#FFE5B4] bg-[#FFF8E7] text-[#7A4700]"
          }`}
        >
          <MapPin className="h-3.5 w-3.5 shrink-0" />
          <span>
            <strong>Post location mode: </strong>
            {d.location_scope === "city" ? (
              <>City — posts use city-wide keywords only (no suburb names).</>
            ) : (
              <>Suburb — posts use your anchor suburb only.</>
            )}
          </span>
          <Link to="/onboarding" className="ml-auto shrink-0 rounded px-2 py-0.5 font-semibold underline hover:no-underline">
            Change in Business Setup →
          </Link>
        </div>
      )}

      <div className="flex flex-wrap items-center gap-2 rounded-lg border border-[#C2E0FF] bg-[#F8FAFC] px-4 py-2.5">
        <span className="text-[11px] text-navy">
          <strong>Live top keywords</strong> from Ahrefs — ranked by local relevance, volume &amp; opportunity.
        </span>
        {ahrefsQ.data?.from_cache ? (
          <span className="text-[10px] text-rp-tlight">Cached · refresh for latest data</span>
        ) : ahrefsQ.data?.source === "ahrefs" ? (
          <span className="text-[10px] text-[#137333]">Fresh from Ahrefs</span>
        ) : null}
        <Button
          type="button"
          size="sm"
          variant="outline"
          className="ml-auto"
          disabled={refreshKeywords.isPending || ahrefsQ.isLoading}
          onClick={() => void refreshKeywords.mutate()}
        >
          {refreshKeywords.isPending ? "Refreshing…" : "↻ Refresh live keywords"}
        </Button>
      </div>

      {/* AI prompt generator — fills post direction slots below */}
      <Card>
        <CardHeader
          title="Generate post directions"
          subtitle="OpenRouter writes deep Runway image briefs + post angles from your Ahrefs keywords"
        />
        <div className="p-4 space-y-4">
          <div className="flex items-center gap-3">
            <label className="text-[10px] font-bold uppercase tracking-[0.08em] text-[#8EA3BC]">
              How many prompts?
            </label>
            <div className="flex gap-1">
              {Array.from({ length: 10 }, (_, i) => i + 1).map((n) => (
                <button
                  key={n}
                  type="button"
                  onClick={() => setPromptGenCount(n)}
                  className={`h-7 w-7 rounded-md text-[11px] font-bold transition ${
                    promptGenCount === n
                      ? "bg-[#1A73E8] text-white"
                      : "bg-rp-light text-navy hover:bg-[#E8EFF7]"
                  }`}
                >
                  {n}
                </button>
              ))}
            </div>
          </div>

          <div className="grid gap-4 lg:grid-cols-[1fr_220px]">
            <div className="rounded-lg border border-dashed border-[#C2E0FF] bg-[#F8FAFC] p-4">
              <p className="text-[11px] text-navy">
                Select Ahrefs keywords on the right, choose how many prompts you need, then generate.
                Each prompt is a detailed persuasive image brief (150+ words) for Runway — not a one-liner.
              </p>
              {selectedPromptKws.length > 0 ? (
                <p className="mt-2 text-[11px] font-semibold text-[#137333]">
                  {selectedPromptKws.length} keyword{selectedPromptKws.length > 1 ? "s" : ""} selected
                  {selectedPromptKws.length < promptGenCount
                    ? ` — will rotate across ${promptGenCount} prompts`
                    : ""}
                </p>
              ) : (
                <p className="mt-2 text-[11px] text-rp-tlight">No keywords selected yet.</p>
              )}
            </div>

            <div>
              <p className="mb-1.5 text-[10px] font-bold uppercase tracking-[0.08em] text-[#8EA3BC]">
                Select keywords
              </p>
              <p className="mb-2 text-[10px] text-rp-tlight">
                Tick to select · click keyword text to view full phrase
              </p>
              {ahrefsKeywords.length === 0 && !ahrefsQ.isLoading ? (
                <p className="text-[11px] text-rp-tlight">No Ahrefs keywords yet.</p>
              ) : (
                <div className="max-h-48 space-y-1 overflow-y-auto rounded-lg border border-rp-border bg-[#F8FAFC] p-2">
                  {ahrefsKeywords.map((item) => {
                    const kw = item.keyword;
                    const checked = selectedPromptKws.includes(kw);
                    return (
                      <div
                        key={kw}
                        className={`flex w-full items-center gap-2 rounded px-2 py-1 text-[11px] transition ${
                          checked
                            ? "bg-[#E6F4EA] text-[#137333] ring-1 ring-[#34A853]"
                            : "text-navy hover:bg-white"
                        }`}
                      >
                        <button
                          type="button"
                          onClick={() => togglePromptKw(kw)}
                          aria-label={checked ? `Deselect ${kw}` : `Select ${kw}`}
                          className="shrink-0"
                        >
                          <span
                            className={`flex h-4 w-4 items-center justify-center rounded border text-[9px] font-bold ${
                              checked
                                ? "border-[#34A853] bg-[#34A853] text-white"
                                : "border-rp-border bg-white text-transparent"
                            }`}
                          >
                            ✓
                          </span>
                        </button>
                        <button
                          type="button"
                          onClick={() => setKeywordPreview(kw)}
                          className="min-w-0 flex-1 truncate text-left hover:underline"
                          title={`${kw} · ${formatKeywordVolume(item.avg_monthly_searches)}`}
                        >
                          {kw}
                        </button>
                        <span className="shrink-0 text-[9px] text-rp-tlight">
                          {formatKeywordVolume(item.avg_monthly_searches)}
                        </span>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <Button
              type="button"
              size="sm"
              variant="outline"
              disabled={
                generateDirections.isPending ||
                selectedPromptKws.length === 0
              }
              onClick={() => void generateDirections.mutate()}
            >
              <Sparkles className="mr-1.5 h-3.5 w-3.5" />
              {generateDirections.isPending
                ? "Generating prompts…"
                : `Generate ${promptGenCount} prompt${promptGenCount > 1 ? "s" : ""} with AI`}
            </Button>
            {generateDirections.isError && (
              <p className="text-xs text-red-600">
                {formatApiError(generateDirections.error)}
              </p>
            )}
            {generateDirections.isSuccess && (
              <p className="text-xs text-[#137333]">
                Prompts added to the fields below — review, then generate posts.
              </p>
            )}
          </div>
        </div>
      </Card>

      {/* Generator card */}
      <Card>
        <CardHeader
          title="Generate posts"
          subtitle="AI writes each post using your direction + an Ahrefs keyword"
        />
        <div className="p-4 space-y-4">

          {/* How many posts */}
          <div className="flex items-center gap-3">
            <label className="text-[10px] font-bold uppercase tracking-[0.08em] text-[#8EA3BC]">
              How many posts?
            </label>
            <div className="flex gap-1">
              {Array.from({ length: 10 }, (_, i) => i + 1).map((n) => (
                <button
                  key={n}
                  type="button"
                  onClick={() => setPostCount(n)}
                  className={`h-7 w-7 rounded-md text-[11px] font-bold transition ${
                    postCount === n
                      ? "bg-navy text-white"
                      : "bg-rp-light text-navy hover:bg-[#E8EFF7]"
                  }`}
                >
                  {n}
                </button>
              ))}
            </div>
          </div>

          {/* Two-column layout: prompt slots | keyword picker */}
          <div className="grid gap-4 lg:grid-cols-[1fr_220px]">

            {/* Prompt slots */}
            <div className="space-y-2">
              <p className="text-[10px] font-bold uppercase tracking-[0.08em] text-[#8EA3BC]">
                Post directions / image prompts{postCount > 1 ? ` (${postCount} posts)` : ""}
              </p>
              <div className="max-h-[420px] space-y-3 overflow-y-auto pr-1">
              {Array.from({ length: postCount }, (_, i) => (
                <div key={i} className="relative">
                  <span className="absolute left-2.5 top-2.5 flex h-4 w-4 items-center justify-center rounded bg-navy text-[9px] font-bold text-white">
                    {i + 1}
                  </span>
                  <textarea
                    rows={5}
                    value={prompts[i] ?? ""}
                    onChange={(e) => {
                      const next = [...prompts];
                      next[i] = e.target.value;
                      setPrompts(next);
                    }}
                    onFocus={() => setActivePromptIdx(i)}
                    placeholder={`Post ${i + 1} — detailed image prompt (generate above) or leave blank`}
                    className={`w-full resize-y rounded-md border py-2 pl-8 pr-3 text-[11px] leading-relaxed text-navy placeholder:text-rp-tlight focus:outline-none focus:ring-1 focus:ring-[#34A853] ${
                      activePromptIdx === i && document.activeElement?.tagName === "TEXTAREA"
                        ? "border-[#34A853] bg-[#F6FFF8]"
                        : "border-rp-border bg-white"
                    }`}
                  />
                </div>
              ))}
              </div>
              <p className="text-[10px] text-rp-tlight">
                Use Generate post directions above for deep Runway prompts, or click a keyword on the right to add manually.
              </p>
            </div>

            {/* Ahrefs keyword picker */}
            <div>
              <div className="flex items-center gap-1.5 mb-1.5">
                <span className="text-[10px] font-bold uppercase tracking-[0.08em] text-[#8EA3BC]">
                  Ahrefs keywords
                </span>
                {ahrefsQ.isLoading && (
                  <span className="text-[10px] text-rp-tlight">loading…</span>
                )}
              </div>
              {ahrefsKeywords.length === 0 && !ahrefsQ.isLoading ? (
                <p className="text-[11px] text-rp-tlight">
                  No Ahrefs keywords yet — add your AHREFS_API_KEY in Settings.
                </p>
              ) : (
                <div className="flex max-h-64 flex-wrap gap-1.5 overflow-y-auto rounded-lg border border-rp-border bg-[#F8FAFC] p-2.5">
                  {ahrefsKeywords.map((item) => {
                    const kw = item.keyword;
                    return (
                    <button
                      key={kw}
                      type="button"
                      title={`Add "${kw}" (${formatKeywordVolume(item.avg_monthly_searches)}) to prompt ${activePromptIdx + 1}`}
                      onClick={() => {
                        const next = [...prompts];
                        const cur = (next[activePromptIdx] ?? "").trim();
                        next[activePromptIdx] = cur ? `${cur}, ${kw}` : kw;
                        setPrompts(next);
                      }}
                      className="rounded-full border border-[#C2E0FF] bg-white px-2 py-0.5 text-[10px] font-medium text-[#0050A0] transition hover:border-[#34A853] hover:bg-[#E6F4EA] hover:text-[#137333] active:scale-95"
                    >
                      + {kw}
                    </button>
                    );
                  })}
                </div>
              )}
              <p className="mt-1.5 text-[10px] text-rp-tlight">
                Click a keyword to set the target phrase for the active post slot. Add extra text before it for a custom angle.
              </p>
            </div>
          </div>

          <Button
            type="button"
            size="sm"
            disabled={busy}
            onClick={() => {
              const raw = prompts.slice(0, postCount).join("\n<<<POST_SLOT>>>\n");
              onGenerate(postCount, raw.trim() ? raw : "");
            }}
          >
            {busy
              ? `Generating ${postCount} post${postCount > 1 ? "s" : ""}…`
              : `+ Generate ${postCount} post${postCount > 1 ? "s" : ""}`}
          </Button>
        </div>
      </Card>

      {/* Draft editor */}
      <Card>
        <CardHeader
          title={isEditable ? "This week's post" : draft ? "Edit post" : "Post preview"}
          subtitle={
            isAlreadyPublished
              ? "This post is live on Google — edit and re-publish to push an update"
              : draft
                ? "Edit the text, pick a publish date, then approve or publish to GBP"
                : "Text + AI image — approve to publish to GBP"
          }
          right={
            draft?.status === "pending" && isEditable ? (
              <Badge tone="amber">Scheduled · pending approval</Badge>
            ) : draft ? statusBadge(draft.status) : null
          }
        />
        <div className="grid gap-5 p-4 lg:grid-cols-[1fr_auto]">
          <div>
            <p className="mb-1.5 text-[10px] font-bold uppercase tracking-[0.08em] text-[#8EA3BC]">
              Post content — edit, paste, or write your own text:
            </p>
            {draft ? (
              <div className="rounded-lg border border-rp-border bg-[#F8FAFC] p-3">
                {photoUrl && (
                  <div className="mb-3">
                    <p className="mb-1 text-[10px] font-semibold text-[#8EA3BC] uppercase tracking-wide">
                      Post image (Runway)
                    </p>
                    <img
                      src={`${photoUrl}${token ? `?token=${token}` : ""}`}
                      alt="Post"
                      className="max-h-48 w-full rounded object-cover"
                      onError={(e) => { (e.target as HTMLImageElement).style.display = "none"; }}
                    />
                  </div>
                )}
                <textarea
                  readOnly={!canEditBody}
                  value={editBody}
                  onChange={(e) => setEditBody(e.target.value)}
                  rows={10}
                  className={`w-full resize-y rounded border bg-white p-2.5 text-[12px] leading-relaxed text-navy focus:outline-none ${
                    canEditBody ? "border-[#34A853] focus:ring-1 focus:ring-[#34A853]" : "border-transparent text-navy/80"
                  }`}
                />
                <p className={`mt-1 text-[10px] ${overLimit ? "text-red-600 font-semibold" : "text-rp-tlight"}`}>
                  {charCount} / {GBP_POST_CHAR_LIMIT} characters
                  {!canEditBody ? " · read-only" : ""}
                </p>
                <div className="mt-2 flex flex-wrap gap-1.5">
                  <Badge tone="teal">STANDARD post type</Badge>
                  {photoUrl && <Badge tone="teal">Image ready</Badge>}
                  {draft.target_keyword && <Badge tone="green">"{draft.target_keyword}" included</Badge>}
                  {statusBadge(draft.status)}
                </div>
              </div>
            ) : (
              <p className="text-sm text-rp-tlight">No draft post yet. Click "+ Generate" to create with AI.</p>
            )}

            {draft?.target_keyword && (
              <div className="mt-3">
                <KeywordCompetitorsPanel keyword={draft.target_keyword} />
              </div>
            )}

            {canAct && draft && (
              <div className="mt-3 space-y-2">
                <div className="flex flex-wrap items-center gap-2 rounded-lg border border-rp-border bg-rp-light px-3 py-2">
                  <label className="text-[11px] font-bold uppercase tracking-wide text-rp-tlight">
                    📅 Publish date
                  </label>
                  <input
                    type="date"
                    min={todayStr}
                    value={scheduleDate}
                    onChange={(e) => setScheduleDate(e.target.value)}
                    className="rounded-md border border-rp-border bg-white px-2 py-1 text-[12px] text-navy outline-none ring-[#72C219]/30 focus:ring-2"
                  />
                  <span className="text-[11px] text-rp-tlight">
                    {scheduleDate
                      ? `Auto-publishes on ${new Date(scheduleDate).toLocaleDateString("en-AU")}`
                      : "Leave empty to auto-schedule (next free day, one post per day)"}
                  </span>
                </div>
                <div className="flex flex-wrap gap-2">
                  <Button
                    size="sm"
                    disabled={busy || overLimit || !editBody.trim()}
                    onClick={() => onApprove(draft.id, editBody.trim(), scheduleDate || undefined)}
                  >
                    ✓ Approve for schedule
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={busy || overLimit || !editBody.trim()}
                    onClick={() => onPublish(draft.id, editBody.trim())}
                  >
                    Publish to GBP now
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={busy || !editBody.trim()}
                    onClick={() => onSaveDraft(draft.id, editBody.trim())}
                  >
                    {saveDraftPending ? "Saving…" : "Save changes"}
                  </Button>
                  {isCurrentDraft && (
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={busy}
                      onClick={() => onGenerate(1, prompts[0]?.trim() ?? "")}
                    >
                      Regenerate
                    </Button>
                  )}
                </div>
              </div>
            )}
            {isAlreadyPublished && draft && (
              <p className="mt-3 text-[12px] text-rp-tlight">
                This post is already live on Google. To change it, generate a new post or edit a draft.
              </p>
            )}
            {draft && !isCurrentDraft && (
              <button
                className="mt-3 text-[11px] text-teal underline"
                onClick={() => setSelectedPostId(null)}
              >
                ← Back to current draft
              </button>
            )}
          </div>

          {/* Google Maps listing preview */}
          <div className="hidden w-[260px] shrink-0 lg:block">
            <p className="mb-1.5 text-[10px] font-bold uppercase tracking-[0.08em] text-[#8EA3BC]">
              Google Maps preview
            </p>
            <div className="overflow-hidden rounded-xl border border-[#DADCE0] bg-white shadow-md">
              {/* Header */}
              <div className="flex items-center gap-2 bg-[#EA4335] px-3 py-2">
                <div className="flex h-6 w-6 items-center justify-center rounded-full bg-white text-[#EA4335]">
                  <svg viewBox="0 0 24 24" className="h-4 w-4 fill-current"><path d="M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7zm0 9.5c-1.38 0-2.5-1.12-2.5-2.5s1.12-2.5 2.5-2.5 2.5 1.12 2.5 2.5-1.12 2.5-2.5 2.5z"/></svg>
                </div>
                <span className="text-[12px] font-semibold text-white">Google Maps listing</span>
              </div>

              {/* Business info */}
              <div className="px-3 pt-3">
                <p className="text-[14px] font-bold text-[#202124] leading-tight">
                  {d.business_name || "Your Business"}
                </p>
                <p className="mt-0.5 text-[11px] text-[#5F6368]">
                  {d.location_name ? `${d.location_name}` : "Internet marketing service"}
                </p>
                {/* Stars */}
                <div className="mt-1 flex items-center gap-1">
                  {Array.from({ length: 5 }).map((_, i) => (
                    <svg key={i} viewBox="0 0 24 24" className="h-3 w-3 fill-[#FBBC04]">
                      <path d="M12 17.27L18.18 21l-1.64-7.03L22 9.24l-7.19-.61L12 2 9.19 8.63 2 9.24l5.46 4.73L5.82 21z"/>
                    </svg>
                  ))}
                  <span className="text-[10px] text-[#5F6368]">—</span>
                </div>
              </div>

              {/* Post photo */}
              {photoUrl ? (
                <div className="mx-3 mt-2 overflow-hidden rounded">
                  <img
                    src={`${photoUrl}${token ? `?token=${token}` : ""}`}
                    alt="Post image"
                    className="h-28 w-full object-cover"
                    onError={(e) => { (e.target as HTMLImageElement).style.display = "none"; }}
                  />
                </div>
              ) : (
                <div className="mx-3 mt-2 flex h-28 items-center justify-center rounded bg-[#F1F3F4] text-[11px] text-[#9AA0A6]">
                  No image
                </div>
              )}

              {/* Post body */}
              <div className="px-3 py-2">
                <p className="text-[11px] font-semibold text-[#202124] leading-snug">
                  {d.business_name || "Your Business"}
                </p>
                <p className="mt-0.5 text-[11px] leading-relaxed text-[#5F6368] line-clamp-3">
                  {editBody
                    ? editBody.slice(0, 150) + (editBody.length > 150 ? "…" : "")
                    : "Your post text will appear here once generated."}
                </p>
                <p className="mt-1.5 text-[11px] font-medium text-[#1A73E8]">Learn more</p>
              </div>
            </div>
            <p className="mt-1.5 text-[10px] text-rp-tlight">
              Preview shows ~150 chars · Google publishes your full post (up to 1,500 chars)
            </p>
          </div>
        </div>
      </Card>

      {/* Batch schedule — appears when there are posts to schedule / reschedule */}
      {schedulablePosts.length > 0 && (
        <Card>
          <CardHeader
            title={`Schedule ${schedulablePosts.length} post${schedulablePosts.length > 1 ? "s" : ""}`}
            subtitle="Spread multiple posts across a date range (from–to) or one per day, then approve them all at once"
          />
          <div className="space-y-3 p-4">
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => setBatchMode("daily")}
                className={`rounded-lg border px-3 py-2 text-[12px] font-semibold transition ${
                  batchMode === "daily"
                    ? "border-[#34A853] bg-[#E6F4EA] text-[#137333]"
                    : "border-rp-border bg-white text-rp-tmid hover:border-[#34A853]"
                }`}
              >
                📆 One post per day
              </button>
              <button
                type="button"
                onClick={() => setBatchMode("range")}
                className={`rounded-lg border px-3 py-2 text-[12px] font-semibold transition ${
                  batchMode === "range"
                    ? "border-[#34A853] bg-[#E6F4EA] text-[#137333]"
                    : "border-rp-border bg-white text-rp-tmid hover:border-[#34A853]"
                }`}
              >
                📅 Spread across a date range
              </button>
            </div>

            <div className="flex flex-wrap items-end gap-3">
              <div>
                <label className="mb-1 block text-[10px] font-bold uppercase tracking-wide text-rp-tlight">
                  Start date
                </label>
                <input
                  type="date"
                  min={todayStr}
                  value={batchStart}
                  onChange={(e) => setBatchStart(e.target.value)}
                  className="rounded-md border border-rp-border bg-white px-2 py-1.5 text-[12px] text-navy outline-none ring-[#72C219]/30 focus:ring-2"
                />
              </div>
              {batchMode === "range" && (
                <div>
                  <label className="mb-1 block text-[10px] font-bold uppercase tracking-wide text-rp-tlight">
                    End date
                  </label>
                  <input
                    type="date"
                    min={batchStart || todayStr}
                    value={batchEnd}
                    onChange={(e) => setBatchEnd(e.target.value)}
                    className="rounded-md border border-rp-border bg-white px-2 py-1.5 text-[12px] text-navy outline-none ring-[#72C219]/30 focus:ring-2"
                  />
                </div>
              )}
              <Button
                size="sm"
                disabled={scheduleAllPending || (batchMode === "range" && (!batchStart || !batchEnd))}
                onClick={() =>
                  onScheduleAll(batchMode, batchStart || undefined, batchEnd || undefined)
                }
              >
                {scheduleAllPending
                  ? "Scheduling…"
                  : `✓ Approve & schedule all ${schedulablePosts.length}`}
              </Button>
            </div>
            <p className="text-[11px] text-rp-tlight">
              {batchMode === "daily"
                ? `Posts will publish one per day starting ${batchStart ? new Date(batchStart).toLocaleDateString("en-AU") : "today"}.`
                : "Posts will be spread evenly between the start and end dates."}{" "}
              Each post auto-publishes to Google on its assigned day.
            </p>
          </div>
        </Card>
      )}

      {/* History */}
      <Card>
        <CardHeader
          title="Generated post history"
          subtitle="Select posts and/or filter by date, then download Excel"
          right={
            <div className="flex flex-wrap gap-2">
              <Button
                size="sm"
                variant="outline"
                disabled={exportPending || allPosts.length === 0}
                onClick={handleDownloadExcel}
              >
                {exportLabel}
              </Button>
              <Button
                size="sm"
                variant="outline"
                disabled={syncPostsPending}
                onClick={onSyncPosts}
              >
                {syncPostsPending ? "Syncing…" : "Sync with Google"}
              </Button>
            </div>
          }
        />
        {allPosts.length === 0 ? (
          <p className="px-4 py-6 text-center text-sm text-rp-tlight">
            No posts yet — generate your first post above
          </p>
        ) : (
          <>
            <div className="flex flex-wrap items-end gap-3 border-b border-rp-border px-4 py-3">
              <div>
                <label className="mb-1 block text-[10px] font-bold uppercase tracking-wide text-rp-tlight">
                  Generated from
                </label>
                <input
                  type="date"
                  value={exportDateFrom}
                  onChange={(e) => setExportDateFrom(e.target.value)}
                  className="rounded-md border border-rp-border px-2 py-1.5 text-[12px] text-navy"
                />
              </div>
              <div>
                <label className="mb-1 block text-[10px] font-bold uppercase tracking-wide text-rp-tlight">
                  Generated to
                </label>
                <input
                  type="date"
                  value={exportDateTo}
                  min={exportDateFrom || undefined}
                  onChange={(e) => setExportDateTo(e.target.value)}
                  className="rounded-md border border-rp-border px-2 py-1.5 text-[12px] text-navy"
                />
              </div>
              <button
                type="button"
                onClick={selectAllForExport}
                className="rounded-md border border-rp-border bg-white px-2.5 py-1.5 text-[11px] font-semibold text-navy hover:bg-rp-light"
              >
                Select all in range
              </button>
              <button
                type="button"
                onClick={clearExportSelection}
                className="rounded-md border border-rp-border bg-white px-2.5 py-1.5 text-[11px] text-rp-tlight hover:bg-rp-light"
              >
                Clear selection
              </button>
              <p className="text-[11px] text-rp-tlight">
                {selectedExportIds.length > 0
                  ? `${selectedExportIds.length} selected`
                  : "Tick posts below, or use dates only"}
                {exportDateFrom || exportDateTo
                  ? ` · ${exportCandidates.length} match filter`
                  : ""}
              </p>
            </div>
            <div className="max-h-80 overflow-y-auto divide-y divide-rp-border">
            {allPosts.map((p) => {
              const inDateRange = matchesExportDate(p);
              const checked = selectedExportIds.includes(p.id);
              return (
              <div
                key={p.id}
                className={`group flex items-center gap-2 px-4 py-3 hover:bg-rp-light ${
                  selectedPostId === p.id ? "bg-rp-light" : ""
                } ${!inDateRange && (exportDateFrom || exportDateTo) ? "opacity-45" : ""}`}
              >
                <button
                  type="button"
                  aria-label={checked ? "Deselect for export" : "Select for export"}
                  onClick={(e) => {
                    e.stopPropagation();
                    toggleExportPost(p.id);
                  }}
                  className={`flex h-4 w-4 shrink-0 items-center justify-center rounded border text-[9px] font-bold transition ${
                    checked
                      ? "border-[#34A853] bg-[#34A853] text-white"
                      : "border-rp-border bg-white text-transparent hover:border-[#34A853]"
                  }`}
                >
                  ✓
                </button>
                {/* Clickable row area */}
                <button
                  type="button"
                  className="min-w-0 flex-1 text-left"
                  onClick={() => setSelectedPostId((prev) => (prev === p.id ? null : p.id))}
                >
                  <p className="truncate text-[12px] font-semibold text-navy">
                    {p.title ?? p.body?.slice(0, 60) ?? "Post"}
                  </p>
                  <p className="mt-0.5 truncate text-[11px] text-rp-tlight">
                    {p.target_keyword && `🔑 ${p.target_keyword} · `}
                    {p.generated_at
                      ? new Date(p.generated_at).toLocaleDateString("en-AU")
                      : ""}
                  </p>
                  {p.status === "approved" && p.scheduled_for && (
                    <p className="mt-0.5 truncate text-[11px] font-semibold text-[#0050A0]">
                      📅 Auto-publishes {new Date(p.scheduled_for).toLocaleDateString("en-AU")}
                    </p>
                  )}
                </button>

                <div className="shrink-0">{statusBadge(p.status)}</div>

                {/* Delete button — visible on row hover */}
                <button
                  type="button"
                  title="Delete post"
                  className="shrink-0 rounded p-1 text-rp-tlight opacity-0 transition hover:bg-red-50 hover:text-red-500 group-hover:opacity-100"
                  onClick={(e) => {
                    e.stopPropagation();
                    if (window.confirm("Delete this post? This cannot be undone.")) {
                      onDeletePost(p.id);
                    }
                  }}
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </div>
              );
            })}
            </div>
          </>
        )}
      </Card>
    </div>
  );
}

// ── Description History ───────────────────────────────────────────────────────

function DescriptionHistory({
  items,
  activeId,
  onSelect,
}: {
  items: GbpQueueItem[];
  activeId?: string | null;
  onSelect: (item: GbpQueueItem) => void;
}) {
  if (items.length === 0) {
    return (
      <Card>
        <CardHeader
          title="Description history"
          subtitle="Generated descriptions — published, scheduled, and archived versions"
        />
        <p className="px-4 pb-4 text-sm text-rp-tlight">
          No descriptions yet. Generate your first one above.
        </p>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader
        title="Description history"
        subtitle="Click a row to preview · see which versions are published, pending, or archived"
      />
      <div className="max-h-80 divide-y divide-rp-border overflow-y-auto">
        {items.map((item) => {
          const ts =
            item.published_at || item.generated_at || item.created_at || item.updated_at;
          const preview = (item.body ?? "").trim();
          const chars = item.char_count ?? preview.length;
          const kws = asArray<string>(item.keywords_used);
          const isActive = activeId === item.id;

          return (
            <button
              key={item.id}
              type="button"
              onClick={() => onSelect(item)}
              className={`w-full px-4 py-3 text-left transition hover:bg-[#F8FAFC] ${
                isActive ? "bg-[#F6FFF8] ring-1 ring-inset ring-[#CEEAD6]" : ""
              }`}
            >
              <div className="flex flex-wrap items-center gap-2">
                {statusBadge(item.status)}
                <span className="text-[11px] text-rp-tlight">{formatGbpHistoryDate(ts)}</span>
                <span className="text-[11px] text-rp-tlight">· {chars} chars</span>
                {item.scheduled_for && item.status === "approved" && (
                  <span className="text-[11px] text-[#137333]">
                    · scheduled {item.scheduled_for.slice(0, 10)}
                  </span>
                )}
              </div>
              {kws.length > 0 && (
                <p className="mt-1 text-[10px] text-rp-tlight">
                  Keywords: {kws.join(", ")}
                </p>
              )}
              <p className="mt-1 line-clamp-2 text-[12px] leading-relaxed text-navy">
                {preview || <span className="text-rp-tlight">Empty description</span>}
              </p>
              {item.archived_reason && item.status === "archived" && (
                <p className="mt-1 text-[10px] text-rp-tlight capitalize">
                  Archived — {item.archived_reason.replace(/_/g, " ")}
                </p>
              )}
            </button>
          );
        })}
      </div>
    </Card>
  );
}

// ── Description Tab ───────────────────────────────────────────────────────────

function DescriptionTab({
  d,
  busy,
  saveDraftPending,
  onGenerate,
  onSaveDraft,
  onApprove,
  onPublish,
}: {
  d: GbpOverview;
  busy: boolean;
  saveDraftPending: boolean;
  onGenerate: (keywords: string[]) => void;
  onSaveDraft: (body: string, draftId?: string) => void;
  onApprove: (id: string, body: string, scheduledFor?: string) => void;
  onPublish: (id: string, body: string) => void;
}) {
  const draft = d.description_draft ?? null;
  const history = asArray<GbpQueueItem>(d.description_history);
  const draftBody = typeof draft?.body === "string" ? draft.body : "";
  const liveDesc = gbpListingDescription(d);
  const [viewingId, setViewingId] = useState<string | null>(draft?.id ?? null);
  const [editBody, setEditBody] = useState(draftBody || liveDesc);
  const [selectedKws, setSelectedKws] = useState<string[]>([]);
  const [scheduleDate, setScheduleDate] = useState("");
  const todayStr = new Date().toISOString().slice(0, 10);

  const ahrefsQ = useQuery({
    queryKey: ["keywords", "suburb-research", "desc-tab"],
    queryFn: () => fetchSuburbKeywordResearch(),
    staleTime: 120_000,
  });
  const researchedKws = useResearchedKeywords();
  const ahrefsKws = useMemo(
    () => mergeResearchedIntoIdeas(researchedKws, pickTopAhrefsKeywords(ahrefsQ.data, 30)),
    [ahrefsQ.data, researchedKws],
  );

  useEffect(() => {
    setViewingId(draft?.id ?? null);
    setEditBody(draftBody || liveDesc);
    setScheduleDate(draft?.scheduled_for?.slice(0, 10) ?? "");
  }, [draft?.id, draftBody, liveDesc, draft?.scheduled_for]);

  const viewingItem =
    (viewingId ? history.find((h) => h.id === viewingId) : null) ?? draft;
  const isHistoryReadOnly = Boolean(
    viewingId &&
      viewingItem &&
      ["published", "archived", "rejected"].includes(viewingItem.status) &&
      (!draft || viewingId !== draft.id),
  );
  const canEdit = !isHistoryReadOnly;

  const charCount = editBody.trim().length;
  const overLimit = charCount > 750;
  const remaining = 750 - charCount;
  const canAct = canEdit;

  const audit = asArray<KeywordAuditItem>(
    d.keyword_audit_draft ?? d.keyword_audit_primary ?? d.keyword_audit,
  );
  const gaps = asArray<string>(d.keyword_gaps_draft ?? d.keyword_gaps);

  const toggleKw = (kw: string) =>
    setSelectedKws((prev) => {
      if (prev.includes(kw)) return prev.filter((k) => k !== kw);
      if (prev.length >= 2) return prev;
      return [...prev, kw];
    });

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader
          title="GBP Description"
          subtitle="GPT-4o mini · 700–750 chars with your keywords · approve to schedule or publish now"
          right={viewingItem ? statusBadge(viewingItem.status) : null}
        />
        <div className="p-4 space-y-4">

          {/* Two-column: keyword picker | description editor */}
          <div className="grid gap-4 lg:grid-cols-[200px_1fr]">

            {/* Keyword picker */}
            <div>
              <p className="mb-1.5 text-[10px] font-bold uppercase tracking-[0.08em] text-[#8EA3BC]">
                Ahrefs keywords
                {ahrefsQ.isLoading && <span className="ml-1 font-normal">loading…</span>}
              </p>
              <p className="mb-2 text-[10px] text-rp-tlight">
                Select 1–2 keywords for AI generation, or click to insert into the description.
              </p>
              <div className="max-h-[280px] overflow-y-auto rounded-lg border border-rp-border bg-[#F8FAFC] p-2 space-y-1">
                {ahrefsQ.isError && (
                  <p className="px-1 text-[11px] text-red-600">
                    {formatApiError(ahrefsQ.error)}
                  </p>
                )}
                {ahrefsKws.length === 0 && !ahrefsQ.isLoading && !ahrefsQ.isError && (
                  <p className="text-[11px] text-rp-tlight px-1">
                    {d.primary_keyword
                      ? `No Ahrefs suggestions yet for “${d.primary_keyword.split(",")[0]?.trim()}”.`
                      : "No keywords yet — complete onboarding first."}
                  </p>
                )}
                {ahrefsKws.map((item) => {
                  const kw = item.keyword;
                  const checked = selectedKws.includes(kw);
                  return (
                    <div key={kw} className="flex items-center gap-1.5">
                      <button
                        type="button"
                        onClick={() => toggleKw(kw)}
                        className={`flex h-4 w-4 shrink-0 items-center justify-center rounded border text-[9px] font-bold transition ${
                          checked
                            ? "border-[#34A853] bg-[#34A853] text-white"
                            : "border-rp-border bg-white text-transparent"
                        }`}
                      >
                        ✓
                      </button>
                      <button
                        type="button"
                        title={`Insert into description · ${formatKeywordVolume(item.avg_monthly_searches)}`}
                        onClick={() =>
                          setEditBody((b) => (b ? `${b} ${kw}` : kw))
                        }
                        className="flex-1 text-left text-[11px] text-navy hover:text-[#1A73E8] hover:underline truncate"
                      >
                        {kw}
                        <span className="ml-1 text-[9px] text-rp-tlight">
                          {formatKeywordVolume(item.avg_monthly_searches)}
                        </span>
                      </button>
                    </div>
                  );
                })}
              </div>
              {selectedKws.length > 0 && (
                <p className="mt-1.5 text-[10px] text-[#137333]">
                  {selectedKws.length} keyword{selectedKws.length > 1 ? "s" : ""} selected — AI will use only these
                </p>
              )}
              {selectedKws.length === 0 && (
                <p className="mt-1.5 text-[10px] text-amber-700">
                  Pick at least 1 keyword before generating.
                </p>
              )}
            </div>

            {/* Description editor */}
            <div className="space-y-2">
              {isHistoryReadOnly && viewingItem && (
                <p className="rounded-md border border-rp-border bg-rp-light px-3 py-2 text-[11px] text-rp-tlight">
                  Viewing {viewingItem.status.replace(/_/g, " ")} version from{" "}
                  {formatGbpHistoryDate(
                    viewingItem.published_at ||
                      viewingItem.generated_at ||
                      viewingItem.created_at,
                  )}{" "}
                  — read only.
                  {draft && viewingId !== draft.id && (
                    <button
                      type="button"
                      className="ml-2 font-semibold text-[#1A73E8] hover:underline"
                      onClick={() => {
                        setViewingId(draft.id);
                        setEditBody(draftBody);
                        setScheduleDate(draft.scheduled_for?.slice(0, 10) ?? "");
                      }}
                    >
                      Back to current draft
                    </button>
                  )}
                  <button
                    type="button"
                    className="ml-2 font-semibold text-[#1A73E8] hover:underline"
                    onClick={() => setViewingId(null)}
                  >
                    Edit this version
                  </button>
                </p>
              )}
              <div className="relative">
                <textarea
                  rows={14}
                  value={editBody}
                  readOnly={!canEdit}
                  onChange={(e) => setEditBody(e.target.value)}
                  placeholder="Type or paste your GBP description here, or generate with AI using the selected keywords…"
                  className={`w-full resize-y rounded-md border p-2.5 text-[12px] leading-relaxed text-navy placeholder:text-rp-tlight focus:outline-none focus:ring-1 ${
                    !canEdit ? "cursor-default bg-[#F8FAFC]" : "bg-white"
                  } ${
                    overLimit
                      ? "border-red-400 focus:ring-red-400"
                      : "border-rp-border focus:border-[#34A853] focus:ring-[#34A853]"
                  }`}
                />
                {/* Live character counter overlay */}
                <div
                  className={`absolute bottom-2.5 right-2.5 rounded px-1.5 py-0.5 text-[10px] font-bold ${
                    overLimit
                      ? "bg-red-100 text-red-600"
                      : remaining <= 50
                        ? "bg-amber-100 text-amber-700"
                        : "bg-rp-light text-rp-tlight"
                  }`}
                >
                  {overLimit ? `−${Math.abs(remaining)}` : `${charCount} / 750`}
                </div>
              </div>
              <p className={`text-[10px] ${overLimit ? "font-semibold text-red-600" : "text-rp-tlight"}`}>
                {overLimit
                  ? `${Math.abs(remaining)} characters over Google's 750-char limit — shorten the text`
                  : `${remaining} characters remaining · Google shows your full description (no truncation)`}
              </p>

              {draft?.status === "approved" && draft.scheduled_for && (
                <p className="text-[11px] font-semibold text-[#137333]">
                  📅 Auto-publishes {new Date(draft.scheduled_for).toLocaleDateString("en-AU")}
                </p>
              )}

              {canAct && (
                <div className="space-y-2">
                  <div className="flex flex-wrap items-center gap-2 rounded-lg border border-rp-border bg-rp-light px-3 py-2">
                    <label className="text-[11px] font-bold uppercase tracking-wide text-rp-tlight">
                      📅 Publish date
                    </label>
                    <input
                      type="date"
                      min={todayStr}
                      value={scheduleDate}
                      onChange={(e) => setScheduleDate(e.target.value)}
                      className="rounded-md border border-rp-border bg-white px-2 py-1 text-[12px] text-navy outline-none ring-[#72C219]/30 focus:ring-2"
                    />
                    <span className="text-[11px] text-rp-tlight">
                      {scheduleDate
                        ? `Auto-publishes on ${new Date(scheduleDate).toLocaleDateString("en-AU")}`
                        : "Leave empty to auto-schedule (next free day)"}
                    </span>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={busy || selectedKws.length === 0}
                      onClick={() => onGenerate(selectedKws)}
                    >
                      {busy
                        ? "Generating…"
                        : selectedKws.length > 0
                          ? `Generate with ${selectedKws.length} keyword${selectedKws.length > 1 ? "s" : ""}`
                          : "Select keywords to generate"}
                    </Button>
                    <Button
                      size="sm"
                      disabled={busy || overLimit || !editBody.trim()}
                      onClick={() => onApprove(draft?.id ?? "", editBody.trim(), scheduleDate || undefined)}
                    >
                      ✓ Approve for schedule
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={busy || overLimit || !editBody.trim()}
                      onClick={() => onPublish(draft?.id ?? "", editBody.trim())}
                    >
                      Publish to GBP now
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={busy || !editBody.trim()}
                      onClick={() => onSaveDraft(editBody.trim(), draft?.id)}
                    >
                      {saveDraftPending ? "Saving…" : "Save draft"}
                    </Button>
                  </div>
                </div>
              )}

              {!canAct && (
                <div className="flex flex-wrap gap-2">
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={busy || selectedKws.length === 0}
                    onClick={() => onGenerate(selectedKws)}
                  >
                    {busy
                      ? "Generating…"
                      : selectedKws.length > 0
                        ? `Regenerate with ${selectedKws.length} keyword${selectedKws.length > 1 ? "s" : ""}`
                        : "Select keywords to regenerate"}
                  </Button>
                </div>
              )}

              {(() => {
                const used = asArray<string>(viewingItem?.keywords_used);
                const kws = (used.length > 0 ? used : selectedKws).slice(0, 2);
                return kws.map((kw) => <KeywordCompetitorsPanel key={kw} keyword={kw} />);
              })()}
            </div>
          </div>
        </div>
      </Card>

      {/* Keyword audit */}
      {audit.length > 0 && (
        <Card>
          <CardHeader title="Keyword audit" subtitle="Which target keywords appear in your description" />
          <div className="divide-y divide-rp-border">
            {audit.map((a) => (
              <div key={a.keyword} className="flex items-center gap-3 px-4 py-2.5">
                <span className={`h-2 w-2 shrink-0 rounded-full ${a.present ? "bg-[#34A853]" : "bg-red-400"}`} />
                <span className="flex-1 text-[12px] text-navy">{a.keyword}</span>
                <span className="text-[11px] text-rp-tlight">{a.count}×</span>
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* Missing keywords */}
      {gaps.length > 0 && (
        <Card>
          <CardHeader title="Missing keywords" subtitle="Click to append to description" />
          <div className="flex flex-wrap gap-2 p-4">
            {gaps.map((g) => (
              <button
                key={g}
                type="button"
                className="rounded-full border border-red-200 bg-red-50 px-2 py-0.5 text-[11px] text-red-700 hover:bg-red-100"
                onClick={() => setEditBody((b) => b ? `${b} ${g}` : g)}
              >
                + {g}
              </button>
            ))}
          </div>
        </Card>
      )}

      {/* Live Google description */}
      <Card>
        <CardHeader title="Live description (Google)" subtitle="Currently shown on your listing" />
        <div className="p-4 text-[12px] leading-relaxed text-navy whitespace-pre-wrap">
          {liveDesc || <span className="text-rp-tlight">No description on your Google listing yet.</span>}
        </div>
      </Card>

      <DescriptionHistory
        items={history}
        activeId={viewingId}
        onSelect={(item) => {
          setViewingId(item.id);
          setEditBody(item.body ?? "");
          setScheduleDate(item.scheduled_for?.slice(0, 10) ?? "");
        }}
      />
    </div>
  );
}

// ── Photos Tab ────────────────────────────────────────────────────────────────

type PhotoPreviewState = { src: string; caption: string };

function KeywordPreviewModal({
  keyword,
  onClose,
}: {
  keyword: string | null;
  onClose: () => void;
}) {
  useEffect(() => {
    if (!keyword) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [keyword, onClose]);

  if (!keyword) return null;

  return (
    <div
      className="fixed inset-0 z-[999] flex items-center justify-center bg-black/50 p-4"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-label="Keyword preview"
    >
      <div
        className="relative w-full max-w-lg rounded-xl bg-white p-5 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <button
          type="button"
          onClick={onClose}
          className="absolute right-3 top-3 flex h-8 w-8 items-center justify-center rounded-full bg-rp-light text-navy hover:bg-[#E8EFF7]"
          aria-label="Close"
        >
          <X className="h-4 w-4" />
        </button>
        <p className="mb-2 text-[10px] font-bold uppercase tracking-[0.08em] text-[#8EA3BC]">
          Full keyword
        </p>
        <p className="break-words pr-8 text-sm leading-relaxed text-navy">{keyword}</p>
      </div>
    </div>
  );
}

function photoDisplayLabel(ph: {
  prompt?: string | null;
  slot_label?: string | null;
  source?: string | null;
}): string {
  const raw = (ph.prompt ?? "").trim();
  if (raw.startsWith("{")) {
    try {
      const parsed = JSON.parse(raw) as { meta?: { keyword?: string; archetype?: string }; prompt?: string };
      const kw = parsed.meta?.keyword?.trim();
      const arch = parsed.meta?.archetype?.trim();
      if (kw && arch) return `${kw} · ${arch.replace(/_/g, " ")}`;
      if (kw) return kw;
      if (parsed.prompt) return parsed.prompt.slice(0, 120);
    } catch {
      /* plain text prompt */
    }
  }
  return raw || ph.slot_label || ph.source || "GBP photo";
}

function ImagePreviewModal({
  preview,
  onClose,
}: {
  preview: PhotoPreviewState | null;
  onClose: () => void;
}) {
  useEffect(() => {
    if (!preview) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [preview, onClose]);

  if (!preview) return null;

  return (
    <div
      className="fixed inset-0 z-[999] flex items-center justify-center bg-black/75 p-4"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-label="Photo preview"
    >
      <div
        className="relative max-h-[92vh] w-full max-w-4xl overflow-hidden rounded-xl bg-white shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <button
          type="button"
          onClick={onClose}
          className="absolute right-3 top-3 z-10 flex h-8 w-8 items-center justify-center rounded-full bg-black/55 text-white hover:bg-black/75"
          aria-label="Close preview"
        >
          <X className="h-4 w-4" />
        </button>
        <img
          src={preview.src}
          alt={preview.caption}
          className="max-h-[78vh] w-full bg-[#111] object-contain"
        />
        {preview.caption ? (
          <p className="border-t border-rp-border px-4 py-3 text-sm text-navy">{preview.caption}</p>
        ) : null}
      </div>
    </div>
  );
}

function PhotosTab({ d, token }: { d: GbpOverview; token: string | null }) {
  const qc = useQueryClient();
  const photos = asArray<GbpPhoto>(d.library_photos);
  const [promptText, setPromptText] = useState("");
  const [preview, setPreview] = useState<PhotoPreviewState | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const generatePhoto = useMutation({
    mutationFn: ({ prompt, slot }: { prompt: string; slot?: string }) =>
      generateGbpPhoto(prompt, slot),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["gbp"] }),
  });

  const uploadPhoto = useMutation({
    mutationFn: (file: File) => uploadGbpPhoto(file),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["gbp"] }),
  });

  const deletePhoto = useMutation({
    mutationFn: (id: string) => deleteGbpPhoto(id),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["gbp"] }),
  });

  const publishPhoto = useMutation({
    mutationFn: (id: string) => publishGbpPhoto(id),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["gbp"] }),
  });

  return (
    <div className="space-y-4">
      <ImagePreviewModal preview={preview} onClose={() => setPreview(null)} />
      <Card>
        <CardHeader title="Generate photo" subtitle="AI-generated via Runway — describe the scene" />
        <div className="p-4 space-y-3">
          <textarea
            rows={3}
            value={promptText}
            onChange={(e) => setPromptText(e.target.value)}
            placeholder="e.g. Professional team in a modern Melbourne office, natural light, friendly"
            className="w-full resize-none rounded-md border border-rp-border bg-white p-2.5 text-[12px] text-navy placeholder:text-rp-tlight focus:border-[#34A853] focus:outline-none focus:ring-1 focus:ring-[#34A853]"
          />
          <div className="flex gap-2">
            <Button
              size="sm"
              disabled={generatePhoto.isPending || !promptText.trim()}
              onClick={() => void generatePhoto.mutate({ prompt: promptText.trim() })}
            >
              <Sparkles className="mr-1.5 h-3.5 w-3.5" />
              {generatePhoto.isPending ? "Generating…" : "Generate with AI"}
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={() => fileRef.current?.click()}
              disabled={uploadPhoto.isPending}
            >
              <Upload className="mr-1.5 h-3.5 w-3.5" />
              {uploadPhoto.isPending ? "Uploading…" : "Upload photo"}
            </Button>
            <input
              ref={fileRef}
              type="file"
              accept="image/*"
              className="hidden"
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) void uploadPhoto.mutate(f);
              }}
            />
          </div>
          {(generatePhoto.isError || uploadPhoto.isError) && (
            <p className="text-xs text-red-600">
              {formatApiError(generatePhoto.error ?? uploadPhoto.error)}
            </p>
          )}
        </div>
      </Card>

      <Card>
        <CardHeader
          title="Photo library"
          subtitle={`${photos.length} photo${photos.length !== 1 ? "s" : ""}`}
        />
        {photos.length === 0 ? (
          <p className="px-4 py-8 text-center text-sm text-rp-tlight">
            No photos yet — generate or upload above.
          </p>
        ) : (
          <div className="grid gap-3 p-4 sm:grid-cols-2 lg:grid-cols-3">
              {photos.map((ph) => {
              const src = `/api/v1/gbp/photos/${ph.id}/file${token ? `?token=${token}` : ""}`;
              const caption = photoDisplayLabel(ph);
              return (
              <div key={ph.id} className="group relative overflow-hidden rounded-lg border border-rp-border bg-rp-light">
                <button
                  type="button"
                  className="block w-full cursor-zoom-in text-left"
                  title="Click to preview full size"
                  onClick={() => setPreview({ src, caption })}
                >
                  <img
                    src={src}
                    alt={caption}
                    className="h-36 w-full object-cover transition group-hover:opacity-90"
                    onError={(e) => { (e.target as HTMLImageElement).style.display = "none"; }}
                  />
                </button>
                <div className="p-2">
                  <p className="truncate text-[11px] text-rp-tlight">{caption}</p>
                  <div className="mt-2 flex gap-1.5">
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={publishPhoto.isPending}
                      onClick={() => void publishPhoto.mutate(ph.id)}
                    >
                      Publish
                    </Button>
                    <button
                      className="rounded p-1 text-red-400 hover:bg-red-50"
                      onClick={() => void deletePhoto.mutate(ph.id)}
                      disabled={deletePhoto.isPending}
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </div>
                </div>
              </div>
              );
            })}
          </div>
        )}
      </Card>
    </div>
  );
}

// ── Brand Kit Tab ─────────────────────────────────────────────────────────────

function BrandKitTab({ d }: { d: GbpOverview }) {
  const qc = useQueryClient();
  const token = useAuthStore((s) => s.accessToken);
  const bk = d.brand_kit ?? {};
  const [form, setForm] = useState<GbpBrandKit>({
    brand_name: bk.brand_name ?? "",
    agency_type: bk.agency_type ?? "",
    language: bk.language ?? "English",
    brand_voice: bk.brand_voice ?? "",
    forbidden_words: bk.forbidden_words ?? "",
    primary_color: bk.primary_color ?? "#FF5F32",
    secondary_color: bk.secondary_color ?? "#000000",
    heading_font: bk.heading_font ?? "",
    body_font: bk.body_font ?? "",
  });
  const logoLightRef = useRef<HTMLInputElement>(null);
  const logoDarkRef = useRef<HTMLInputElement>(null);
  const logoUrl = (path?: string | null) =>
    path ? `${path}${token ? `?token=${encodeURIComponent(token)}` : ""}` : null;
  const field = (k: keyof GbpBrandKit) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) =>
    setForm((f) => ({ ...f, [k]: e.target.value }));

  const save = useMutation({
    mutationFn: () => saveGbpBrandKit(form),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["gbp"] }),
  });
  const uploadLogo = useMutation({
    mutationFn: ({ file, variant }: { file: File; variant: "light" | "dark" }) =>
      uploadGbpBrandLogo(file, variant),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["gbp"] }),
  });

  const inputCls = "w-full rounded-md border border-rp-border bg-white px-3 py-2 text-[12px] text-navy focus:border-[#34A853] focus:outline-none focus:ring-1 focus:ring-[#34A853]";

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader title="Brand Kit" subtitle="Controls AI post tone, colours, and logo" />
        <div className="grid gap-4 p-4 sm:grid-cols-2">
          <div>
            <label className="mb-1 block text-[10px] font-bold uppercase tracking-wide text-[#8EA3BC]">Brand name</label>
            <input className={inputCls} value={form.brand_name ?? ""} onChange={field("brand_name")} />
          </div>
          <div>
            <label className="mb-1 block text-[10px] font-bold uppercase tracking-wide text-[#8EA3BC]">Agency type</label>
            <input className={inputCls} value={form.agency_type ?? ""} onChange={field("agency_type")} />
          </div>
          <div>
            <label className="mb-1 block text-[10px] font-bold uppercase tracking-wide text-[#8EA3BC]">Language</label>
            <select className={inputCls} value={form.language ?? "English"} onChange={field("language")}>
              {["English", "Spanish", "French", "German", "Italian", "Portuguese"].map((l) => (
                <option key={l}>{l}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="mb-1 block text-[10px] font-bold uppercase tracking-wide text-[#8EA3BC]">Primary colour</label>
            <input type="color" className="h-9 w-full cursor-pointer rounded-md border border-rp-border" value={form.primary_color ?? "#FF5F32"} onChange={field("primary_color")} />
          </div>
          <div className="sm:col-span-2">
            <label className="mb-1 block text-[10px] font-bold uppercase tracking-wide text-[#8EA3BC]">Brand voice</label>
            <textarea rows={3} className={inputCls} value={form.brand_voice ?? ""} onChange={field("brand_voice")} placeholder="e.g. friendly, professional, concise — no jargon" />
          </div>
          <div className="sm:col-span-2">
            <label className="mb-1 block text-[10px] font-bold uppercase tracking-wide text-[#8EA3BC]">Forbidden words / claims</label>
            <input className={inputCls} value={form.forbidden_words ?? ""} onChange={field("forbidden_words")} placeholder="e.g. best, #1, guaranteed" />
          </div>
        </div>

        <div className="flex flex-wrap gap-3 border-t border-rp-border p-4">
          <Button size="sm" disabled={save.isPending} onClick={() => void save.mutate()}>
            {save.isPending ? "Saving…" : "Save brand kit"}
          </Button>
          <Button size="sm" variant="outline" onClick={() => logoLightRef.current?.click()}>
            <Upload className="mr-1.5 h-3.5 w-3.5" />
            Upload black logo (light bg)
          </Button>
          <Button size="sm" variant="outline" onClick={() => logoDarkRef.current?.click()}>
            <Upload className="mr-1.5 h-3.5 w-3.5" />
            Upload white logo (dark bg)
          </Button>
          <input
            ref={logoLightRef}
            type="file"
            accept="image/*"
            className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) void uploadLogo.mutate({ file: f, variant: "light" });
              e.target.value = "";
            }}
          />
          <input
            ref={logoDarkRef}
            type="file"
            accept="image/*"
            className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) void uploadLogo.mutate({ file: f, variant: "dark" });
              e.target.value = "";
            }}
          />
        </div>

        {(bk.logo_on_light_url || bk.logo_on_dark_url) && (
          <div className="border-t border-rp-border p-4">
            <p className="mb-3 text-[10px] font-bold uppercase text-[#8EA3BC]">Logo preview</p>
            <div className="flex flex-wrap gap-4">
              {bk.logo_on_light_url ? (
                <div className="rounded-lg border border-rp-border bg-white p-4">
                  <p className="mb-2 text-[10px] font-semibold text-rp-tlight">Black logo · light backgrounds</p>
                  <img
                    src={logoUrl(bk.logo_on_light_url) ?? undefined}
                    alt="Black Clicktrends logo for light backgrounds"
                    className="max-h-16 object-contain"
                  />
                </div>
              ) : null}
              {bk.logo_on_dark_url ? (
                <div className="rounded-lg border border-rp-border bg-[#1A1A2E] p-4">
                  <p className="mb-2 text-[10px] font-semibold text-white/70">White logo · dark backgrounds</p>
                  <img
                    src={logoUrl(bk.logo_on_dark_url) ?? undefined}
                    alt="White Clicktrends logo for dark backgrounds"
                    className="max-h-16 object-contain"
                  />
                </div>
              ) : null}
            </div>
          </div>
        )}
      </Card>
    </div>
  );
}

// ── Services Tab ──────────────────────────────────────────────────────────────

function ServicesTab({ d }: { d: GbpOverview }) {
  const services = asArray<string>(d.gbp_services_on_listing);

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader
          title="Services on your GBP listing"
          subtitle="Fetched live from Google Business Profile"
        />
        {services.length === 0 ? (
          <p className="px-4 py-6 text-center text-sm text-rp-tlight">
            No services found on your GBP listing. Add them in Google Business Profile.
          </p>
        ) : (
          <div className="max-h-80 overflow-y-auto divide-y divide-rp-border">
            {services.map((s) => (
              <div key={s} className="flex items-center gap-3 px-4 py-2.5">
                <span className="h-2 w-2 shrink-0 rounded-full bg-[#34A853]" />
                <span className="text-[13px] text-navy">{s}</span>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}

// ── Activity feed ─────────────────────────────────────────────────────────────

function ActivityFeed({ items }: { items?: { type: string; description: string; occurred_at: string; status: string }[] }) {
  if (!items || items.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center gap-2 py-10 text-center">
        <MapPin className="h-6 w-6 text-rp-tlight" />
        <p className="text-sm text-rp-tlight">No GBP activity yet.</p>
      </div>
    );
  }
  return (
    <div className="max-h-72 overflow-y-auto divide-y divide-rp-border">
      {items.map((item, i) => (
        <div key={i} className="flex items-start gap-3 px-4 py-3">
          <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-teal/10 text-teal">
            <MapPin className="h-4 w-4" />
          </div>
          <div>
            <p className="text-[13px] font-semibold capitalize text-navy">
              {item.type.replace(/_/g, " ")}
            </p>
            <p className="text-xs text-rp-tlight">{item.description}</p>
            <p className="mt-0.5 text-[11px] text-rp-tlight">
              {new Date(item.occurred_at).toLocaleString("en-AU")}
            </p>
          </div>
        </div>
      ))}
    </div>
  );
}

// ── Not Connected ─────────────────────────────────────────────────────────────

function NotConnected() {
  return (
    <div className="space-y-4">
      <Card>
        <div className="px-4 py-8 text-center">
          <ShieldCheck className="mx-auto mb-3 h-10 w-10 text-rp-tlight" />
          <p className="text-sm font-semibold text-navy">GBP not connected</p>
          <p className="mt-1 max-w-sm mx-auto text-xs text-rp-tlight">
            Connect your Google Business Profile in Settings → Integrations to unlock AI posts,
            description editing, photo management, and the GBP health score.
          </p>
          <div className="mt-4">
            <Link to="/settings" className="inline-flex items-center gap-1 rounded-lg bg-navy px-4 py-2 text-sm font-semibold text-white hover:bg-navy/90">
              Go to Integrations →
            </Link>
          </div>
        </div>
      </Card>
    </div>
  );
}

// ── Main Page ─────────────────────────────────────────────────────────────────

export function GbpPage() {
  const token = useAuthStore((s) => s.accessToken);
  const qc = useQueryClient();
  const [tab, setTab] = useState<TabId>("posts");

  const overview = useQuery({
    queryKey: ["gbp", "overview", token],
    queryFn: fetchGbpOverview,
    enabled: Boolean(token),
  });

  const profileQ = useQuery({
    queryKey: ["me", "gbp-scope"],
    queryFn: fetchMeForAuth,
    enabled: Boolean(token),
    staleTime: 60_000,
  });

  const [generatePostNote, setGeneratePostNote] = useState<string | null>(null);

  const generatePost = useMutation({
    mutationFn: ({ count, prompts }: { count: number; prompts: string }) =>
      generateGbpPosts(count, prompts || null),
    onSuccess: (data) => {
      void qc.invalidateQueries({ queryKey: ["gbp"] });
      void qc.invalidateQueries({ queryKey: ["me", "gbp-scope"] });
      const scope = (data as Record<string, unknown>).location_scope as string ?? "";
      const area = (data as Record<string, unknown>).target_area as string ?? "";
      const scopeNote = scope && area ? ` Location: ${scope === "city" ? "City" : "Suburb"} — ${area}.` : "";
      const count = (data as Record<string, unknown>).generated as number ?? 1;
      if (count > 1) {
        const kws = ((data as Record<string, unknown>).keywords_used as string[])?.join(", ") ?? "";
        setGeneratePostNote(`Generated ${count} posts.${kws ? ` Keywords: ${kws}.` : ""}${scopeNote}`);
      } else {
        setGeneratePostNote(scopeNote.trim() || null);
      }
    },
  });

  const savePostDraft = useMutation({
    mutationFn: ({ id, body }: { id: string; body: string }) => updateGbpPost(id, { body }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["gbp"] }),
  });

  const approvePost = useMutation({
    mutationFn: ({ id, body, scheduledFor }: { id: string; body: string; scheduledFor?: string }) =>
      updateGbpPost(id, {
        status: "approved",
        body,
        ...(scheduledFor ? { scheduled_for: scheduledFor } : {}),
      }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["gbp"] }),
  });

  const publishPost = useMutation({
    mutationFn: ({ id, body }: { id: string; body: string }) =>
      updateGbpPost(id, { status: "published", body }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["gbp"] }),
  });

  const syncPosts = useMutation({
    mutationFn: syncGbpPosts,
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["gbp"] }),
  });

  const markPostRemoved = useMutation({
    mutationFn: (id: string) => updateGbpPost(id, { status: "removed_on_gbp" }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["gbp"] }),
  });

  const deletePost = useMutation({
    mutationFn: (id: string) => deleteGbpPost(id),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["gbp"] }),
  });

  const generateDesc = useMutation({
    mutationFn: (keywords: string[]) => generateGbpDescription(keywords),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["gbp"] }),
  });

  const saveDescDraft = useMutation({
    mutationFn: ({ body, draftId }: { body: string; draftId?: string }) =>
      draftId ? updateGbpDescription(draftId, { body }) : saveGbpDescriptionDraft(body),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["gbp"] }),
  });

  const approveDesc = useMutation({
    mutationFn: async ({
      id,
      body,
      scheduledFor,
    }: {
      id: string;
      body: string;
      scheduledFor?: string;
    }) => {
      const descId = id || (await saveGbpDescriptionDraft(body) as GbpQueueItem).id;
      return updateGbpDescription(descId, {
        status: "approved",
        body,
        ...(scheduledFor ? { scheduled_for: scheduledFor } : {}),
      });
    },
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["gbp"] }),
  });

  const publishDesc = useMutation({
    mutationFn: async ({ id, body }: { id: string; body: string }) => {
      const descId = id || (await saveGbpDescriptionDraft(body) as GbpQueueItem).id;
      return updateGbpDescription(descId, { status: "published", body });
    },
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["gbp"] }),
  });

  const scheduleAll = useMutation({
    mutationFn: ({ mode, start, end }: { mode: "daily" | "range"; start?: string; end?: string }) =>
      scheduleAllGbpPosts(mode, start, end),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["gbp"] }),
  });

  const exportXlsx = useMutation({
    mutationFn: (opts: GbpPostsExportOptions) => downloadGbpPostsXlsx(opts),
  });

  const d = overview.data;
  const busy =
    generatePost.isPending ||
    approvePost.isPending ||
    publishPost.isPending ||
    savePostDraft.isPending ||
    syncPosts.isPending ||
    markPostRemoved.isPending ||
    deletePost.isPending ||
    scheduleAll.isPending ||
    generateDesc.isPending ||
    saveDescDraft.isPending ||
    approveDesc.isPending ||
    publishDesc.isPending;

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <TopBar
        title="GBP Optimiser"
        subtitle={
          d?.connected
            ? `${d.business_name ?? ""}${d.location_name ? ` · ${d.location_name}` : ""}`
            : "Google Business Profile — weekly posts, Q&A, and health score"
        }
      />

      <div className="page-scroll px-6 py-5">
        {overview.isPending || overview.isLoading ? (
          <p className="text-sm text-rp-tlight">Loading GBP data…</p>
        ) : overview.isError ? (
          <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            Could not load GBP data: {formatApiError(overview.error)}
          </div>
        ) : !d ? (
          <div className="rounded-lg border border-rp-border bg-white px-4 py-6 text-center text-sm text-rp-tlight">
            No GBP data returned. Try refreshing the page.
          </div>
        ) : !d.connected ? (
          <NotConnected />
        ) : (
          <>
            {/* Connected banner */}
            <div className="mb-4 rounded-lg border border-[#CEEAD6] bg-[#E6F4EA] px-4 py-2.5 text-[12px] text-[#1E6B37]">
              <strong>GBP connected</strong>
              {d.location_name && <> — listing <strong>{d.location_name}</strong></>}
              {d.business_name && ` · ${d.business_name}`}
            </div>

            {/* Location scope banner */}
            {profileQ.data && (
              <div
                className={`mb-4 flex items-center gap-2 rounded-lg border px-4 py-2.5 text-[12px] ${
                  profileQ.data.location_scope === "city"
                    ? "border-[#C2E0FF] bg-[#E8F4FF] text-[#0050A0]"
                    : "border-[#FFE5B4] bg-[#FFF8E7] text-[#7A4700]"
                }`}
              >
                <MapPin className="h-3.5 w-3.5 shrink-0" />
                <span>
                  <strong>Post location mode: </strong>
                  {profileQ.data.location_scope === "city" ? (
                    <>
                      <strong>City</strong> — posts use{" "}
                      <strong>{profileQ.data.metro_label?.split(",")[0]?.trim() ?? profileQ.data.metro_label}</strong>{" "}
                      only (no suburb names).
                    </>
                  ) : (
                    <>
                      <strong>Suburb</strong> — posts use{" "}
                      <strong>{profileQ.data.primary_suburb || "your anchor suburb"}</strong>.
                    </>
                  )}
                </span>
                <Link to="/onboarding" className="ml-auto shrink-0 rounded px-2 py-0.5 font-semibold underline hover:no-underline">
                  Change in Business Setup →
                </Link>
              </div>
            )}

            {/* Tab bar */}
            <div className="tab-bar mb-4">
              {TABS.map((t) => (
                <button
                  key={t.id}
                  type="button"
                  onClick={() => setTab(t.id)}
                  className={`flex flex-1 items-center justify-center gap-1.5 rounded-md px-2 py-2 text-[11px] font-medium transition ${
                    tab === t.id ? "tab-bar-active" : "text-neutral-500 hover:text-neutral-900"
                  }`}
                >
                  <t.icon className="h-3.5 w-3.5" />
                  <span className="hidden sm:inline">{t.label}</span>
                </button>
              ))}
            </div>

            {/* Tab panels — mount active tab only; error boundary isolates tab crashes */}
            {tab === "overview" && (
              <TabErrorBoundary label="Overview">
                <OverviewTab d={d} />
              </TabErrorBoundary>
            )}
            {tab === "posts" && (
              <TabErrorBoundary label="Posts">
              <PostsTab
                d={d}
                token={token}
                busy={busy}
                saveDraftPending={savePostDraft.isPending}
                syncPostsPending={syncPosts.isPending}
                onGenerate={(count, prompts) => void generatePost.mutate({ count, prompts })}
                onSaveDraft={(id, body) => void savePostDraft.mutate({ id, body })}
                onApprove={(id, body, scheduledFor) =>
                  void approvePost.mutate({ id, body, scheduledFor })
                }
                onPublish={(id, body) => void publishPost.mutate({ id, body })}
                onSyncPosts={() => void syncPosts.mutate()}
                onDeletePost={(id) => void deletePost.mutate(id)}
                onScheduleAll={(mode, start, end) =>
                  void scheduleAll.mutate({ mode, start, end })
                }
                onDownloadExcel={(opts) => void exportXlsx.mutate(opts)}
                scheduleAllPending={scheduleAll.isPending}
                exportPending={exportXlsx.isPending}
              />
              </TabErrorBoundary>
            )}
            {tab === "description" && (
              <TabErrorBoundary label="Description & Keywords">
                <DescriptionTab
                  d={d}
                  busy={busy}
                  saveDraftPending={saveDescDraft.isPending}
                  onGenerate={(kws) => void generateDesc.mutate(kws)}
                  onSaveDraft={(body, draftId) => void saveDescDraft.mutate({ body, draftId })}
                  onApprove={(id, body, scheduledFor) =>
                    void approveDesc.mutate({ id, body, scheduledFor })
                  }
                  onPublish={(id, body) => void publishDesc.mutate({ id, body })}
                />
              </TabErrorBoundary>
            )}
            {tab === "keywords" && (
              <TabErrorBoundary label="Keyword Research">
                <AhrefsKeywordOverview defaultKeyword={d.primary_keyword?.split(",")[0]?.trim() ?? ""} />
              </TabErrorBoundary>
            )}
            {tab === "ahrefs" && (
              <TabErrorBoundary label="Ahrefs Overview">
                <CompetitorKeywordsOverview />
              </TabErrorBoundary>
            )}
            {tab === "photos" && (
              <TabErrorBoundary label="Photos">
                <PhotosTab d={d} token={token} />
              </TabErrorBoundary>
            )}
            {tab === "brandkit" && (
              <TabErrorBoundary label="Brand Kit">
                <BrandKitTab d={d} />
              </TabErrorBoundary>
            )}
            {tab === "services" && (
              <TabErrorBoundary label="Services">
                <ServicesTab d={d} />
              </TabErrorBoundary>
            )}

            {tab !== "description" && (
              <Card className="mt-4">
                <CardHeader title="GBP Activity Feed" subtitle="Posts, descriptions, and queue events" />
                <ActivityFeed items={d.activity} />
              </Card>
            )}
          </>
        )}

        {/* Errors */}
        {(generatePost.isError || approvePost.isError || publishPost.isError || savePostDraft.isError) && (
          <p className="mt-3 text-sm text-red-600">
            {formatApiError(generatePost.error ?? approvePost.error ?? publishPost.error ?? savePostDraft.error)}
          </p>
        )}
        {approvePost.isSuccess && tab === "posts" && (
          <p className="mt-3 text-sm text-[#137333]">Post approved for schedule.</p>
        )}
        {publishPost.isSuccess && tab === "posts" && (
          <p className="mt-3 text-sm text-[#137333]">Post sent to Google Business Profile.</p>
        )}
        {generatePostNote && tab === "posts" && (
          <p className="mt-3 text-sm text-[#137333]">{generatePostNote}</p>
        )}
      </div>
    </div>
  );
}
