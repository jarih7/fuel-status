#!/usr/bin/env python3
"""
fetch_prices.py – Scrape Czech fuel station prices from:
  1. tank-ono.cz  (primary)  – all ~45 Tank ONO stations.
                               URL: https://www.tank-ono.cz/cz/index.php?page=cenik
                               Single-page CZK price table; confirmed working structure.
  2. mbenzin.cz   (secondary) – price aggregator; flexible multi-strategy parsing.

Writes combined results to data/prices.json.
"""

import json
import datetime
import re
import sys
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

OUTPUT_PATH = Path(__file__).parent.parent / "data" / "prices.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "cs,en;q=0.8",
}

# ── City → region lookup ──────────────────────────────────────────────────────
CITY_REGION: dict[str, str] = {
    "Praha": "Praha",
    "Brno": "Jihomoravský",
    "Ostrava": "Moravskoslezský",
    "Plzeň": "Plzeňský",
    "Liberec": "Liberecký",
    "Olomouc": "Olomoucký",
    "Hradec Králové": "Královéhradecký",
    "České Budějovice": "Jihočeský",
    "Zlín": "Zlínský",
    "Pardubice": "Pardubický",
    "Jihlava": "Vysočina",
    "Ústí nad Labem": "Ústecký",
    "Karlovy Vary": "Karlovarský",
    "Mladá Boleslav": "Středočeský",
    "Kladno": "Středočeský",
    "Teplice": "Ústecký",
    "Chomutov": "Ústecký",
    "Most": "Ústecký",
    "Opava": "Moravskoslezský",
    "Havířov": "Moravskoslezský",
    "Přerov": "Olomoucký",
    "Prostějov": "Olomoucký",
    "Znojmo": "Jihomoravský",
    "Hodonín": "Jihomoravský",
    "Uherské Hradiště": "Zlínský",
    "Vsetín": "Zlínský",
    "Nový Jičín": "Moravskoslezský",
    "Třinec": "Moravskoslezský",
    "Frýdek-Místek": "Moravskoslezský",
    "Karviná": "Moravskoslezský",
    "Šlapanice": "Jihomoravský",
    "Popovice": "Jihomoravský",
    "Pohořelice": "Jihomoravský",
    "Zličín": "Praha",
    "Dolní Měcholupy": "Praha",
    "Letňany": "Praha",
    "Čakovice": "Praha",
    "Smíchov": "Praha",
    "Holešovice": "Praha",
    "Kobylisy": "Praha",
    "Pankrác": "Praha",
    "Říčany": "Středočeský",
    "Beroun": "Středočeský",
    "Příbram": "Středočeský",
    "Kutná Hora": "Středočeský",
    "Kolín": "Středočeský",
    "Nymburk": "Středočeský",
    "Mělník": "Středočeský",
    "Rakovník": "Středočeský",
    "Benešov": "Středočeský",
    "Písek": "Jihočeský",
    "Tábor": "Jihočeský",
    "Strakonice": "Jihočeský",
    "Český Krumlov": "Jihočeský",
    "Klatovy": "Plzeňský",
    "Rokycany": "Plzeňský",
    "Sokolov": "Karlovarský",
    "Cheb": "Karlovarský",
    "Děčín": "Ústecký",
    "Litoměřice": "Ústecký",
    "Jablonec nad Nisou": "Liberecký",
    "Česká Lípa": "Liberecký",
    "Trutnov": "Královéhradecký",
    "Náchod": "Královéhradecký",
    "Chrudim": "Pardubický",
    "Svitavy": "Pardubický",
    "Třebíč": "Vysočina",
    "Žďár nad Sázavou": "Vysočina",
    "Havlíčkův Brod": "Vysočina",
    "Vyškov": "Jihomoravský",
    "Blansko": "Jihomoravský",
    "Kroměříž": "Zlínský",
    "Šumperk": "Olomoucký",
    "Jeseník": "Olomoucký",
    "Frýdlant nad Ostravicí": "Moravskoslezský",
    "Hlučín": "Moravskoslezský",
    "Bohumín": "Moravskoslezský",
    "Orlová": "Moravskoslezský",
    "Bruntál": "Moravskoslezský",
}


