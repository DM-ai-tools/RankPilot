"""Clicktrends-style local SEO landing page generation (module library A–N)."""

from __future__ import annotations

import json
import random
import re
from typing import Any

from fastapi import HTTPException

# Anchors — always included
ANCHOR_MODULES = ("A", "L", "M", "N")

CREDIBILITY = frozenset({"F", "G", "K"})
SERVICE_EXPLANATION = frozenset({"C", "D", "I"})
PROCESS_DIFF = frozenset({"E", "H"})
OPTIONAL_POOL = frozenset({"B", "C", "D", "E", "F", "G", "H", "I", "J", "K"})
GRID_MODULES = frozenset({"C", "D", "F", "H"})
NARRATIVE_MODULES = frozenset({"B", "I", "K", "J", "N"})

LOCAL_SEO_MODULES: dict[str, dict[str, str]] = {
    "A": {
        "label": "Hero Intro",
        "group": "anchor",
        "description": "H1 with keyword + 2–3 sentence intro establishing who you help and where",
    },
    "B": {
        "label": "Local-relevance narrative",
        "group": "narrative",
        "description": "Why local search matters specifically in this suburb",
    },
    "C": {
        "label": "Service grid",
        "group": "service",
        "description": "4–6 short service cards (icon + heading + 1–2 sentences each)",
    },
    "D": {
        "label": "Three-path CTA cards",
        "group": "service",
        "description": "DIY / Do-it-with-us / Done-for-you engagement levels",
    },
    "E": {
        "label": "Numbered process timeline",
        "group": "process",
        "description": "4–6 numbered steps (Research → Optimise → Content → Analysis)",
    },
    "F": {
        "label": "Stats / proof counters",
        "group": "credibility",
        "description": "3–4 big-number stat callouts with short labels",
    },
    "G": {
        "label": "Case-study snapshot cards",
        "group": "credibility",
        "description": "2 short result cards (problem → outcome), illustrative only",
    },
    "H": {
        "label": "Why-choose-us grid",
        "group": "process",
        "description": "4–6 differentiator cards (local expertise, ROI focus, certified team)",
    },
    "I": {
        "label": "Plain-language explainer",
        "group": "service",
        "description": "One analogy-driven paragraph explaining how SEO works",
    },
    "J": {
        "label": "Industry / niche callout",
        "group": "narrative",
        "description": "Block tailored to service focus or generic local business angle",
    },
    "K": {
        "label": "Testimonial quote",
        "group": "credibility",
        "description": "1–2 short generic quotes with role-based attribution",
    },
    "L": {
        "label": "Areas We Serve",
        "group": "anchor",
        "description": "Intro line + list built from nearby suburbs",
    },
    "M": {
        "label": "FAQ accordion",
        "group": "anchor",
        "description": (
            "4–6 local SEO FAQs — every question must relate to the primary keyword AND suburb/area; "
            "heading must mention keyword + locality"
        ),
    },
    "N": {
        "label": "Closing CTA paragraph",
        "group": "anchor",
        "description": "2–3 sentences restating the keyword once, inviting contact",
    },
}

LOCAL_SEO_PRESETS: list[dict[str, Any]] = [
    {
        "id": "balanced",
        "label": "Balanced (auto)",
        "description": "Random layout per selection rules — avoids repeating recent pages",
        "optional_modules": None,
    },
    {
        "id": "credibility",
        "label": "Credibility focus",
        "description": "Service grid + stats + process + local narrative",
        "optional_modules": ["B", "C", "E", "F"],
    },
    {
        "id": "service",
        "label": "Service explanation",
        "description": "Service grid + three-path CTA + why-choose-us + explainer",
        "optional_modules": ["C", "D", "H", "I"],
    },
    {
        "id": "trust",
        "label": "Trust & proof",
        "description": "Case studies + testimonials + stats + local narrative",
        "optional_modules": ["B", "F", "G", "K"],
    },
]


def module_library_payload() -> dict[str, Any]:
    modules = [
        {
            "type": letter,
            "label": meta["label"],
            "group": meta["group"],
            "description": meta["description"],
            "required": letter in ANCHOR_MODULES,
        }
        for letter, meta in LOCAL_SEO_MODULES.items()
    ]
    return {"modules": modules, "presets": LOCAL_SEO_PRESETS, "anchors": list(ANCHOR_MODULES)}


