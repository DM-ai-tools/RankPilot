from app.lib.maps_pack_rank import infer_maps_pack_rank


def test_prefers_rank_absolute_over_rank_group_one():
    item = {"rank_group": 1, "rank_absolute": 4}
    assert infer_maps_pack_rank(item, list_order_1based=1) == 4


def test_uses_list_order_when_rank_group_is_one():
    item = {"rank_group": 1, "rank_absolute": None}
    assert infer_maps_pack_rank(item, list_order_1based=7) == 7


def test_uses_rank_group_when_greater_than_one():
    item = {"rank_group": 3, "rank_absolute": None}
    assert infer_maps_pack_rank(item, list_order_1based=1) == 3
