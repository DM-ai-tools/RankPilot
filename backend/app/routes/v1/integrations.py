"""
OAuth 2.0 + WordPress integration endpoints.

Google OAuth flow (GSC / GBP / GA4):
  1. Frontend calls GET /api/v1/integrations/google/auth-url?type=gsc
  2. Backend returns a Google OAuth URL with signed `state`.
  3. Frontend opens URL in a popup window.
  4. User grants permissions on Google.
  5. Google redirects to GET /api/v1/integrations/google/callback?code=…&state=…
  6. Backend exchanges code for tokens, stores in rp_integrations.
  7. Callback returns a minimal HTML page that calls window.opener.postMessage
     and closes the popup — the onboarding page updates its connected state.

WordPress flow:
  POST /api/v1/integrations/wordpress
  { site_url, username, app_password }
  Backend verifies credentials against the WP REST API, then stores them.
"""

from __future__ import annotations

import base64
import contextlib
import html
import hashlib
import hmac
import json
import re
import time
import urllib.parse
from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

import httpx
from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy import text

from app.core.config import (
    Settings,
    get_openrouter_api_key,
    get_openrouter_model,
    get_settings,
)
from app.deps import CurrentClientId, DbSession, OAuthCallbackDbSession

router = APIRouter()


def _cfg() -> Settings:
    """Fresh settings each call (uvicorn --reload picks up .env changes)."""
    return get_settings()

# ── Google OAuth scopes per integration type ───────────────────────────
GOOGLE_SCOPES: dict[str, str] = {
    "gsc": "https://www.googleapis.com/auth/webmasters.readonly",
    "gbp": "https://www.googleapis.com/auth/business.manage",
    "ga4": "https://www.googleapis.com/auth/analytics.readonly",
    "google_ads": "https://www.googleapis.com/auth/adwords",
}

GOOGLE_TOKEN_URL  = "https://oauth2.googleapis.com/token"
GOOGLE_AUTH_URL   = "https://accounts.google.com/o/oauth2/v2/auth"
GSC_SITES_URL     = "https://www.googleapis.com/webmasters/v3/sites"
GA4_SUMMARY_URL   = "https://analyticsadmin.googleapis.com/v1beta/accountSummaries?pageSize=200"
GBP_ACCOUNTS_URL  = "https://mybusinessaccountmanagement.googleapis.com/v1/accounts"
# Business Information API requires readMask on locations list (else INVALID_ARGUMENT).
GBP_LOCATIONS_READ_MASK = "name,title,storefrontAddress"
GBP_SETUP_DOC = "docs/GBP_API_SETUP.md"
GBP_PREREQS_URL = "https://developers.google.com/my-business/content/prereqs#request-access"


def _gbp_google_error_detail(message: str, *, context: str) -> str:
    """Turn Google API error text into actionable RankPilot guidance."""
    low = (message or "").lower()
    if "service is disabled" in low or "has not been used" in low or "accessnotconfigured" in low:
        return (
            f"{context}: enable My Business Account Management and Business Information APIs "
            f"in Google Cloud Console (Library). If already enabled, your project may not have "
            f"GBP API access yet — request Basic API Access: {GBP_PREREQS_URL} "
            f"(see {GBP_SETUP_DOC})."
        )
    if "invalid argument" in low:
        return (
            f"{context}: invalid request to Google (often missing API enablement or 0 QPM quota). "
            f"See {GBP_SETUP_DOC} and {GBP_PREREQS_URL}."
        )
    if "quota" in low or "rate limit" in low or "resource_exhausted" in low:
        return (
            f"{context}: GBP API quota may be 0 until Google approves your project (300 QPM when approved). "
            f"See {GBP_PREREQS_URL}."
        )
    if "insufficient authentication scopes" in low or "insufficient permissions" in low:
        return (
            f"{context}: reconnect GBP with the Google account that owns or manages the Business Profile."
        )
    if "permission_denied" in low or "forbidden" in low:
        return (
            f"{context}: {message}. Confirm GBP API access is approved for this Cloud project ({GBP_PREREQS_URL})."
        )
    if ("request" in low and "access" in low) or "has not been granted" in low:
        return (
            f"{context}: Your Google Cloud project can update descriptions (Business Information API) "
            f"but photo upload uses Google's Media API, which needs separate approval. "
            f"Request Basic API Access: {GBP_PREREQS_URL} — enable **Google My Business API** in Cloud Console "
            f"after approval. Until then, upload photos at business.google.com."
        )
    return f"{context}: {message}" if message else context


def _gbp_media_error_detail(message: str, *, context: str) -> str:
    """Photo/media errors — pass through Google text; do not imply GBP is disconnected."""
    raw = (message or "").strip()
    low = raw.lower()
    if "fetching image failed" in low or "fetching image" in low:
        return (
            f"{context}: {raw} "
            "Google could not read the uploaded bytes (common in local dev). "
            "AI-generated photos: delete and re-generate, then Publish (uses Runway's public URL). "
            "Uploaded files: enable **Google My Business API** in Cloud Console, or run "
            "`ngrok http 8000` and set PUBLIC_API_BASE_URL to the https URL in backend/.env."
        )
    if "service is disabled" in low or "has not been used" in low or "accessnotconfigured" in low:
        return (
            f"{context}: enable **Google My Business API** (mybusiness.googleapis.com) in Cloud Console → Library. "
            f"GBP account connection uses a different API (Business Information). See {GBP_SETUP_DOC}."
        )
    if "invalid argument" in low and raw:
        return f"{context}: {raw}"
    return _gbp_google_error_detail(message, context=context)


# ── State HMAC helpers ─────────────────────────────────────────────────

def _sign_state(payload: str) -> str:
    """Return base64(payload):base64(hmac-sha256)."""
    secret = (_cfg().jwt_secret_key or "rankpilot-dev").encode()
    sig    = hmac.new(secret, payload.encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(payload.encode()).decode() + "." + base64.urlsafe_b64encode(sig).decode()


def _verify_state(state: str) -> dict:
    """Raise if state is tampered; return the decoded payload dict."""
    try:
        enc_payload, enc_sig = state.split(".", 1)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid state")
    payload_bytes = base64.urlsafe_b64decode(enc_payload)
    secret        = (_cfg().jwt_secret_key or "rankpilot-dev").encode()
    expected_sig  = hmac.new(secret, payload_bytes, hashlib.sha256).digest()
    if not hmac.compare_digest(base64.urlsafe_b64decode(enc_sig), expected_sig):
        raise HTTPException(status_code=400, detail="State signature mismatch")
    data = json.loads(payload_bytes)
    if time.time() - data.get("ts", 0) > 600:
        raise HTTPException(status_code=400, detail="State expired")
    return data


# ── Helpers ────────────────────────────────────────────────────────────

_GOOGLE_OAUTH_CALLBACK_PATH = "/api/v1/integrations/google/callback"


def _redirect_uri() -> str:
    """OAuth redirect URI sent to Google (must match Cloud Console exactly)."""
    base = (_cfg().google_redirect_base_url or "http://localhost:8000").strip().rstrip("/")
    # Accept either base URL or full callback URL in GOOGLE_REDIRECT_BASE_URL.
    if base.endswith(_GOOGLE_OAUTH_CALLBACK_PATH):
        return base
    return f"{base}{_GOOGLE_OAUTH_CALLBACK_PATH}"


def _popup_result_html(success: bool, integration_type: str, error: str = "") -> str:
    """Tiny HTML page that notifies the opener and closes the popup."""
    msg = json.dumps({"rankpilot_oauth": True, "type": integration_type, "success": success, "error": error})
    return f"""<!doctype html>
<html>
<head><title>Connecting…</title></head>
<body style="font-family:sans-serif;display:flex;align-items:center;justify-content:center;min-height:100vh;background:#F4F7FB;">
<div style="text-align:center;">
  <div style="font-size:48px;">{'✅' if success else '❌'}</div>
  <p style="font-size:14px;color:#0B2545;">{'Connected successfully! Closing window…' if success else f'Connection failed: {error}'}</p>
</div>
<script>
  try {{ window.opener.postMessage({msg}, "*"); }} catch(e) {{}}
  setTimeout(function(){{ window.close(); }}, 1200);
</script>
</body></html>"""


async def _get_integration_row(session: DbSession, client_id: UUID, intg_type: str):
    row = (
        await session.execute(
            text(
                """
                SELECT access_token, refresh_token, token_expiry, extra_data
                FROM rp_integrations
                WHERE client_id = :cid AND type = :type
                LIMIT 1
                """
            ),
            {"cid": str(client_id), "type": intg_type},
        )
    ).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail=f"{intg_type.upper()} is not connected")
    return row


