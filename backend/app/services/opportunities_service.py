"""L2: Opportunity cards from latest Maps ranks."""

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.lib.visibility_scoring import MAX_VISIBLE_RANK
from app.schemas.opportunities import OpportunityRow, OpportunitiesResponse


class OpportunitiesService:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def list_opportunities(self, client_id: UUID) -> OpportunitiesResponse:
        client = (
            await self._session.execute(
                text("SELECT primary_keyword FROM rp_clients WHERE client_id = :cid LIMIT 1"),
                {"cid": str(client_id)},
            )
        ).mappings().first()
        keyword = str(client["primary_keyword"] if client else "").strip()

        rows = (
            await self._session.execute(
                text(
                    """
                    SELECT DISTINCT ON (s.id)
                      s.id AS suburb_id,
                      s.suburb,
                      s.postcode,
                      s.population,
                      r.rank_position
                    FROM rp_suburb_grid s
                    LEFT JOIN rp_rank_history r
                      ON r.suburb_id = s.id
                     AND r.client_id = :cid
                     AND LOWER(TRIM(r.keyword)) = LOWER(TRIM(:kw))
                    WHERE s.client_id = :cid
                    ORDER BY s.id, r.checked_at DESC NULLS LAST
                    """
                ),
                {"kw": keyword, "cid": str(client_id)},
            )
        ).mappings().all()

        candidates: list[tuple[dict, str, str]] = []
        for r in rows:
            rank = r["rank_position"]
            if rank is not None and int(rank) <= MAX_VISIBLE_RANK:
                continue
            if rank is None:
                band = "not_ranking"
                action = (
                    f"Add {r['suburb']} to GBP service areas and publish a suburb landing page "
                    f"targeting high-intent local queries."
                )
            else:
                band = "beyond_pack"
                action = (
                    f"Beyond top 20 Maps pack — improve relevance and citations for \"{keyword}\" "
                    f"in {r['suburb']}."
                )
            candidates.append((dict(r), band, action))

        candidates.sort(key=lambda x: int(x[0]["population"] or 0), reverse=True)

        items: list[OpportunityRow] = []
        for r, band, action in candidates[:12]:
            items.append(
                OpportunityRow(
                    suburb_id=r["suburb_id"],
                    suburb=str(r["suburb"]),
                    postcode=str(r["postcode"]) if r.get("postcode") else None,
                    population=r["population"],
                    rank_position=r["rank_position"],
                    band=band,
                    recommended_action=action,
                )
            )

        return OpportunitiesResponse(items=items)
