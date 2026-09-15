"""Klient Shopify Admin API do zarzadzania stanami per Location.

Tryb realny uzywa Admin GraphQL API (mutacja inventorySetOnHandQuantities).
Tryb demo trzyma stany w pamieci, bez realnych kluczy.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any

DEFAULT_API_VERSION = "2024-10"


@dataclass
class Location:
    """Shopify Location (fizyczna lokalizacja magazynowa)."""

    location_id: str
    name: str


@dataclass
class ShopifyClient:
    """Klient Shopify Admin API.

    W trybie demo (demo=True lub brak konfiguracji) stany trzymane sa w pamieci.
    W trybie realnym potrzebne sa SHOPIFY_SHOP i SHOPIFY_TOKEN (Admin API token).
    """

    shop: str | None = None
    token: str | None = None
    api_version: str = DEFAULT_API_VERSION
    demo: bool = False
    timeout: float = 15.0
    max_retries: int = 3
    _demo_locations: list[Location] = field(default_factory=list)
    # _demo_levels[location_id][sku] = on_hand
    _demo_levels: dict[str, dict[str, int]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.shop is None:
            self.shop = os.environ.get("SHOPIFY_SHOP")
        if self.token is None:
            self.token = os.environ.get("SHOPIFY_TOKEN")
        if not self.shop or not self.token:
            self.demo = True
        if self.demo and not self._demo_locations:
            self._load_demo_data()

    def _load_demo_data(self) -> None:
        """Wbudowane dane demo: 2 Locations, czesc SKU juz istnieje w Shopify."""
        self._demo_locations = [
            Location(location_id="LOC-A", name="Shopify Warszawa"),
            Location(location_id="LOC-B", name="Shopify Krakow"),
        ]
        self._demo_levels = {
            "LOC-A": {
                "SKU-APPLE": 0,
                "SKU-BANANA": 0,
                "SKU-CHERRY": 0,
                "SKU-ONLYSHOP": 4,  # SKU tylko po stronie Shopify (konflikt)
            },
            "LOC-B": {
                "SKU-APPLE": 0,
                "SKU-BANANA": 0,
                "SKU-DATE": 0,
                "SKU-ONLYSHOP": 1,
            },
        }

    def _graphql(self, query: str, variables: dict[str, Any]) -> dict[str, Any]:
        """Wykonuje zapytanie GraphQL do Admin API z retry i timeoutem."""
        url = f"https://{self.shop}/admin/api/{self.api_version}/graphql.json"
        body = json.dumps({"query": query, "variables": variables}).encode("utf-8")
        headers = {
            "X-Shopify-Access-Token": self.token or "",
            "Content-Type": "application/json",
        }
        last_err: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                req = urllib.request.Request(url, data=body, headers=headers)
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                if data.get("errors"):
                    raise RuntimeError(f"Shopify GraphQL error: {data['errors']}")
                return data
            except (urllib.error.URLError, TimeoutError, RuntimeError) as exc:
                last_err = exc
                if attempt < self.max_retries - 1:
                    time.sleep(2**attempt)
        raise RuntimeError(f"Shopify request failed: {last_err}")

    def get_locations(self) -> list[Location]:
        """Zwraca liste Locations."""
        if self.demo:
            return list(self._demo_locations)
        query = """
        query {
          locations(first: 50) {
            edges { node { id name } }
          }
        }
        """
        data = self._graphql(query, {})
        result = []
        for edge in data["data"]["locations"]["edges"]:
            node = edge["node"]
            result.append(Location(location_id=node["id"], name=node["name"]))
        return result

    def get_inventory_level(self, location_id: str, sku: str) -> int | None:
        """Zwraca aktualny stan on_hand dla SKU w danej Location.

        Zwraca None jesli SKU nie istnieje w tej Location (sygnal konfliktu).
        """
        if self.demo:
            return self._demo_levels.get(location_id, {}).get(sku)
        # W realnym API trzeba najpierw zmapowac sku -> inventory_item_id.
        # Tu zwracamy uproszczenie; mapowanie realizuje warstwa sync.
        raise NotImplementedError(
            "Realne odczyty wymagaja mapowania sku -> inventory_item_id"
        )

    def set_inventory_on_hand(self, location_id: str, sku: str, quantity: int) -> None:
        """Ustawia stan on_hand dla SKU w danej Location.

        Realnie: mutacja inventorySetOnHandQuantities. Demo: aktualizacja pamieci.
        """
        if self.demo:
            self._demo_levels.setdefault(location_id, {})[sku] = quantity
            return
        mutation = """
        mutation setOnHand($input: InventorySetOnHandQuantitiesInput!) {
          inventorySetOnHandQuantities(input: $input) {
            userErrors { field message }
          }
        }
        """
        variables = {
            "input": {
                "reason": "correction",
                "setQuantities": [
                    {
                        "inventoryItemId": sku,  # realnie: gid inventory_item
                        "locationId": location_id,
                        "quantity": quantity,
                    }
                ],
            }
        }
        self._graphql(mutation, variables)

    def get_all_levels(self) -> dict[str, dict[str, int]]:
        """Zwraca stany dla wszystkich Locations: {location_id: {sku: on_hand}}."""
        if self.demo:
            return {loc: dict(skus) for loc, skus in self._demo_levels.items()}
        raise NotImplementedError("Dostepne tylko w trybie demo")
