"""Google Ads API — Keyword Planner ideas for the tenant primary keyword."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.services.content_generation_service import _get_client_profile

logger = logging.getLogger(__name__)

# Common AU geo targets (Google Ads API geoTargetConstants).
_AU_GEO_BY_CITY: dict[str, str] = {
    "sydney": "geoTargetConstants/1000287",
    "melbourne": "geoTargetConstants/1000286",
    "brisbane": "geoTargetConstants/1000289",
    "perth": "geoTargetConstants/1000290",
    "adelaide": "geoTargetConstants/1000291",
    "canberra": "geoTargetConstants/1000288",
    "hobart": "geoTargetConstants/1000292",
    "darwin": "geoTargetConstants/1000294",
    "gold coast": "geoTargetConstants/1000293",
    "newcastle": "geoTargetConstants/1000295",
}
_DEFAULT_GEO_AU = "geoTargetConstants/2036"
_LANG_EN = "languageConstants/1000"


def _geo_for_metro(metro_label: str) -> str:
    s = (metro_label or "").lower()
    for key, geo in _AU_GEO_BY_CITY.items():
        if key in s:
            return geo
    return _DEFAULT_GEO_AU


def _ads_client(refresh_token: str):
    settings = get_settings()
    dev = (settings.google_ads_developer_token or "").strip()
    if not dev:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "GOOGLE_ADS_DEVELOPER_TOKEN is not set. Apply for a developer token in Google Ads "
                "(Tools → API Center) and add it to backend/.env, then restart the API."
            ),
        )
    if not settings.google_client_id or not settings.google_client_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET missing in backend/.env",
        )
    login_cid = re.sub(r"\D", "", settings.google_ads_login_customer_id or "")
    cfg: dict[str, Any] = {
        "developer_token": dev,
        "client_id": settings.google_client_id,
        "client_secret": settings.google_client_secret,
        "refresh_token": refresh_token,
        "use_proto_plus": True,
    }
    if login_cid:
        cfg["login_customer_id"] = login_cid
    try:
        from google.ads.googleads.client import GoogleAdsClient
    except ImportError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="google-ads package not installed. Run: pip install google-ads",
        ) from exc
    return GoogleAdsClient.load_from_dict(cfg)


def _google_ads_error_detail(exc: Exception) -> str:
    msg = str(exc)
    if "DEVELOPER_TOKEN" in msg.upper() or "developer token" in msg.lower():
        return (
            f"{msg} — Check GOOGLE_ADS_DEVELOPER_TOKEN in backend/.env and that the token is approved "
            "(test tokens only work on test accounts)."
        )
    if "CUSTOMER_NOT_FOUND" in msg or "USER_PERMISSION_DENIED" in msg:
        return (
            f"{msg} — Reconnect Google Ads and select the correct customer ID. "
            "Set GOOGLE_ADS_LOGIN_CUSTOMER_ID to your MCC if you manage client accounts."
        )
    if "API has not been used" in msg or "disabled" in msg.lower():
        return (
            f"{msg} — Enable Google Ads API in Google Cloud Console → APIs & Services → Library."
        )
    return msg


async def _integration_row(session: AsyncSession, client_id: UUID, intg_type: str) -> dict[str, Any] | None:
    row = (
        await session.execute(
            text(
                """
                SELECT access_token, refresh_token, token_expiry, extra_data
                FROM rp_integrations
                WHERE client_id = :cid AND type = :type
                """
            ),
            {"cid": str(client_id), "type": intg_type},
        )
    ).mappings().first()
    return dict(row) if row else None


async def get_setup_status(session: AsyncSession, client_id: UUID) -> dict[str, Any]:
    settings = get_settings()
    row = await _integration_row(session, client_id, "google_ads")
    extra = (row or {}).get("extra_data") or {}
    if isinstance(extra, str):
        import json

        try:
            extra = json.loads(extra)
        except json.JSONDecodeError:
            extra = {}
    return {
        "oauth_configured": bool(settings.google_client_id and settings.google_client_secret),
        "developer_token_configured": bool((settings.google_ads_developer_token or "").strip()),
        "login_customer_configured": bool((settings.google_ads_login_customer_id or "").strip()),
        "connected": row is not None and bool(row.get("refresh_token") or row.get("access_token")),
        "customer_id": str(extra.get("customer_id") or ""),
        "customer_name": str(extra.get("customer_name") or ""),
    }


def _list_customers_sync(refresh_token: str) -> list[dict[str, str]]:
    client = _ads_client(refresh_token)
    service = client.get_service("CustomerService")
    response = service.list_accessible_customers()
    items: list[dict[str, str]] = []
    for resource in response.resource_names:
        cid = resource.split("/")[-1] if "/" in resource else resource
        cid = re.sub(r"\D", "", cid)
        if cid:
            items.append({"customer_id": cid, "resource_name": resource})
    return items


def _generate_ideas_sync(
    refresh_token: str,
    customer_id: str,
    seed_keyword: str,
    metro_label: str,
    *,
    limit: int = 40,
) -> list[dict[str, Any]]:
    client = _ads_client(refresh_token)
    cid = re.sub(r"\D", "", customer_id)
    idea_service = client.get_service("KeywordPlanIdeaService")
    request = client.get_type("GenerateKeywordIdeasRequest")
    request.customer_id = cid
    request.language = _LANG_EN
    request.geo_target_constants.append(_geo_for_metro(metro_label))
    request.keyword_seed.keywords.append(seed_keyword.strip())
    request.include_adult_keywords = False
    request.keyword_plan_network = client.enums.KeywordPlanNetworkEnum.GOOGLE_SEARCH

    items: list[dict[str, Any]] = []
    for idea in idea_service.generate_keyword_ideas(request=request):
        metrics = idea.keyword_idea_metrics
        if not metrics:
            continue
        items.append(
            {
                "keyword": str(idea.text or "").strip(),
                "avg_monthly_searches": int(metrics.avg_monthly_searches or 0),
                "competition": metrics.competition.name if metrics.competition else None,
                "competition_index": int(metrics.competition_index or 0),
                "low_top_of_page_bid_micros": int(metrics.low_top_of_page_bid_micros or 0),
                "high_top_of_page_bid_micros": int(metrics.high_top_of_page_bid_micros or 0),
            }
        )
        if len(items) >= limit:
            break
    items.sort(key=lambda x: x.get("avg_monthly_searches") or 0, reverse=True)
    return items


async def list_google_ads_customers(session: AsyncSession, client_id: UUID) -> dict[str, Any]:
    from app.routes.v1.integrations import _get_google_access_token

    await _get_google_access_token(session, client_id, "google_ads")
    row = await _integration_row(session, client_id, "google_ads")
    if not row or not row.get("refresh_token"):
        raise HTTPException(status_code=400, detail="Google Ads not connected")
    try:
        items = await asyncio.to_thread(_list_customers_sync, str(row["refresh_token"]))
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Google Ads list customers failed")
        raise HTTPException(status_code=502, detail=_google_ads_error_detail(exc)) from exc
    return {"items": items}


async def select_google_ads_customer(
    session: AsyncSession,
    client_id: UUID,
    customer_id: str,
    customer_name: str | None = None,
) -> dict[str, Any]:
    cid = re.sub(r"\D", "", customer_id)
    if not cid:
        raise HTTPException(status_code=400, detail="customer_id required")
    extra: dict[str, str] = {"customer_id": cid}
    if customer_name:
        extra["customer_name"] = customer_name
    await session.execute(
        text(
            """
            UPDATE rp_integrations
            SET extra_data = COALESCE(extra_data, '{}'::jsonb) || (CAST(:extra AS text))::jsonb,
                updated_at = now()
            WHERE client_id = :cid AND type = 'google_ads'
            """
        ),
        {"extra": json.dumps(extra), "cid": str(client_id)},
    )
    return {"selected": True, "customer_id": cid}


async def _resolve_customer_id(session: AsyncSession, client_id: UUID, refresh_token: str) -> str:
    row = await _integration_row(session, client_id, "google_ads")
    extra = (row or {}).get("extra_data") or {}
    if isinstance(extra, str):
        import json

        try:
            extra = json.loads(extra)
        except json.JSONDecodeError:
            extra = {}
    cid = re.sub(r"\D", "", str(extra.get("customer_id") or ""))
    if cid:
        return cid
    customers = await asyncio.to_thread(_list_customers_sync, refresh_token)
    if len(customers) == 1:
        cid = customers[0]["customer_id"]
        await select_google_ads_customer(session, client_id, cid)
        return cid
    if not customers:
        raise HTTPException(
            status_code=400,
            detail="No accessible Google Ads accounts. Use an account with Ads access.",
        )
    raise HTTPException(
        status_code=400,
        detail="Select a Google Ads account in onboarding (Connect → Google Ads → choose account).",
    )


async def fetch_keyword_ideas(
    session: AsyncSession,
    client_id: UUID,
    *,
    seed_keyword: str | None = None,
    limit: int = 40,
) -> dict[str, Any]:
    from app.routes.v1.integrations import _get_google_access_token

    profile = await _get_client_profile(session, client_id)
    seed = (seed_keyword or profile.get("primary_keyword") or "").strip()
    metro = str(profile.get("metro_label") or "").strip()
    if not seed:
        raise HTTPException(status_code=400, detail="Set a primary keyword in onboarding first.")

    setup = await get_setup_status(session, client_id)
    if not setup["connected"]:
        return {
            **setup,
            "seed_keyword": seed,
            "metro_label": metro,
            "items": [],
            "message": "Connect Google Ads in onboarding to load Keyword Planner ideas.",
        }

    refresh_token = await _get_google_access_token(session, client_id, "google_ads")
    row = await _integration_row(session, client_id, "google_ads")
    rt = str((row or {}).get("refresh_token") or refresh_token)

    try:
        customer_id = await _resolve_customer_id(session, client_id, rt)
        items = await asyncio.to_thread(
            _generate_ideas_sync, rt, customer_id, seed, metro, limit=limit
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Google Ads keyword ideas failed")
        raise HTTPException(status_code=502, detail=_google_ads_error_detail(exc)) from exc

    return {
        **setup,
        "seed_keyword": seed,
        "metro_label": metro,
        "geo_target": _geo_for_metro(metro),
        "customer_id": customer_id,
        "items": items,
        "source": "google_ads_keyword_plan_ideas",
        "message": None,
    }
