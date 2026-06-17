import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ExternalLink, X, ZoomIn } from "lucide-react";
import { useMemo, useState } from "react";

import { formatApiError } from "../api/client";
import {
  approveAll,
  downloadContentPlanExcel,
  fetchContentQueue,
  generateMonthlyTimeline,
  publishContentItem,
  updateItemStatus,
} from "../api/contentQueue";
import { fetchIntegrationsStatus } from "../api/integrations";
import { fetchMe } from "../api/onboarding";
import {
  fetchContentTemplates,
  fetchSuburbPageHistory,
  fetchSuburbPageHistoryItem,
  fetchSuburbPageModules,
  fetchWordpressPages,
  deleteSuburbPageHistory,
  generateSuburbPage,
  generateWordpressContent,
  generateWordpressMeta,
  publishSuburbPage,
  updateWordpressPageSeo,
  saveWordpressPageContent,
  type GenerateSuburbPageResponse,
  type SeoWebsitePage,
} from "../api/seoWebsite";
import { gbpPhotoFileUrl } from "../api/gbp";
import { FaqAccordionPreview } from "../components/seo/FaqAccordionPreview";
import { WordPressLivePageEditor } from "../components/seo/WordPressLivePageEditor";
import { TopBar } from "../components/layout/TopBar";
import { AhrefsKeywordExplorer } from "../components/keywords/AhrefsKeywordExplorer";
import { Button } from "../components/ui/Button";
import { Card, CardHeader } from "../components/ui/Card";
import { useAuthStore } from "../stores/authStore";

function slugifyKeyword(raw: string): string {
  return raw
    .toLowerCase()
    .replace(/[^\w\s-]/g, "")
    .replace(/[\s_]+/g, "-")
    .replace(/-+/g, "-")
    .replace(/^-|-$/g, "")
    .slice(0, 80);
}

const MANUAL_MODULE_GROUPS: { key: string; label: string; types: string[] }[] = [
  { key: "credibility", label: "Credibility (pick 1)", types: ["F", "G", "K"] },
  { key: "service", label: "Service explanation (pick 1)", types: ["C", "D", "I"] },
  { key: "process", label: "Process / differentiator (pick 1)", types: ["E", "H"] },
  { key: "extra", label: "Local angle (pick 1)", types: ["B", "J"] },
];

function pickManualModule(groupTypes: string[], letter: string, current: string[]): string[] {
  const withoutGroup = current.filter((m) => !groupTypes.includes(m));
  return [...withoutGroup, letter];
}

