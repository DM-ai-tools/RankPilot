"""One-off: verify GOOGLE_PLACES_API_KEY — uses Places API (New), same as the app."""
from __future__ import annotations

import asyncio
import sys

import httpx

from app.core.config import get_settings
from app.services.google_places_new_client import places_search_text


async def main() -> int:
    s = get_settings()
    k = (s.google_places_api_key or "").strip()
    if not k:
        print("GOOGLE_PLACES_API_KEY: NOT SET (empty after load from backend/.env)")
        return 1
    print(f"GOOGLE_PLACES_API_KEY: loaded ({len(k)} chars, value not printed)")
    try:
        async with httpx.AsyncClient(timeout=25.0) as c:
            places = await places_search_text(c, k, "coffee shop Sydney NSW Australia", page_size=3)
    except httpx.HTTPStatusError as exc:
        print("HTTP error:", exc.response.status_code)
        try:
            print(exc.response.text[:500])
        except Exception:
            pass
        return 1
    except Exception as exc:
        print("Request failed:", type(exc).__name__, str(exc)[:200])
        return 1
    print("Places API (New) searchText: OK")
    print("results count:", len(places))
    if places:
        p0 = places[0]
        print("first id:", str(p0.get("id") or "")[:24] + ("…" if len(str(p0.get("id") or "")) > 24 else ""))
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