async def _get_google_access_token(session: DbSession, client_id: UUID, intg_type: str) -> str:
    row = await _get_integration_row(session, client_id, intg_type)
    access_token = str(row.get("access_token") or "")
    refresh_token = str(row.get("refresh_token") or "")
    expiry = row.get("token_expiry")
    now_ts = datetime.now(timezone.utc)
    still_valid = bool(access_token) and (expiry is None or expiry > now_ts)
    if still_valid:
        return access_token
    if not refresh_token:
        # 403 not 401 — frontend treats 401 as RankPilot session invalid and redirects to login.
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"{intg_type.upper()} token expired; reconnect required",
        )
    if not _cfg().google_client_id or not _cfg().google_client_secret:
        raise HTTPException(status_code=503, detail="Google OAuth credentials missing in backend/.env")
    async with httpx.AsyncClient(timeout=15) as http:
        resp = await http.post(
            GOOGLE_TOKEN_URL,
            data={
                "client_id": _cfg().google_client_id,
                "client_secret": _cfg().google_client_secret,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
        )
    if not resp.is_success:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Failed to refresh {intg_type.upper()} token; disconnect and reconnect in onboarding.",
        )
    token_payload = resp.json()
    new_access = str(token_payload.get("access_token") or "")
    expires_in = int(token_payload.get("expires_in") or 3600)
    new_expiry = datetime.fromtimestamp(time.time() + expires_in, tz=timezone.utc)
    await session.execute(
        text(
            """
            UPDATE rp_integrations
            SET access_token = :at, token_expiry = :exp, updated_at = now()
            WHERE client_id = :cid AND type = :type
            """
        ),
        {"at": new_access, "exp": new_expiry, "cid": str(client_id), "type": intg_type},
    )
    return new_access


# ═══════════════════════════════════════════════════════════════════════
# STATUS — which integrations are connected for the current client
# ═══════════════════════════════════════════════════════════════════════

@router.get("/integrations/status")
async def get_status(client_id: CurrentClientId, session: DbSession) -> dict:
    rows = (
        await session.execute(
            text(
                """
                SELECT type, connected_at, extra_data
                FROM rp_integrations
                WHERE client_id = :cid
                """
            ),
            {"cid": str(client_id)},
        )
    ).mappings().all()

    result: dict[str, dict] = {}
    for r in rows:
        extra = r["extra_data"] if isinstance(r["extra_data"], dict) else {}
        if isinstance(r["extra_data"], str):
            with contextlib.suppress(json.JSONDecodeError):
                extra = json.loads(r["extra_data"])
        location_selected = bool(
            str(extra.get("selected_property") or extra.get("customer_id") or "").strip()
        )
        result[r["type"]] = {
            "connected": True,
            "connected_at": r["connected_at"].isoformat() if r["connected_at"] else None,
            "extra": extra,
            "location_selected": location_selected,
            "ready": location_selected if r["type"] in ("gbp", "gsc", "ga4") else True,
        }
    return result


class SelectPropertyRequest(BaseModel):
    property_id: str
    property_name: str | None = None


@router.get("/integrations/gsc/properties")
async def list_gsc_properties(client_id: CurrentClientId, session: DbSession) -> dict:
    token = await _get_google_access_token(session, client_id, "gsc")
    async with httpx.AsyncClient(timeout=15) as http:
        resp = await http.get(GSC_SITES_URL, headers={"Authorization": f"Bearer {token}"})
    if not resp.is_success:
        detail = "GSC fetch failed."
        with contextlib.suppress(Exception):
            payload = resp.json()
            message = str(payload.get("error", {}).get("message") or "").strip()
            if message:
                detail = message
        if "searchconsole.googleapis.com" in detail.lower() and ("not been used" in detail.lower() or "disabled" in detail.lower()):
            detail = (
                "Google Search Console API is disabled in your Google Cloud project. "
                "Enable it in Google Cloud Console -> APIs & Services -> Library, then retry."
            )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN if resp.status_code == 401 else resp.status_code,
            detail=detail,
        )
    payload = resp.json()
    rows = payload.get("siteEntry") or []
    items = []
    for r in rows:
        site_url = str(r.get("siteUrl") or "")
        if not site_url:
            continue
        items.append(
            {
                "property_id": site_url,
                "property_name": site_url,
                "property_type": "domain" if site_url.startswith("sc-domain:") else "url",
                "permission_level": str(r.get("permissionLevel") or ""),
            }
        )
    return {"items": items}


@router.post("/integrations/gsc/select-property")
async def select_gsc_property(
    body: SelectPropertyRequest,
    client_id: CurrentClientId,
    session: DbSession,
) -> dict:
    await _get_integration_row(session, client_id, "gsc")
    extra = {"selected_property": body.property_id}
    if body.property_name:
        extra["selected_property_name"] = body.property_name
    await session.execute(
        text(
            """
            UPDATE rp_integrations
            SET extra_data = COALESCE(extra_data, '{}'::jsonb) || (CAST(:extra AS text))::jsonb,
                updated_at = now()
            WHERE client_id = :cid AND type = 'gsc'
            """
        ),
        {"extra": json.dumps(extra), "cid": str(client_id)},
    )
    return {"selected": True, "property_id": body.property_id}


@router.get("/integrations/ga4/properties")
async def list_ga4_properties(client_id: CurrentClientId, session: DbSession) -> dict:
    token = await _get_google_access_token(session, client_id, "ga4")
    async with httpx.AsyncClient(timeout=15) as http:
        resp = await http.get(GA4_SUMMARY_URL, headers={"Authorization": f"Bearer {token}"})
    if not resp.is_success:
        detail = "GA4 fetch failed."
        with contextlib.suppress(Exception):
            payload = resp.json()
            message = str(payload.get("error", {}).get("message") or "").strip()
            if message:
                detail = message
        if "analyticsadmin.googleapis.com" in detail.lower() and ("not been used" in detail.lower() or "disabled" in detail.lower()):
            detail = (
                "Google Analytics Admin API is disabled in your Google Cloud project. "
                "Enable it in Google Cloud Console -> APIs & Services -> Library, then retry."
            )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN if resp.status_code == 401 else resp.status_code,
            detail=detail,
        )
    payload = resp.json()
    items = []
    for acc in payload.get("accountSummaries") or []:
        account_name = str(acc.get("displayName") or "")
        for p in acc.get("propertySummaries") or []:
            prop = str(p.get("property") or "")  # properties/123
            pid = prop.split("/")[-1] if "/" in prop else prop
            if not pid:
                continue
            items.append(
                {
                    "property_id": pid,
                    "property_name": str(p.get("displayName") or pid),
                    "account_name": account_name,
                }
            )
    return {"items": items}


