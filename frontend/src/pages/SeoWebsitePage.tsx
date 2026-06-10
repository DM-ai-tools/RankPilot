import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ExternalLink } from "lucide-react";
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
  fetchWordpressPages,
  generateWordpressContent,
  generateWordpressMeta,
  updateWordpressPageSeo,
  type SeoWebsitePage,
} from "../api/seoWebsite";
import { TopBar } from "../components/layout/TopBar";
import { AhrefsKeywordExplorer } from "../components/keywords/AhrefsKeywordExplorer";
import { Button } from "../components/ui/Button";
import { Card, CardHeader } from "../components/ui/Card";
import { useAuthStore } from "../stores/authStore";

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
  const [lastGeneratedMeta, setLastGeneratedMeta] = useState<{
    model: string;
    mode: "default" | "research";
    researchSignals: string[];
  } | null>(null);

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

  const selected = useMemo(() => {
    const rows = pagesQ.data?.items ?? [];
    return rows.find((p) => p.id === selectedId) ?? rows[0] ?? null;
  }, [pagesQ.data?.items, selectedId]);

  const saveMut = useMutation({
    mutationFn: (pageId: number) => updateWordpressPageSeo(pageId, { title, slug, excerpt }),
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
      setGeneratedContent(data.content ?? "");
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

  const parsedKeywords = useMemo(
    () =>
      keywordInput
        .split(/[\n,]+/)
        .map((k) => k.trim())
        .filter(Boolean),
    [keywordInput],
  );

  function loadIntoEditor(p: SeoWebsitePage | null) {
    if (!p) return;
    setSelectedId(p.id);
    setTitle(p.title ?? "");
    setSlug(p.slug ?? "");
    setExcerpt(p.excerpt ?? "");
    setKeywordInput("");
    setContentPrompt("");
    setGeneratedContent("");
    setLastGeneratedMeta(null);
  }

  function insertKeyword(
    phrase: string,
    meta?: { volume?: number | null; difficulty?: number | null; opportunity?: number | null },
  ) {
    const vol = meta?.volume;
    const kd = meta?.difficulty;
    const opp = meta?.opportunity;
    const hasMeta = vol != null || kd != null || opp != null;
    const details = hasMeta
      ? ` (Vol: ${vol != null ? vol.toLocaleString() : "n/a"}, KD: ${kd != null ? kd : "n/a"}, Opp: ${opp != null ? opp.toLocaleString() : "n/a"})`
      : "";
    const chunk = `${phrase}${details}`;

    setExcerpt((prev) => {
      const base = prev.trim();
      let next = base ? `${base} ${chunk}` : chunk;
      if (next.length > 150) {
        // fallback to keyword-only when full metrics do not fit
        next = base ? `${base} ${phrase}` : phrase;
      }
      if (next.length > 150) {
        // final fallback: trim existing excerpt tail to keep the keyword
        const reserve = phrase.length + 1;
        const head = base.slice(0, Math.max(0, 150 - reserve)).trimEnd();
        next = head ? `${head} ${phrase}` : phrase.slice(0, 150);
      }
      return next;
    });
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
                      <p className="text-xs text-emerald-700">Saved to WordPress.</p>
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
                      {contentMut.isPending ? "Generating page content..." : "Generate page content"}
                    </Button>
                    {contentMut.isError ? (
                      <p className="text-xs text-red-600">{formatApiError(contentMut.error)}</p>
                    ) : null}
                    {generatedContent ? (
                      <label className="block text-[11px] font-semibold text-rp-tmid">
                        Generated page content (Markdown)
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
                  </>
                )}
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
                      : `Suburb — ${meQ.data?.primary_suburb || "not set"}${meQ.data?.search_radius_km ? ` · ${meQ.data.search_radius_km} km radius` : ""}`}
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
    </>
  );
}