def validate_optional_modules(modules: list[str]) -> list[str]:
    """Validate exactly 4 optional modules (B–K) with group constraints."""
    cleaned = [m.strip().upper() for m in modules if m and m.strip()]
    if len(cleaned) != 4:
        raise HTTPException(
            status_code=400,
            detail="Choose exactly 4 optional modules (B–K). Anchors A, L, M, N are always included.",
        )
    if len(set(cleaned)) != 4:
        raise HTTPException(status_code=400, detail="Each optional module can only be selected once.")
    invalid = [m for m in cleaned if m not in OPTIONAL_POOL]
    if invalid:
        raise HTTPException(status_code=400, detail=f"Invalid module letters: {', '.join(invalid)}")

    cred = [m for m in cleaned if m in CREDIBILITY]
    svc = [m for m in cleaned if m in SERVICE_EXPLANATION]
    proc = [m for m in cleaned if m in PROCESS_DIFF]
    if len(cred) != 1:
        raise HTTPException(status_code=400, detail="Pick exactly 1 credibility module: F, G, or K.")
    if len(svc) != 1:
        raise HTTPException(status_code=400, detail="Pick exactly 1 service module: C, D, or I.")
    if len(proc) != 1:
        raise HTTPException(status_code=400, detail="Pick exactly 1 process module: E or H.")
    return cleaned


def _combo_key(module_set: list[str]) -> str:
    return ",".join(module_set)


def _has_grid_clash(order: list[str]) -> bool:
    for i in range(len(order) - 1):
        if order[i] in GRID_MODULES and order[i + 1] in GRID_MODULES:
            return True
    return False


def order_module_set(modules: list[str]) -> list[str]:
    """A first, N last; shuffle middle with grid/narrative rhythm."""
    anchors_start = [m for m in modules if m == "A"]
    anchors_end = [m for m in modules if m in ("L", "M", "N")]
    middle = [m for m in modules if m not in ("A", "L", "M", "N")]

    best: list[str] | None = None
    for _ in range(40):
        random.shuffle(middle)
        candidate = anchors_start + middle + anchors_end
        if not _has_grid_clash(candidate):
            return candidate
        best = candidate
    return best or (anchors_start + middle + anchors_end)


def select_module_set_auto(
    recent_sets: list[list[str]],
    *,
    rng: random.Random | None = None,
) -> list[str]:
    """Pick 8 modules per Clicktrends selection rules."""
    r = rng or random.Random()
    recent_keys = {_combo_key(s) for s in recent_sets if s}

    for _ in range(60):
        cred = r.choice(sorted(CREDIBILITY))
        svc = r.choice(sorted(SERVICE_EXPLANATION))
        proc = r.choice(sorted(PROCESS_DIFF))
        used = {cred, svc, proc}
        remaining = sorted(OPTIONAL_POOL - used)
        wildcard = r.choice(remaining)
        optional = [cred, svc, proc, wildcard]
        full = ["A", *optional, "L", "M", "N"]
        ordered = order_module_set(full)
        if _combo_key(ordered) not in recent_keys:
            return ordered

    # Fallback — return last attempt even if collision
    return ordered  # type: ignore[possibly-undefined]


def build_module_set(
    *,
    structure_mode: str,
    optional_modules: list[str] | None,
    preset_id: str | None,
    recent_sets: list[list[str]],
) -> list[str]:
    mode = (structure_mode or "auto").strip().lower()
    if mode == "preset" and preset_id:
        preset = next((p for p in LOCAL_SEO_PRESETS if p["id"] == preset_id), None)
        if preset and preset.get("optional_modules"):
            optional = validate_optional_modules(list(preset["optional_modules"]))
            return order_module_set(["A", *optional, "L", "M", "N"])
        return select_module_set_auto(recent_sets)

    if mode == "manual" and optional_modules:
        optional = validate_optional_modules(optional_modules)
        return order_module_set(["A", *optional, "L", "M", "N"])

    return select_module_set_auto(recent_sets)


