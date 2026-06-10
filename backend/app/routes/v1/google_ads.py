"""Google Ads — Keyword Planner related keywords."""

from pydantic import BaseModel, Field

from fastapi import APIRouter, Query

from app.deps import CurrentClientId, DbSession
from app.services.google_ads_service import (
    fetch_keyword_ideas,
    get_setup_status,
    list_google_ads_customers,
    select_google_ads_customer,
)

router = APIRouter()


class SelectGoogleAdsCustomerRequest(BaseModel):
    customer_id: str = Field(min_length=3, max_length=20)
    customer_name: str | None = None


@router.get("/google-ads/setup-status")
async def google_ads_setup_status(client_id: CurrentClientId, session: DbSession) -> dict:
    return await get_setup_status(session, client_id)


@router.get("/google-ads/keyword-ideas")
async def google_ads_keyword_ideas(
    client_id: CurrentClientId,
    session: DbSession,
    seed: str | None = Query(default=None, description="Override primary keyword seed"),
    limit: int = Query(default=40, ge=5, le=100),
) -> dict:
    """Related keywords from Google Ads Keyword Planner for the main (primary) keyword."""
    return await fetch_keyword_ideas(session, client_id, seed_keyword=seed, limit=limit)


@router.get("/integrations/google-ads/customers")
async def google_ads_list_customers(client_id: CurrentClientId, session: DbSession) -> dict:
    return await list_google_ads_customers(session, client_id)


@router.post("/integrations/google-ads/select-customer")
async def google_ads_select_customer(
    body: SelectGoogleAdsCustomerRequest,
    client_id: CurrentClientId,
    session: DbSession,
) -> dict:
    return await select_google_ads_customer(
        session,
        client_id,
        body.customer_id,
        body.customer_name,
    )
