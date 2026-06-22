import { apiDelete, apiGet, apiPatchJson, apiPostJson } from "./client";

export type SeoWebsitePage = {
  id: number;
  title: string;
  slug: string;
  status: string;
  link: string;
  modified: string | null;
  excerpt: string | null;
  word_count: number;
};

export type SeoWebsitePagesResponse = {
  items: SeoWebsitePage[];
  page: number;
  per_page: number;
  total: number;
};

export type ContentTemplateItem = {
  id: string;
  label: string;
  sections: string[];
};

export type ContentTemplatesResponse = {
  items: ContentTemplateItem[];
};

export const fetchWordpressPages = (search = ""): Promise<SeoWebsitePagesResponse> => {
  const params = new URLSearchParams({ page: "1", per_page: "30" });
  if (search.trim()) params.set("search", search.trim());
  return apiGet<SeoWebsitePagesResponse>(`/api/v1/integrations/wordpress/pages?${params.toString()}`);
};

export const fetchContentTemplates = (): Promise<ContentTemplatesResponse> =>
  apiGet<ContentTemplatesResponse>("/api/v1/integrations/wordpress/content-templates");

export const updateWordpressPageSeo = (
  pageId: number,
  body: { title?: string; slug?: string; excerpt?: string },
): Promise<SeoWebsitePage> =>
  apiPatchJson<SeoWebsitePage, { title?: string; slug?: string; excerpt?: string }>(
    `/api/v1/integrations/wordpress/pages/${pageId}`,
    body,
  );

export const saveWordpressPageContent = (
  pageId: number,
  body: { content_markdown: string; status?: string },
): Promise<SeoWebsitePage> =>
  apiPatchJson<SeoWebsitePage, { content_markdown: string; status?: string }>(
    `/api/v1/integrations/wordpress/pages/${pageId}/save-content`,
    body,
  );

export type WordPressPageEditContent = {
  id: number;
  title: string;
  excerpt: string;
  content_html: string;
  link: string;
  slug: string;
  status: string;
};

export const fetchWordpressPageEditContent = (pageId: number): Promise<WordPressPageEditContent> =>
  apiGet<WordPressPageEditContent>(`/api/v1/integrations/wordpress/pages/${pageId}/edit-content`);

export const saveWordpressPageHtml = (
  pageId: number,
  body: { content_html: string; title?: string; excerpt?: string; status?: string },
): Promise<SeoWebsitePage> =>
  apiPatchJson<
    SeoWebsitePage,
    { content_html: string; title?: string; excerpt?: string; status?: string }
  >(`/api/v1/integrations/wordpress/pages/${pageId}/save-html-content`, body);

export type GenerateMetaResponse = {
  title: string;
  excerpt: string;
  model: string;
  mode: "default" | "research";
  research_signals: string[];
};

export const generateWordpressMeta = (
  pageId: number,
  body: {
    title?: string;
    slug?: string;
    link?: string;
    current_excerpt?: string;
    keywords?: string[];
    mode?: "default" | "research";
  },
): Promise<GenerateMetaResponse> =>
  apiPostJson<
    GenerateMetaResponse,
    {
      title?: string;
      slug?: string;
      link?: string;
      current_excerpt?: string;
      keywords?: string[];
      mode?: "default" | "research";
    }
  >(
    `/api/v1/integrations/wordpress/pages/${pageId}/generate-meta`,
    body,
  );

export type SuburbPageModule = {
  type: string;
  heading?: string | null;
  body: string;
};

export type GenerateContentResponse = {
  title: string;
  excerpt: string;
  content: string;
  model: string;
  mode: "default" | "research";
  module_set_used: string[];
  word_count: number;
  modules: SuburbPageModule[];
};

export const generateWordpressContent = (
  pageId: number,
  body: {
    template_id: string;
    prompt?: string;
    keywords?: string[];
    mode?: "default" | "research";
    suburb?: string;
    nearby_suburbs?: string;
    service_focus?: string;
    structure_mode?: "auto" | "preset" | "manual";
    preset_id?: string;
    optional_modules?: string[];
    module_set_used?: string[];
  },
): Promise<GenerateContentResponse> =>
  apiPostJson<
    GenerateContentResponse,
    {
      template_id: string;
      prompt?: string;
      keywords?: string[];
      mode?: "default" | "research";
      suburb?: string;
      nearby_suburbs?: string;
      service_focus?: string;
      structure_mode?: "auto" | "preset" | "manual";
      preset_id?: string;
      optional_modules?: string[];
      module_set_used?: string[];
    }
  >(`/api/v1/integrations/wordpress/pages/${pageId}/generate-content`, body);

// ── Suburb / geo landing pages (keyword + text + images → WordPress) ──────────

export type SuburbPageImage = {
  role: string;
  photo_id?: string | null;
  url?: string | null;
  preview_data_url?: string | null;
  note?: string | null;
};

export type LocalSeoModuleInfo = {
  type: string;
  label: string;
  group: string;
  description: string;
  required: boolean;
};

export type LocalSeoPreset = {
  id: string;
  label: string;
  description: string;
  optional_modules: string[] | null;
};

export type LocalSeoModuleLibraryResponse = {
  modules: LocalSeoModuleInfo[];
  presets: LocalSeoPreset[];
  anchors: string[];
};