def suggest_nearby_suburbs(
    *,
    suburb: str,
    metro_label: str,
    count: int = 6,
) -> str:
    """Return comma-separated nearby suburb names for Module L."""
    from app.data.au_suburbs import get_suburbs_for_metro, haversine_km  # noqa: PLC0415

    anchor = (suburb or "").strip()
    suburbs = get_suburbs_for_metro(metro_label, radius_km=25, primary_suburb=anchor or None)
    if not suburbs:
        return ""

    if anchor:
        center = next(
            (s for s in suburbs if str(s.get("suburb", "")).lower() == anchor.lower()),
            None,
        )
        if center:
            la, lo = float(center["lat"]), float(center["lng"])
            ranked = sorted(
                (
                    s
                    for s in suburbs
                    if str(s.get("suburb", "")).lower() != anchor.lower()
                ),
                key=lambda s: haversine_km(la, lo, float(s["lat"]), float(s["lng"])),
            )
            names = [str(s["suburb"]) for s in ranked[: max(5, min(count, 7))]]
            return ", ".join(names)

    names = [
        str(s["suburb"])
        for s in suburbs
        if str(s.get("suburb", "")).lower() != anchor.lower()
    ][: max(5, min(count, 7))]
    return ", ".join(names)


def build_generation_prompt(
    *,
    primary_keyword: str,
    suburb: str,
    nearby_suburbs: str,
    service_focus: str,
    module_set: list[str],
    business: str,
    business_url: str,
    recent_module_sets: list[list[str]],
) -> str:
    module_letters = ", ".join(module_set)
    recent_json = json.dumps(recent_module_sets[:5]) if recent_module_sets else "[]"
    service_line = service_focus.strip() or "general local business"

    module_specs = "\n".join(
        f"- {letter}: {LOCAL_SEO_MODULES[letter]['label']} — {LOCAL_SEO_MODULES[letter]['description']}"
        for letter in module_set
        if letter in LOCAL_SEO_MODULES
    )

    return f"""You are generating body content for a Clicktrends local SEO landing page.

FIXED BRAND SHELL — DO NOT TOUCH OR REGENERATE:
Header, nav, phone, lead-capture form, footer, map embed, and closing button styles already exist in WordPress/Elementor. Never write copy for those. Never invent new colours or hex values.

INPUT:
- primary_keyword: {primary_keyword}
- suburb: {suburb or "N/A"}
- nearby_suburbs: {nearby_suburbs or "N/A"}
- service_focus: {service_line}
- business: {business or "N/A"}
- website: {business_url or "N/A"}
- module_set_for_this_page: [{module_letters}]
- recent_module_sets: {recent_json}

MODULES TO GENERATE (in this order):
{module_specs}

RULES:
- Length target: 900–1,250 words total across all modules.
- Use primary_keyword exactly 3 times total: once in H1 (module A), once in module A intro, once in module N closing. Do not repeat the exact keyword elsewhere.
- Australian English spelling (optimise, organisation, centre).
- Tone: clear, practical, consultative — not hype-heavy.
- NEVER write body paragraphs in ALL CAPS. Use normal sentence case for all paragraph text (like the Clicktrends Malvern reference pages).
- Module headings (H1/H2 fields): Title Case only — never SHOUTY ALL CAPS.
- Use **bold** ONLY for FAQ questions in module M. Do not wrap paragraphs, subheadings, or bullet labels in **bold** in any other module.
- Do not put subheadings inside module body as standalone **BOLD CAPS LINES**. Use plain sentences, or bullet lists (- item), or numbered steps (1. Step name: explanation).
- Stats, case studies, and testimonials must be generic/illustrative — no invented real client names or specific dollar figures.
- suburb should appear naturally in H2s, FAQ, and local-relevance sections.
- Module M (FAQ) is REQUIRED on every page — never omit, merge, or replace it.
- Module M heading: must mention the primary keyword AND suburb/locality (e.g. "SEO questions from {suburb} professional services firms" or "FAQ: {primary_keyword} in {suburb}").
- Module M body: 4–6 FAQ items for an accordion UI. Format each as **Question in bold?** then a short answer paragraph on the next line(s). Do not use images in FAQ.
- Every FAQ question must be about the primary keyword service IN the local area (suburb, metro, or nearby suburbs) — not generic national SEO trivia.
- At least 3 FAQ questions must explicitly name the suburb or nearby areas.
- Recommended FAQ themes (pick what fits): how local SEO differs here, timelines for results, working with an existing website, service area coverage, what to prepare before starting, cost/engagement expectations.
- Generate ONLY the modules listed above, in the order given.
- Each module "heading" must be PLAIN TEXT only — never include HTML tags like <h2> in the heading field.
- Each module "body" must be plain text or simple markdown: paragraphs separated by blank lines, use ## only in heading field not body, use - for bullet lists. Only module M FAQ questions use **bold**. Do NOT put <h1>, <h2>, or other HTML heading tags in body.
- Module A heading is the H1 text (plain). Other module headings are H2 text (plain).
- Module L must list the nearby suburbs from the input.
- Module M: follow the FAQ rules above — this is the dedicated keyword + locality FAQ block (not optional).

Return ONLY valid JSON (no markdown fences):
{{
  "meta": {{
    "title": "page title under 60 chars",
    "description": "meta description under 160 chars",
    "h1": "H1 plain text"
  }},
  "module_set_used": {json.dumps(module_set)},
  "modules": [
    {{"type": "A", "heading": "plain text or null", "body": "plain text / markdown paragraphs"}}
  ]
}}"""


