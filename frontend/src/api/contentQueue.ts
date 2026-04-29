import { apiGet, apiPatchJson, apiPostJson } from "./client";

export type ContentItem = {
  id: string;
  content_type: string;
  title: string;
  status: string;
  approval_mode: string;
  word_count: number | null;
  generated_at: string | null;
  published_at: string | null;
  target_url: string | null;
  body: string | null;
  notes: string | null;
};

export type ContentQueueResponse = { items: ContentItem[] };

export const fetchContentQueue = (): Promise<ContentQueueResponse> =>
  apiGet<ContentQueueResponse>("/api/v1/content-queue/");

export const updateItemStatus = (id: string, status: string): Promise<ContentItem> =>
  apiPatchJson<ContentItem, { status: string }>(`/api/v1/content-queue/${id}/status`, { status });

export const approveAll = (): Promise<{ updated: number }> =>
  apiPostJson<{ updated: number }, object>("/api/v1/content-queue/approve-all", {});

export const purgeShellQueueItems = (): Promise<{ removed: number }> =>
  apiPostJson<{ removed: number }, object>("/api/v1/content-queue/purge-shell-items", {});

export const generateContent = (): Promise<{
  generated: number;
  items: unknown[];
  error?: string;
  warnings?: string[];
}> => apiPostJson("/api/v1/content-queue/generate", {});