export type GenerateSuburbPageRequest = {
  keyword: string;
  suburb?: string;
  slug?: string;
  word_count_target?: number;
  image_count?: number;
  prompt?: string;
  structure_mode?: "auto" | "preset" | "manual";
  preset_id?: string;
  optional_modules?: string[];
  nearby_suburbs?: string;
  service_focus?: string;
  keep_image_photo_ids?: string[];
  module_set_used?: string[];
  regenerate_images_only?: boolean;
  preserved_title?: string;
  preserved_excerpt?: string;
  preserved_content?: string;
  preserved_modules?: SuburbPageModule[];
};

export type GenerateSuburbPageResponse = {
  history_id: string;
  title: string;
  excerpt: string;
  content: string;
  word_count: number;
  target_keyword: string;
  slug: string;
  model: string;
  images: SuburbPageImage[];
  module_set_used: string[];
  modules: SuburbPageModule[];
  nearby_suburbs: string;
  service_focus: string;
};

export const fetchSuburbPageModules = (): Promise<LocalSeoModuleLibraryResponse> =>
  apiGet<LocalSeoModuleLibraryResponse>("/api/v1/integrations/wordpress/suburb-pages/modules");

export const generateSuburbPage = (
  body: GenerateSuburbPageRequest,
): Promise<GenerateSuburbPageResponse> =>
  apiPostJson<GenerateSuburbPageResponse, GenerateSuburbPageRequest>(
    "/api/v1/integrations/wordpress/suburb-pages/generate",
    body,
  );

export type PublishSuburbPageRequest = {
  history_id?: string;
  title: string;
  content: string;
  excerpt?: string;
  slug?: string;
  target_keyword?: string;
  suburb?: string;
  image_photo_ids?: string[];
};

export type PublishSuburbPageResponse = {
  history_id: string;
  link: string;
  slug: string;
  page_id?: number | null;
  media_ids: number[];
};

export const publishSuburbPage = (
  body: PublishSuburbPageRequest,
): Promise<PublishSuburbPageResponse> =>
  apiPostJson<PublishSuburbPageResponse, PublishSuburbPageRequest>(
    "/api/v1/integrations/wordpress/suburb-pages/publish",
    body,
  );

export type SuburbPageHistoryItem = {
  id: string;
  status: string;
  keyword: string;
  suburb: string;
  slug: string;
  title: string;
  excerpt?: string;
  word_count: number | null;
  image_photo_ids: string[];
  module_set_used: string[];
  nearby_suburbs: string;
  service_focus: string;
  model: string | null;
  wordpress_page_id: number | null;
  wordpress_link: string | null;
  page_url: string | null;
  generated_at: string | null;
  published_at: string | null;
};

export type SuburbPageHistoryResponse = {
  items: SuburbPageHistoryItem[];
};

export const fetchSuburbPageHistory = (): Promise<SuburbPageHistoryResponse> =>
  apiGet<SuburbPageHistoryResponse>("/api/v1/integrations/wordpress/suburb-pages/history");

export type SuburbPageHistoryDetail = {
  history_id: string;
  id: string;
  status: string;
  title: string;
  excerpt: string;
  content: string;
  word_count: number;
  target_keyword: string;
  suburb: string;
  slug: string;
  model: string | null;
  images: SuburbPageImage[];
  module_set_used: string[];
  modules: SuburbPageModule[];
  nearby_suburbs: string;
  service_focus: string;
  wordpress_page_id: number | null;
  wordpress_link: string | null;
  page_url: string | null;
  generated_at: string | null;
  published_at: string | null;
};

export const fetchSuburbPageHistoryItem = (historyId: string): Promise<SuburbPageHistoryDetail> =>
  apiGet<SuburbPageHistoryDetail>(
    `/api/v1/integrations/wordpress/suburb-pages/history/${historyId}`,
  );

export const deleteSuburbPageHistory = (
  historyId: string,
  deleteWordpress = true,
): Promise<{ deleted: boolean; wordpress_page_deleted: boolean }> =>
  apiDelete(
    `/api/v1/integrations/wordpress/suburb-pages/history/${historyId}?delete_wordpress=${deleteWordpress}`,
  );

export type SuburbPageRankingItem = {
  history_id: string;
  title: string;
  keyword: string;
  search_keywords?: string[];
  suburb: string;
  slug: string;
  page_url: string | null;
  published_at: string | null;
  last_week_organic: number | null;
  last_week_maps: number | null;
  last_week_position: number | null;
  last_week_label: string;
  this_week_organic: number | null;
  this_week_maps: number | null;
  this_week_position: number | null;
  this_week_label: string;
  position_change: number | null;
  is_ranking: boolean;
  status: "ranking" | "not_ranking" | string;
  rank_note?: string | null;
};

export type SuburbPageRankingsResponse = {
  items: SuburbPageRankingItem[];
};

export const fetchSuburbPageRankings = (): Promise<SuburbPageRankingsResponse> =>
  apiGet<SuburbPageRankingsResponse>("/api/v1/integrations/wordpress/suburb-pages/rankings");

export const syncSuburbPageRankings = (): Promise<
  SuburbPageRankingsResponse & { added_keywords: number; checked: number }
> => apiPostJson("/api/v1/integrations/wordpress/suburb-pages/rankings/sync", {});