@router.post("/integrations/ga4/select-property")
async def select_ga4_property(
    body: SelectPropertyRequest,
    client_id: CurrentClientId,
    session: DbSession,
) -> dict:
    await _get_integration_row(session, client_id, "ga4")
    extra = {"selected_property": body.property_id}
    if body.property_name:
        extra["selected_property_name"] = body.property_name
    await session.execute(
        text(
            """
            UPDATE rp_integrations
            SET extra_data = COALESCE(extra_data, '{}'::jsonb) || (CAST(:extra AS text))::jsonb,
                updated_at = now()
            WHERE client_id = :cid AND type = 'ga4'
            """
        ),
        {"extra": json.dumps(extra), "cid": str(client_id)},
    )
    return {"selected": True, "property_id": body.property_id}


@router.get("/integrations/gbp/properties")
async def list_gbp_locations(client_id: CurrentClientId, session: DbSession) -> dict:
    token = await _get_google_access_token(session, client_id, "gbp")
    items: list[dict[str, str]] = []
    async with httpx.AsyncClient(timeout=20) as http:
        acc_resp = await http.get(GBP_ACCOUNTS_URL, headers={"Authorization": f"Bearer {token}"})
        if not acc_resp.is_success:
            message = ""
            with contextlib.suppress(Exception):
                payload = acc_resp.json()
                message = str(payload.get("error", {}).get("message") or "").strip()
            detail = _gbp_google_error_detail(message, context="GBP accounts fetch failed")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN if acc_resp.status_code == 401 else acc_resp.status_code,
                detail=detail,
            )
        accounts = (acc_resp.json().get("accounts") or []) if isinstance(acc_resp.json(), dict) else []
        for acc in accounts:
            acc_name = str(acc.get("name") or "")  # accounts/123
            if not acc_name:
                continue
            acc_display = str(acc.get("accountName") or acc_name)
            loc_qs = urllib.parse.urlencode(
                {"pageSize": 100, "readMask": GBP_LOCATIONS_READ_MASK},
            )
            loc_resp = await http.get(
                f"https://mybusinessbusinessinformation.googleapis.com/v1/{acc_name}/locations?{loc_qs}",
                headers={"Authorization": f"Bearer {token}"},
            )
            if not loc_resp.is_success:
                message = ""
                with contextlib.suppress(Exception):
                    payload = loc_resp.json()
                    message = str(payload.get("error", {}).get("message") or "").strip()
                detail = _gbp_google_error_detail(message, context="GBP locations fetch failed")
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN if loc_resp.status_code == 401 else loc_resp.status_code,
                    detail=detail,
                )
            loc_payload = loc_resp.json() if isinstance(loc_resp.json(), dict) else {}
            locations = loc_payload.get("locations") or []
            if not isinstance(locations, list):
                continue
            for loc in locations:
                loc_name = str(loc.get("name") or "")
                title = str(loc.get("title") or "")
                storefront = (
                    str(loc.get("storefrontAddress", {}).get("addressLines", [""])[0])
                    if isinstance(loc.get("storefrontAddress"), dict)
                    else ""
                )
                if not loc_name:
                    continue
                items.append(
                    {
                        "property_id": loc_name,
                        "property_name": title or loc_name,
                        "account_name": acc_display,
                        "address": storefront,
                    }
                )
    if not items:
        raise HTTPException(
            status_code=404,
            detail=(
                "No GBP locations found for this Google account. "
                "Use the GBP owner account, or ensure locations are visible in Google Business Profile Manager."
            ),
        )
    return {"items": items}


@router.post("/integrations/gbp/select-property")
async def select_gbp_property(
    body: SelectPropertyRequest,
    client_id: CurrentClientId,
    session: DbSession,
) -> dict:
    await _get_integration_row(session, client_id, "gbp")
    extra = {"selected_property": body.property_id}
    if body.property_name:
        extra["selected_property_name"] = body.property_name
    await session.execute(
        text(
            """
            UPDATE rp_integrations
            SET extra_data = COALESCE(extra_data, '{}'::jsonb) || (CAST(:extra AS text))::jsonb,
                updated_at = now()
            WHERE client_id = :cid AND type = 'gbp'
            """
        ),
        {"extra": json.dumps(extra), "cid": str(client_id)},
    )
    return {"selected": True, "property_id": body.property_id}


# ═══════════════════════════════════════════════════════════════════════
# GOOGLE OAUTH — auth URL generator
# ═══════════════════════════════════════════════════════════════════════

@router.get("/integrations/google/auth-url")
async def google_auth_url(
    client_id: CurrentClientId,
    type: str = Query(..., pattern="^(gsc|gbp|ga4|google_ads)$"),
) -> dict:
    """Return the Google OAuth consent URL for the requested integration type."""
    if not _cfg().google_client_id:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="GOOGLE_CLIENT_ID is not configured. Add it to backend/.env and restart.",
        )

    scopes = GOOGLE_SCOPES.get(type)
    if not scopes:
        raise HTTPException(status_code=400, detail=f"Unknown integration type: {type}")

    state_payload = json.dumps({"client_id": str(client_id), "type": type, "ts": int(time.time())})
    state         = _sign_state(state_payload)

    params = {
        "client_id":     _cfg().google_client_id,
        "redirect_uri":  _redirect_uri(),
        "response_type": "code",
        "scope":         f"openid email {scopes}",
        "access_type":   "offline",
        "prompt":        "select_account consent",
        "state":         state,
    }
    url = GOOGLE_AUTH_URL + "?" + urllib.parse.urlencode(params)
    return {"url": url, "type": type}


# ═══════════════════════════════════════════════════════════════════════
# GOOGLE OAUTH — callback (receives code from Google, exchanges for tokens)
# ═══════════════════════════════════════════════════════════════════════

@router.get("/integrations/google/callback", response_class=HTMLResponse)
async def google_callback(
    session: OAuthCallbackDbSession,
    code:  str  = Query(default=""),
    state: str  = Query(default=""),
    error: str  = Query(default=""),
) -> HTMLResponse:
    if error:
        return HTMLResponse(_popup_result_html(False, "unknown", error))

    try:
        data        = _verify_state(state)
        client_id   = UUID(data["client_id"])
        intg_type   = data["type"]
    except Exception as exc:
        return HTMLResponse(_popup_result_html(False, "unknown", str(exc)))

    # Re-establish tenant context from signed state (no Bearer token in popup callback).
    await session.execute(
        text("SELECT set_config('app.client_id', :cid, true)"),
        {"cid": str(client_id)},
    )

    # Exchange code for tokens
    try:
        async with httpx.AsyncClient(timeout=15) as http:
            resp = await http.post(
                GOOGLE_TOKEN_URL,
                data={
                    "code":          code,
                    "client_id":     _cfg().google_client_id,
                    "client_secret": _cfg().google_client_secret,
                    "redirect_uri":  _redirect_uri(),
                    "grant_type":    "authorization_code",
                },
            )
            resp.raise_for_status()
            tokens = resp.json()
    except Exception as exc:
        return HTMLResponse(_popup_result_html(False, intg_type, f"Token exchange failed: {exc}"))

    access_token  = tokens.get("access_token", "")
    refresh_token = tokens.get("refresh_token", "")
    expires_in    = tokens.get("expires_in", 3600)
    expiry        = datetime.fromtimestamp(time.time() + expires_in, tz=timezone.utc)

    # Upsert into rp_integrations
    await session.execute(
        text(
            """
            INSERT INTO rp_integrations
                (client_id, type, access_token, refresh_token, token_expiry, connected_at, updated_at)
            VALUES
                (:cid, :type, :at, :rt, :exp, now(), now())
            ON CONFLICT (client_id, type) DO UPDATE
                SET access_token  = EXCLUDED.access_token,
                    refresh_token = COALESCE(EXCLUDED.refresh_token, rp_integrations.refresh_token),
                    token_expiry  = EXCLUDED.token_expiry,
                    updated_at    = now()
            """
        ),
        {
            "cid":  str(client_id),
            "type": intg_type,
            "at":   access_token,
            "rt":   refresh_token or None,
            "exp":  expiry,
        },
    )
    await session.commit()

    return HTMLResponse(_popup_result_html(True, intg_type))


