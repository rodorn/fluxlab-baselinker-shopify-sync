"""Logika synchronizacji stanow BaseLinker -> Shopify per Location.

- mapowanie magazyn BaseLinker -> Shopify Location (MAG1->LOC-A, MAG2->LOC-B)
- mapowanie SKU miedzy systemami (domyslnie identycznosciowe)
- synchronizacja stanow osobno per Location
- log konfliktow (SKU obecny tylko po jednej stronie)
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .baselinker import BaseLinkerClient
from .shopify import ShopifyClient

# Mapowanie magazyn BaseLinker -> Shopify Location
DEFAULT_WAREHOUSE_MAP: dict[str, str] = {
    "MAG1": "LOC-A",
    "MAG2": "LOC-B",
}


@dataclass
class Conflict:
    """Konflikt: SKU obecny tylko po jednej stronie integracji."""

    sku: str
    location_id: str
    side: str  # "baselinker_only" lub "shopify_only"

    def __str__(self) -> str:
        return f"[{self.side}] SKU={self.sku} Location={self.location_id}"


@dataclass
class SyncResult:
    """Wynik synchronizacji."""

    # applied[location_id][sku] = ustawiona ilosc
    applied: dict[str, dict[str, int]] = field(default_factory=dict)
    conflicts: list[Conflict] = field(default_factory=list)


def map_sku(sku: str, sku_map: dict[str, str] | None = None) -> str:
    """Mapuje SKU BaseLinker -> SKU Shopify. Domyslnie identycznosciowe."""
    if sku_map:
        return sku_map.get(sku, sku)
    return sku


def sync_stock(
    bl: BaseLinkerClient,
    shop: ShopifyClient,
    warehouse_map: dict[str, str] | None = None,
    sku_map: dict[str, str] | None = None,
) -> SyncResult:
    """Synchronizuje stany z magazynow BaseLinker do Shopify Locations.

    Kazdy magazyn trafia do swojej Location niezaleznie (osobny stan per
    Location). Konflikty (SKU tylko po jednej stronie) sa logowane, a stan
    Shopify ktory nie ma odpowiednika w BaseLinker nie jest nadpisywany.
    """
    warehouse_map = warehouse_map or DEFAULT_WAREHOUSE_MAP
    result = SyncResult()

    bl_stock = bl.get_all_stock()
    shop_levels = shop.get_all_levels()

    for warehouse_id, location_id in warehouse_map.items():
        bl_skus = bl_stock.get(warehouse_id, {})
        shop_skus = shop_levels.get(location_id, {})
        result.applied.setdefault(location_id, {})

        # BaseLinker jest zrodlem prawdy dla stanow.
        for bl_sku, qty in bl_skus.items():
            target_sku = map_sku(bl_sku, sku_map)
            if target_sku not in shop_skus:
                result.conflicts.append(
                    Conflict(target_sku, location_id, "baselinker_only")
                )
            shop.set_inventory_on_hand(location_id, target_sku, qty)
            result.applied[location_id][target_sku] = qty

        # SKU obecne w Shopify ale nieznane BaseLinkerowi -> konflikt.
        mapped_bl = {map_sku(s, sku_map) for s in bl_skus}
        for shop_sku in shop_skus:
            if shop_sku not in mapped_bl:
                result.conflicts.append(Conflict(shop_sku, location_id, "shopify_only"))

    return result
