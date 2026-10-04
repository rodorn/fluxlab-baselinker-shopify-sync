# BaseLinker to Shopify - synchronizacja multi-location

> Automatyzacje i integracje dla sklepów internetowych: [fluxlab.pl/automatyzacja-dla-ecommerce](https://fluxlab.pl/automatyzacja-dla-ecommerce?utm_source=github&utm_campaign=fluxlab-baselinker-shopify-sync)

Synchronizacja stanow magazynowych z WIELU magazynow BaseLinker na WIELE
Shopify Locations, z osobnym stanem per lokalizacja oraz obsluga zamowienia
realizowanego z wiecej niz jednego magazynu.

## Co to robi

- Pobiera magazyny i stany z BaseLinker (`getInventoryWarehouses`,
  `getInventoryProductsStock`) per magazyn.
- Mapuje magazyn BaseLinker na Shopify Location (domyslnie MAG1 -> LOC-A,
  MAG2 -> LOC-B) i ustawia stan osobno per Location
  (`inventorySetOnHandQuantities`).
- Mapuje SKU miedzy systemami (domyslnie identycznosciowe, mozliwy slownik
  nadpisan).
- Loguje konflikty, czyli SKU obecne tylko po jednej stronie integracji.
- Obsluguje zamowienie multi-magazyn: gdy zamowiona ilosc jest zbierana z
  wiecej niz jednego magazynu, dekrementuje stan per Location wg strategii
  (priorytet magazynu lub proporcjonalnie), z jawnym logiem ktora Location
  ile oddala.

## Struktura

- `src/baselinker.py` - klient BaseLinker API (retry, timeout, tryb demo).
- `src/shopify.py` - klient Shopify Admin API (GraphQL, tryb demo).
- `src/sync.py` - mapowanie i synchronizacja stanow per Location, log konfliktow.
- `src/orders.py` - reguly realizacji zamowienia z wielu magazynow.
- `run.py` - demo end-to-end na danych mock.
- `tests/` - testy pytest.

## Jak uruchomic demo

Demo dziala bez zadnych kluczy, na wbudowanych danych mock (2 magazyny,
2 Locations, kilka SKU):

```bash
python run.py
```

## Testy

```bash
pip install -r requirements.txt
pytest -q
```

## Jak podpiac realne klucze

Klucze przekazywane sa WYLACZNIE przez zmienne srodowiskowe (zadnych sekretow
w kodzie). Skopiuj `.env.example` do `.env` i uzupelnij:

```bash
export BASELINKER_TOKEN="twoj_token_baselinker"   # naglowek X-BLToken
export SHOPIFY_SHOP="twoj-sklep.myshopify.com"
export SHOPIFY_TOKEN="shpat_..."                  # Admin API access token
```

Gdy zmienne sa ustawione, klienci automatycznie przechodza w tryb realny
(pole `demo` staje sie `False`). BaseLinker uzywa endpointu
`https://api.baselinker.com/connector.php`, Shopify uzywa Admin GraphQL API.
Mapowanie magazyn -> Location oraz SKU dostosuj w `src/sync.py`
(`DEFAULT_WAREHOUSE_MAP`) lub przekazujac wlasne slowniki do `sync_stock`.

## Strategie realizacji zamowienia

- `priority` - pobiera maksymalnie z magazynu o wyzszym priorytecie, reszte z
  kolejnych. Typowe dla multi-warehouse fulfillment.
- `proportional` - dzieli zapotrzebowanie proporcjonalnie do dostepnych stanow.

---

Zbudowane przez Pawel Iwanek, FluxLab, https://fluxlab.pl