# ═══════════════════════════════════════════════════════════════════════
# WORDPRESS — verify + save credentials
# ═══════════════════════════════════════════════════════════════════════

class WordPressConnectRequest(BaseModel):
    site_url:     str
    username:     str
    app_password: str  # WordPress Application Password (no spaces)


class WordPressPageSummary(BaseModel):
    id: int
    title: str
    slug: str
    status: str
    link: str
    modified: str | None = None
    excerpt: str | None = None
    word_count: int = 0


class WordPressPagesResponse(BaseModel):
    items: list[WordPressPageSummary]
    page: int
    per_page: int
    total: int


class WordPressPageUpdateRequest(BaseModel):
    title: str | None = None
    slug: str | None = None
    excerpt: str | None = None
    status: str | None = None


class GenerateMetaRequest(BaseModel):
    title: str | None = None
    slug: str | None = None
    link: str | None = None
    current_excerpt: str | None = None
    keywords: list[str] | None = None
    mode: Literal["default", "research"] | None = None


class GenerateMetaResponse(BaseModel):
    title: str
    excerpt: str
    model: str
    mode: Literal["default", "research"]
    research_signals: list[str] = []


class ContentTemplateItem(BaseModel):
    id: str
    label: str
    sections: list[str]


class ContentTemplatesResponse(BaseModel):
    items: list[ContentTemplateItem]


class GenerateContentRequest(BaseModel):
    template_id: str
    prompt: str | None = None
    keywords: list[str] | None = None
    mode: Literal["default", "research"] | None = None


class GenerateContentResponse(BaseModel):
    title: str
    excerpt: str
    content: str
    model: str
    mode: Literal["default", "research"]


CONTENT_TEMPLATES: list[ContentTemplateItem] = [
    ContentTemplateItem(id="homepage", label="Homepage", sections=["Hero", "Trust Bar", "Services", "Case Studies", "FAQs", "Final CTA"]),
    ContentTemplateItem(id="service_page", label="Service Page", sections=["Hero", "What Is Service", "Problems We Solve", "Benefits", "Deliverables", "Process", "Case Studies", "CTA"]),
    ContentTemplateItem(id="collection_page", label="Collection Page (eCommerce)", sections=["Intro", "Category Highlights", "Buyer Guide", "FAQs", "Internal Links"]),
    ContentTemplateItem(id="product_page", label="Product Page", sections=["Product Summary", "Benefits", "Specs", "Social Proof", "FAQs", "Purchase CTA"]),
    ContentTemplateItem(id="blog_page", label="Blog Page", sections=["Intro", "Key Insights", "Detailed Sections", "Examples", "FAQs", "Conclusion"]),
    ContentTemplateItem(id="guide_page", label="Guide Page", sections=["Problem Definition", "Step-by-Step Framework", "Tools/Checklist", "FAQs", "Summary"]),
    ContentTemplateItem(id="case_study", label="Case Study", sections=["Client Challenge", "Strategy", "Implementation", "Results", "Lessons", "CTA"]),
    ContentTemplateItem(id="about_page", label="About Page", sections=["Brand Story", "Mission", "Team", "Credentials", "Proof", "Contact CTA"]),
    ContentTemplateItem(id="contact_page", label="Contact Page", sections=["Contact Options", "Who We Help", "Response SLA", "Location Info", "FAQs"]),
    ContentTemplateItem(id="resource_hub", label="Resource Hub", sections=["Featured Resources", "Topic Clusters", "Learning Paths", "FAQs", "Newsletter CTA"]),
    ContentTemplateItem(id="location_page", label="Location Page", sections=["Local Service Intro", "Area-Specific Problems", "Local Proof", "Service Coverage", "FAQs", "CTA"]),
]


def _normalize_wordpress_site_url(raw: str) -> str:
    """Use site root only — /wp-json lives at root, not under /wp-admin."""
    s = (raw or "").strip().rstrip("/")
    if not s:
        return s
    if not s.startswith(("http://", "https://")):
        s = "https://" + s
    low = s.lower()
    for suffix in ("/wp-admin", "/wp-login.php", "/xmlrpc.php"):
        if suffix in low:
            idx = low.find(suffix)
            s = s[:idx].rstrip("/")
            low = s.lower()
    return s.rstrip("/")


def _wordpress_app_password_for_auth(raw: str) -> str:
    """WP shows app passwords with spaces; Basic auth must use the secret without spaces."""
    return "".join((raw or "").split())


def _strip_html(text_raw: str | None) -> str:
    if not text_raw:
        return ""
    no_tags = re.sub(r"<[^>]+>", " ", text_raw)
    return re.sub(r"\s+", " ", html.unescape(no_tags)).strip()


def _extract_wp_seo_title_and_description(
    page_row: dict,
    *,
    fallback_title: str,
    fallback_excerpt: str,
) -> tuple[str, str]:
    """Prefer plugin SEO meta (Yoast etc.) over plain WP excerpt/title."""
    title = fallback_title
    excerpt = fallback_excerpt

    # Generic meta bag from SEO plugins when exposed in REST.
    meta = page_row.get("meta")
    if isinstance(meta, dict):
        for key in (
            "_yoast_wpseo_title",
            "rank_math_title",
            "aioseo_title",
            "_aioseo_title",
        ):
            v = _strip_html(str(meta.get(key) or ""))
            if v:
                title = v
                break
        for key in (
            "_yoast_wpseo_metadesc",
            "rank_math_description",
            "aioseo_description",
            "_aioseo_description",
        ):
            v = _strip_html(str(meta.get(key) or ""))
            if v:
                excerpt = v
                break

    yoast_json = page_row.get("yoast_head_json")
    if isinstance(yoast_json, dict):
        y_title = _strip_html(str(yoast_json.get("title") or ""))
        y_desc = _strip_html(str(yoast_json.get("description") or ""))
        if y_title:
            title = y_title
        if y_desc:
            excerpt = y_desc

    # Fallback parse when only yoast_head HTML is exposed.
    if (not title or not excerpt) and isinstance(page_row.get("yoast_head"), str):
        head_html = str(page_row.get("yoast_head") or "")
        if not title:
            m_title = re.search(r"<title>(.*?)</title>", head_html, flags=re.I | re.S)
            if m_title:
                parsed = _strip_html(m_title.group(1))
                if parsed:
                    title = parsed
        if not excerpt:
            m_desc = re.search(
                r'<meta\s+name=["\']description["\']\s+content=["\'](.*?)["\']',
                head_html,
                flags=re.I | re.S,
            )
            if m_desc:
                parsed = _strip_html(m_desc.group(1))
                if parsed:
                    excerpt = parsed

    return title, excerpt


def _openrouter_extract_text(data: dict) -> str:
    """Extract assistant text across OpenAI/OpenRouter response shapes."""
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
    # Fallbacks used by some providers
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
        code = err.get("code")
        if isinstance(msg, str) and msg.strip():
            return f"{msg.strip()} ({code})" if code else msg.strip()
    return ""