def city_and_region(station_name: str) -> tuple[str, str]:
    """
    Derive city and Czech region from a Tank ONO station name.

    Tank ONO formats include:
      "Brno-Popovice"          → city="Brno",  region="Jihomoravský"
      "Praha, Dolní Měcholupy" → city="Praha", region="Praha"
      "Zlín"                   → city="Zlín",  region="Zlínský"
    """
    name = station_name.strip()

    if "," in name:
        city = name.split(",")[0].strip()
    elif "-" in name:
        city = name.split("-")[0].strip()
    else:
        city = name

    region = CITY_REGION.get(city)
    if region is None:
        for known, r in CITY_REGION.items():
            if known.lower() in city.lower() or city.lower() in known.lower():
                region = r
                city = known
                break

    return city, region or "Neznámý kraj"


def parse_price(raw: str) -> float | None:
    """
    Convert a Czech price string ('37,90' / '37.90 Kč' / '37,9') to a float.
    Returns None if the value looks invalid.
    """
    if not raw:
        return None
    cleaned = (
        raw.strip()
        .replace("\xa0", "")
        .replace("Kč", "")
        .replace("€", "")
        .replace(",", ".")
        .strip()
    )
    if cleaned in ("", "---", "*", "—", "-"):
        return None
    match = re.search(r"\d+\.\d+|\d+", cleaned)
    if match:
        try:
            price = float(match.group())
            if 15.0 <= price <= 100.0:   # sanity-check: CZK fuel price range
                return price
        except ValueError:
            pass
    return None


# ── tank-ono.cz ──────────────────────────────────────────────────────────────

TANK_ONO_URL = "https://www.tank-ono.cz/cz/index.php?page=cenik"

# Column indices inside each <tr> (0-based):
#   cells[0] = station name
#   cells[1] = NM 95          ← petrol 95
#   cells[2] = NM 95 Premium
#   cells[3] = NM 98
#   cells[4] = ON             ← standard diesel
#   cells[5] = ON Premium
#   cells[6] = AdBlue
#   cells[7] = LPG
_ONO_NM95_IDX   = 1
_ONO_DIESEL_IDX = 4


def scrape_tank_ono() -> list[dict]:
    """Return a list of station dicts from the single Tank ONO price page."""
    print("  Fetching tank-ono.cz …", file=sys.stderr)
    try:
        resp = requests.get(
            TANK_ONO_URL,
            headers={**HEADERS, "User-Agent": "FuelStatus-Scraper/1.0 (educational use)"},
            timeout=30,
        )
        resp.encoding = "utf-8"
        resp.raise_for_status()
    except requests.RequestException as exc:
        print(f"  [WARN] tank-ono.cz request failed: {exc}", file=sys.stderr)
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    stations: list[dict] = []

    # The page contains two nearly identical tables: one in CZK, one in EUR.
    # We want the CZK table.
    for table in soup.find_all("table"):
        table_text = table.get_text()
        # Skip the EUR table
        if "(EUR)" in table_text and "(CZK)" not in table_text:
            continue
        # Skip tables that look like headers / navigation (too few rows)
        rows = table.find_all("tr")
        if len(rows) < 3:
            continue

        for row in rows:
            cells = row.find_all("td")
            if len(cells) <= _ONO_DIESEL_IDX:
                continue

            station_name = cells[0].get_text(strip=True)
            # Skip header-like rows
            if not station_name or station_name.lower() in (
                "stanice", "čerpací stanice", "cs", "název"
            ):
                continue

            nm95   = parse_price(cells[_ONO_NM95_IDX].get_text(strip=True))
            diesel = parse_price(cells[_ONO_DIESEL_IDX].get_text(strip=True))

            if nm95 is None and diesel is None:
                continue

            city, region = city_and_region(station_name)
            stations.append({
                "name":         f"Tank ONO – {station_name}",
                "chain":        "Tank ONO",
                "city":         city,
                "region":       region,
                "address":      "",
                "petrol_95":    nm95   or 0.0,
                "diesel":       diesel or 0.0,
                "last_updated": datetime.date.today().isoformat(),
            })

    print(f"  tank-ono.cz: {len(stations)} stations", file=sys.stderr)
    return stations


