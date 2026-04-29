"""Google Maps local-pack visibility score (keyword + suburb ranks).

Uses the same weighting as product spec §6:
- Visible in pack: ranks 1–20 (DataForSEO Maps / local finder positions).
- Rank weights: top 3 → 1.0, ranks 4–10 → 0.6, ranks 11–20 → 0.3, else → 0.
- Score = SUM(rankWeight * volumeWeight) / SUM(maxPossible * volumeWeight) * 100
  where volumeWeight is suburb population relative to max population in the grid
  (equal weights when all populations are zero).
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

MAX_VISIBLE_RANK = 20
MAX_RANK_WEIGHT = 1.0


def rank_weight(rank: int | None) -> float:
    if rank is None:
        return 0.0
    try:
        r = int(rank)
    except (TypeError, ValueError):
        return 0.0
    if r < 1 or r > MAX_VISIBLE_RANK:
        return 0.0
    if r <= 3:
        return 1.0
    if r <= 10:
        return 0.6
    return 0.3


def visibility_score_pct(rows: Sequence[Mapping[str, Any]]) -> float:
    """rows: mappings with rank_position, population (from suburb grid + latest rank)."""
    if not rows:
        return 0.0
    pops = [max(int(r.get("population") or 0), 0) for r in rows]
    max_pop = max(pops) if pops else 0

    num = 0.0
    den = 0.0
    for r, pop in zip(rows, pops, strict=True):
        rw = rank_weight(_as_int_or_none(r.get("rank_position")))
        if max_pop <= 0:
            vw = 1.0
        else:
            vw = max(pop, 1) / max_pop
        num += rw * vw
        den += MAX_RANK_WEIGHT * vw

    if den <= 0:
        return 0.0
    return min(100.0, round(100.0 * num / den, 1))


def count_rank_bands(rows: Sequence[Mapping[str, Any]]) -> tuple[int, int, int, int]:
    """Returns (top3, pack_4_10, pack_11_20, not_visible). not_visible = no rank or rank > 20."""
    t3 = p1 = p2 = nr = 0
    for r in rows:
        rank = _as_int_or_none(r.get("rank_position"))
        if rank is not None and 1 <= rank <= 3:
            t3 += 1
        elif rank is not None and 4 <= rank <= 10:
            p1 += 1
        elif rank is not None and 11 <= rank <= MAX_VISIBLE_RANK:
            p2 += 1
        else:
            nr += 1
    return t3, p1, p2, nr


def _as_int_or_none(v: Any) -> int | None:
    if v is None:
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None
