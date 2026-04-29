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
import hashlib
import hmac
import json
import time
import urllib.parse
from datetime import datetime, timezone
from uuid import UUID

import httpx
from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy import text

from app.core.config import Settings, get_settings
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
}

GOOGLE_TOKEN_URL  = "https://oauth2.googleapis.com/token"
GOOGLE_AUTH_URL   = "https://accounts.google.com/o/oauth2/v2/auth"
GSC_SITES_URL     = "https://www.googleapis.com/webmasters/v3/sites"
GA4_SUMMARY_URL   = "https://analyticsadmin.googleapis.com/v1beta/accountSummaries?pageSize=200"
GBP_ACCOUNTS_URL  = "https://mybusinessaccountmanagement.googleapis.com/v1/accounts"

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

def _redirect_uri() -> str:
    base = (_cfg().google_redirect_base_url or "http://localhost:8000").rstrip("/")
    return f"{base}/api/v1/integrations/google/callback"


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
        result[r["type"]] = {
            "connected":    True,
            "connected_at": r["connected_at"].isoformat() if r["connected_at"] else None,
            "extra":        r["extra_data"] or {},
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
            detail = "GBP accounts fetch failed."
            with contextlib.suppress(Exception):
                payload = acc_resp.json()
                message = str(payload.get("error", {}).get("message") or "").strip()
                if message:
                    detail = message
            low = detail.lower()
            if "service is disabled" in low or "has not been used" in low:
                detail = (
                    "Google Business Profile Account Management API is disabled. "
                    "Enable it in Google Cloud Console -> APIs & Services -> Library, then reconnect GBP."
                )
            elif "insufficient authentication scopes" in low or "insufficient permissions" in low:
                detail = "GBP permission denied. Disconnect GBP and reconnect with the business owner Google account."
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
            loc_resp = await http.get(
                f"https://mybusinessbusinessinformation.googleapis.com/v1/{acc_name}/locations?pageSize=100",
                headers={"Authorization": f"Bearer {token}"},
            )
            if not loc_resp.is_success:
                detail = "GBP locations fetch failed."
                with contextlib.suppress(Exception):
                    payload = loc_resp.json()
                    message = str(payload.get("error", {}).get("message") or "").strip()
                    if message:
                        detail = message
                low = detail.lower()
                if "service is disabled" in low or "has not been used" in low:
                    detail = (
                        "Google Business Profile Business Information API is disabled. "
                        "Enable it in Google Cloud Console -> APIs & Services -> Library, then reconnect GBP."
                    )
                elif "insufficient authentication scopes" in low or "insufficient permissions" in low:
                    detail = "GBP location permission denied. Reconnect GBP with a Google account that owns the location."
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
    type: str = Query(..., pattern="^(gsc|gbp|ga4)$"),
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
        "prompt":        "consent",
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