# ── mbenzin.cz ───────────────────────────────────────────────────────────────

# Try multiple candidate URLs; the site may redirect or use a subfolder.
_MBENZIN_URLS = [
    "https://www.mbenzin.cz/",
    "https://mbenzin.cz/",
    "https://www.mbenzin.cz/stanice/",
    "https://www.mbenzin.cz/pumpy/",
    "https://www.mbenzin.cz/cerpaci-stanice/",
]


def scrape_mbenzin() -> list[dict]:
    """
    Attempt to scrape fuel prices from mbenzin.cz.
    Uses three fallback strategies:
      1. HTML table rows
      2. div/li card elements
      3. JSON data embedded in <script> tags
    Returns a (possibly empty) list of station dicts.
    """
    print("  Fetching mbenzin.cz …", file=sys.stderr)
    soup = None
    used_url = None

    for url in _MBENZIN_URLS:
        try:
            resp = requests.get(url, headers=HEADERS, timeout=20, allow_redirects=True)
            if resp.status_code == 200 and len(resp.text) > 2000:
                resp.encoding = resp.apparent_encoding or "utf-8"
                soup = BeautifulSoup(resp.text, "html.parser")
                used_url = url
                print(f"    Loaded {url} ({len(resp.text):,} bytes)", file=sys.stderr)
                break
        except requests.RequestException as exc:
            print(f"    [WARN] {url} → {exc}", file=sys.stderr)

    if soup is None:
        print("  [WARN] mbenzin.cz: no URL responded successfully", file=sys.stderr)
        return []

    stations: list[dict] = []

    # Strategy 1: HTML tables
    for table in soup.find_all("table"):
        for row in table.find_all("tr"):
            cells = row.find_all("td")
            if len(cells) < 3:
                continue
            s = _parse_mbenzin_row(cells)
            if s:
                stations.append(s)

    # Strategy 2: card/div elements
    if not stations:
        for item in soup.select(
            ".pump, .station, .cs-item, .stanice, "
            "[class*='pump'], [class*='station'], [class*='cs-']"
        ):
            s = _parse_mbenzin_card(item)
            if s:
                stations.append(s)

    # Strategy 3: JSON embedded in <script> tags
    if not stations:
        for script in soup.find_all("script"):
            text = script.string or ""
            if any(k in text.lower() for k in ("benzin", "petrol", "nafta", "diesel")):
                stations.extend(_extract_json_stations(text))

    print(f"  mbenzin.cz ({used_url}): {len(stations)} stations", file=sys.stderr)
    return stations


def _parse_mbenzin_row(cells) -> dict | None:
    texts = [c.get_text(strip=True) for c in cells]
    prices = [parse_price(t) for t in texts]
    valid = [(i, p) for i, p in enumerate(prices) if p is not None]
    if not valid:
        return None

    name = city = ""
    for t in texts:
        if t and parse_price(t) is None and len(t) > 2 and not t.isdigit():
            if not name:
                name = t
            elif not city:
                city = t
                break
    if not name:
        return None

    p95  = valid[0][1] if len(valid) > 0 else 0.0
    dies = valid[1][1] if len(valid) > 1 else 0.0
    _, region = city_and_region(city or name)
    return {
        "name":         name,
        "chain":        infer_chain(name),
        "city":         city,
        "region":       region,
        "address":      "",
        "petrol_95":    p95,
        "diesel":       dies,
        "last_updated": datetime.date.today().isoformat(),
    }


def _parse_mbenzin_card(element) -> dict | None:
    full_text = element.get_text(separator=" ", strip=True)
    price_matches = re.findall(r"\b(\d{2}[,.]\d{1,2})\b", full_text)
    prices = [parse_price(p) for p in price_matches]
    prices = [p for p in prices if p is not None]
    if not prices:
        return None

    name_el = element.select_one(".name, .title, h3, h4, strong, b")
    name = name_el.get_text(strip=True) if name_el else ""
    if not name:
        return None

    city_el = element.select_one(".city, .mesto, .location, .town")
    city = city_el.get_text(strip=True) if city_el else ""
    _, region = city_and_region(city or name)
    return {
        "name":         name,
        "chain":        infer_chain(name),
        "city":         city,
        "region":       region,
        "address":      "",
        "petrol_95":    prices[0] if len(prices) > 0 else 0.0,
        "diesel":       prices[1] if len(prices) > 1 else 0.0,
        "last_updated": datetime.date.today().isoformat(),
    }


