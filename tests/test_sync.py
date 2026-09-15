from src.baselinker import BaseLinkerClient
from src.orders import fulfill_order_line
from src.shopify import ShopifyClient
from src.sync import DEFAULT_WAREHOUSE_MAP, map_sku, sync_stock


def make_clients():
    return BaseLinkerClient(demo=True), ShopifyClient(demo=True)


def test_map_sku_identity_and_override():
    assert map_sku("SKU-APPLE") == "SKU-APPLE"
    assert map_sku("SKU-APPLE", {"SKU-APPLE": "SHOP-APPLE"}) == "SHOP-APPLE"
    assert map_sku("SKU-X", {"SKU-APPLE": "SHOP-APPLE"}) == "SKU-X"


def test_warehouse_map_default():
    assert DEFAULT_WAREHOUSE_MAP == {"MAG1": "LOC-A", "MAG2": "LOC-B"}


def test_sync_per_location_independent():
    bl, shop = make_clients()
    sync_stock(bl, shop)
    levels = shop.get_all_levels()
    # MAG1 -> LOC-A, MAG2 -> LOC-B, stany niezalezne per Location.
    assert levels["LOC-A"]["SKU-APPLE"] == 12
    assert levels["LOC-B"]["SKU-APPLE"] == 3
    assert levels["LOC-A"]["SKU-BANANA"] == 5
    assert levels["LOC-B"]["SKU-BANANA"] == 20
    # SKU-DATE tylko w MAG2 -> tylko LOC-B.
    assert levels["LOC-B"]["SKU-DATE"] == 8


def test_sync_conflicts_logged():
    bl, shop = make_clients()
    result = sync_stock(bl, shop)
    sides = {(c.sku, c.side) for c in result.conflicts}
    # SKU-ONLYBL istnieje tylko w BaseLinker.
    assert ("SKU-ONLYBL", "baselinker_only") in sides
    # SKU-ONLYSHOP istnieje tylko w Shopify.
    assert ("SKU-ONLYSHOP", "shopify_only") in sides


def test_multi_warehouse_decrement_priority():
    bl, shop = make_clients()
    sync_stock(bl, shop)
    # LOC-A=12, LOC-B=3, razem 15. Zamowienie 14 -> obie Location.
    res = fulfill_order_line(
        shop,
        "SKU-APPLE",
        14,
        strategy="priority",
        warehouse_priority=["MAG1", "MAG2"],
    )
    assert res.fulfilled == 14
    assert res.shortage == 0
    taken = {a.location_id: a.taken for a in res.allocations}
    assert taken["LOC-A"] == 12  # najpierw priorytetowy magazyn
    assert taken["LOC-B"] == 2  # reszta z drugiego
    levels = shop.get_all_levels()
    assert levels["LOC-A"]["SKU-APPLE"] == 0
    assert levels["LOC-B"]["SKU-APPLE"] == 1


def test_multi_warehouse_decrement_proportional():
    bl, shop = make_clients()
    sync_stock(bl, shop)
    # LOC-A=12, LOC-B=3, razem 15. Proporcjonalnie dla 10.
    res = fulfill_order_line(shop, "SKU-APPLE", 10, strategy="proportional")
    assert res.fulfilled == 10
    taken = {a.location_id: a.taken for a in res.allocations}
    # 10 * 12/15 = 8, 10 * 3/15 = 2.
    assert taken.get("LOC-A") == 8
    assert taken.get("LOC-B") == 2


def test_order_shortage_when_insufficient():
    bl, shop = make_clients()
    sync_stock(bl, shop)
    res = fulfill_order_line(shop, "SKU-APPLE", 100, strategy="priority")
    assert res.fulfilled == 15  # 12 + 3
    assert res.shortage == 85
