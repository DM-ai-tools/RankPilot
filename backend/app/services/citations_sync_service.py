"""Firecrawl-backed citations sync into rp_citations."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import quote_plus, urlparse
from uuid import UUID

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.services.google_places_new_client import display_name_text, place_details, places_search_text


@dataclass(frozen=True)
class DirectoryTarget:
    name: str
    url_template: str


DIRECTORIES: tuple[DirectoryTarget, ...] = (
    DirectoryTarget("TrueLocal", "https://www.truelocal.com.au/search?query={q}"),
    DirectoryTarget("Yelp AU", "https://www.yelp.com.au/search?find_desc={q}&find_loc={loc}"),
    DirectoryTarget("Yellow Pages AU", "https://www.yellowpages.com.au/search/listings?clue={q}&locationClue={loc}"),
    DirectoryTarget("Hotfrog AU", "https://www.hotfrog.com.au/search/{q}"),
    DirectoryTarget("Word of Mouth", "https://www.wordofmouth.com.au/search?query={q}"),
    DirectoryTarget("StartLocal", "https://www.startlocal.com.au/search.aspx?q={q}"),
    DirectoryTarget("dLook", "https://www.dlook.com.au/search/{q}"),
    DirectoryTarget("LocalSearch", "https://www.localsearch.com.au/search?what={q}&where={loc}"),
)


def _norm_host(url: str) -> str:
    raw = (url or "").strip()
    if not raw:
        return ""
    if not raw.startswith(("http://", "https://")):
        raw = "https://" + raw
    host = (urlparse(raw).netloc or "").lower()
    return re.sub(r"^www\.", "", host)


def _host_matches(expected: str, actual: str) -> bool:
    e = (expected or "").strip().lower()
    a = (actual or "").strip().lower()
    if not e or not a:
        return False
    if e == a:
        return True
    return e.endswith("." + a) or a.endswith("." + e)


def _norm_text(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").lower()).strip()


def _digits(s: str) -> str:
    return re.sub(r"\D+", "", s or "")


def _extract_phone(text: str) -> str:
    # Keep it simple/robust for AU formats (+61, landline/mobile with spaces).
    m = re.search(r"(\+?\d[\d\-\s\(\)]{7,}\d)", text or "")
    if not m:
        return ""
    val = re.sub(r"\s+", " ", m.group(1)).strip()
    return val if len(_digits(val)) >= 8 else ""


def _extract_address(text: str) -> str:
    # Prefer explicit AU-like address lines with state + postcode.
    patterns = [
        r"\b\d{1,6}\s+[A-Za-z0-9 .'-]+(?:Street|St|Road|Rd|Avenue|Ave|Boulevard|Blvd|Drive|Dr|Lane|Ln|Way|Place|Pl|Court|Ct|Terrace|Tce)\b[^\n]{0,120}\b(?:NSW|VIC|QLD|WA|SA|TAS|ACT|NT)\s*\d{4}\b",
        r"\b[A-Za-z0-9 .'-]{3,120}\b(?:NSW|VIC|QLD|WA|SA|TAS|ACT|NT)\s*\d{4}\b",
    ]
    for p in patterns:
        m = re.search(p, text or "", flags=re.IGNORECASE)
        if m:
            return re.sub(r"\s+", " ", m.group(0)).strip(" ,.;")
    return ""


def _extract_business_name(md: str, canonical_name_n: str) -> str:
    """
    Try to find the listed business name on the directory page.
    Strategy: look for the canonical name first; if found verbatim, return it.
    Otherwise grab the first heading-like line (# or ## markdown) that is nearby.
    """
    txt = md or ""
    norm = _norm_text(txt)
    if canonical_name_n and canonical_name_n in norm:
        # Find the original-case version around where the match is
        idx = norm.find(canonical_name_n)
        return txt[idx : idx + len(canonical_name_n)].strip()
    # Grab first H1 / H2 heading as fallback
    for line in txt.splitlines():
        stripped = line.lstrip("#").strip()
        if stripped and len(stripped) < 120:
            return stripped
    return ""


def _addr_token(addr: str) -> str:
    parts = re.split(r"[,;]", _norm_text(addr))
    return (parts[0] or "").strip() if parts else ""


def _mk_url(t: DirectoryTarget, business: str, metro: str) -> str:
    q = quote_plus(business.strip())
    loc = quote_plus(metro.split(",")[0].strip() if metro else "")
    return t.url_template.format(q=q, loc=loc)


async def _firecrawl_scrape(url: str, api_key: str) -> str:
    payload = {"url": url, "formats": ["markdown"]}
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=45) as c:
        r = await c.post("https://api.firecrawl.dev/v1/scrape", json=payload, headers=headers)
        r.raise_for_status()
        data = r.json()
    if not bool(data.get("success", True)):
        return ""
    d = data.get("data") or {}
    return str(d.get("markdown") or d.get("content") or "")


async def _google_places_nap(
    business_name: str,
    business_url: str,
    metro: str,
    api_key: str,
) -> dict | None:
    """Resolve canonical NAP from Google Places (New API), prioritising website-host match."""
    host_target = _norm_host(business_url)
    queries: list[str] = []
    if business_name.strip():
        queries.append(f"{business_name.strip()} {metro.strip()}".strip())
    if host_target:
        queries.append(f"{host_target} {metro.strip()}".strip())
        queries.append(host_target)
    if business_name.strip():
        queries.append(business_name.strip())

    async with httpx.AsyncClient(timeout=30) as c:
        candidates: list[dict] = []
        seen_place_ids: set[str] = set()
        for query in queries:
            if not query:
                continue
            try:
                rows = await places_search_text(c, api_key, query, page_size=10)
            except httpx.HTTPStatusError:
                continue
            for row in rows[:5]:
                pid = str(row.get("id") or "").strip()
                if not pid or pid in seen_place_ids:
                    continue
                seen_place_ids.add(pid)
                candidates.append(row)
        if not candidates:
            return None

        best: dict | None = None
        best_score = -1
        for cand in candidates[:10]:
            pid = str(cand.get("id") or "").strip()
            if not pid:
                continue
            try:
                details = await place_details(c, api_key, pid)
            except httpx.HTTPStatusError:
                continue
            if not isinstance(details, dict):
                continue
            nm = display_name_text(details) or display_name_text(cand)
            website = str(details.get("websiteUri") or "").strip()
            addr = str(details.get("formattedAddress") or cand.get("formattedAddress") or "").strip()
            phone = str(
                details.get("internationalPhoneNumber")
                or details.get("nationalPhoneNumber")
                or ""
            ).strip()
            site_host = _norm_host(website)
            if host_target and _host_matches(host_target, site_host):
                return {"name": nm, "address": addr, "phone": phone, "website": website}
            score = 0
            if _norm_text(nm) and (
                _norm_text(nm) in _norm_text(business_name)
                or _norm_text(business_name) in _norm_text(nm)
            ):
                score += 2
            if addr:
                score += 1
            if phone:
                score += 1
            if score > best_score:
                best_score = score
                best = {"name": nm, "address": addr, "phone": phone, "website": website}
        # If URL exists but no host match was found, avoid ambiguous business details.
        if host_target:
            return None
        return best


async def _website_nap_from_firecrawl(url: str, api_key: str) -> dict:
    try:
        md = await _firecrawl_scrape(url, api_key)
    except Exception:
        return {"address": "", "phone": ""}
    txt = re.sub(r"\s+", " ", md or " ").strip()
    return {"address": _extract_address(txt), "phone": _extract_phone(txt)}


async def sync_citations_for_client(session: AsyncSession, client_id: UUID) -> dict:
    settings = get_settings()
    crawl_api_key = (settings.firecrawl_api_key or "").strip()
    if not crawl_api_key:
        return {"updated": 0, "error": "FIRECRAWL_API_KEY is not set in backend/.env"}

    row = (
        await session.execute(
            text(
                """
                SELECT business_name, business_url, business_address, business_phone, metro_label
                FROM rp_clients
                WHERE client_id = :cid
                """
            ),
            {"cid": str(client_id)},
        )
    ).mappings().first()
    if not row:
        return {"updated": 0, "error": "Client not found"}

    bname = str(row.get("business_name") or "").strip()
    burl = str(row.get("business_url") or "").strip()
    baddr = str(row.get("business_address") or "").strip()
    bphone = str(row.get("business_phone") or "").strip()
    metro = str(row.get("metro_label") or "").strip()
    if not bname:
        return {"updated": 0, "error": "Missing business_name"}

    canonical_name = bname
    canonical_addr = baddr
    canonical_phone = bphone
    warnings: list[str] = []
    source = "profile"
    if (settings.google_places_api_key or "").strip():
        try:
            gnap = await _google_places_nap(
                business_name=bname,
                business_url=burl,
                metro=metro,
                api_key=settings.google_places_api_key.strip(),
            )
            if gnap:
                canonical_name = str(gnap.get("name") or canonical_name).strip() or canonical_name
                canonical_addr = str(gnap.get("address") or canonical_addr).strip() or canonical_addr
                canonical_phone = str(gnap.get("phone") or canonical_phone).strip() or canonical_phone
                source = "google_places"
            elif _norm_host(burl):
                warnings.append("Google Places: no place matched your business website URL")
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"Google Places: {exc!s}")

    # Fallback to Firecrawl website extraction when Google cannot resolve URL-matched place.
    if (not canonical_addr or not canonical_phone) and burl:
        website_nap = await _website_nap_from_firecrawl(burl, crawl_api_key)
        if not canonical_addr and website_nap.get("address"):
            canonical_addr = str(website_nap["address"]).strip()
        if not canonical_phone and website_nap.get("phone"):
            canonical_phone = str(website_nap["phone"]).strip()
        if (website_nap.get("address") or website_nap.get("phone")) and source != "google_places":
            source = "firecrawl_website"

    # Persist canonical address/phone so citation page can display real NAP without onboarding inputs.
    await session.execute(
        text(
            """
            UPDATE rp_clients
            SET business_address = :addr,
                business_phone = :phone,
                updated_at = now()
            WHERE client_id = :cid
            """
        ),
        {"cid": str(client_id), "addr": canonical_addr, "phone": canonical_phone},
    )

    host = _norm_host(burl)
    bname_n = _norm_text(canonical_name)
    baddr_n = _addr_token(canonical_addr)
    phone_digits = _digits(canonical_phone)
    now = datetime.now(UTC)
    updates = 0

    import json as _json

    for d in DIRECTORIES:
        target_url = _mk_url(d, bname, metro)
        try:
            md = await _firecrawl_scrape(target_url, crawl_api_key)
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"{d.name}: {exc!s}")
            md = ""
        txt = _norm_text(md)

        # ── Extract what was actually found on this directory page ───────────
        scraped_name  = _extract_business_name(md, bname_n)
        scraped_addr  = _extract_address(md)
        scraped_phone = _extract_phone(md)

        has_name  = bool(bname_n and bname_n in txt)
        has_host  = bool(host and host in txt)
        has_addr  = bool(baddr_n and baddr_n in txt)
        has_phone = bool(phone_digits and phone_digits in _digits(txt))

        if has_name and (has_host or not host) and (has_addr or not baddr_n) and (has_phone or not phone_digits):
            status = "consistent"
            drift  = False
        elif has_name or has_host or has_addr or has_phone:
            status = "inconsistent"
            drift  = True
        else:
            status = "missing"
            drift  = False

        # Build the structured scraped snapshot
        scraped_nap = {
            "name":       scraped_name or None,
            "address":    scraped_addr or None,
            "phone":      scraped_phone or None,
            "name_ok":    has_name,
            "address_ok": has_addr,
            "phone_ok":   has_phone,
        }

        nap_hash = hashlib.sha256(
            f"{d.name}|{status}|{int(drift)}|{has_name}|{has_host}|{has_addr}|{has_phone}".encode()
        ).hexdigest()

        await session.execute(
            text(
                """
                INSERT INTO rp_citations
                    (id, client_id, directory, status, nap_hash, drift_flag,
                     scraped_nap, last_checked, created_at, updated_at)
                VALUES
                    (gen_random_uuid(), :cid, :dir, :status, :nap, :drift,
                     :scraped_nap, :ts, :ts, :ts)
                ON CONFLICT (client_id, directory)
                DO UPDATE SET
                    status      = EXCLUDED.status,
                    nap_hash    = EXCLUDED.nap_hash,
                    drift_flag  = EXCLUDED.drift_flag,
                    scraped_nap = EXCLUDED.scraped_nap,
                    last_checked = EXCLUDED.last_checked,
                    updated_at  = now()
                """
            ),
            {
                "cid":         str(client_id),
                "dir":         d.name,
                "status":      status,
                "nap":         nap_hash,
                "drift":       drift,
                "scraped_nap": _json.dumps(scraped_nap),
                "ts":          now,
            },
        )
        updates += 1

    return {
        "updated": updates,
        "warnings": warnings,
        "canonical": {
            "name":    canonical_name,
            "address": canonical_addr,
            "phone":   canonical_phone,
            "source":  source,
        },
    }