def _extract_json_stations(script_text: str) -> list[dict]:
    out: list[dict] = []
    for m in re.findall(r"\[(\{.+?\})\]", script_text, re.DOTALL):
        try:
            data = json.loads(f"[{m}]")
        except json.JSONDecodeError:
            continue
        for item in data:
            if not isinstance(item, dict):
                continue
            name = item.get("name") or item.get("nazev") or item.get("jmeno", "")
            city = item.get("city") or item.get("mesto") or item.get("obec", "")
            p95  = parse_price(str(item.get("natural95") or item.get("nm95") or item.get("benzin", "")))
            die  = parse_price(str(item.get("diesel")    or item.get("nafta") or item.get("on", "")))
            if name and (p95 or die):
                _, region = city_and_region(city or name)
                out.append({
                    "name":         name,
                    "chain":        infer_chain(name),
                    "city":         city,
                    "region":       region,
                    "address":      item.get("address") or item.get("adresa", ""),
                    "petrol_95":    p95 or 0.0,
                    "diesel":       die or 0.0,
                    "last_updated": datetime.date.today().isoformat(),
                })
    return out


# ── shared helpers ────────────────────────────────────────────────────────────

def infer_chain(name: str) -> str:
    n = name.lower()
    for kw, chain in [
        ("tank ono", "Tank ONO"), ("ono",     "Tank ONO"),
        ("shell",    "Shell"),    ("omv",     "OMV"),
        (" mol",     "MOL"),      ("mol ",    "MOL"),
        ("benzina",  "Benzina"),  ("orlen",   "Benzina"),
        ("eurooil",  "EuroOil"),  ("euro oil","EuroOil"),
        ("globus",   "Globus"),   ("čepro",   "ČEPRO"),
        ("cepro",    "ČEPRO"),
    ]:
        if kw in n:
            return chain
    return "Ostatní"


def compute_averages(stations: list[dict]) -> dict:
    p95  = [s["petrol_95"] for s in stations if s["petrol_95"] > 0]
    dies = [s["diesel"]    for s in stations if s["diesel"]    > 0]

    def safe_avg(lst: list[float]) -> float:
        return round(sum(lst) / len(lst), 2) if lst else 0.0

    return {"petrol_95": safe_avg(p95), "diesel": safe_avg(dies)}


def deduplicate(stations: list[dict]) -> list[dict]:
    seen: set[tuple] = set()
    out:  list[dict] = []
    for s in stations:
        key = (s["name"].lower().strip(), s["city"].lower().strip())
        if key not in seen:
            seen.add(key)
            out.append(s)
    return out


def add_ids(stations: list[dict]) -> list[dict]:
    for i, s in enumerate(stations, start=1):
        s["id"] = i
    return stations


# ── entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    print("Fetching Czech fuel prices …", file=sys.stderr)
    all_stations: list[dict] = []

    # Primary source
    all_stations.extend(scrape_tank_ono())
    time.sleep(1)

    # Secondary source
    all_stations.extend(scrape_mbenzin())

    if not all_stations:
        print(
            "[ERROR] No station data scraped from any source. "
            "Leaving existing data/prices.json unchanged.",
            file=sys.stderr,
        )
        sys.exit(1)

    all_stations = deduplicate(all_stations)
    all_stations = add_ids(all_stations)

    output = {
        "last_updated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "tank-ono.cz + mbenzin.cz",
        "averages": compute_averages(all_stations),
        "stations": all_stations,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as fh:
        json.dump(output, fh, ensure_ascii=False, indent=2)

    print(f"Saved {len(all_stations)} stations to {OUTPUT_PATH}", file=sys.stderr)


if __name__ == "__main__":
    main()