export function SeoWebsitePage() {
  const token = useAuthStore((s) => s.accessToken);
  const qc = useQueryClient();
  const [search, setSearch] = useState("");
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [title, setTitle] = useState("");
  const [slug, setSlug] = useState("");
  const [excerpt, setExcerpt] = useState("");
  const [keywordInput, setKeywordInput] = useState("");
  const [generationMode, setGenerationMode] = useState<"default" | "research">("default");
  const [contentPrompt, setContentPrompt] = useState("");
  const [templateId, setTemplateId] = useState("service_page");
  const [generatedContent, setGeneratedContent] = useState("");
  const [pageModuleSetUsed, setPageModuleSetUsed] = useState<string[]>([]);
  const [pageWordCount, setPageWordCount] = useState(0);
  const [lastGeneratedMeta, setLastGeneratedMeta] = useState<{
    model: string;
    mode: "default" | "research";
    researchSignals: string[];
  } | null>(null);

  // Suburb / geo landing page builder (keyword + text + images → WordPress)
  const [sbKeyword, setSbKeyword] = useState("");
  const [sbSuburb, setSbSuburb] = useState("");
  const [sbSlug, setSbSlug] = useState("");
  const [sbSlugManual, setSbSlugManual] = useState(false);
  const [sbWordTarget, setSbWordTarget] = useState(1000);
  const [sbImageCount, setSbImageCount] = useState(2);
  const [sbStructureMode, setSbStructureMode] = useState<"auto" | "preset" | "manual">("auto");
  const [sbPresetId, setSbPresetId] = useState("balanced");
  const [sbOptionalModules, setSbOptionalModules] = useState<string[]>([]);
  const [sbNearbySuburbs, setSbNearbySuburbs] = useState("");
  const [sbServiceFocus, setSbServiceFocus] = useState("");
  const [sbResult, setSbResult] = useState<GenerateSuburbPageResponse | null>(null);
  const [sbHistoryId, setSbHistoryId] = useState<string | null>(null);
  const [sbTitle, setSbTitle] = useState("");
  const [sbExcerpt, setSbExcerpt] = useState("");
  const [sbContent, setSbContent] = useState("");
  const [sbPublishedUrl, setSbPublishedUrl] = useState("");
  const [liveEditPageId, setLiveEditPageId] = useState<number | null>(null);
  const [sbImageErrors, setSbImageErrors] = useState<Record<string, boolean>>({});
  const [sbImageViewer, setSbImageViewer] = useState<{ src: string; role: string } | null>(null);

  const meQ = useQuery({
    queryKey: ["me", token],
    queryFn: fetchMe,
    enabled: Boolean(token),
  });
  const statusQ = useQuery({
    queryKey: ["integrations", "status", token],
    queryFn: fetchIntegrationsStatus,
    enabled: Boolean(token),
  });
  const timelineMut = useMutation({
    mutationFn: generateMonthlyTimeline,
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["content-queue"] }),
  });
  const queueQ = useQuery({
    queryKey: ["content-queue", token],
    queryFn: fetchContentQueue,
    enabled: Boolean(token),
  });
  const approveAllMut = useMutation({
    mutationFn: approveAll,
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["content-queue"] }),
  });
  const approveItemMut = useMutation({
    mutationFn: (id: string) => updateItemStatus(id, "approved"),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["content-queue"] }),
  });
  const publishItemMut = useMutation({
    mutationFn: publishContentItem,
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["content-queue"] }),
  });
  const wpConnected = Boolean(statusQ.data?.wordpress?.connected);

  const pagesQ = useQuery({
    queryKey: ["seo-website", "wordpress-pages", search, token],
    queryFn: () => fetchWordpressPages(search),
    enabled: Boolean(token) && wpConnected,
    staleTime: 60_000,
  });
  const templatesQ = useQuery({
    queryKey: ["seo-website", "content-templates"],
    queryFn: fetchContentTemplates,
    enabled: Boolean(token) && wpConnected,
    staleTime: 5 * 60_000,
  });
  const suburbHistoryQ = useQuery({
    queryKey: ["suburb-page-history", token],
    queryFn: fetchSuburbPageHistory,
    enabled: Boolean(token) && wpConnected,
    staleTime: 30_000,
  });
  const suburbModulesQ = useQuery({
    queryKey: ["suburb-page-modules", token],
    queryFn: fetchSuburbPageModules,
    enabled: Boolean(token) && wpConnected,
    staleTime: 10 * 60_000,
  });

  const selected = useMemo(() => {
    const rows = pagesQ.data?.items ?? [];
    return rows.find((p) => p.id === selectedId) ?? rows[0] ?? null;
  }, [pagesQ.data?.items, selectedId]);

  const wpSiteUrl = useMemo(() => {
    const raw = String(statusQ.data?.wordpress?.extra?.site_url ?? "").trim().replace(/\/+$/, "");
    return raw || null;
  }, [statusQ.data?.wordpress?.extra?.site_url]);

  const effectiveSbSlug = useMemo(
    () => sbSlug.trim() || slugifyKeyword(sbKeyword.trim()),
    [sbSlug, sbKeyword],
  );

  const sbPagePreviewUrl = useMemo(() => {
    if (!wpSiteUrl || !effectiveSbSlug) return null;
    return `${wpSiteUrl}/${effectiveSbSlug}/`;
  }, [wpSiteUrl, effectiveSbSlug]);

  const parsedKeywords = useMemo(
    () =>
      keywordInput
        .split(/[\n,]+/)
        .map((k) => k.trim())
        .filter(Boolean),
    [keywordInput],
  );

  const saveMut = useMutation({
    mutationFn: (pageId: number) => updateWordpressPageSeo(pageId, { title, slug, excerpt }),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ["seo-website", "wordpress-pages"] });
    },
  });

  const saveContentMut = useMutation({
    mutationFn: (pageId: number) =>
      saveWordpressPageContent(pageId, {
        content_markdown: generatedContent,
        status: "publish",
      }),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ["seo-website", "wordpress-pages"] });
    },
  });

  const genMut = useMutation({
    mutationFn: (pageId: number) =>
      generateWordpressMeta(pageId, {
        title,
        slug,
        link: selected?.link,
        current_excerpt: excerpt,
        keywords: keywordInput
          .split(/[\n,]+/)
          .map((k) => k.trim())
          .filter(Boolean)
          .slice(0, 10),
        mode: generationMode,
      }),
    onSuccess: (data) => {
      setTitle(data.title ?? "");
      setExcerpt(data.excerpt ?? "");
      setLastGeneratedMeta({
        model: data.model,
        mode: data.mode,
        researchSignals: data.research_signals ?? [],
      });
    },
  });
  const contentMut = useMutation({
    mutationFn: (pageId: number) =>
      generateWordpressContent(pageId, {
        template_id: templateId,
        prompt: contentPrompt.trim() || undefined,
        keywords: parsedKeywords.slice(0, 10),
        mode: generationMode,
        suburb: sbSuburb.trim() || undefined,
        nearby_suburbs: sbNearbySuburbs.trim() || undefined,
        service_focus: sbServiceFocus.trim() || undefined,
        structure_mode: sbStructureMode,
        preset_id: sbStructureMode === "preset" ? sbPresetId : undefined,
        optional_modules: sbStructureMode === "manual" ? sbOptionalModules : undefined,
        module_set_used: pageModuleSetUsed.length ? pageModuleSetUsed : undefined,
      }),
    onSuccess: (data) => {
      setTitle(data.title ?? "");
      setExcerpt(data.excerpt ?? "");
      setGeneratedContent(data.content ?? "");
      setPageModuleSetUsed(data.module_set_used ?? []);
      setPageWordCount(data.word_count ?? 0);
    },
  });

  const buildSuburbGenBody = (mode: false | "content" | "images" = false) => {
    const base = {
      keyword: sbKeyword.trim(),
      suburb: sbSuburb.trim() || undefined,
      slug: effectiveSbSlug || undefined,
      word_count_target: sbWordTarget,
      image_count: sbImageCount,
      structure_mode: sbStructureMode,
      preset_id: sbStructureMode === "preset" ? sbPresetId : undefined,
      optional_modules: sbStructureMode === "manual" ? sbOptionalModules : undefined,
      nearby_suburbs: sbNearbySuburbs.trim() || undefined,
      service_focus: sbServiceFocus.trim() || undefined,
    };
    if (mode === "content") {
      return {
        ...base,
        keep_image_photo_ids: (sbResult?.images ?? [])
          .map((img) => img.photo_id)
          .filter((id): id is string => Boolean(id)),
        module_set_used: sbResult?.module_set_used?.length ? sbResult.module_set_used : undefined,
      };
    }
    if (mode === "images") {
      return {
        ...base,
        regenerate_images_only: true,
        preserved_title: sbTitle.trim() || sbResult?.title || undefined,
        preserved_excerpt: sbExcerpt.trim() || sbResult?.excerpt || undefined,
        preserved_content: sbContent.trim() || sbResult?.content || undefined,
        preserved_modules: sbResult?.modules ?? [],
        module_set_used: sbResult?.module_set_used?.length ? sbResult.module_set_used : undefined,
      };
    }
    return base;
  };

  const suburbGenMut = useMutation({
    mutationFn: (mode: false | "content" | "images" = false) => generateSuburbPage(buildSuburbGenBody(mode)),
    onSuccess: async (data) => {
      setSbResult(data);
      setSbHistoryId(data.history_id ?? null);
      setSbTitle(data.title ?? "");
      setSbExcerpt(data.excerpt ?? "");
      setSbContent(data.content ?? "");
      setSbSlug(data.slug ?? effectiveSbSlug);
      setSbNearbySuburbs(data.nearby_suburbs ?? sbNearbySuburbs);
      setSbServiceFocus(data.service_focus ?? sbServiceFocus);
      setSbPublishedUrl("");
      setSbImageErrors({});
      await qc.invalidateQueries({ queryKey: ["suburb-page-history"] });
    },
  });

  const suburbPublishMut = useMutation({
    mutationFn: () => {
      const effectiveSlug = sbSlug.trim() || slugifyKeyword(sbKeyword.trim());
      return publishSuburbPage({
        history_id: sbHistoryId ?? undefined,
        title: sbTitle.trim() || sbResult?.title || "",
        content: sbContent,
        excerpt: sbExcerpt.trim() || sbResult?.excerpt || undefined,
        slug: effectiveSlug || undefined,
        target_keyword: sbKeyword.trim() || sbResult?.target_keyword || undefined,
        suburb: sbSuburb.trim() || undefined,
        image_photo_ids: (sbResult?.images ?? [])
          .map((img) => img.photo_id)
          .filter((id): id is string => Boolean(id)),
      });
    },
    onSuccess: async (data) => {
      setSbPublishedUrl(data.link ?? "");
      setSbHistoryId(data.history_id ?? sbHistoryId);
      if (data.page_id) setLiveEditPageId(data.page_id);
      if (data.slug) setSbSlug(data.slug);
      document.getElementById("edit-live-wordpress-page")?.scrollIntoView({ behavior: "smooth", block: "start" });
      await qc.invalidateQueries({ queryKey: ["suburb-page-history"] });
      await qc.invalidateQueries({ queryKey: ["seo-website", "wordpress-pages"] });
    },
  });

  const suburbDeleteMut = useMutation({
    mutationFn: (historyId: string) => deleteSuburbPageHistory(historyId, true),
    onSuccess: async (_data, historyId) => {
      if (sbHistoryId === historyId) {
        setSbResult(null);
        setSbTitle("");
        setSbExcerpt("");
        setSbContent("");
        setSbHistoryId(null);
        setSbImageViewer(null);
        setSbPublishedUrl("");
        setLiveEditPageId(null);
      }
      await qc.invalidateQueries({ queryKey: ["suburb-page-history"] });
      await qc.invalidateQueries({ queryKey: ["seo-website", "wordpress-pages"] });
    },
  });

  const historyLoadMut = useMutation({
    mutationFn: (historyId: string) => fetchSuburbPageHistoryItem(historyId),
    onSuccess: (detail) => {
      setSbKeyword(detail.target_keyword);
      setSbSuburb(detail.suburb);
      setSbSlug(detail.slug);
      setSbSlugManual(true);
      setSbHistoryId(detail.history_id);
      setSbTitle(detail.title ?? "");
      setSbExcerpt(detail.excerpt ?? "");
      setSbContent(detail.content);
      setSbNearbySuburbs(detail.nearby_suburbs ?? "");
      setSbServiceFocus(detail.service_focus ?? "");
      setSbImageErrors({});
      setSbPublishedUrl(detail.wordpress_link ?? "");
      if (detail.wordpress_page_id) setLiveEditPageId(detail.wordpress_page_id);
      setSbResult({
        history_id: detail.history_id,
        title: detail.title,
        excerpt: detail.excerpt,
        content: detail.content,
        word_count: detail.word_count,
        target_keyword: detail.target_keyword,
        slug: detail.slug,
        model: detail.model ?? "",
        images: detail.images ?? [],
        module_set_used: detail.module_set_used ?? [],
        modules: detail.modules ?? [],
        nearby_suburbs: detail.nearby_suburbs ?? "",
        service_focus: detail.service_focus ?? "",
      });
      document.getElementById("suburb-landing-builder")?.scrollIntoView({ behavior: "smooth", block: "start" });
    },
  });

  const descStatus = useMemo(() => {
    const len = excerpt.trim().length;
    if (len === 0) return { tone: "text-rp-tlight", label: "Start writing or generate with Sonar." };
    if (len < 120) return { tone: "text-red-600", label: "Too short for SEO snippets." };
    if (len < 135) return { tone: "text-amber-700", label: "Close — target 135 to 150 characters." };
    if (len <= 150) return { tone: "text-emerald-700", label: "Ideal SEO meta length (135 to 150)." };
    return { tone: "text-red-600", label: "Too long — keep it at 150 or less." };
  }, [excerpt]);

  const titleStatus = useMemo(() => {
    const len = title.trim().length;
    if (len === 0) return { tone: "text-rp-tlight", label: "Add SEO title or generate." };
    if (len < 30) return { tone: "text-amber-700", label: "Could be stronger; target 45 to 60." };
    if (len <= 60) return { tone: "text-emerald-700", label: "Good title length." };
    return { tone: "text-red-600", label: "Too long — keep it at 60 or less." };
  }, [title]);

  function handleSbKeywordChange(value: string) {
    setSbKeyword(value);
    if (!sbSlugManual) {
      setSbSlug(slugifyKeyword(value));
    }
  }

  function insertKeyword(phrase: string) {
    const kw = phrase.trim();
    if (!kw) return;
    setSbKeyword(kw);
    if (!sbSlugManual) {
      setSbSlug(slugifyKeyword(kw));
    }
  }

  function formatHistoryDate(iso: string | null | undefined) {
    if (!iso) return "—";
    const d = new Date(iso);
    return Number.isNaN(d.getTime()) ? iso : d.toLocaleString();
  }

  function historyPageUrl(item: { slug: string; wordpress_link: string | null; page_url?: string | null }) {
    const fromApi = (item.page_url ?? "").trim();
    if (fromApi) return fromApi;
    const live = (item.wordpress_link ?? "").trim();
    if (live) return live;
    if (wpSiteUrl && item.slug.trim()) {
      return `${wpSiteUrl}/${item.slug.trim().replace(/^\/+|\/+$/g, "")}/`;
    }
    return null;
  }

  const suburbHistoryItems = suburbHistoryQ.data?.items ?? [];
  const suburbModuleLibrary = suburbModulesQ.data;
  const sbManualReady = sbOptionalModules.length === 4;
  function loadIntoEditor(p: SeoWebsitePage | null) {
    if (!p) return;
    setSelectedId(p.id);
    setLiveEditPageId(p.id);
    setTitle(p.title ?? "");
    setSlug(p.slug ?? "");
    setExcerpt(p.excerpt ?? "");
    setKeywordInput("");
    setContentPrompt("");
    setGeneratedContent("");
    setPageModuleSetUsed([]);
    setPageWordCount(0);
    setLastGeneratedMeta(null);
  }

  return (
    <>
      <TopBar
        title="Content Engine"
        subtitle="One WordPress workspace: list, edit, and optimize all website pages"
      />
      <div className="page-scroll px-6 py-5">
        {!wpConnected ? (
          <Card>
            <CardHeader title="WordPress not connected" subtitle="Connect WordPress in Business Setup to manage pages here." />
            <div className="p-4 text-sm text-rp-tmid">
              Open <strong>Business Setup</strong> and connect your WordPress site first.
            </div>
          </Card>
        ) : (
          <>
            <div className="grid gap-4 lg:grid-cols-[1.1fr_1fr]">
              <Card>
              <CardHeader
                title="Website pages"
                subtitle={`${pagesQ.data?.total ?? 0} page(s) found on your connected WordPress site`}
                right={
                  <input
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    placeholder="Search page title..."
                    className="w-52 rounded-md border border-rp-border bg-white px-2 py-1 text-xs text-navy"
                  />
                }
              />
              <div className="max-h-[560px] overflow-auto">
                {pagesQ.isLoading ? (
                  <p className="p-4 text-sm text-rp-tlight">Loading pages…</p>
                ) : pagesQ.isError ? (
                  <p className="p-4 text-sm text-red-600">{formatApiError(pagesQ.error)}</p>
                ) : (
                  <table className="w-full border-collapse text-left text-[12px]">
                    <thead>
                      <tr className="border-b border-rp-border bg-rp-light text-[10px] font-bold uppercase text-rp-tlight">
                        <th className="px-3 py-2">Title</th>
                        <th className="px-3 py-2">Slug</th>
                        <th className="px-3 py-2 text-right">Words</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(pagesQ.data?.items ?? []).map((p) => {
                        const active = selected?.id === p.id;
                        return (
                          <tr
                            key={p.id}
                            className={`cursor-pointer border-b border-[#F0F4F8] hover:bg-[#FAFBFD] ${active ? "bg-[#72C219]/[0.05]" : ""}`}
                            onClick={() => loadIntoEditor(p)}
                          >
                            <td className="px-3 py-2">
                              <div className="font-semibold text-navy">{p.title}</div>
                              {p.link ? (
                                <a
                                  href={p.link}
                                  target="_blank"
                                  rel="noreferrer"
                                  className="inline-flex items-center gap-1 text-[10px] text-[#72C219] hover:underline"
                                  onClick={(e) => e.stopPropagation()}
                                >
                                  View page <ExternalLink className="h-3 w-3" />
                                </a>
                              ) : null}
                            </td>
                            <td className="px-3 py-2 text-rp-tmid">{p.slug}</td>
                            <td className="px-3 py-2 text-right text-rp-tmid">{p.word_count.toLocaleString()}</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                )}
              </div>
              </Card>

              <Card>
              <CardHeader
                title="Page-level optimization"
                subtitle={selected ? `Editing: ${selected.title}` : "Select a page from the left"}
              />
              <div className="space-y-3 p-4">
                {!selected ? (
                  <p className="text-sm text-rp-tlight">Pick a WordPress page to edit title, slug, and SEO description.</p>
                ) : (
                  <>
                    <label className="block text-[11px] font-semibold text-rp-tmid">
                      SEO Title
                      <input
                        className="mt-1 w-full rounded-md border border-rp-border px-3 py-2 text-[12px] text-navy"
                        value={title}
                        maxLength={60}
                        onChange={(e) => setTitle(e.target.value)}
                      />
                      <div className="mt-1 flex items-center justify-between">
                        <span className="text-[10px] text-rp-tlight">{title.length}/60</span>
                        <span className={`text-[10px] font-semibold ${titleStatus.tone}`}>{titleStatus.label}</span>
                      </div>
                    </label>
                    <label className="block text-[11px] font-semibold text-rp-tmid">
                      URL Slug
                      <input
                        className="mt-1 w-full rounded-md border border-rp-border px-3 py-2 text-[12px] text-navy"
                        value={slug}
                        onChange={(e) => setSlug(e.target.value)}
                      />
                    </label>
                    <label className="block text-[11px] font-semibold text-rp-tmid">
                      Meta description / excerpt
                      <textarea
                        className="mt-1 min-h-[120px] w-full rounded-md border border-rp-border px-3 py-2 text-[12px] text-navy"
                        value={excerpt}
                        maxLength={150}
                        onChange={(e) => setExcerpt(e.target.value)}
                      />
                      <div className="mt-1 flex items-center justify-between">
                        <span className="text-[10px] text-rp-tlight">{excerpt.length}/150</span>
                        <span className={`text-[10px] font-semibold ${descStatus.tone}`}>{descStatus.label}</span>
                      </div>
                    </label>
                    <label className="block text-[11px] font-semibold text-rp-tmid">
                      Focus keywords (up to 10)
                      <textarea
                        className="mt-1 min-h-[88px] w-full rounded-md border border-rp-border px-3 py-2 text-[12px] text-navy"
                        placeholder={"ai consulting, strategic ai solutions, business growth\nclick trends, ai services melbourne"}
                        value={keywordInput}
                        onChange={(e) => setKeywordInput(e.target.value)}
                      />
                      <div className="mt-1 flex items-center justify-between">
                        <span className="text-[10px] text-rp-tlight">
                          {Math.min(parsedKeywords.length, 10)}/10 keywords used for generation
                        </span>
                        {parsedKeywords.length > 10 ? (
                          <span className="text-[10px] font-semibold text-amber-700">
                            Extra keywords will be ignored
                          </span>
                        ) : null}
                      </div>
                    </label>
                    <label className="block text-[11px] font-semibold text-rp-tmid">
                      Content structure template (from framework)
                      <select
                        className="mt-1 w-full rounded-md border border-rp-border bg-white px-2 py-2 text-[12px] text-navy"
                        value={templateId}
                        onChange={(e) => setTemplateId(e.target.value)}
                      >
                        {(templatesQ.data?.items ?? []).map((t) => (
                          <option key={t.id} value={t.id}>
                            {t.label}
                          </option>
                        ))}
                      </select>
                      <p className="mt-1 text-[10px] font-normal text-rp-tlight">
                        Page content uses the same A–N module skeleton as the Suburb landing page builder below
                        {sbSuburb.trim() ? ` (${sbSuburb.trim()})` : ""}. Set structure, suburb, and nearby areas there,
                        then generate here. Regenerating text keeps the same module layout; published images stay on the
                        live page.
                      </p>
                    </label>
                    <label className="block text-[11px] font-semibold text-rp-tmid">
                      Prompt / instructions
                      <textarea
                        className="mt-1 min-h-[96px] w-full rounded-md border border-rp-border px-3 py-2 text-[12px] text-navy"
                        placeholder="Add specific instructions for this page content (tone, offer, audience, sections to emphasize)."
                        value={contentPrompt}
                        onChange={(e) => setContentPrompt(e.target.value)}
                      />
                    </label>
                    {genMut.isError ? (
                      <p className="text-xs text-red-600">{formatApiError(genMut.error)}</p>
                    ) : null}
                    {genMut.isSuccess && lastGeneratedMeta ? (
                      <div className="space-y-1">
                        <p className="text-xs text-emerald-700">
                          Generated with {lastGeneratedMeta.model} ({lastGeneratedMeta.mode} mode).
                        </p>
                        {lastGeneratedMeta.mode === "research" && lastGeneratedMeta.researchSignals.length > 0 ? (
                          <div className="rounded-md border border-[#C7D7FD] bg-[#EEF4FF] px-2.5 py-2 text-[11px] text-navy">
                            <p className="mb-1 font-semibold text-[#1D4ED8]">Research signals used:</p>
                            <ul className="list-inside list-disc space-y-0.5">
                              {lastGeneratedMeta.researchSignals.map((s) => (
                                <li key={s}>{s}</li>
                              ))}
                            </ul>
                          </div>
                        ) : null}
                      </div>
                    ) : null}
                    {saveMut.isError ? (
                      <p className="text-xs text-red-600">{formatApiError(saveMut.error)}</p>
                    ) : null}
                    {saveMut.isSuccess ? (
                      <p className="text-xs text-emerald-700">Saved SEO to WordPress.</p>
                    ) : null}
                    <div className="flex flex-wrap items-center gap-2">
                      <select
                        className="rounded-md border border-rp-border bg-white px-2 py-1.5 text-[11px] text-navy"
                        value={generationMode}
                        onChange={(e) => setGenerationMode(e.target.value as "default" | "research")}
                      >
                        <option value="default">Default generation</option>
                        <option value="research">Research mode</option>
                      </select>
                      <Button
                        type="button"
                        size="sm"
                        variant="outline"
                        disabled={genMut.isPending}
                        onClick={() => selected && void genMut.mutate(selected.id)}
                      >
                        {genMut.isPending ? "Generating..." : "Generate title + meta with Sonar"}
                      </Button>
                    </div>
                    <Button
                      type="button"
                      size="sm"
                      variant="outline"
                      disabled={contentMut.isPending || !(templatesQ.data?.items?.length)}
                      onClick={() => selected && void contentMut.mutate(selected.id)}
                    >
                      {contentMut.isPending
                        ? "Generating page content..."
                        : pageModuleSetUsed.length
                          ? "Regenerate page content"
                          : "Generate page content"}
                    </Button>
                    {contentMut.isError ? (
                      <p className="text-xs text-red-600">{formatApiError(contentMut.error)}</p>
                    ) : null}
                    {pageModuleSetUsed.length ? (
                      <p className="text-[10px] text-rp-tlight">
                        Module layout: {pageModuleSetUsed.join(" → ")}
                        {pageWordCount ? ` · ${pageWordCount} words` : ""}
                      </p>
                    ) : null}
                    {generatedContent ? (
                      <label className="block text-[11px] font-semibold text-rp-tmid">
                        Generated page content (Markdown — editable, publishes via Save content + Publish)
                        <textarea
                          className="mt-1 min-h-[220px] w-full rounded-md border border-rp-border px-3 py-2 font-mono text-[11px] text-navy"
                          value={generatedContent}
                          onChange={(e) => setGeneratedContent(e.target.value)}
                        />
                      </label>
                    ) : null}
                    <Button
                      type="button"
                      size="sm"
                      disabled={saveMut.isPending || genMut.isPending}
                      onClick={() => void saveMut.mutate(selected.id)}
                    >
                      {saveMut.isPending ? "Saving..." : "Save optimization"}
                    </Button>
                    <Button
                      type="button"
                      size="sm"
                      variant="outline"
                      disabled={saveContentMut.isPending || !generatedContent.trim()}
                      onClick={() => void saveContentMut.mutate(selected.id)}
                    >
                      {saveContentMut.isPending ? "Publishing…" : "Save content + Publish"}
                    </Button>
                    {saveContentMut.isError ? (
                      <p className="text-xs text-red-600">{formatApiError(saveContentMut.error)}</p>
                    ) : null}
                    {saveContentMut.isSuccess ? (
                      <p className="text-xs text-emerald-700">Content published ✓</p>
                    ) : null}
                  </>
                )}
              </div>
              </Card>
            </div>

            <div className="mt-4" id="suburb-landing-builder">
              <Card>
                <CardHeader
                  title="Suburb landing page builder"
                  subtitle={
                    sbHistoryId && sbResult
                      ? "Loaded from history — Clicktrends module layout (A–N)"
                      : "Clicktrends-style local pages — pick a layout, generate modules, publish to WordPress"
                  }
                />
                <div className="grid gap-4 p-4 lg:grid-cols-[1fr_1.3fr]">
                  {/* Inputs */}
                  <div className="space-y-3">
                    <label className="block text-[11px] font-semibold text-rp-tmid">
                      Focus keyword
                      <input
                        className="mt-1 w-full rounded-md border border-rp-border px-3 py-2 text-[12px] text-navy"
                        placeholder="e.g. seo services south yarra"
                        value={sbKeyword}
                        onChange={(e) => handleSbKeywordChange(e.target.value)}
                      />
                      <span className="mt-1 block text-[10px] text-rp-tlight">
                        Tip: use the Ahrefs checker below and click “+ Add” — slug updates automatically.
                      </span>
                    </label>
                    <div className="grid grid-cols-2 gap-2">
                      <label className="block text-[11px] font-semibold text-rp-tmid">
                        Suburb / area
                        <input
                          className="mt-1 w-full rounded-md border border-rp-border px-3 py-2 text-[12px] text-navy"
                          placeholder="South Yarra"
                          value={sbSuburb}
                          onChange={(e) => setSbSuburb(e.target.value)}
                        />
                      </label>
                      <label className="block text-[11px] font-semibold text-rp-tmid">
                        URL slug (from keyword)
                        <input
                          className="mt-1 w-full rounded-md border border-rp-border px-3 py-2 text-[12px] text-navy"
                          placeholder="seo-services-south-yarra"
                          value={sbSlug}
                          onChange={(e) => {
                            setSbSlugManual(true);
                            setSbSlug(e.target.value);
                          }}
                        />
                      </label>
                    </div>
                    {sbPagePreviewUrl ? (
                      <div className="rounded-md border border-[#C2E0FF] bg-[#F8FAFC] px-3 py-2 text-[11px] text-navy">
                        <span className="font-semibold text-rp-tmid">Page URL on your site: </span>
                        <span className="break-all text-[#1D4ED8]">{sbPagePreviewUrl}</span>
                      </div>
                    ) : sbKeyword.trim() ? (
                      <p className="text-[10px] text-rp-tlight">
                        Slug preview: <strong className="text-navy">/{effectiveSbSlug || "…"}/</strong>
                      </p>
                    ) : null}
                    <label className="block text-[11px] font-semibold text-rp-tmid">
                      Nearby suburbs (for “Areas we serve” module)
                      <input
                        className="mt-1 w-full rounded-md border border-rp-border px-3 py-2 text-[12px] text-navy"
                        placeholder="Cremorne, South Yarra, Burnley… (auto-filled if blank)"
                        value={sbNearbySuburbs}
                        onChange={(e) => setSbNearbySuburbs(e.target.value)}
                      />
                    </label>
                    <label className="block text-[11px] font-semibold text-rp-tmid">
                      Service focus (optional)
                      <select
                        className="mt-1 w-full rounded-md border border-rp-border bg-white px-2 py-2 text-[12px] text-navy"
                        value={sbServiceFocus}
                        onChange={(e) => setSbServiceFocus(e.target.value)}
                      >
                        <option value="">General local business</option>
                        <option value="ecommerce">Ecommerce</option>
                        <option value="trades">Trades</option>
                        <option value="professional services">Professional services</option>
                      </select>
                    </label>
                    <div className="rounded-md border border-rp-border bg-[#FAFBFC] p-3">
                      <p className="text-[11px] font-bold text-navy">Page structure (modules A–N)</p>
                      <p className="mt-1 text-[10px] text-rp-tlight">
                        Anchors A, L, M, N are always included. Pick how the other 4 modules are chosen.
                      </p>
                      <div className="mt-2 flex flex-wrap gap-2">
                        {(
                          [
                            ["auto", "Auto (varied)"],
                            ["preset", "Preset layout"],
                            ["manual", "Choose modules"],
                          ] as const
                        ).map(([mode, label]) => (
                          <button
                            key={mode}
                            type="button"
                            className={`rounded-full px-3 py-1 text-[10px] font-semibold ${
                              sbStructureMode === mode
                                ? "bg-[#72C219] text-white"
                                : "bg-white text-rp-tmid ring-1 ring-rp-border"
                            }`}
                            onClick={() => setSbStructureMode(mode)}
                          >
                            {label}
                          </button>
                        ))}
                      </div>
                      {sbStructureMode === "preset" ? (
                        <select
                          className="mt-2 w-full rounded-md border border-rp-border bg-white px-2 py-2 text-[12px] text-navy"
                          value={sbPresetId}
                          onChange={(e) => setSbPresetId(e.target.value)}
                        >
                          {(suburbModuleLibrary?.presets ?? []).map((p) => (
                            <option key={p.id} value={p.id}>
                              {p.label}
                            </option>
                          ))}
                        </select>
                      ) : null}
                      {sbStructureMode === "manual" ? (
                        <div className="mt-2 space-y-2">
                          {MANUAL_MODULE_GROUPS.map((group) => (
                            <div key={group.key}>
                              <p className="text-[10px] font-semibold text-rp-tmid">{group.label}</p>
                              <div className="mt-1 flex flex-wrap gap-1">
                                {group.types.map((letter) => {
                                  const meta = suburbModuleLibrary?.modules.find((m) => m.type === letter);
                                  const active = sbOptionalModules.includes(letter);
                                  return (
                                    <button
                                      key={letter}
                                      type="button"
                                      title={meta?.description}
                                      className={`rounded px-2 py-0.5 text-[10px] font-semibold ${
                                        active
                                          ? "bg-navy text-white"
                                          : "bg-white text-rp-tmid ring-1 ring-rp-border"
                                      }`}
                                      onClick={() =>
                                        setSbOptionalModules((prev) =>
                                          pickManualModule(group.types, letter, prev),
                                        )
                                      }
                                    >
                                      {letter}: {meta?.label ?? letter}
                                    </button>
                                  );
                                })}
                              </div>
                            </div>
                          ))}
                          {!sbManualReady ? (
                            <p className="text-[10px] text-amber-700">Select 4 optional modules to continue.</p>
                          ) : (
                            <p className="text-[10px] text-[#137333]">
                              Layout: A → {sbOptionalModules.join(" → ")} → L → M → N
                            </p>
                          )}
                        </div>
                      ) : null}
                    </div>
                    <div className="grid grid-cols-2 gap-2">
                      <label className="block text-[11px] font-semibold text-rp-tmid">
                        Word count target
                        <select
                          className="mt-1 w-full rounded-md border border-rp-border bg-white px-2 py-2 text-[12px] text-navy"
                          value={sbWordTarget}
                          onChange={(e) => setSbWordTarget(Number(e.target.value))}
                        >
                          <option value={900}>~900 words</option>
                          <option value={1000}>~1,000 words</option>
                          <option value={1100}>~1,100 words</option>
                          <option value={1250}>~1,250 words</option>
                        </select>
                      </label>
                      <label className="block text-[11px] font-semibold text-rp-tmid">
                        AI images
                        <select
                          className="mt-1 w-full rounded-md border border-rp-border bg-white px-2 py-2 text-[12px] text-navy"
                          value={sbImageCount}
                          onChange={(e) => setSbImageCount(Number(e.target.value))}
                        >
                          <option value={0}>No images</option>
                          <option value={1}>1 image (hero)</option>
                          <option value={2}>2 images (hero + service)</option>
                        </select>
                      </label>
                    </div>
                    <Button
                      type="button"
                      size="sm"
                      disabled={
                        suburbGenMut.isPending ||
                        !sbKeyword.trim() ||
                        (sbStructureMode === "manual" && !sbManualReady)
                      }
                      onClick={() => void suburbGenMut.mutate()}
                    >
                      {suburbGenMut.isPending ? "Generating modules + images…" : "Generate suburb page"}
                    </Button>
                    {suburbGenMut.isError ? (
                      <p className="text-xs text-red-600">{formatApiError(suburbGenMut.error)}</p>
                    ) : null}
                  </div>

                  {/* Preview */}
                  <div className="space-y-3">
                    {!sbResult ? (
                      <p className="text-sm text-rp-tlight">
                        Generated content and images will appear here. Nothing is published until you click
                        “Publish to WordPress”.
                      </p>
                    ) : (
                      <>
                        <div className="flex flex-wrap items-center gap-2 text-[11px]">
                          <span className="rounded-full bg-rp-light px-2.5 py-0.5 font-semibold text-rp-tmid">
                            {sbResult.word_count.toLocaleString()} words
                          </span>
                          <span className="rounded-full bg-[#E6F4EA] px-2.5 py-0.5 font-semibold text-[#137333]">
                            “{sbResult.target_keyword}”
                          </span>
                          <span className="rounded-full bg-rp-light px-2.5 py-0.5 text-rp-tlight">
                            {sbResult.model}
                          </span>
                          {sbResult.module_set_used?.length ? (
                            <span className="rounded-full bg-[#FFF7ED] px-2.5 py-0.5 font-semibold text-[#9A3412]">
                              {sbResult.module_set_used.join(" → ")}
                            </span>
                          ) : null}
                          {effectiveSbSlug ? (
                            <span className="rounded-full bg-[#EEF4FF] px-2.5 py-0.5 font-semibold text-[#1D4ED8]">
                              /{effectiveSbSlug}/
                            </span>
                          ) : null}
                        </div>
                        {sbPagePreviewUrl ? (
                          <p className="text-[11px] text-rp-tmid">
                            Will publish to:{" "}
                            <a
                              href={sbPublishedUrl || sbPagePreviewUrl}
                              target="_blank"
                              rel="noreferrer"
                              className="font-semibold text-[#72C219] hover:underline"
                            >
                              {sbPublishedUrl || sbPagePreviewUrl}
                            </a>
                          </p>
                        ) : null}

                        {sbResult.images.length > 0 ? (
                          <div>
                            <p className="mb-1.5 text-[10px] text-rp-tlight">
                              Images (hero + service) — click any thumbnail to view full size. Use{" "}
                              <strong>Regenerate images</strong> for new photos (keeps your text). Use{" "}
                              <strong>Regenerate content</strong> to rewrite text (keeps these images).
                            </p>
                            <div className="grid grid-cols-2 gap-2">
                            {sbResult.images.map((img, i) => {
                              const previewSrc =
                                img.preview_data_url ||
                                (img.photo_id ? gbpPhotoFileUrl(img.photo_id, token) : null);
                              const imgKey = img.photo_id ?? `${img.role}-${i}`;
                              const loadFailed = Boolean(img.photo_id && sbImageErrors[imgKey]);

                              if (!previewSrc && !img.photo_id) {
                                return (
                                  <div
                                    key={`${img.role}-${i}`}
                                    className="flex min-h-[8rem] items-center justify-center rounded-md border border-dashed border-amber-300 bg-[#FFFBEB] p-2 text-center text-[10px] text-[#92400E]"
                                  >
                                    {img.note || `${img.role}: no image`}
                                  </div>
                                );
                              }

                              return (
                                <button
                                  type="button"
                                  key={`${img.role}-${i}`}
                                  className="group relative overflow-hidden rounded-md border border-rp-border bg-[#FAFBFC] text-left transition hover:border-[#72C219] hover:shadow-sm"
                                  disabled={loadFailed || !previewSrc}
                                  onClick={() => {
                                    if (previewSrc && !loadFailed) {
                                      setSbImageViewer({ src: previewSrc, role: img.role });
                                    }
                                  }}
                                >
                                  {loadFailed ? (
                                    <div className="flex h-36 items-center justify-center p-2 text-center text-[10px] text-amber-700">
                                      Image could not load — regenerate the page.
                                    </div>
                                  ) : previewSrc ? (
                                    <>
                                      <img
                                        src={previewSrc}
                                        alt={img.role}
                                        className="h-36 w-full object-cover"
                                        onError={() => {
                                          setSbImageErrors((prev) => ({ ...prev, [imgKey]: true }));
                                        }}
                                      />
                                      <span className="absolute right-2 top-2 rounded-full bg-black/55 p-1 text-white opacity-0 transition group-hover:opacity-100">
                                        <ZoomIn className="h-3.5 w-3.5" />
                                      </span>
                                    </>
                                  ) : null}
                                  <p className="px-2 py-1 text-[10px] font-semibold uppercase text-rp-tlight">
                                    {img.role}
                                    {previewSrc && !loadFailed ? (
                                      <span className="ml-1 font-normal normal-case text-[#72C219]">
                                        · click to view
                                      </span>
                                    ) : null}
                                  </p>
                                </button>
                              );
                            })}
                            </div>
                          </div>
                        ) : null}

                        <div className="rounded-md border border-[#C7D7FD] bg-[#EEF4FF] px-3 py-2 text-[11px] text-navy">
                          <p className="font-semibold text-[#1D4ED8]">What publishes to WordPress</p>
                          <ul className="mt-1 list-inside list-disc space-y-0.5 text-rp-tmid">
                            <li>
                              <strong>SEO title</strong> and <strong>meta description</strong> — editable below
                            </li>
                            <li>
                              <strong>Page content (Markdown)</strong> — editable; this is the main page body
                            </li>
                            <li>
                              <strong>Hero + service images</strong> — from preview above (not editable as text)
                            </li>
                            <li>
                              Module cards (A–N) are <strong>preview only</strong> — edit the Markdown field to change
                              what goes live
                            </li>
                          </ul>
                        </div>

                        <label className="block text-[11px] font-semibold text-rp-tmid">
                          SEO title (editable — publishes)
                          <input
                            type="text"
                            className="mt-1 w-full rounded-md border border-rp-border px-3 py-2 text-[13px] font-semibold text-navy"
                            value={sbTitle}
                            onChange={(e) => setSbTitle(e.target.value)}
                          />
                        </label>
                        <label className="block text-[11px] font-semibold text-rp-tmid">
                          Meta description (editable — publishes)
                          <textarea
                            className="mt-1 min-h-[64px] w-full rounded-md border border-rp-border px-3 py-2 text-[11px] text-rp-tmid"
                            value={sbExcerpt}
                            onChange={(e) => setSbExcerpt(e.target.value)}
                          />
                          <span className="mt-0.5 block text-[10px] text-rp-tlight">{sbExcerpt.length}/150 characters</span>
                        </label>

                        {sbResult.modules?.length ? (
                          <div>
                            <p className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-rp-tlight">
                              Module preview (read-only)
                            </p>
                            <div className="max-h-[320px] space-y-2 overflow-y-auto rounded-md border border-rp-border bg-[#FAFBFC] p-2">
                            {sbResult.modules.map((mod, i) => (
                              <div
                                key={`${mod.type}-${i}`}
                                className="rounded-md border border-rp-border bg-white p-3"
                              >
                                <div className="mb-1 flex items-center gap-2">
                                  <span className="rounded bg-navy px-1.5 py-0.5 text-[10px] font-bold text-white">
                                    {mod.type}
                                  </span>
                                  {mod.heading ? (
                                    <span className="text-[12px] font-semibold text-navy">{mod.heading}</span>
                                  ) : null}
                                </div>
                                <div className="whitespace-pre-wrap text-[11px] leading-relaxed text-rp-tmid">
                                  {mod.type === "M" ? (
                                    <FaqAccordionPreview heading={mod.heading} body={mod.body} />
                                  ) : (
                                    mod.body
                                  )}
                                </div>
                              </div>
                            ))}
                            </div>
                          </div>
                        ) : null}

                        <label className="block text-[11px] font-semibold text-rp-tmid">
                          Page content (Markdown — editable, publishes)
                          <textarea
                            className="mt-1 min-h-[180px] w-full rounded-md border border-rp-border px-3 py-2 font-mono text-[11px] text-navy"
                            value={sbContent}
                            onChange={(e) => setSbContent(e.target.value)}
                          />
                        </label>

                        <div className="flex flex-wrap items-center gap-2">
                          <Button
                            type="button"
                            size="sm"
                            disabled={suburbPublishMut.isPending || !sbContent.trim() || !sbTitle.trim()}
                            onClick={() => void suburbPublishMut.mutate()}
                          >
                            {suburbPublishMut.isPending ? "Publishing to WordPress…" : "Publish to WordPress"}
                          </Button>
                          <Button
                            type="button"
                            size="sm"
                            variant="outline"
                            disabled={suburbGenMut.isPending}
                            onClick={() => void suburbGenMut.mutate("content")}
                          >
                            Regenerate content
                          </Button>
                          <Button
                            type="button"
                            size="sm"
                            variant="outline"
                            disabled={
                              suburbGenMut.isPending || sbImageCount === 0 || !sbContent.trim()
                            }
                            onClick={() => void suburbGenMut.mutate("images")}
                          >
                            Regenerate images
                          </Button>
                        </div>
                        {suburbPublishMut.isError ? (
                          <p className="text-xs text-red-600">{formatApiError(suburbPublishMut.error)}</p>
                        ) : null}
                        {sbPublishedUrl ? (
                          <p className="text-xs text-emerald-700">
                            Published ✓{" "}
                            <a
                              href={sbPublishedUrl}
                              target="_blank"
                              rel="noreferrer"
                              className="inline-flex items-center gap-1 font-semibold text-[#72C219] hover:underline"
                            >
                              Open page <ExternalLink className="h-3 w-3" />
                            </a>
                            {liveEditPageId ? (
                              <span className="ml-2 text-rp-tmid">
                                — use <strong>Edit live WordPress page</strong> below to change it
                              </span>
                            ) : null}
                          </p>
                        ) : null}
                      </>
                    )}
                  </div>
                </div>
              </Card>
            </div>

            <div className="mt-4" id="edit-live-wordpress-page">
              <Card>
                <CardHeader
                  title="Edit live WordPress page"
                  subtitle="Choose any published page — load it, edit title or sentences, update without changing layout or fonts"
                />
                <div className="p-4">
                  {pagesQ.isLoading ? (
                    <p className="text-sm text-rp-tlight">Loading WordPress pages…</p>
                  ) : (pagesQ.data?.items ?? []).length === 0 ? (
                    <p className="text-sm text-rp-tlight">No WordPress pages found.</p>
                  ) : (
                    <WordPressLivePageEditor
                      pages={pagesQ.data?.items ?? []}
                      selectedPageId={liveEditPageId}
                      onPageIdChange={setLiveEditPageId}
                      onSaved={() => {
                        void qc.invalidateQueries({ queryKey: ["seo-website", "wordpress-pages"] });
                        void qc.invalidateQueries({ queryKey: ["suburb-page-history"] });
                      }}
                    />
                  )}
                </div>
              </Card>
            </div>

            <div className="mt-4">
              <Card>
                <CardHeader
                  title="Suburb page history"
                  subtitle="Click a row to load saved content back into the builder above"
                />
                <div className="p-4">
                  {suburbHistoryQ.isLoading ? (
                    <p className="text-sm text-rp-tlight">Loading history…</p>
                  ) : suburbHistoryQ.isError ? (
                    <p className="text-sm text-red-600">{formatApiError(suburbHistoryQ.error)}</p>
                  ) : suburbHistoryItems.length === 0 ? (
                    <p className="text-sm text-rp-tlight">
                      No suburb pages yet. Generate one above — it will appear here with the date.
                    </p>
                  ) : (
                    <div className="max-h-[360px] overflow-auto rounded-md border border-rp-border">
                      <table className="w-full border-collapse text-left text-[11px]">
                        <thead className="sticky top-0 bg-rp-light text-[10px] font-bold uppercase text-rp-tlight">
                          <tr>
                            <th className="px-3 py-2">Keyword</th>
                            <th className="px-3 py-2">Status</th>
                            <th className="px-3 py-2">Generated</th>
                            <th className="px-3 py-2">Published</th>
                            <th className="px-3 py-2">Page link</th>
                            <th className="px-3 py-2 text-right">Actions</th>
                          </tr>
                        </thead>
                        <tbody>
                          {suburbHistoryItems.map((item) => {
                            const pageUrl = historyPageUrl(item);
                            const isActive = sbHistoryId === item.id;
                            const isLoading = historyLoadMut.isPending && historyLoadMut.variables === item.id;
                            return (
                            <tr
                              key={item.id}
                              className={`cursor-pointer border-t border-rp-border hover:bg-[#FAFBFD] ${
                                isActive ? "bg-[#72C219]/[0.08]" : ""
                              }`}
                              onClick={() => void historyLoadMut.mutate(item.id)}
                            >
                              <td className="px-3 py-2 font-semibold text-navy">
                                {item.keyword || "—"}
                                {isLoading ? (
                                  <span className="ml-1 text-[10px] font-normal text-rp-tlight">Loading…</span>
                                ) : null}
                              </td>
                              <td className="px-3 py-2">
                                <span
                                  className={`rounded-full px-2 py-0.5 text-[10px] font-bold uppercase ${
                                    item.status === "published"
                                      ? "bg-[#E6F4EA] text-[#137333]"
                                      : "bg-[#FFF8E7] text-[#7A4700]"
                                  }`}
                                >
                                  {item.status}
                                </span>
                              </td>
                              <td className="px-3 py-2 text-rp-tmid whitespace-nowrap">
                                {formatHistoryDate(item.generated_at)}
                              </td>
                              <td className="px-3 py-2 text-rp-tmid whitespace-nowrap">
                                {formatHistoryDate(item.published_at)}
                              </td>
                              <td className="px-3 py-2 text-rp-tmid">
                                {pageUrl ? (
                                  <a
                                    href={pageUrl}
                                    target="_blank"
                                    rel="noreferrer"
                                    className="inline-flex max-w-[220px] items-center gap-1 break-all text-[11px] font-semibold text-[#72C219] hover:underline"
                                    title={pageUrl}
                                    onClick={(e) => e.stopPropagation()}
                                  >
                                    {pageUrl}
                                    <ExternalLink className="h-3 w-3 shrink-0" />
                                  </a>
                                ) : item.slug ? (
                                  <span className="text-[11px] text-rp-tlight">/{item.slug}/</span>
                                ) : (
                                  "—"
                                )}
                                {item.status === "generated" && pageUrl ? (
                                  <p className="mt-0.5 text-[9px] text-rp-tlight">Planned URL (not live yet)</p>
                                ) : null}
                              </td>
                              <td className="px-3 py-2 text-right">
                                <button
                                  type="button"
                                  className="mr-2 text-[10px] font-semibold text-[#72C219] hover:underline disabled:opacity-50"
                                  disabled={historyLoadMut.isPending}
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    void historyLoadMut.mutate(item.id);
                                  }}
                                >
                                  Load
                                </button>
                                <button
                                  type="button"
                                  className="text-[10px] font-semibold text-red-600 hover:underline disabled:opacity-50"
                                  disabled={suburbDeleteMut.isPending}
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    const msg = item.wordpress_link
                                      ? "Delete this history entry and remove the page from WordPress?"
                                      : "Delete this history entry?";
                                    if (window.confirm(msg)) {
                                      void suburbDeleteMut.mutate(item.id);
                                    }
                                  }}
                                >
                                  Delete
                                </button>
                              </td>
                            </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  )}
                  {historyLoadMut.isError ? (
                    <p className="mt-2 text-xs text-red-600">{formatApiError(historyLoadMut.error)}</p>
                  ) : null}
                  {suburbDeleteMut.isError ? (
                    <p className="mt-2 text-xs text-red-600">{formatApiError(suburbDeleteMut.error)}</p>
                  ) : null}
                </div>
              </Card>
            </div>

            <div className="mt-4 grid gap-4 lg:grid-cols-2">
              <Card>
                <CardHeader
                  title="1-month content timeline"
                  subtitle="4 weekly GBP posts + landing pages from Ahrefs suburb keywords"
                />
                <div className="space-y-2 p-4 text-sm text-rp-tmid">
                  <p>
                    Target:{" "}
                    {meQ.data?.location_scope === "city"
                      ? `City-wide — ${meQ.data?.metro_label ?? "metro"}`
                      : `${meQ.data?.search_radius_km ?? 25} km radius · ${meQ.data?.primary_suburb?.trim() || `${(meQ.data?.metro_label || "metro").split(",")[0]} CBD`}`}
                  </p>
                  <div className="flex flex-wrap gap-2">
                    <Button
                      type="button"
                      size="sm"
                      disabled={timelineMut.isPending}
                      onClick={() => void timelineMut.mutate()}
                    >
                      {timelineMut.isPending ? "Generating 4-week plan…" : "Generate 1-month plan"}
                    </Button>
                    <Button
                      type="button"
                      size="sm"
                      variant="outline"
                      onClick={() => {
                        void downloadContentPlanExcel().then(({ blob, filename }) => {
                          const url = URL.createObjectURL(blob);
                          const a = document.createElement("a");
                          a.href = url;
                          a.download = filename;
                          a.click();
                          URL.revokeObjectURL(url);
                        });
                      }}
                    >
                      Download Excel (review)
                    </Button>
                    <Button
                      type="button"
                      size="sm"
                      variant="outline"
                      disabled={approveAllMut.isPending}
                      onClick={() => void approveAllMut.mutate()}
                    >
                      {approveAllMut.isPending ? "Approving…" : "Approve all pending"}
                    </Button>
                  </div>
                  <p className="text-[11px] text-rp-tlight">
                    Download Excel first to review text + image links. After approval, items auto-publish on their
                    scheduled week (hourly check). GBP posts need GBP connected; landing pages need WordPress.
                  </p>
                  {(queueQ.data?.items ?? []).filter((i) =>
                    ["gbp_post", "landing_page"].includes(i.content_type),
                  ).length > 0 ? (
                    <div className="max-h-48 overflow-auto rounded-md border border-rp-border">
                      <table className="w-full border-collapse text-left text-[11px]">
                        <thead className="bg-rp-light text-[10px] font-bold uppercase text-rp-tlight">
                          <tr>
                            <th className="px-2 py-1.5">Title</th>
                            <th className="px-2 py-1.5">Type</th>
                            <th className="px-2 py-1.5">Status</th>
                            <th className="px-2 py-1.5">Action</th>
                          </tr>
                        </thead>
                        <tbody>
                          {(queueQ.data?.items ?? [])
                            .filter((i) => ["gbp_post", "landing_page"].includes(i.content_type))
                            .map((item) => (
                              <tr key={item.id} className="border-t border-rp-border">
                                <td className="px-2 py-1.5 font-medium text-navy">{item.title}</td>
                                <td className="px-2 py-1.5 text-rp-tmid">{item.content_type}</td>
                                <td className="px-2 py-1.5">{item.status}</td>
                                <td className="px-2 py-1.5">
                                  {item.status === "pending" ? (
                                    <button
                                      type="button"
                                      className="text-[#72C219] hover:underline"
                                      onClick={() => void approveItemMut.mutate(item.id)}
                                    >
                                      Approve
                                    </button>
                                  ) : item.status === "approved" ? (
                                    <button
                                      type="button"
                                      className="text-navy hover:underline"
                                      onClick={() => void publishItemMut.mutate(item.id)}
                                    >
                                      Publish now
                                    </button>
                                  ) : (
                                    "—"
                                  )}
                                </td>
                              </tr>
                            ))}
                        </tbody>
                      </table>
                    </div>
                  ) : null}
                  {timelineMut.isSuccess ? (
                    <p className="text-xs text-emerald-700">
                      Queued {timelineMut.data.generated} items across {timelineMut.data.weeks} weeks.
                    </p>
                  ) : null}
                  {timelineMut.isError ? (
                    <p className="text-xs text-red-600">{formatApiError(timelineMut.error)}</p>
                  ) : null}
                </div>
              </Card>
              <AhrefsKeywordExplorer onInsert={insertKeyword} compact />
            </div>
          </>
        )}
      </div>

      {sbImageViewer ? (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 p-4"
          role="dialog"
          aria-modal="true"
          aria-label={`${sbImageViewer.role} image preview`}
          onClick={() => setSbImageViewer(null)}
        >
          <div
            className="relative max-h-[90vh] max-w-5xl overflow-hidden rounded-lg bg-white shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            <button
              type="button"
              className="absolute right-3 top-3 z-10 rounded-full bg-black/60 p-1.5 text-white hover:bg-black/80"
              aria-label="Close image preview"
              onClick={() => setSbImageViewer(null)}
            >
              <X className="h-4 w-4" />
            </button>
            <p className="absolute left-3 top-3 z-10 rounded-full bg-black/60 px-2.5 py-1 text-[11px] font-semibold uppercase text-white">
              {sbImageViewer.role}
            </p>
            <img
              src={sbImageViewer.src}
              alt={sbImageViewer.role}
              className="max-h-[85vh] w-full object-contain"
            />
          </div>
        </div>
      ) : null}
    </>
  );
}