def _extract_title_and_description(content: str) -> tuple[str, str]:
    text = re.sub(r"\s+", " ", (content or "")).strip()
    if not text:
        return "", ""

    # Preferred response shape: JSON object
    with contextlib.suppress(Exception):
        data = json.loads(text)
        if isinstance(data, dict):
            t = str(data.get("title") or "").strip()
            d = str(data.get("description") or data.get("excerpt") or "").strip()
            return t, d

    # Fallback: markdown/json code block containing object
    m_json = re.search(r"\{.*\}", text, flags=re.S)
    if m_json:
        with contextlib.suppress(Exception):
            data = json.loads(m_json.group(0))
            if isinstance(data, dict):
                t = str(data.get("title") or "").strip()
                d = str(data.get("description") or data.get("excerpt") or "").strip()
                return t, d

    # Fallback: line-based format
    m_title = re.search(r"(?:^|\n)\s*title\s*[:\-]\s*(.+?)(?:\n|$)", text, flags=re.I)
    m_desc = re.search(r"(?:^|\n)\s*(?:description|excerpt)\s*[:\-]\s*(.+?)(?:\n|$)", text, flags=re.I)
    if m_title or m_desc:
        return (
            (m_title.group(1).strip() if m_title else ""),
            (m_desc.group(1).strip() if m_desc else ""),
        )

    # Fallback: JSON-like one-liner that may be slightly malformed (common LLM output).
    # Example:
    # {"title":"...","description":"..."}
    # {"title":"...","description":"...""}
    m_jsonish = re.search(
        r"""["']title["']\s*:\s*["'](?P<title>.*?)["']\s*,\s*["'](?:description|excerpt)["']\s*:\s*["'](?P<desc>.*?)["']\s*[\}\n]""",
        text,
        flags=re.I | re.S,
    )
    if m_jsonish:
        title_out = re.sub(r'\\"', '"', m_jsonish.group("title")).strip()
        desc_out = re.sub(r'\\"', '"', m_jsonish.group("desc")).strip()
        return title_out, desc_out

    # If it clearly looks like metadata JSON but could not be parsed, do not dump JSON into excerpt.
    if text.startswith("{") and ("title" in text.lower()) and ("description" in text.lower()):
        return "", ""

    # Final fallback: treat entire output as description
    return "", text


def _extract_research_signals(content: str) -> list[str]:
    text = re.sub(r"\s+", " ", (content or "")).strip()
    if not text:
        return []
    with contextlib.suppress(Exception):
        data = json.loads(text)
        if isinstance(data, dict):
            raw = data.get("research_signals")
            if isinstance(raw, list):
                out = [str(x).strip() for x in raw if str(x).strip()]
                return out[:3]
    return []


def _norm_meta_text(raw: str, *, lower: bool = True) -> str:
    text = re.sub(r"\s+", " ", (raw or "")).strip()
    return text.lower() if lower else text


def _clip_words(text: str, max_words: int) -> str:
    words = [w for w in (text or "").split() if w]
    if len(words) <= max_words:
        return " ".join(words)
    return " ".join(words[:max_words])


async def _fetch_wp_generation_context(
    *,
    site: str,
    wp_user: str,
    app_secret: str,
    page_id: int,
) -> tuple[str, str, list[dict[str, str]]]:
    """
    Fetch current page content sample + existing SEO metadata from sibling pages
    so we can avoid title/meta cannibalization.
    """
    headers = {"Accept": "application/json", "User-Agent": "RankPilot/1.0 (WP SEO context)"}
    fields = "id,slug,title,excerpt,content,meta,yoast_head_json,yoast_head"
    content_sample = ""
    style_hint = ""
    existing: list[dict[str, str]] = []
    async with httpx.AsyncClient(timeout=22, follow_redirects=True) as http:
        # Current page
        cur = await http.get(
            f"{site}/wp-json/wp/v2/pages/{page_id}?_fields={urllib.parse.quote(fields, safe=',')}",
            auth=(wp_user, app_secret),
            headers=headers,
        )
        if cur.is_success and isinstance(cur.json(), dict):
            row = cur.json()
            raw_title = _strip_html(str((row.get("title") or {}).get("rendered") if isinstance(row.get("title"), dict) else ""))
            raw_excerpt = _strip_html(str((row.get("excerpt") or {}).get("rendered") if isinstance(row.get("excerpt"), dict) else ""))
            _, cur_desc = _extract_wp_seo_title_and_description(
                row,
                fallback_title=raw_title,
                fallback_excerpt=raw_excerpt,
            )
            content_txt = _strip_html(
                str((row.get("content") or {}).get("rendered") if isinstance(row.get("content"), dict) else "")
            )
            content_sample = _clip_words(content_txt, 70)
            style_hint = cur_desc or _clip_words(content_txt, 28)

        # Sibling pages for anti-cannibalization
        sib = await http.get(
            f"{site}/wp-json/wp/v2/pages?page=1&per_page=50&orderby=modified&order=desc&_fields={urllib.parse.quote(fields, safe=',')}",
            auth=(wp_user, app_secret),
            headers=headers,
        )
        if sib.is_success and isinstance(sib.json(), list):
            for r in sib.json():
                if not isinstance(r, dict):
                    continue
                try:
                    rid = int(r.get("id"))
                except (TypeError, ValueError):
                    continue
                if rid == page_id:
                    continue
                raw_title = _strip_html(
                    str((r.get("title") or {}).get("rendered") if isinstance(r.get("title"), dict) else "")
                )
                raw_excerpt = _strip_html(
                    str((r.get("excerpt") or {}).get("rendered") if isinstance(r.get("excerpt"), dict) else "")
                )
                t, d = _extract_wp_seo_title_and_description(
                    r,
                    fallback_title=raw_title,
                    fallback_excerpt=raw_excerpt,
                )
                if t or d:
                    existing.append(
                        {
                            "title": _norm_meta_text(t, lower=False),
                            "description": _norm_meta_text(d, lower=False),
                        }
                    )
                if len(existing) >= 25:
                    break

    return content_sample, style_hint, existing


def _avoid_cannibalization(
    *,
    generated_title: str,
    generated_desc: str,
    existing_rows: list[dict[str, str]],
    slug: str,
    primary_kw: str,
) -> tuple[str, str]:
    title = _norm_meta_text(generated_title, lower=False)
    desc = _norm_meta_text(generated_desc, lower=False)
    existing_titles = {_norm_meta_text(str(r.get("title") or "")) for r in existing_rows if r.get("title")}
    existing_descs = {_norm_meta_text(str(r.get("description") or "")) for r in existing_rows if r.get("description")}

    seed = _norm_meta_text(primary_kw, lower=False) or _norm_meta_text(slug.replace("-", " "), lower=False)
    seed = _clip_words(seed, 4)

    if _norm_meta_text(title) in existing_titles and seed:
        # Make an explicit unique variant
        title = f"{title} | {seed}".strip()

    if _norm_meta_text(desc) in existing_descs and seed:
        desc = f"{desc.rstrip('.')} {seed}.".strip()

    return title, desc


async def _wordpress_credentials(session: DbSession, client_id: UUID) -> tuple[str, str, str]:
    row = (
        await session.execute(
            text(
                """
                SELECT access_token, extra_data
                FROM rp_integrations
                WHERE client_id = :cid AND type = 'wordpress'
                LIMIT 1
                """
            ),
            {"cid": str(client_id)},
        )
    ).mappings().first()
    if not row:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="WordPress is not connected. Connect it in Business Setup first.",
        )
    app_secret = str(row.get("access_token") or "").strip()
    extra = row.get("extra_data") or {}
    if isinstance(extra, str):
        with contextlib.suppress(Exception):
            extra = json.loads(extra)
    if not isinstance(extra, dict):
        extra = {}
    site = _normalize_wordpress_site_url(str(extra.get("site_url") or ""))
    wp_user = str(extra.get("username") or "").strip()
    if not site or not wp_user or not app_secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="WordPress integration is incomplete. Reconnect it in Business Setup.",
        )
    return site, wp_user, app_secret


