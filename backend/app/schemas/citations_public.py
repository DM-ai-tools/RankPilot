from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class ScrapedNap(BaseModel):
    name: str | None = None
    address: str | None = None
    phone: str | None = None
    name_ok: bool = False
    address_ok: bool = False
    phone_ok: bool = False


class CitationRow(BaseModel):
    id: UUID
    directory: str
    status: str
    drift_flag: bool
    last_checked: datetime | None
    scraped_nap: ScrapedNap | None = None


class CitationsListResponse(BaseModel):
    items: list[CitationRow]
