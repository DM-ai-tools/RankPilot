import type { GbpActivityResponse } from "./types";
import { apiDelete, apiGet, apiGetBlob, apiPatchJson, apiPostFormData, apiPostJson } from "./client";
import { useAuthStore } from "../stores/authStore";

// ── Types ─────────────────────────────────────────────────────────────────────

export type GbpQueueItem = {
  id: string;
  content_type: string;
  status: string;
  title?: string;
  body?: string;
  word_count?: number;
  target_keyword?: string;
  photo_id?: string;
  photo_url?: string;
  image_note?: string;
  generation_prompt?: string;
  batch_index?: number;
  batch_total?: number;
  location_scope?: string;
  target_area?: string;
  scheduled_for?: string;
  char_count?: number;
  keywords_used?: string[];
  note?: string;
  created_at?: string;
  updated_at?: string;
  generated_at?: string;
  published_at?: string;
  google_post_name?: string;
  approval_mode?: string;
  archived_reason?: string;
};

export type KeywordAuditItem = {
  keyword: string;
  count: number;
  present: boolean;
};

/** Alias used by gbpKeywordAudit lib */
export type GbpKeywordAudit = KeywordAuditItem;

export type GbpPhoto = {
  id: string;
  source: string;
  prompt?: string;
  storage_path?: string;
  slot_label?: string;
  status: string;
  url?: string;
  created_at?: string;
};

export type GbpBrandKit = {
  brand_name?: string;
  agency_type?: string;
  language?: string;
  brand_voice?: string;
  forbidden_words?: string;
  primary_color?: string;
  secondary_color?: string;
  heading_font?: string;
  body_font?: string;
  logo_on_light_url?: string;
  logo_on_dark_url?: string;
};

export type GbpOverview = {
  connected: boolean;
  location_name?: string;
  business_name?: string;
  health_score?: number;
  health_breakdown?: Record<string, unknown>;
  description?: string;
  description_google?: string;
  /** Whether Google has a live description — not the description text itself. */
  description_live?: boolean;
  primary_keyword?: string;
  keyword_targets?: string[];
  keyword_placement?: string;
  keyword_audit?: KeywordAuditItem[];
  keyword_audit_primary?: KeywordAuditItem[];
  keyword_audit_live?: KeywordAuditItem[];
  keyword_audit_draft?: KeywordAuditItem[];
  keyword_audit_services?: KeywordAuditItem[];
  keyword_gaps?: string[];
  keyword_gaps_live?: string[];
  keyword_gaps_draft?: string[];
  gbp_services_on_listing?: string[];
  photo_count?: number;
  categories?: string[];
  weekly_post?: GbpQueueItem | null;
  posts?: GbpQueueItem[];
  description_draft?: GbpQueueItem | null;
  description_history?: GbpQueueItem[];
  activity?: { type: string; description: string; occurred_at: string; status: string }[];
  website_uri?: string;
  library_photos?: GbpPhoto[];
  brand_kit?: GbpBrandKit;
  location_scope?: string;
};

// ── Overview ──────────────────────────────────────────────────────────────────

/** Authenticated GBP photo URL for <img src> (JWT in query — img tags cannot send Authorization). */
export function gbpPhotoFileUrl(photoId: string, token?: string | null): string {
  const jwt = token ?? useAuthStore.getState().accessToken;
  const path = `/api/v1/gbp/photos/${photoId}/file`;
  // Dev: same-origin via Vite proxy. Prod: optional absolute API base.
  const base = import.meta.env.DEV
    ? ""
    : String(import.meta.env.VITE_API_BASE_URL ?? "").trim().replace(/\/+$/, "");
  const url = base ? `${base}${path}` : path;
  if (!jwt) return url;
  return `${url}?${new URLSearchParams({ token: jwt }).toString()}`;
}

export const fetchGbpOverview = (): Promise<GbpOverview> =>
  apiGet<GbpOverview>("/api/v1/gbp/overview");

/** Live Google listing description (never use `description_live` — that field is a boolean flag). */
export function gbpListingDescription(
  d: Pick<GbpOverview, "description_google" | "description">,
): string {
  const google = (d.description_google ?? "").trim();
  if (google) return google;
  return (d.description ?? "").trim();
}

// ── Posts ─────────────────────────────────────────────────────────────────────

export const generateGbpPosts = (count: number, prompt: string | null): Promise<Record<string, unknown>> =>
  apiPostJson("/api/v1/gbp/posts/generate", { count, prompt });

export type GbpPostDirection = {
  direction: string;
  keyword: string;
  slot: string;
  archetype?: string;
  image_prompt?: string;
};

export type GenerateGbpPostDirectionsResult = {
  count: number;
  prompts: GbpPostDirection[];
  model?: string;
  keywords_selected?: string[];
};

