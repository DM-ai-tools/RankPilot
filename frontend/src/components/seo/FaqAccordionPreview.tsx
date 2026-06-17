import { useState } from "react";

export function parseFaqPairs(body: string): { question: string; answer: string }[] {
  const text = (body || "").trim();
  if (!text) return [];
  const pairs: { question: string; answer: string }[] = [];
  for (const chunk of text.split(/\n(?=\*\*)/)) {
    const trimmed = chunk.trim();
    if (!trimmed) continue;
    const match = trimmed.match(/^\*\*(.+?)\*\*\s*\n?([\s\S]*)$/);
    if (match) {
      const question = match[1].trim();
      const answer = match[2].trim();
      if (question) pairs.push({ question, answer });
    }
  }
  return pairs;
}

function faqTitleParts(heading: string): { before: string; accent: string; after: string } {
  const raw = (heading || "").trim();
  if (!raw) {
    return { before: "FREQUENTLY ASKED ", accent: "QUESTIONS", after: "" };
  }
  const match = raw.match(/\b(questions?|faq)\b/i);
  if (match && match.index !== undefined) {
    return {
      before: raw.slice(0, match.index).trim(),
      accent: match[0],
      after: raw.slice(match.index + match[0].length).trim(),
    };
  }
  const words = raw.rsplit(" ", 1);
  if (words.length === 2) {
    return { before: words[0], accent: words[1], after: "" };
  }
  return { before: "", accent: raw, after: "" };
}

type Props = {
  heading?: string | null;
  body: string;
};

export function FaqAccordionPreview({ heading, body }: Props) {
  const pairs = parseFaqPairs(body);
  const [openIndex, setOpenIndex] = useState(0);
  const title = faqTitleParts(heading || "");

  if (!pairs.length) {
    return (
      <div className="whitespace-pre-wrap text-[11px] leading-relaxed text-rp-tmid">{body}</div>
    );
  }

  return (
    <div className="rounded-lg bg-[#f8f8f8] p-3">
      <h3 className="mb-3 text-center text-[11px] font-extrabold uppercase tracking-wide text-navy">
        {title.before ? <span>{title.before} </span> : null}
        <span className="text-[#FF6B00]">{title.accent}</span>
        {title.after ? <span> {title.after}</span> : null}
      </h3>
      <div className="space-y-2">
        {pairs.map((item, i) => {
          const open = openIndex === i;
          return (
            <div
              key={`${item.question.slice(0, 40)}-${i}`}
              className={`overflow-hidden rounded-xl shadow-sm transition-colors ${
                open ? "bg-[#FF6B00] text-white shadow-[0_6px_20px_rgba(255,107,0,0.28)]" : "bg-white text-navy"
              }`}
            >
              <button
                type="button"
                className="flex w-full items-center justify-between gap-3 px-3 py-2.5 text-left"
                onClick={() => setOpenIndex(open ? -1 : i)}
                aria-expanded={open}
              >
                <span className="text-[11px] font-bold leading-snug">{item.question}</span>
                <span
                  className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-lg leading-none ${
                    open ? "bg-white text-[#FF6B00]" : "bg-navy text-white"
                  }`}
                  aria-hidden
                >
                  {open ? "−" : "+"}
                </span>
              </button>
              {open ? (
                <div className="space-y-2 px-3 pb-3 text-[11px] font-normal leading-relaxed opacity-95">
                  {item.answer.split(/\n\s*\n/).map((para) => (
                    <p key={para.slice(0, 30)}>{para}</p>
                  ))}
                </div>
              ) : null}
            </div>
          );
        })}
      </div>
      <p className="mt-2 text-center text-[9px] text-rp-tlight">
        Accordion preview — publishes with + expand on WordPress
      </p>
    </div>
  );
}
