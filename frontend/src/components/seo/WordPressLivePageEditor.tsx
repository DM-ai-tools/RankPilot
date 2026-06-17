import { useMutation } from "@tanstack/react-query";
import { ExternalLink, RefreshCw } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { formatApiError } from "../../api/client";
import {
  fetchWordpressPageEditContent,
  saveWordpressPageHtml,
  type SeoWebsitePage,
} from "../../api/seoWebsite";
import { Button } from "../ui/Button";

type Props = {
  pages: SeoWebsitePage[];
  selectedPageId: number | null;
  onPageIdChange: (pageId: number | null) => void;
  onSaved?: () => void;
};

export function WordPressLivePageEditor({
  pages,
  selectedPageId,
  onPageIdChange,
  onSaved,
}: Props) {
  const editorRef = useRef<HTMLDivElement>(null);
  const [title, setTitle] = useState("");
  const [excerpt, setExcerpt] = useState("");
  const [loaded, setLoaded] = useState(false);
  const [liveLink, setLiveLink] = useState<string | null>(null);

  const activePage = pages.find((p) => p.id === selectedPageId) ?? null;

  const loadMut = useMutation({
    mutationFn: () => fetchWordpressPageEditContent(selectedPageId!),
    onSuccess: (data) => {
      setTitle(data.title ?? "");
      setExcerpt(data.excerpt ?? "");
      setLiveLink(data.link || activePage?.link || null);
      if (editorRef.current) {
        editorRef.current.innerHTML = data.content_html ?? "";
      }
      setLoaded(true);
    },
  });

  const saveMut = useMutation({
    mutationFn: () =>
      saveWordpressPageHtml(selectedPageId!, {
        title: title.trim(),
        excerpt: excerpt.trim(),
        content_html: editorRef.current?.innerHTML ?? "",
        status: "publish",
      }),
    onSuccess: () => {
      onSaved?.();
    },
  });

  useEffect(() => {
    setLoaded(false);
    setTitle("");
    setExcerpt("");
    setLiveLink(activePage?.link ?? null);
    if (editorRef.current) {
      editorRef.current.innerHTML = "";
    }
  }, [selectedPageId, activePage?.link]);

  return (
    <div className="space-y-3">
      <label className="block text-[11px] font-semibold text-rp-tmid">
        Choose WordPress page to edit
        <select
          className="mt-1 w-full rounded-md border border-rp-border bg-white px-3 py-2 text-[12px] text-navy"
          value={selectedPageId ?? ""}
          onChange={(e) => {
            const next = Number(e.target.value);
            onPageIdChange(Number.isFinite(next) && next > 0 ? next : null);
          }}
        >
          <option value="">Select a published page…</option>
          {pages.map((p) => (
            <option key={p.id} value={p.id}>
              {p.title} · /{p.slug}/ · {p.status}
            </option>
          ))}
        </select>
      </label>

      {!selectedPageId ? (
        <p className="text-[11px] text-rp-tlight">
          Pick any page from your WordPress site — not only the page you just published or have selected above.
        </p>
      ) : (
        <div className="space-y-3 rounded-md border border-[#D1FAE5] bg-[#F0FDF4] p-3">
          <div>
            <p className="text-[12px] font-semibold text-navy">
              Editing: {activePage?.title ?? `Page ${selectedPageId}`}
            </p>
            <p className="mt-0.5 text-[11px] text-rp-tmid">
              Load the live page, click any title or sentence to change it, then update. Layout, font sizes,
              alignment, and images stay exactly as WordPress has them — only your text changes.
            </p>
            {liveLink ? (
              <a
                href={liveLink}
                target="_blank"
                rel="noreferrer"
                className="mt-1 inline-flex items-center gap-1 text-[11px] font-semibold text-[#72C219] hover:underline"
              >
                View live page <ExternalLink className="h-3 w-3" />
              </a>
            ) : null}
          </div>

          {!loaded ? (
            <Button
              type="button"
              size="sm"
              variant="outline"
              disabled={loadMut.isPending}
              onClick={() => void loadMut.mutate()}
            >
              {loadMut.isPending ? "Loading from WordPress…" : "Load live content from WordPress"}
            </Button>
          ) : (
            <>
              <label className="block text-[11px] font-semibold text-rp-tmid">
                Page title (editable)
                <input
                  type="text"
                  className="mt-1 w-full rounded-md border border-rp-border bg-white px-3 py-2 text-[13px] font-semibold text-navy"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                />
              </label>
              <label className="block text-[11px] font-semibold text-rp-tmid">
                Meta description (editable)
                <textarea
                  className="mt-1 min-h-[56px] w-full rounded-md border border-rp-border bg-white px-3 py-2 text-[11px] text-rp-tmid"
                  value={excerpt}
                  onChange={(e) => setExcerpt(e.target.value)}
                />
              </label>
              <div>
                <p className="mb-1 text-[11px] font-semibold text-rp-tmid">
                  Page body — click any paragraph or heading to edit
                </p>
                <div
                  ref={editorRef}
                  contentEditable
                  suppressContentEditableWarning
                  className="wp-live-editor min-h-[280px] max-h-[480px] overflow-y-auto rounded-md border border-rp-border bg-white px-4 py-3 text-[13px] leading-relaxed text-navy outline-none focus:border-[#72C219] focus:ring-2 focus:ring-[#72C219]/20"
                />
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <Button
                  type="button"
                  size="sm"
                  disabled={saveMut.isPending || !title.trim()}
                  onClick={() => void saveMut.mutate()}
                >
                  {saveMut.isPending ? "Updating WordPress…" : "Update on WordPress"}
                </Button>
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  disabled={loadMut.isPending}
                  onClick={() => void loadMut.mutate()}
                >
                  <RefreshCw className="mr-1 inline h-3.5 w-3.5" />
                  Reload from WordPress
                </Button>
              </div>
            </>
          )}

          {loadMut.isError ? (
            <p className="text-xs text-red-600">{formatApiError(loadMut.error)}</p>
          ) : null}
          {saveMut.isError ? (
            <p className="text-xs text-red-600">{formatApiError(saveMut.error)}</p>
          ) : null}
          {saveMut.isSuccess ? (
            <p className="text-xs text-emerald-700">Live page updated on WordPress ✓</p>
          ) : null}
        </div>
      )}
    </div>
  );
}