def _strip_json_fences(raw: str) -> str:
    text = (raw or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def parse_generation_response(raw: str) -> dict[str, Any]:
    cleaned = _strip_json_fences(raw)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=502, detail=f"AI returned invalid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise HTTPException(status_code=502, detail="AI response was not a JSON object.")
    modules = data.get("modules")
    if not isinstance(modules, list) or not modules:
        raise HTTPException(status_code=502, detail="AI response missing modules array.")
    meta = data.get("meta") if isinstance(data.get("meta"), dict) else {}
    return {
        "meta": meta,
        "module_set_used": data.get("module_set_used") or [],
        "modules": normalize_modules(modules),
    }


def _plain_heading(text: str) -> str:
    """Strip HTML wrappers the model sometimes puts in heading fields."""
    t = (text or "").strip()
    if not t:
        return ""
    match = re.match(r"^<h[1-6][^>]*>(.*?)</h[1-6]>$", t, re.I | re.S)
    if match:
        t = match.group(1)
    return re.sub(r"<[^>]+>", "", t).strip()


def _html_body_to_markdown(body: str) -> str:
    """Convert AI HTML fragments in body to clean markdown (avoids raw tags on WordPress)."""
    b = (body or "").strip()
    if not b or "<" not in b:
        return b
    b = re.sub(r"^<h[1-6][^>]*>.*?</h[1-6]>\s*", "", b, count=1, flags=re.I | re.S)
    b = re.sub(r"<p[^>]*>", "", b, flags=re.I)
    b = re.sub(r"</p>", "\n\n", b, flags=re.I)
    b = re.sub(r"<br\s*/?>", "\n", b, flags=re.I)
    b = re.sub(r"<strong>(.*?)</strong>", r"**\1**", b, flags=re.I | re.S)
    b = re.sub(r"<b>(.*?)</b>", r"**\1**", b, flags=re.I | re.S)
    b = re.sub(r"<em>(.*?)</em>", r"*\1*", b, flags=re.I | re.S)
    b = re.sub(r"<li[^>]*>", "- ", b, flags=re.I)
    b = re.sub(r"</li>", "\n", b, flags=re.I)
    b = re.sub(r"</?ul[^>]*>", "\n", b, flags=re.I)
    b = re.sub(r"</?ol[^>]*>", "\n", b, flags=re.I)
    b = re.sub(r"<[^>]+>", "", b)
    b = re.sub(r"\n{3,}", "\n\n", b)
    return b.strip()


_PRESERVE_UPPER = frozenset({"SEO", "AI", "GBP", "ROI", "API", "CTA", "FAQ", "NAP"})


def _is_shouty_text(text: str) -> bool:
    letters = [c for c in text if c.isalpha()]
    if len(letters) < 12:
        return False
    return sum(1 for c in letters if c.isupper()) / len(letters) > 0.82


def _readable_case(text: str) -> str:
    """Convert SHOUTY CAPS lines to readable Title/sentence case; keep common acronyms."""
    raw = (text or "").strip()
    if not raw or not _is_shouty_text(raw):
        return raw
    parts = re.findall(r"\w+|\W+", raw.lower())
    out: list[str] = []
    for part in parts:
        if part.isalnum():
            if part.upper() in _PRESERVE_UPPER:
                out.append(part.upper())
            else:
                out.append(part.capitalize())
        else:
            out.append(part)
    return "".join(out)


def _unwrap_excessive_bold(text: str) -> str:
    """Remove ** when the model bolded whole paragraphs or long lines."""

    def repl(match: re.Match[str]) -> str:
        inner = match.group(1).strip()
        if len(inner) > 70 or inner.count(" ") >= 10:
            return inner
        return match.group(0)

    return re.sub(r"\*\*(.+?)\*\*", repl, text, flags=re.S)


def sanitize_module_body(body: str, *, module_type: str = "") -> str:
    """Normalize AI body text so WordPress does not publish shouty bold blocks."""
    mtype = (module_type or "").strip().upper()
    text = (body or "").strip()
    if not text:
        return text

    lines_out: list[str] = []
    for line in text.split("\n"):
        stripped = line.strip()
        if not stripped:
            lines_out.append("")
            continue

        if re.match(r"^#{2,6}\s+", stripped):
            stripped = re.sub(r"^#{2,6}\s+", "### ", stripped)

        if mtype != "M":
            bold_only = re.match(r"^\*\*(.+?)\*\*\s*$", stripped)
            if bold_only:
                label = bold_only.group(1).strip()
                if _is_shouty_text(label):
                    label = _readable_case(label)
                stripped = f"**{label}**"
            else:
                stripped = _unwrap_excessive_bold(stripped)
                if _is_shouty_text(stripped):
                    stripped = _readable_case(stripped)

        lines_out.append(stripped)

    cleaned = "\n".join(lines_out)
    if mtype != "M":
        cleaned = _unwrap_excessive_bold(cleaned)
        cleaned = _merge_bold_label_paragraphs(cleaned)
    return re.sub(r"\n{3,}", "\n\n", cleaned).strip()


def _merge_bold_label_paragraphs(text: str) -> str:
    """Turn standalone **Label** + next paragraph into one normal body line."""
    blocks = [b.strip() for b in re.split(r"\n\s*\n", text) if b.strip()]
    if not blocks:
        return text
    merged: list[str] = []
    i = 0
    while i < len(blocks):
        block = blocks[i]
        label_match = re.match(r"^\*\*(.+?)\*\*\s*$", block)
        if label_match and i + 1 < len(blocks):
            nxt = blocks[i + 1]
            if not re.match(r"^[-*#]", nxt) and not re.match(r"^\d+\.\s", nxt):
                merged.append(f"**{label_match.group(1).strip()}** — {nxt}")
                i += 2
                continue
        merged.append(block)
        i += 1
    return "\n\n".join(merged)


_FAQ_MARKER_START = "<!--RANKPILOT_FAQ-->"
_FAQ_MARKER_END = "<!--/RANKPILOT_FAQ-->"
_FAQ_MD_MARKER = "<!--RANKPILOT_FAQ_MD-->"
_FAQ_ACCENT = "#FF6B00"


def parse_faq_pairs(body: str) -> list[tuple[str, str]]:
    """Extract Q/A pairs from module M body (**Question?** then answer paragraph)."""
    text = (body or "").strip()
    if not text:
        return []
    pairs: list[tuple[str, str]] = []
    for chunk in re.split(r"\n(?=\*\*)", text):
        chunk = chunk.strip()
        if not chunk:
            continue
        match = re.match(r"^\*\*(.+?)\*\*\s*\n?([\s\S]*)$", chunk)
        if match:
            question = match.group(1).strip()
            answer = match.group(2).strip()
            if question:
                pairs.append((question, answer))
    return pairs


def _faq_title_html(heading: str) -> str:
    """Accent 'questions' / 'faq' or the last word — matches Clicktrends FAQ hero style."""
    import html as html_lib

    raw = (heading or "").strip()
    if not raw:
        return (
            'FREQUENTLY ASKED <span style="color:'
            + _FAQ_ACCENT
            + ';font-style:normal;">QUESTIONS</span>'
        )
    match = re.search(r"\b(questions?|faq)\b", raw, re.I)
    if match:
        before = html_lib.escape(raw[: match.start()])
        accent = html_lib.escape(match.group(0))
        after = html_lib.escape(raw[match.end() :])
        mid = f'<span style="color:{_FAQ_ACCENT};font-style:normal;">{accent}</span>'
        return f"{before}{mid}{after}".strip()
    words = raw.rsplit(" ", 1)
    if len(words) == 2:
        return (
            f'{html_lib.escape(words[0])} '
            f'<span style="color:{_FAQ_ACCENT};font-style:normal;">{html_lib.escape(words[1])}</span>'
        )
    return f'<span style="color:{_FAQ_ACCENT};font-style:normal;">{html_lib.escape(raw)}</span>'


def _faq_answer_html(answer: str) -> str:
    import html as html_lib

    text = (answer or "").strip()
    if not text:
        return ""
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    if not paras:
        return f"<p>{html_lib.escape(text)}</p>"
    return "".join(f"<p>{html_lib.escape(p)}</p>" for p in paras)


def faq_accordion_html(heading: str, pairs: list[tuple[str, str]]) -> str:
    """WordPress-ready FAQ accordion (+ toggle) — no images."""
    import html as html_lib

    if not pairs:
        return ""

    title_html = _faq_title_html(heading)
    items: list[str] = []
    for idx, (question, answer) in enumerate(pairs):
        open_attr = ' open' if idx == 0 else ""
        q_esc = html_lib.escape(question)
        a_html = _faq_answer_html(answer)
        items.append(
            f'<details class="rp-faq-item"{open_attr}>'
            f'<summary class="rp-faq-summary">'
            f'<span class="rp-faq-question">{q_esc}</span>'
            f'<span class="rp-faq-toggle" aria-hidden="true"></span>'
            f"</summary>"
            f'<div class="rp-faq-answer">{a_html}</div>'
            f"</details>"
        )

    block = f"""<section class="rankpilot-faq-accordion" aria-label="Frequently asked questions">
<style>
.rankpilot-faq-accordion{{max-width:920px;margin:2.5rem auto 2rem;font-family:inherit}}
.rankpilot-faq-accordion .rp-faq-heading{{text-align:center;font-size:clamp(1.15rem,2.8vw,1.85rem);font-weight:800;text-transform:uppercase;letter-spacing:.04em;line-height:1.25;margin:0 0 1.75rem;color:#111}}
.rankpilot-faq-accordion .rp-faq-item{{background:#fff;border-radius:14px;box-shadow:0 4px 22px rgba(0,0,0,.08);margin-bottom:1rem;overflow:hidden;transition:background .2s,box-shadow .2s,color .2s}}
.rankpilot-faq-accordion .rp-faq-item[open]{{background:{_FAQ_ACCENT};color:#fff;box-shadow:0 8px 28px rgba(255,107,0,.32)}}
.rankpilot-faq-accordion .rp-faq-summary{{display:flex;align-items:center;justify-content:space-between;gap:1rem;padding:1.2rem 1.4rem;cursor:pointer;list-style:none;font-weight:700;font-size:clamp(.9rem,2vw,1.05rem);line-height:1.35}}
.rankpilot-faq-accordion .rp-faq-summary::-webkit-details-marker{{display:none}}
.rankpilot-faq-accordion .rp-faq-summary::marker{{content:""}}
.rankpilot-faq-accordion .rp-faq-question{{flex:1;text-align:left}}
.rankpilot-faq-accordion .rp-faq-toggle{{flex-shrink:0;width:42px;height:42px;border-radius:50%;display:flex;align-items:center;justify-content:center;background:#1a1a1a;color:#fff;font-size:1.6rem;font-weight:400;line-height:1}}
.rankpilot-faq-accordion .rp-faq-toggle::before{{content:"+"}}
.rankpilot-faq-accordion .rp-faq-item[open] .rp-faq-toggle{{background:#fff;color:{_FAQ_ACCENT}}}
.rankpilot-faq-accordion .rp-faq-item[open] .rp-faq-toggle::before{{content:"−"}}
.rankpilot-faq-accordion .rp-faq-answer{{padding:0 1.4rem 1.25rem;font-size:.95rem;line-height:1.65;font-weight:400}}
.rankpilot-faq-accordion .rp-faq-answer p{{margin:0 0 .75rem}}
.rankpilot-faq-accordion .rp-faq-answer p:last-child{{margin-bottom:0}}
</style>
<h2 class="rp-faq-heading">{title_html}</h2>
{"".join(items)}
</section>"""
    return f"{_FAQ_MARKER_START}\n{block}\n{_FAQ_MARKER_END}"


def faq_markdown_sections_to_accordion(md: str) -> str:
    """Replace module-M markdown (marker + **Q/A** pairs) with accordion HTML blocks."""

    def _repl(match: re.Match[str]) -> str:
        heading = match.group(1).strip()
        body = match.group(2).strip()
        pairs = parse_faq_pairs(body)
        if not pairs:
            return match.group(0)
        accordion = faq_accordion_html(heading, pairs)
        return accordion or match.group(0)

    return re.sub(
        rf"^## ([^\n]+?)\n\n{_FAQ_MD_MARKER}\n(.*?)(?=\n## |\Z)",
        _repl,
        md,
        flags=re.M | re.S,
    )


def normalize_modules(modules: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for mod in modules:
        if not isinstance(mod, dict):
            continue
        cleaned = dict(mod)
        mtype = str(cleaned.get("type") or "").strip().upper()
        if cleaned.get("heading") is not None:
            heading = _plain_heading(str(cleaned.get("heading") or ""))
            cleaned["heading"] = _readable_case(heading) if heading else None
        if cleaned.get("body") is not None:
            body = _html_body_to_markdown(str(cleaned.get("body") or ""))
            cleaned["body"] = sanitize_module_body(body, module_type=mtype)
        out.append(cleaned)
    return out


def modules_to_markdown(modules: list[dict[str, Any]], *, h1: str | None = None) -> str:
    """Build WordPress-ready Markdown from modules (same format that worked before)."""
    parts: list[str] = []
    for mod in modules:
        mtype = str(mod.get("type") or "").strip().upper()
        heading = _plain_heading(str(mod.get("heading") or ""))
        body = str(mod.get("body") or "").strip()
        if not body and not heading and mtype != "A":
            continue

        if mtype == "A":
            title = _plain_heading(h1) if h1 else heading
            if title:
                parts.append(f"# {title}")
        elif mtype == "M":
            if heading and body:
                parts.append(f"## {heading}\n\n<!--RANKPILOT_FAQ_MD-->\n{body}")
            elif heading:
                parts.append(f"## {heading}")
            elif body:
                parts.append(body)
        else:
            if heading:
                parts.append(f"## {heading}")
            if body:
                parts.append(body)
    return "\n\n".join(parts)


def modules_to_html(modules: list[dict[str, Any]], *, h1: str | None = None) -> str:
    """Convert module JSON to HTML — headings are plain text, never double-wrapped."""
    import html as html_lib

    parts: list[str] = []
    for mod in modules:
        mtype = str(mod.get("type") or "").strip().upper()
        heading = _plain_heading(str(mod.get("heading") or ""))
        body = _html_body_to_markdown(str(mod.get("body") or ""))
        if not body and not heading:
            continue

        tag = "h1" if mtype == "A" else "h2"
        if mtype == "A" and h1:
            heading = _plain_heading(h1)

        if mtype == "M":
            faq_pairs = parse_faq_pairs(body)
            accordion = faq_accordion_html(heading, faq_pairs)
            if accordion:
                inner = accordion.replace(_FAQ_MARKER_START, "").replace(_FAQ_MARKER_END, "").strip()
                parts.append(inner)
                continue

        section = [f'<section class="rp-local-module" data-module-type="{html_lib.escape(mtype)}">']
        if heading:
            section.append(f"<{tag}>{html_lib.escape(heading)}</{tag}>")
        if body:
            if "<" in body[:200]:
                section.append(f'<div class="rp-module-body">{body}</div>')
            else:
                paras = [f"<p>{html_lib.escape(p.strip())}</p>" for p in re.split(r"\n\s*\n", body) if p.strip()]
                section.append(f'<div class="rp-module-body">{"".join(paras)}</div>')
        section.append("</section>")
        parts.append("\n".join(section))
    return "\n\n".join(parts)


def count_words_from_modules(modules: list[dict[str, Any]]) -> int:
    text = " ".join(str(m.get("heading") or "") + " " + str(m.get("body") or "") for m in modules)
    plain = re.sub(r"<[^>]+>", " ", text)
    return len([w for w in plain.split() if w])


def _openrouter_extract_text(data: dict) -> str:
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    first = choices[0] if isinstance(choices[0], dict) else {}
    msg = first.get("message") if isinstance(first, dict) else None
    if isinstance(msg, dict):
        content = msg.get("content")
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, dict):
                    txt = item.get("text")
                    if isinstance(txt, str) and txt.strip():
                        parts.append(txt.strip())
                elif isinstance(item, str) and item.strip():
                    parts.append(item.strip())
            if parts:
                return " ".join(parts).strip()
    txt = first.get("text") if isinstance(first, dict) else None
    if isinstance(txt, str) and txt.strip():
        return txt.strip()
    out = data.get("output_text")
    if isinstance(out, str) and out.strip():
        return out.strip()
    return ""


def _openrouter_error_message(data: dict) -> str:
    err = data.get("error")
    if isinstance(err, dict):
        msg = err.get("message")
        if isinstance(msg, str) and msg.strip():
            return msg.strip()
    return ""


async def call_openrouter_for_modules(
    *,
    prompt: str,
    api_key: str,
    referer: str,
    title_header: str = "RankPilot Local SEO Page",
    timeout: float = 120,
) -> tuple[str, str]:
    """Call OpenRouter and return (raw_text, model_used)."""
    import httpx  # noqa: PLC0415

    from app.core.config import get_openrouter_model  # noqa: PLC0415

    primary_model = get_openrouter_model()
    models = ["perplexity/sonar-pro", "perplexity/sonar"]
    if primary_model not in models:
        models.append(primary_model)

    last_error = "Unknown OpenRouter error"
    content_raw = ""
    used_model = primary_model
    for i, mdl in enumerate(models):
        used_model = mdl
        try:
            async with httpx.AsyncClient(timeout=timeout) as http:
                resp = await http.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                        "Accept": "application/json",
                        "HTTP-Referer": referer,
                        "X-Title": title_header,
                    },
                    json={
                        "model": mdl,
                        "messages": [
                            {
                                "role": "system",
                                "content": (
                                    "You are an expert local SEO copywriter for Clicktrends-style "
                                    "suburb landing pages. Return strict JSON only."
                                ),
                            },
                            {"role": "user", "content": prompt},
                        ],
                        "temperature": 0.55,
                        "max_tokens": 4500 if i == 0 else 3600,
                    },
                )
        except httpx.HTTPError as exc:
            last_error = f"OpenRouter request failed on model {mdl}: {exc}"
            continue

        if not resp.is_success:
            if resp.status_code == 401:
                raise HTTPException(
                    status_code=400,
                    detail="OpenRouter unauthorized (401). Check OPENROUTER_API_KEY in backend/.env.",
                )
            last_error = f"OpenRouter error ({resp.status_code}) on {mdl}: {resp.text[:220]}"
            continue

        data = resp.json() if isinstance(resp.json(), dict) else {}
        upstream_error = _openrouter_error_message(data if isinstance(data, dict) else {})
        if upstream_error:
            last_error = f"Upstream provider error on {mdl}: {upstream_error}"
            continue
        content_raw = _openrouter_extract_text(data if isinstance(data, dict) else {})
        if content_raw:
            return content_raw, used_model
        last_error = f"OpenRouter empty output on {mdl}"

    raise HTTPException(status_code=502, detail=f"Content generation failed: {last_error}")


