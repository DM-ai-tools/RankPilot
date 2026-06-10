import type { GbpKeywordAudit } from "../api/gbp";

/** Mirror backend phrase matching for live description audit while typing. */
function phraseOccurrences(text: string, phrase: string): number {
  const low = (text || "").toLowerCase();
  const p = (phrase || "").trim().toLowerCase().replace(/\s+/g, " ");
  if (!p) return 0;
  if (p.includes(" ")) {
    let count = 0;
    let idx = 0;
    while ((idx = low.indexOf(p, idx)) !== -1) {
      count += 1;
      idx += p.length;
    }
    return count;
  }
  const re = new RegExp(`\\b${p.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\b`, "gi");
  return (low.match(re) ?? []).length;
}

export function auditDescriptionKeywords(text: string, targets: string[]): GbpKeywordAudit[] {
  return targets
    .map((kw) => {
      const keyword = kw.trim().replace(/\s+/g, " ");
      if (!keyword) return null;
      const count = phraseOccurrences(text, keyword);
      return { keyword, count, present: count > 0 };
    })
    .filter((x): x is GbpKeywordAudit => x !== null);
}

export function keywordGapMessages(primary: GbpKeywordAudit[]): string[] {
  const gaps: string[] = [];
  for (const item of primary) {
    if (!item.present) {
      gaps.push(`"${item.keyword}" not in description — add the phrase below, then publish`);
    }
  }
  return gaps;
}
