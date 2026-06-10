import { apiGet, apiPatchJson, apiPostJson } from "./client";

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

export type GenerateContentResponse = {
  title: string;
  excerpt: string;
  content: string;
  model: string;
  mode: "default" | "research";
};

export const generateWordpressContent = (
  pageId: number,
  body: { template_id: string; prompt?: string; keywords?: string[]; mode?: "default" | "research" },
): Promise<GenerateContentResponse> =>
  apiPostJson<
    GenerateContentResponse,
    { template_id: string; prompt?: string; keywords?: string[]; mode?: "default" | "research" }
  >(`/api/v1/integrations/wordpress/pages/${pageId}/generate-content`, body);
