"""Infer Google Maps local-listing position from DataForSEO SERP rows.

DataForSEO `rank_group` is position within a SERP *element type* (often 1 for every
Maps listing in the same block). `rank_absolute` or list order is a better pack index.
"""

from __future__ import annotations


def _safe_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def maps_pack_reviews_count(item: dict) -> int | None:
    """Review count from a Maps SERP row (DataForSEO uses rating.votes_count)."""
    direct = _safe_int(item.get("reviews_count"))
    if direct is not None:
        return direct
    rating = item.get("rating")
    if isinstance(rating, dict):
        return _safe_int(rating.get("votes_count"))
    return None


def maps_pack_rating_value(item: dict) -> float | None:
    rating = item.get("rating")
    if isinstance(rating, dict):
        try:
            v = rating.get("value")
            return float(v) if v is not None else None
        except (TypeError, ValueError):
            return None
    try:
        return float(rating) if rating is not None else None
    except (TypeError, ValueError):
        return None


def infer_maps_pack_rank(item: dict, list_order_1based: int) -> int:
    """1-based position in the Maps result list for one suburb scan."""
    abs_r = _safe_int(item.get("rank_absolute"))
    if abs_r is not None and 1 <= abs_r <= 100:
        return abs_r

    grp_r = _safe_int(item.get("rank_group"))
    # rank_group=1 is shared by many listings in one SERP block — ignore when alone.
    if grp_r is not None and grp_r > 1:
        return grp_r

    return max(1, list_order_1based)
