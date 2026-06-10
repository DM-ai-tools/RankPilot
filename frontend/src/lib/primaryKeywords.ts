/** Comma-separated primary service keywords from onboarding / profile. */

export function parsePrimaryKeywords(raw: string): string[] {
  const out: string[] = [];
  const seen = new Set<string>();
  for (const part of (raw || "").split(/[,;\n]+/)) {
    const s = part.trim().replace(/\s+/g, " ");
    if (s.length < 2) continue;
    const key = s.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(s);
  }
  return out;
}

export function normalizePrimaryKeywords(raw: string): string {
  return parsePrimaryKeywords(raw).join(", ");
}

/** First keyword — Maps scans track one keyword at a time. */
export function scanKeywordFromPrimary(raw: string): string {
  const parsed = parsePrimaryKeywords(raw);
  return parsed[0] ?? (raw || "").trim();
}

export function formatPrimaryKeywordsLabel(raw: string): string {
  const parsed = parsePrimaryKeywords(raw);
  if (parsed.length <= 1) return parsed[0] ?? raw;
  return parsed.join(", ");
}