@router.post("/integrations/wordpress", status_code=status.HTTP_200_OK)
async def connect_wordpress(
    body:      WordPressConnectRequest,
    client_id: CurrentClientId,
    session:   DbSession,
) -> dict:
    """Verify WordPress Application Password credentials and store them."""
    site = _normalize_wordpress_site_url(body.site_url)
    wp_login = (body.username or "").strip()
    app_secret = _wordpress_app_password_for_auth(body.app_password)
    if not wp_login or not app_secret:
        raise HTTPException(status_code=400, detail="Username and Application Password are required.")

    headers = {
        "User-Agent": "RankPilot/1.0 (WordPress integration)",
        "Accept": "application/json",
    }

    # Verify credentials by calling the WP REST API
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as http:
            resp = await http.get(
                f"{site}/wp-json/wp/v2/users/me",
                auth=(wp_login, app_secret),
                headers=headers,
            )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Cannot reach WordPress site: {exc}") from exc

    if resp.status_code == 401:
        msg = (
            "WordPress rejected these credentials. Use an Application Password from "
            "WP Admin → Users → Profile → Application Passwords (create one named e.g. RankPilot). "
            "Do not use your normal WordPress login password here. Paste the full generated password; spaces are removed automatically."
        )
        with contextlib.suppress(Exception):
            data = resp.json()
            if isinstance(data, dict):
                raw_m = str(data.get("message") or data.get("code") or "").strip()
                if raw_m and len(raw_m) < 300:
                    msg = f"{msg} (WordPress said: {raw_m})"
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)
    if resp.status_code == 403:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "WordPress REST API returned Forbidden (403). A security plugin, firewall, or host rule may be blocking "
                "REST authentication. Allow /wp-json/ for authenticated requests or temporarily disable the rule to test."
            ),
        )
    if resp.status_code == 404:
        raise HTTPException(
            status_code=404,
            detail=(
                "WordPress REST API not found. Use your site root URL (e.g. https://clicktrends.com.au), "
                "not /wp-admin. Ensure REST is enabled and not blocked by a security plugin."
            ),
        )
    if not resp.is_success:
        raise HTTPException(status_code=400, detail=f"WordPress returned {resp.status_code}: {resp.text[:200]}")

    me = resp.json()
    wp_name = me.get("name", wp_login) if isinstance(me, dict) else wp_login

    # Store credentials (app_password stored in access_token field)
    await session.execute(
        text(
            """
            INSERT INTO rp_integrations
                (client_id, type, access_token, extra_data, connected_at, updated_at)
            VALUES
                (:cid, 'wordpress', :ap, (CAST(:extra AS text))::jsonb, now(), now())
            ON CONFLICT (client_id, type) DO UPDATE
                SET access_token = EXCLUDED.access_token,
                    extra_data   = EXCLUDED.extra_data,
                    updated_at   = now()
            """
        ),
        {
            "cid":   str(client_id),
            "ap":    app_secret,
            "extra": json.dumps({"site_url": site, "username": wp_login, "wp_name": wp_name}),
        },
    )
    await session.commit()

    return {"connected": True, "type": "wordpress", "site": site, "wp_user": wp_name}


@router.get("/integrations/wordpress/pages", response_model=WordPressPagesResponse)
async def list_wordpress_pages(
    client_id: CurrentClientId,
    session: DbSession,
    page: int = Query(default=1, ge=1, le=20),
    per_page: int = Query(default=30, ge=1, le=50),
    search: str = Query(default="", max_length=120),
) -> WordPressPagesResponse:
    site, wp_user, app_secret = await _wordpress_credentials(session, client_id)
    qs: dict[str, str | int] = {
        "page": page,
        "per_page": per_page,
        "orderby": "modified",
        "order": "desc",
        # Keep payload light for shared hosting / slower WP instances.
        "_fields": "id,link,slug,status,title,modified,excerpt,meta,yoast_head_json,yoast_head",
    }
    if (search or "").strip():
        qs["search"] = search.strip()
    url = f"{site}/wp-json/wp/v2/pages?{urllib.parse.urlencode(qs)}"
    try:
        async with httpx.AsyncClient(timeout=25, follow_redirects=True) as http:
            resp = await http.get(
                url,
                auth=(wp_user, app_secret),
                headers={"Accept": "application/json", "User-Agent": "RankPilot/1.0 (WP pages list)"},
            )
    except httpx.ReadTimeout:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=(
                "WordPress took too long to respond while fetching pages. "
                "Try narrowing search or refresh again."
            ),
        ) from None
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"WordPress request failed: {exc}",
        ) from None
    if resp.status_code in (401, 403):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="WordPress rejected credentials while fetching pages. Reconnect WordPress.",
        )
    if not resp.is_success:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"WordPress pages fetch failed ({resp.status_code}): {resp.text[:220]}",
        )
    payload = resp.json()
    rows = payload if isinstance(payload, list) else []
    items: list[WordPressPageSummary] = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        raw_title = _strip_html(str((r.get("title") or {}).get("rendered") if isinstance(r.get("title"), dict) else ""))
        raw_excerpt = _strip_html(str((r.get("excerpt") or {}).get("rendered") if isinstance(r.get("excerpt"), dict) else ""))
        title, excerpt = _extract_wp_seo_title_and_description(
            r,
            fallback_title=raw_title,
            fallback_excerpt=raw_excerpt,
        )
        wc = 0
        try:
            pid = int(r.get("id"))
        except (TypeError, ValueError):
            continue
        items.append(
            WordPressPageSummary(
                id=pid,
                title=title or f"Page {pid}",
                slug=str(r.get("slug") or ""),
                status=str(r.get("status") or ""),
                link=str(r.get("link") or ""),
                modified=str(r.get("modified") or "") or None,
                excerpt=excerpt or None,
                word_count=wc,
            )
        )
    total_raw = resp.headers.get("X-WP-Total", "0")
    try:
        total = int(total_raw)
    except ValueError:
        total = len(items)
    return WordPressPagesResponse(items=items, page=page, per_page=per_page, total=total)


