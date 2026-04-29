/**
 * Derives preview sections and SEO-ish signals from draft markdown only.
 * No business-keyword literals — detection is structural / pattern-based.
 */

export type PreviewSignals = {
  wordCount: number;
  hasH1Line: boolean;
  hasSubheadings: boolean;
  hasFaqBlock: boolean;
  hasJsonLd: boolean;
  hasRelativeLinks: boolean;
  hasList: boolean;
  hasExternalLinks: boolean;
};

export type PreviewDerived = {
  pageTitle: string;
  introMd: string | null;
  restMd: string;
  faqMd: string | null;
  jsonLdPretty: string | null;
  signals: PreviewSignals;
};

function countWords(s: string): number {
  const t = s.trim();
  if (!t) return 0;
  return t.split(/\s+/).length;
}

/** Heading line: FAQ, Frequently asked…, Common questions… */
const FAQ_HEADING_RE =
  /(^|\n)(#{1,6})\s*(faq|frequently asked questions?|common questions?)\s*(?:\n|$)/i;

function extractFaqMarkdown(body: string): string | null {
  const m = body.match(FAQ_HEADING_RE);
  if (!m || m.index === undefined) return null;
  const start = m.index + m[0].length;
  const tail = body.slice(start);
  const nextH2 = tail.search(/\n##\s+/);
  const slice = (nextH2 >= 0 ? tail.slice(0, nextH2) : tail).trim();
  return slice.length ? slice : null;
}

function extractJsonLdPretty(body: string): string | null {
  const fenceRe = /```(?:json|application\/ld\+json|ld\+json)?\s*([\s\S]*?)```/gi;
  let m: RegExpExecArray | null;
  while ((m = fenceRe.exec(body)) !== null) {
    const inner = m[1].trim();
    if (!/"(?:@context|@type)"|@(context|type)\s*:/i.test(inner)) continue;
    try {
      return JSON.stringify(JSON.parse(inner), null, 2);
    } catch {
      if (inner.length > 0 && inner.length < 16000) return inner;
    }
  }
  const script = body.match(/<script[^>]*type\s*=\s*["']application\/ld\+json["'][^>]*>([\s\S]*?)<\/script>/i);
  if (script) {
    const raw = script[1].trim();
    try {
      return JSON.stringify(JSON.parse(raw), null, 2);
    } catch {
      return raw || null;
    }
  }
  return null;
}

function computeSignals(body: string, wordCount: number, hasFaqBlock: boolean, hasJsonLd: boolean): PreviewSignals {
  const hasH1Line = /(^|\n)#\s(?!#)/.test(body);
  const hasSubheadings = /\n##\s/.test(body) || /^##\s/m.test(body);
  const hasRelativeLinks = /\]\(\/[^)\s]+\)/.test(body) || /\]\(\.\/[^)]+\)/.test(body);
  const hasList = /(^|\n)\s*[-*+]\s/.test(body) || /(^|\n)\s*\d+\.\s/.test(body);
  const hasExternalLinks = /\]\(https?:\/\/[^)]+\)/i.test(body);
  return {
    wordCount,
    hasH1Line,
    hasSubheadings,
    hasFaqBlock,
    hasJsonLd,
    hasRelativeLinks,
    hasList,
    hasExternalLinks,
  };
}

/**
 * Split opening narrative (before first H2 / rule / deep H3) from the rest.
 */
function splitIntroRest(blocks: string[]): { introParts: string[]; restStart: number } {
  const introParts: string[] = [];
  let i = 0;
  for (; i < blocks.length; i++) {
    const b = blocks[i];
    const head = b.split("\n")[0] ?? "";
    if (/^##\s/.test(head)) break;
    if (/^---+\s*$/.test(b.trim())) break;
    if (/^###\s/.test(head) && introParts.length > 0) break;
    if (/^[-*+]\s/.test(head) && introParts.length > 0) break;
    introParts.push(b);
    if (introParts.join("\n\n").length > 1200) {
      i++;
      break;
    }
  }
  return { introParts, restStart: i };
}

export function derivePreviewDraft(body: string, fallbackTitle: string, apiWordCount: number | null): PreviewDerived {
  const trimmed = (body || "").trim();
  const wc = apiWordCount ?? countWords(trimmed);

  if (!trimmed) {
    return {
      pageTitle: (fallbackTitle || "").trim() || "Untitled draft",
      introMd: null,
      restMd: "",
      faqMd: null,
      jsonLdPretty: null,
      signals: computeSignals("", wc, false, false),
    };
  }

  const jsonLdPretty = extractJsonLdPretty(trimmed);
  const faqMd = extractFaqMarkdown(trimmed);
  const hasFaqBlock = Boolean(faqMd);
  const hasJsonLd = Boolean(jsonLdPretty);

  let blocks = trimmed.split(/\n\n+/);
  let pageTitle = (fallbackTitle || "").trim() || "Untitled draft";

  const firstBlock = blocks[0] ?? "";
  const firstLines = firstBlock.split("\n");
  const firstLine = firstLines[0] ?? "";

  if (/^#\s(?!#)/.test(firstLine)) {
    const fromH1 = firstLine.replace(/^#\s+/, "").trim();
    if (fromH1) pageTitle = fromH1;
    const remainder = firstLines.slice(1).join("\n").trim();
    blocks = remainder ? [remainder, ...blocks.slice(1)] : blocks.slice(1);
  }

  const { introParts, restStart } = splitIntroRest(blocks);
  const introMd = introParts.length ? introParts.join("\n\n") : null;
  const restMd = blocks.slice(restStart).join("\n\n").trim();

  return {
    pageTitle,
    introMd,
    restMd,
    faqMd,
    jsonLdPretty,
    signals: computeSignals(trimmed, wc, hasFaqBlock, hasJsonLd),
  };
}
