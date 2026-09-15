"""Realizacja zamowienia z wielu magazynow (multi-location fulfillment).

Gdy zamowiona ilosc SKU jest zbierana z wiecej niz jednego magazynu, stan
dekrementowany jest per Location wg wybranej strategii:
- "priority": najpierw magazyny wg kolejnosci priorytetu, potem kolejne
- "proportional": proporcjonalnie do dostepnych stanow

Kazda decyzja jest jawnie logowana (ktora Location ile oddala).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .shopify import ShopifyClient
from .sync import DEFAULT_WAREHOUSE_MAP


@dataclass
class Allocation:
    """Ile sztuk SKU pobrano z danej Location."""

    location_id: str
    sku: str
    taken: int
    before: int
    after: int

    def __str__(self) -> str:
        return (
            f"Location={self.location_id} SKU={self.sku} "
            f"oddala={self.taken} ({self.before} -> {self.after})"
        )


@dataclass
class FulfillmentResult:
    """Wynik realizacji jednej pozycji zamowienia."""

    sku: str
    requested: int
    fulfilled: int
    allocations: list[Allocation] = field(default_factory=list)
    shortage: int = 0  # ile nie udalo sie zrealizowac


def _location_priority(
    warehouse_map: dict[str, str], priority: list[str] | None
) -> list[str]:
    """Zwraca kolejnosc Locations wg priorytetu magazynow."""
    if priority:
        ordered_wh = [w for w in priority if w in warehouse_map]
        ordered_wh += [w for w in warehouse_map if w not in priority]
    else:
        ordered_wh = list(warehouse_map)
    return [warehouse_map[w] for w in ordered_wh]


def fulfill_order_line(
    shop: ShopifyClient,
    sku: str,
    quantity: int,
    strategy: str = "priority",
    warehouse_map: dict[str, str] | None = None,
    warehouse_priority: list[str] | None = None,
) -> FulfillmentResult:
    """Realizuje jedna pozycje zamowienia, dekrementujac stany per Location.

    strategy:
      - "priority": pobiera maksymalnie z Location o wyzszym priorytecie,
        reszte z kolejnych (typowe multi-warehouse fulfillment).
      - "proportional": dzieli zapotrzebowanie proporcjonalnie do stanow.
    """
    warehouse_map = warehouse_map or DEFAULT_WAREHOUSE_MAP
    locations = _location_priority(warehouse_map, warehouse_priority)
    available = {loc: (shop.get_inventory_level(loc, sku) or 0) for loc in locations}
    total_available = sum(available.values())

    result = FulfillmentResult(sku=sku, requested=quantity, fulfilled=0)

    if strategy == "proportional" and total_available > 0:
        plan = _plan_proportional(available, quantity, locations)
    else:
        plan = _plan_priority(available, quantity, locations)

    for loc in locations:
        take = plan.get(loc, 0)
        if take <= 0:
            continue
        before = available[loc]
        after = before - take
        shop.set_inventory_on_hand(loc, sku, after)
        result.allocations.append(
            Allocation(location_id=loc, sku=sku, taken=take, before=before, after=after)
        )
        result.fulfilled += take

    result.shortage = max(0, quantity - result.fulfilled)
    return result


def _plan_priority(
    available: dict[str, int], quantity: int, locations: list[str]
) -> dict[str, int]:
    """Pobiera po kolei z Location wg priorytetu do wyczerpania zapotrzebowania."""
    remaining = quantity
    plan: dict[str, int] = {}
    for loc in locations:
        if remaining <= 0:
            break
        take = min(available[loc], remaining)
        plan[loc] = take
        remaining -= take
    return plan


def _plan_proportional(
    available: dict[str, int], quantity: int, locations: list[str]
) -> dict[str, int]:
    """Dzieli zapotrzebowanie proporcjonalnie do dostepnych stanow.

    Reszty z zaokraglenia rozdzielane sa deterministycznie wg kolejnosci, a
    calosc jest ograniczona dostepnym stanem per Location.
    """
    total = sum(available.values())
    to_fulfill = min(quantity, total)
    plan: dict[str, int] = {}
    assigned = 0
    for loc in locations:
        share = to_fulfill * available[loc] // total if total else 0
        share = min(share, available[loc])
        plan[loc] = share
        assigned += share
    # Rozdziel reszte (zaokraglenia w dol) wg dostepnego zapasu.
    leftover = to_fulfill - assigned
    for loc in locations:
        if leftover <= 0:
            break
        room = available[loc] - plan[loc]
        add = min(room, leftover)
        plan[loc] += add
        leftover -= add
    return plan


def fulfill_order(
    shop: ShopifyClient,
    lines: list[tuple[str, int]],
    strategy: str = "priority",
    warehouse_map: dict[str, str] | None = None,
    warehouse_priority: list[str] | None = None,
) -> list[FulfillmentResult]:
    """Realizuje wielopozycyjne zamowienie (lista (sku, ilosc))."""
    return [
        fulfill_order_line(
            shop,
            sku,
            qty,
            strategy=strategy,
            warehouse_map=warehouse_map,
            warehouse_priority=warehouse_priority,
        )
        for sku, qty in lines
    ]