@router.patch("/integrations/wordpress/pages/{page_id}", response_model=WordPressPageSummary)
async def update_wordpress_page(
    page_id: int,
    body: WordPressPageUpdateRequest,
    client_id: CurrentClientId,
    session: DbSession,
) -> WordPressPageSummary:
    site, wp_user, app_secret = await _wordpress_credentials(session, client_id)
    payload: dict[str, str] = {}
    if body.title is not None:
        payload["title"] = body.title.strip()
    if body.slug is not None:
        payload["slug"] = body.slug.strip()
    if body.excerpt is not None:
        payload["excerpt"] = body.excerpt.strip()
    if body.status is not None:
        payload["status"] = body.status.strip()
    if not payload:
        raise HTTPException(status_code=400, detail="Nothing to update.")

    url = f"{site}/wp-json/wp/v2/pages/{page_id}"

    # Best-effort SEO plugin meta update payloads.
    seo_meta_payload: dict[str, object] = {}
    if body.title is not None or body.excerpt is not None:
        seo_meta_payload = {
            "meta": {
                "_yoast_wpseo_title": (body.title or "").strip(),
                "_yoast_wpseo_metadesc": (body.excerpt or "").strip(),
                "rank_math_title": (body.title or "").strip(),
                "rank_math_description": (body.excerpt or "").strip(),
                "aioseo_title": (body.title or "").strip(),
                "aioseo_description": (body.excerpt or "").strip(),
                "_aioseo_title": (body.title or "").strip(),
                "_aioseo_description": (body.excerpt or "").strip(),
            }
        }
    try:
        async with httpx.AsyncClient(timeout=25, follow_redirects=True) as http:
            resp = await http.post(
                url,
                json=payload,
                auth=(wp_user, app_secret),
                headers={"Accept": "application/json", "Content-Type": "application/json"},
            )
            # Try plugin-specific SEO meta update, but do not fail the whole request if blocked.
            if seo_meta_payload:
                with contextlib.suppress(Exception):
                    await http.post(
                        url,
                        json=seo_meta_payload,
                        auth=(wp_user, app_secret),
                        headers={"Accept": "application/json", "Content-Type": "application/json"},
                    )
            # Re-fetch with SEO fields so response matches what WP actually stored.
            refresh = await http.get(
                f"{url}?_fields=id,link,slug,status,title,modified,excerpt,meta,yoast_head_json,yoast_head,content",
                auth=(wp_user, app_secret),
                headers={"Accept": "application/json"},
            )
            if refresh.is_success and isinstance(refresh.json(), dict):
                r = refresh.json()
            else:
                r = resp.json() if isinstance(resp.json(), dict) else {}
    except httpx.ReadTimeout:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="WordPress took too long to save this page. Try again.",
        ) from None
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"WordPress update request failed: {exc}",
        ) from None
    if resp.status_code in (401, 403):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="WordPress rejected update credentials/permissions. Reconnect with an editor/admin user.",
        )
    if not resp.is_success:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"WordPress page update failed ({resp.status_code}): {resp.text[:220]}",
        )
    raw_title = _strip_html(str((r.get("title") or {}).get("rendered") if isinstance(r.get("title"), dict) else ""))
    raw_excerpt = _strip_html(str((r.get("excerpt") or {}).get("rendered") if isinstance(r.get("excerpt"), dict) else ""))
    title, excerpt = _extract_wp_seo_title_and_description(
        r,
        fallback_title=raw_title,
        fallback_excerpt=raw_excerpt,
    )
    content_txt = _strip_html(str((r.get("content") or {}).get("rendered") if isinstance(r.get("content"), dict) else ""))
    wc = len(content_txt.split()) if content_txt else 0
    return WordPressPageSummary(
        id=int(r.get("id") or page_id),
        title=title or f"Page {page_id}",
        slug=str(r.get("slug") or ""),
        status=str(r.get("status") or ""),
        link=str(r.get("link") or ""),
        modified=str(r.get("modified") or "") or None,
        excerpt=excerpt or None,
        word_count=wc,
    )


@router.post("/integrations/wordpress/pages/{page_id}/generate-meta", response_model=GenerateMetaResponse)
async def generate_wordpress_page_meta(
    page_id: int,
    body: GenerateMetaRequest,
    client_id: CurrentClientId,
    session: DbSession,
) -> GenerateMetaResponse:
    settings = _cfg()
    api_key = get_openrouter_api_key()
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OPENROUTER_API_KEY is missing in backend/.env (or server needs reload).",
        )
    row = (
        await session.execute(
            text(
                """
                SELECT business_name, primary_keyword, metro_label
                FROM rp_clients
                WHERE client_id = :cid
                LIMIT 1
                """
            ),
            {"cid": str(client_id)},
        )
    ).mappings().first()
    business = str((row or {}).get("business_name") or "").strip()
    primary_kw = str((row or {}).get("primary_keyword") or "").strip()
    metro = str((row or {}).get("metro_label") or "").strip()
    title = (body.title or "").strip() or f"Page {page_id}"
    slug = (body.slug or "").strip()
    link = (body.link or "").strip()
    current_excerpt = (body.current_excerpt or "").strip()
    generation_mode = body.mode or "default"
    page_content_sample = ""
    page_style_hint = ""
    existing_meta_rows: list[dict[str, str]] = []
    raw_keywords = body.keywords or []
    keywords: list[str] = []
    seen_kw: set[str] = set()
    for kw in raw_keywords:
        token = re.sub(r"\s+", " ", str(kw or "").strip())
        if not token:
            continue
        key = token.lower()
        if key in seen_kw:
            continue
        seen_kw.add(key)
        keywords.append(token)
        if len(keywords) >= 10:
            break
    keyword_line = ", ".join(keywords) if keywords else "N/A"

    # Pull live page context + existing SEO metadata to reduce cannibalization.
    with contextlib.suppress(Exception):
        site, wp_user, app_secret = await _wordpress_credentials(session, client_id)
        page_content_sample, page_style_hint, existing_meta_rows = await _fetch_wp_generation_context(
            site=site,
            wp_user=wp_user,
            app_secret=app_secret,
            page_id=page_id,
        )

    existing_meta_hint = "\n".join(
        [
            f"- title: {r.get('title','')[:90]} | desc: {r.get('description','')[:130]}"
            for r in existing_meta_rows[:12]
        ]
    )

    mode_note = (
        "- Research mode: analyze current web/SERP patterns before writing\n"
        "- Also return 2-3 short research_signals from your analysis\n"
        if generation_mode == "research"
        else "- Default mode: use provided business context only (no external research)\n"
    )
    output_schema_line = (
        '- Output strict JSON only: {"title":"...","description":"...","research_signals":["...","..."]}\n\n'
        if generation_mode == "research"
        else '- Output strict JSON only: {"title":"...","description":"..."}\n\n'
    )

    prompt = (
        "Create SEO metadata for a WordPress page.\n"
        "Requirements:\n"
        "- Return BOTH title and description\n"
        "- Title max 60 characters\n"
        "- Description max 150 characters\n"
        "- Natural, persuasive, local-business tone\n"
        "- Match this page's writing style and intent (not generic template)\n"
        "- Use provided keyword list naturally when relevant\n"
        "- Avoid cannibalization: do not duplicate existing page title/meta exactly\n"
        f"{mode_note}"
        f"{output_schema_line}"
        f"Business: {business or 'N/A'}\n"
        f"Primary keyword: {primary_kw or 'N/A'}\n"
        f"Keyword list (use up to 10): {keyword_line}\n"
        f"Metro: {metro or 'N/A'}\n"
        f"Page title: {title}\n"
        f"Page slug: {slug or 'N/A'}\n"
        f"Page URL: {link or 'N/A'}\n"
        f"Page content sample: {page_content_sample or 'N/A'}\n"
        f"Page style hint: {page_style_hint or 'N/A'}\n"
        f"Current excerpt: {current_excerpt or 'N/A'}\n"
        f"Existing site SEO metadata (avoid exact duplicates):\n{existing_meta_hint or 'N/A'}\n"
    )
    # Retry path: primary model, then faster fallback with lower token budget.
    primary_model = get_openrouter_model()
    if generation_mode == "research":
        models = ["perplexity/sonar-pro", "perplexity/sonar"]
        if primary_model not in models:
            models.append(primary_model)
    else:
        models = [primary_model]
        if primary_model != "perplexity/sonar":
            models.append("perplexity/sonar")
    last_error = "Unknown OpenRouter error"
    content = ""
    used_model = primary_model
    for i, mdl in enumerate(models):
        used_model = mdl
        try:
            async with httpx.AsyncClient(timeout=35) as http:
                resp = await http.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                        "Accept": "application/json",
                        "HTTP-Referer": str(settings.google_redirect_base_url or "http://localhost:5173"),
                        "X-Title": "RankPilot SEO Website",
                    },
                    json={
                        "model": mdl,
                        "messages": [
                            {"role": "system", "content": "You are an SEO copywriting assistant."},
                            {"role": "user", "content": prompt},
                        ],
                        "temperature": 0.4,
                        "max_tokens": 120 if i == 0 else 90,
                    },
                )
        except httpx.ReadTimeout:
            last_error = f"OpenRouter timed out on model {mdl}"
            continue
        except httpx.HTTPError as exc:
            last_error = f"OpenRouter request failed on model {mdl}: {exc}"
            continue

        if not resp.is_success:
            last_error = f"OpenRouter error ({resp.status_code}) on {mdl}: {resp.text[:220]}"
            continue

        data = resp.json() if isinstance(resp.json(), dict) else {}
        upstream_error = _openrouter_error_message(data if isinstance(data, dict) else {})
        if upstream_error:
            last_error = f"Upstream provider error on {mdl}: {upstream_error}"
            continue

        content = _openrouter_extract_text(data if isinstance(data, dict) else {})
        if content:
            break
        last_error = f"OpenRouter empty output on {mdl}: {str(data)[:220]}"

    if not content:
        raise HTTPException(status_code=502, detail=f"Meta generation failed after retries: {last_error}")
    out_title, out_desc = _extract_title_and_description(content)
    out_title = re.sub(r"\s+", " ", out_title).strip() or title
    out_desc = re.sub(r"\s+", " ", out_desc).strip() or current_excerpt
    out_title, out_desc = _avoid_cannibalization(
        generated_title=out_title,
        generated_desc=out_desc,
        existing_rows=existing_meta_rows,
        slug=slug,
        primary_kw=primary_kw,
    )

    if len(out_title) > 60:
        out_title = out_title[:60].rstrip()
    if len(out_desc) > 150:
        out_desc = out_desc[:150].rstrip()
    research_signals = _extract_research_signals(content) if generation_mode == "research" else []

    return GenerateMetaResponse(
        title=out_title,
        excerpt=out_desc,
        model=used_model,
        mode=generation_mode,
        research_signals=research_signals,
    )


