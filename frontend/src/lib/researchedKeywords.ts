import { useSyncExternalStore } from "react";

import type { RelatedKeywordIdea } from "../api/keywords";

/**
 * Keywords the user researched in the "Keyword Research" tab.
 * Persisted in localStorage so they show up as selectable options in the
 * Posts & Content and Description keyword pickers.
 */
export type ResearchedKeyword = {
  keyword: string;
  volume: number | null;
  added_at: string;
};

const STORAGE_KEY = "rp_researched_keywords";
const CHANGE_EVENT = "rp:researched-keywords-changed";
const MAX_ITEMS = 50;

function load(): ResearchedKeyword[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed)
      ? parsed.filter((x) => x && typeof x.keyword === "string" && x.keyword.trim())
      : [];
  } catch {
    return [];
  }
}

let cache: ResearchedKeyword[] = load();

function persist(next: ResearchedKeyword[]) {
  cache = next;
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
  } catch {
    // storage full / unavailable — keep in-memory copy
  }
  window.dispatchEvent(new Event(CHANGE_EVENT));
}

export function getResearchedKeywords(): ResearchedKeyword[] {
  return cache;
}

export function addResearchedKeyword(keyword: string, volume?: number | null): void {
  const kw = keyword.trim();
  if (!kw) return;
  const key = kw.toLowerCase();
  const rest = cache.filter((x) => x.keyword.toLowerCase() !== key);
  persist(
    [{ keyword: kw, volume: volume ?? null, added_at: new Date().toISOString() }, ...rest].slice(
      0,
      MAX_ITEMS,
    ),
  );
}

export function removeResearchedKeyword(keyword: string): void {
  const key = keyword.trim().toLowerCase();
  persist(cache.filter((x) => x.keyword.toLowerCase() !== key));
}

export function isResearchedKeyword(keyword: string): boolean {
  const key = keyword.trim().toLowerCase();
  return cache.some((x) => x.keyword.toLowerCase() === key);
}

function subscribe(cb: () => void) {
  const onStorage = (e: StorageEvent) => {
    if (e.key === STORAGE_KEY) {
      cache = load();
      cb();
    }
  };
  window.addEventListener(CHANGE_EVENT, cb);
  window.addEventListener("storage", onStorage);
  return () => {
    window.removeEventListener(CHANGE_EVENT, cb);
    window.removeEventListener("storage", onStorage);
  };
}

/** Reactive list of researched keywords (updates across tabs/components). */
export function useResearchedKeywords(): ResearchedKeyword[] {
  return useSyncExternalStore(subscribe, getResearchedKeywords);
}

/** Researched keywords first (marked via `suburb: null`), then Ahrefs list, deduped. */
export function mergeResearchedIntoIdeas(
  researched: ResearchedKeyword[],
  ideas: RelatedKeywordIdea[],
): RelatedKeywordIdea[] {
  const seen = new Set<string>();
  const out: RelatedKeywordIdea[] = [];
  for (const r of researched) {
    const key = r.keyword.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    out.push({ keyword: r.keyword, avg_monthly_searches: r.volume ?? 0 });
  }
  for (const item of ideas) {
    const key = (item.keyword ?? "").trim().toLowerCase();
    if (!key || seen.has(key)) continue;
    seen.add(key);
    out.push(item);
  }
  return out;
}
