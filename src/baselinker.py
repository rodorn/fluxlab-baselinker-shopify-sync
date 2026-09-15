"""Klient BaseLinker API do pobierania magazynów i stanów magazynowych.

Tryb realny uzywa endpointu https://api.baselinker.com/connector.php
z naglowkiem X-BLToken. Tryb demo dziala na wbudowanych danych, bez kluczy.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any

API_URL = "https://api.baselinker.com/connector.php"


@dataclass
class Warehouse:
    """Magazyn w BaseLinker (inventory warehouse)."""

    warehouse_id: str
    name: str


@dataclass
class BaseLinkerClient:
    """Klient BaseLinker.

    W trybie demo (demo=True lub brak tokenu) korzysta z wbudowanych danych.
    W trybie realnym token brany jest z argumentu lub zmiennej BASELINKER_TOKEN.
    """

    token: str | None = None
    inventory_id: str = "1"
    demo: bool = False
    timeout: float = 15.0
    max_retries: int = 3
    _demo_warehouses: list[Warehouse] = field(default_factory=list)
    _demo_stock: dict[str, dict[str, int]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.token is None:
            self.token = os.environ.get("BASELINKER_TOKEN")
        if self.token is None:
            self.demo = True
        if self.demo and not self._demo_warehouses:
            self._load_demo_data()

    def _load_demo_data(self) -> None:
        """Wbudowane dane demo: 2 magazyny, kilka SKU z roznymi stanami."""
        self._demo_warehouses = [
            Warehouse(warehouse_id="MAG1", name="Magazyn Warszawa"),
            Warehouse(warehouse_id="MAG2", name="Magazyn Krakow"),
        ]
        # stock[warehouse_id][sku] = ilosc
        self._demo_stock = {
            "MAG1": {
                "SKU-APPLE": 12,
                "SKU-BANANA": 5,
                "SKU-CHERRY": 0,
                "SKU-ONLYBL": 7,  # SKU tylko po stronie BaseLinker (konflikt)
            },
            "MAG2": {
                "SKU-APPLE": 3,
                "SKU-BANANA": 20,
                "SKU-DATE": 8,
                "SKU-ONLYBL": 2,
            },
        }

    def _request(self, method: str, parameters: dict[str, Any]) -> dict[str, Any]:
        """Wykonuje request do BaseLinker z retry i timeoutem (tryb realny)."""
        payload = urllib.parse.urlencode(
            {"method": method, "parameters": json.dumps(parameters)}
        ).encode("utf-8")
        headers = {
            "X-BLToken": self.token or "",
            "Content-Type": "application/x-www-form-urlencoded",
        }
        last_err: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                req = urllib.request.Request(API_URL, data=payload, headers=headers)
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                if data.get("status") == "ERROR":
                    raise RuntimeError(
                        f"BaseLinker error: {data.get('error_code')} "
                        f"{data.get('error_message')}"
                    )
                return data
            except (urllib.error.URLError, TimeoutError, RuntimeError) as exc:
                last_err = exc
                if attempt < self.max_retries - 1:
                    time.sleep(2**attempt)
        raise RuntimeError(f"BaseLinker request failed: {last_err}")

    def get_inventory_warehouses(self) -> list[Warehouse]:
        """Zwraca liste magazynow (metoda getInventoryWarehouses)."""
        if self.demo:
            return list(self._demo_warehouses)
        data = self._request(
            "getInventoryWarehouses", {"inventory_id": self.inventory_id}
        )
        result = []
        for wh in data.get("warehouses", []):
            result.append(
                Warehouse(
                    warehouse_id=str(wh.get("warehouse_id")),
                    name=wh.get("name", ""),
                )
            )
        return result

    def get_inventory_products_stock(self, warehouse_id: str) -> dict[str, int]:
        """Zwraca stany {sku: ilosc} dla danego magazynu.

        Metoda getInventoryProductsStock zwraca stany per produkt per magazyn.
        Tu redukujemy do prostego slownika sku -> ilosc dla wskazanego magazynu.
        """
        if self.demo:
            return dict(self._demo_stock.get(warehouse_id, {}))
        data = self._request(
            "getInventoryProductsStock", {"inventory_id": self.inventory_id}
        )
        stock: dict[str, int] = {}
        for _product_id, product in data.get("products", {}).items():
            sku = product.get("sku")
            if not sku:
                continue
            wh_stock = product.get("stock", {})
            key = f"bl_{warehouse_id}"
            qty = wh_stock.get(key, wh_stock.get(warehouse_id, 0))
            stock[sku] = int(qty)
        return stock

    def get_all_stock(self) -> dict[str, dict[str, int]]:
        """Zwraca stany dla wszystkich magazynow: {warehouse_id: {sku: ilosc}}."""
        result: dict[str, dict[str, int]] = {}
        for wh in self.get_inventory_warehouses():
            result[wh.warehouse_id] = self.get_inventory_products_stock(wh.warehouse_id)
        return result