def build_result_from_module_json(
    content_raw: str,
    *,
    keyword: str,
    module_set: list[str],
) -> dict[str, Any]:
    """Parse module JSON into title, excerpt, markdown, modules, counts."""
    parsed = parse_generation_response(content_raw)
    meta = parsed.get("meta") if isinstance(parsed.get("meta"), dict) else {}
    modules_raw = parsed.get("modules") if isinstance(parsed.get("modules"), list) else []
    modules = normalize_modules([m for m in modules_raw if isinstance(m, dict)])
    module_set_used = parsed.get("module_set_used") or module_set
    if not isinstance(module_set_used, list):
        module_set_used = module_set
    module_set_used = [str(x).upper() for x in module_set_used if x]

    h1 = str(meta.get("h1") or "").strip()
    title = str(meta.get("title") or h1 or keyword.title()).strip()
    if len(title) > 60:
        title = title[:60].rstrip()
    desc = str(meta.get("description") or "").strip()
    if len(desc) > 160:
        desc = desc[:160].rstrip()

    md_content = modules_to_markdown(modules, h1=h1 or None)
    if not md_content.strip():
        raise HTTPException(status_code=502, detail="AI returned modules but content conversion was empty.")

    return {
        "title": title,
        "excerpt": desc,
        "content": md_content,
        "modules": modules,
        "module_set_used": module_set_used,
        "word_count": count_words_from_modules(modules),
    }
