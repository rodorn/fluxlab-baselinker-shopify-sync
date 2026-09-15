"""Demo end-to-end: BaseLinker (2 magazyny) -> Shopify (2 Locations).

Uruchomienie: python run.py
Dziala na danych demo (bez realnych kluczy). Realne klucze przez zmienne
srodowiskowe: BASELINKER_TOKEN, SHOPIFY_SHOP, SHOPIFY_TOKEN.
"""

from __future__ import annotations

from src.baselinker import BaseLinkerClient
from src.orders import fulfill_order
from src.shopify import ShopifyClient
from src.sync import DEFAULT_WAREHOUSE_MAP, sync_stock


def _print_bl(bl: BaseLinkerClient) -> None:
    print("Stany BaseLinker (per magazyn):")
    stock = bl.get_all_stock()
    for wh in bl.get_inventory_warehouses():
        skus = stock[wh.warehouse_id]
        pretty = ", ".join(f"{s}={q}" for s, q in sorted(skus.items()))
        print(f"  {wh.warehouse_id} ({wh.name}): {pretty}")


def _print_shop(shop: ShopifyClient) -> None:
    print("Stany Shopify (per Location):")
    levels = shop.get_all_levels()
    for loc in shop.get_locations():
        skus = levels[loc.location_id]
        pretty = ", ".join(f"{s}={q}" for s, q in sorted(skus.items()))
        print(f"  {loc.location_id} ({loc.name}): {pretty}")


def main() -> None:
    bl = BaseLinkerClient(demo=True)
    shop = ShopifyClient(demo=True)

    print("=" * 70)
    print("DEMO: multi-location BaseLinker -> Shopify sync (FluxLab)")
    print("=" * 70)
    print(f"Mapowanie magazyn -> Location: {DEFAULT_WAREHOUSE_MAP}")
    print()

    print("--- STAN STARTOWY ---")
    _print_bl(bl)
    _print_shop(shop)
    print()

    print("--- SYNCHRONIZACJA STANOW ---")
    result = sync_stock(bl, shop)
    for loc_id, skus in result.applied.items():
        for sku, qty in sorted(skus.items()):
            print(f"  set {loc_id} {sku} -> {qty}")
    print()
    if result.conflicts:
        print("Konflikty (SKU tylko po jednej stronie):")
        for c in result.conflicts:
            print(f"  {c}")
    print()

    print("--- STAN PO SYNCHRONIZACJI ---")
    _print_shop(shop)
    print()

    # SKU-APPLE po synchronizacji: LOC-A=12, LOC-B=3 (lacznie 15).
    # Zamowienie na 14 szt -> musi zejsc z OBU Location (multi-magazyn).
    print("--- ZAMOWIENIE MULTI-MAGAZYN ---")
    order_lines = [("SKU-APPLE", 14)]
    print(f"Zamowienie: {order_lines} (strategy=priority, priorytet MAG1>MAG2)")
    fulfillments = fulfill_order(
        shop, order_lines, strategy="priority", warehouse_priority=["MAG1", "MAG2"]
    )
    for f in fulfillments:
        print(
            f"  SKU={f.sku} zamowiono={f.requested} "
            f"zrealizowano={f.fulfilled} brak={f.shortage}"
        )
        for a in f.allocations:
            print(f"    {a}")
    print()

    print("--- STAN PO ZAMOWIENIU ---")
    _print_shop(shop)
    print()
    print("Gotowe. Zbudowane przez Pawel Iwanek, FluxLab, https://fluxlab.pl")


if __name__ == "__main__":
    main()