export const generateGbpPostDirections = (
  count: number,
  keywords: string[],
): Promise<GenerateGbpPostDirectionsResult> =>
  apiPostJson("/api/v1/gbp/posts/generate-directions", { count, keywords });

export const updateGbpPost = (
  id: string,
  data: { status?: string; body?: string; scheduled_for?: string },
): Promise<Record<string, unknown>> =>
  apiPatchJson(`/api/v1/gbp/posts/${id}`, data);

export const publishGbpPost = (
  id: string,
  body?: string,
): Promise<Record<string, unknown>> =>
  apiPostJson(`/api/v1/gbp/posts/${id}/publish`, { body });

export const deleteGbpPost = (id: string): Promise<Record<string, unknown>> =>
  apiDelete(`/api/v1/gbp/posts/${id}`);

export const syncGbpPosts = (): Promise<Record<string, unknown>> =>
  apiPostJson("/api/v1/gbp/posts/sync", {});

export type ScheduleAllResult = {
  approved: number;
  mode: string;
  first_date: string | null;
  last_date: string | null;
};

export const scheduleAllGbpPosts = (
  mode: "daily" | "range",
  startDate?: string,
  endDate?: string,
): Promise<ScheduleAllResult> =>
  apiPostJson("/api/v1/gbp/posts/schedule-all", {
    mode,
    start_date: startDate ?? null,
    end_date: endDate ?? null,
  });

/** Download GBP posts as Excel — optional date range and/or selected post IDs. */
export type GbpPostsExportOptions = {
  postIds?: string[];
  dateFrom?: string;
  dateTo?: string;
};

export const downloadGbpPostsXlsx = async (opts?: GbpPostsExportOptions): Promise<void> => {
  const params = new URLSearchParams();
  if (opts?.postIds?.length) params.set("post_ids", opts.postIds.join(","));
  if (opts?.dateFrom) params.set("date_from", opts.dateFrom);
  if (opts?.dateTo) params.set("date_to", opts.dateTo);
  const qs = params.toString();
  const path = qs ? `/api/v1/gbp/posts/export?${qs}` : "/api/v1/gbp/posts/export";
  const { blob, filename } = await apiGetBlob(path);
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename || "gbp-posts.xlsx";
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
};

// ── Description ───────────────────────────────────────────────────────────────

export const generateGbpDescription = (userKeywords?: string[]): Promise<Record<string, unknown>> =>
  apiPostJson("/api/v1/gbp/description/generate", { user_keywords: userKeywords ?? [] });

export const saveGbpDescriptionDraft = (body: string): Promise<GbpQueueItem> =>
  apiPostJson("/api/v1/gbp/description/draft", { body });

export const updateGbpDescription = (
  id: string,
  data: { status?: string; body?: string; scheduled_for?: string },
): Promise<Record<string, unknown>> =>
  apiPatchJson(`/api/v1/gbp/description/${id}`, data);

// ── Photos ────────────────────────────────────────────────────────────────────

export const generateGbpPhoto = (
  prompt: string,
  slot_label?: string,
): Promise<Record<string, unknown>> =>
  apiPostJson("/api/v1/gbp/photos/generate", { prompt, slot_label });

export const uploadGbpPhoto = (
  file: File,
  slot_label?: string,
): Promise<Record<string, unknown>> => {
  const fd = new FormData();
  fd.append("file", file);
  if (slot_label) fd.append("slot_label", slot_label);
  return apiPostFormData("/api/v1/gbp/photos/upload", fd);
};

export const deleteGbpPhoto = (id: string): Promise<Record<string, unknown>> =>
  apiDelete(`/api/v1/gbp/photos/${id}`);

export const publishGbpPhoto = (id: string): Promise<Record<string, unknown>> =>
  apiPostJson(`/api/v1/gbp/photos/${id}/publish`, {});

// ── Brand Kit ─────────────────────────────────────────────────────────────────

export const saveGbpBrandKit = (data: Partial<GbpBrandKit>): Promise<Record<string, unknown>> =>
  apiPostJson("/api/v1/gbp/brand-kit", data);

export const uploadGbpBrandLogo = (
  file: File,
  variant: "light" | "dark" = "light",
): Promise<Record<string, unknown>> => {
  const fd = new FormData();
  fd.append("file", file);
  fd.append("variant", variant);
  return apiPostFormData("/api/v1/gbp/brand-kit/logo", fd);
};

// ── Activity (legacy) ─────────────────────────────────────────────────────────

export async function fetchGbpActivity(): Promise<GbpActivityResponse> {
  return apiGet<GbpActivityResponse>("/api/v1/gbp/activity");
}
