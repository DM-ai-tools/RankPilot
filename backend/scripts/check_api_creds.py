"""Quick credential check for DataForSEO + Ahrefs (no secrets printed)."""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

login = (os.getenv("DATAFORSEO_LOGIN") or "").strip().strip('"')
password = (os.getenv("DATAFORSEO_PASSWORD") or "").strip().strip('"')
ahrefs = (os.getenv("AHREFS_API_KEY") or "").strip().strip('"')


async def main() -> int:
    ok = True

    print("=== DataForSEO ===")
    if not login or not password:
        print("MISSING: DATAFORSEO_LOGIN / DATAFORSEO_PASSWORD in backend/.env")
        ok = False
    else:
        async with httpx.AsyncClient(auth=(login, password), timeout=30) as c:
            r = await c.get("https://api.dataforseo.com/v3/appendix/user_data")
            print(f"HTTP {r.status_code}")
            data = r.json()
            tasks = (data.get("tasks") or [{}])[0]
            sc = tasks.get("status_code")
            print(f"API status: {sc} — {tasks.get('status_message')}")
            if sc != 20000:
                ok = False
            else:
                result = tasks.get("result") or []
                u = result[0] if isinstance(result, list) and result else (result or {})
                money = u.get("money")
                if isinstance(money, dict):
                    bal = money.get("balance")
                    print(f"Account balance: ${bal}")
                    if bal is not None and float(bal) < 1:
                        print("WARNING: balance very low — scans may fail with HTTP 402")
                elif money is not None:
                    print(f"Account balance: ${money}")
                    if float(money) < 1:
                        print("WARNING: balance very low — scans may fail with HTTP 402")

    print("\n=== Ahrefs ===")
    if not ahrefs:
        print("MISSING: AHREFS_API_KEY in backend/.env")
        ok = False
    else:
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.get(
                "https://api.ahrefs.com/v3/keywords-explorer/overview",
                headers={"Authorization": f"Bearer {ahrefs}"},
                params={
                    "country": "au",
                    "keyword": "seo melbourne",
                    "select": "keyword,volume,difficulty",
                },
            )
            print(f"HTTP {r.status_code}")
            if r.status_code != 200:
                print(r.text[:400])
                ok = False
            else:
                kw = (r.json().get("keywords") or [{}])[0]
                print(
                    f"Test keyword OK — volume={kw.get('volume')}, kd={kw.get('difficulty')}"
                )

    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