@router.get("/integrations/wordpress/content-templates", response_model=ContentTemplatesResponse)
async def wordpress_content_templates() -> ContentTemplatesResponse:
    return ContentTemplatesResponse(items=CONTENT_TEMPLATES)


@router.post("/integrations/wordpress/pages/{page_id}/generate-content", response_model=GenerateContentResponse)
async def generate_wordpress_page_content(
    page_id: int,
    body: GenerateContentRequest,
    client_id: CurrentClientId,
    session: DbSession,
) -> GenerateContentResponse:
    settings = _cfg()
    api_key = get_openrouter_api_key()
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OPENROUTER_API_KEY is missing in backend/.env (or server needs reload).",
        )

    template = next((t for t in CONTENT_TEMPLATES if t.id == body.template_id), None)
    if template is None:
        raise HTTPException(status_code=400, detail="Unknown content template.")

    row = (
        await session.execute(
            text(
                """
                SELECT business_name, primary_keyword, metro_label
                FROM rp_clients
                WHERE client_id = :cid
                LIMIT 1
                """
            ),
            {"cid": str(client_id)},
        )
    ).mappings().first()
    business = str((row or {}).get("business_name") or "").strip()
    primary_kw = str((row or {}).get("primary_keyword") or "").strip()
    metro = str((row or {}).get("metro_label") or "").strip()
    generation_mode = body.mode or "default"

    site, wp_user, app_secret = await _wordpress_credentials(session, client_id)
    page_content_sample, page_style_hint, existing_meta_rows = await _fetch_wp_generation_context(
        site=site,
        wp_user=wp_user,
        app_secret=app_secret,
        page_id=page_id,
    )
    existing_meta_hint = "\n".join(
        [
            f"- title: {r.get('title','')[:90]} | desc: {r.get('description','')[:130]}"
            for r in existing_meta_rows[:12]
        ]
    )
    raw_keywords = body.keywords or []
    keywords: list[str] = []
    seen_kw: set[str] = set()
    for kw in raw_keywords:
        token = re.sub(r"\s+", " ", str(kw or "").strip())
        if not token:
            continue
        key = token.lower()
        if key in seen_kw:
            continue
        seen_kw.add(key)
        keywords.append(token)
        if len(keywords) >= 10:
            break
    keyword_line = ", ".join(keywords) if keywords else "N/A"

    mode_note = (
        "- Research mode: include current SERP/web wording patterns before drafting\n"
        if generation_mode == "research"
        else "- Default mode: use provided page/business context only\n"
    )

    prompt = (
        "Generate website page content as valid Markdown.\n"
        "Return strict JSON only:\n"
        "{\"title\":\"...\",\"description\":\"...\",\"content\":\"...\"}\n"
        "Rules:\n"
        "- Title max 60 chars\n"
        "- Description max 150 chars\n"
        "- Content should follow template sections in order\n"
        "- Avoid repeating titles/meta already used on other pages\n"
        "- Keep language aligned with page style hint\n"
        f"{mode_note}\n"
        f"Template: {template.label}\n"
        f"Template sections: {', '.join(template.sections)}\n"
        f"Business: {business or 'N/A'}\n"
        f"Primary keyword: {primary_kw or 'N/A'}\n"
        f"Metro: {metro or 'N/A'}\n"
        f"Keyword list (max 10): {keyword_line}\n"
        f"User prompt: {(body.prompt or '').strip() or 'N/A'}\n"
        f"Page content sample: {page_content_sample or 'N/A'}\n"
        f"Page style hint: {page_style_hint or 'N/A'}\n"
        f"Existing site SEO metadata (avoid exact duplicates):\n{existing_meta_hint or 'N/A'}\n"
    )

    primary_model = get_openrouter_model()
    # Always prioritize Sonar family for content generation.
    models = ["perplexity/sonar-pro", "perplexity/sonar"]
    if primary_model not in models:
        models.append(primary_model)

    last_error = "Unknown OpenRouter error"
    content_raw = ""
    used_model = primary_model
    for i, mdl in enumerate(models):
        used_model = mdl
        try:
            async with httpx.AsyncClient(timeout=45) as http:
                resp = await http.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                        "Accept": "application/json",
                        "HTTP-Referer": str(settings.google_redirect_base_url or "http://localhost:5173"),
                        "X-Title": "RankPilot SEO Website Content",
                    },
                    json={
                        "model": mdl,
                        "messages": [
                            {"role": "system", "content": "You are an expert SEO website copywriter."},
                            {"role": "user", "content": prompt},
                        ],
                        "temperature": 0.45,
                        "max_tokens": 900 if i == 0 else 700,
                    },
                )
        except httpx.HTTPError as exc:
            last_error = f"OpenRouter request failed on model {mdl}: {exc}"
            continue

        if not resp.is_success:
            if resp.status_code == 401:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
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
            break
        last_error = f"OpenRouter empty output on {mdl}"

    if not content_raw:
        raise HTTPException(status_code=502, detail=f"Content generation failed: {last_error}")

    title, desc = _extract_title_and_description(content_raw)
    md_content = ""
    with contextlib.suppress(Exception):
        parsed = json.loads(content_raw)
        if isinstance(parsed, dict):
            md_content = str(parsed.get("content") or "").strip()
    if not md_content:
        md_content = content_raw.strip()

    title = (title or template.label).strip()
    desc = (desc or page_style_hint or "").strip()
    if len(title) > 60:
        title = title[:60].rstrip()
    if len(desc) > 150:
        desc = desc[:150].rstrip()
    title, desc = _avoid_cannibalization(
        generated_title=title,
        generated_desc=desc,
        existing_rows=existing_meta_rows,
        slug="",
        primary_kw=primary_kw,
    )

    return GenerateContentResponse(
        title=title,
        excerpt=desc,
        content=md_content,
        model=used_model,
        mode=generation_mode,
    )


# ═══════════════════════════════════════════════════════════════════════
# DISCONNECT — remove an integration
# ═══════════════════════════════════════════════════════════════════════

@router.delete("/integrations/{intg_type}", status_code=status.HTTP_200_OK)
async def disconnect(
    intg_type: str,
    client_id: CurrentClientId,
    session:   DbSession,
) -> dict:
    await session.execute(
        text(
            "DELETE FROM rp_integrations WHERE client_id = :cid AND type = :type"
        ),
        {"cid": str(client_id), "type": intg_type},
    )
    await session.commit()
    return {"disconnected": True, "type": intg_type}
