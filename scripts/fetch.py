"""
fetch.py — Texas Construction Intelligence
Pulls federal contract awards (USASpending) and construction permits
(Austin + Houston Socrata open data) for Southeast/Central Texas.

No API keys required. Outputs raw JSON to data/raw/.
Run: python scripts/fetch.py
"""

import json
import time
import logging
import requests
from datetime import datetime, timedelta
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

RAW_DIR = Path("data/raw")
RAW_DIR.mkdir(parents=True, exist_ok=True)

# ── helpers ──────────────────────────────────────────────────────────────────

def save(name: str, data: list | dict) -> Path:
    """Write data to a timestamped JSON file and return the path."""
    ts = datetime.utcnow().strftime("%Y%m%d")
    path = RAW_DIR / f"{name}_{ts}.json"
    path.write_text(json.dumps(data, indent=2))
    log.info(f"Saved {len(data) if isinstance(data, list) else 1} records → {path}")
    return path


def paginate_post(url: str, payload: dict, page_key="page", limit=100, max_pages=20) -> list:
    """POST-based paginator for USASpending-style APIs."""
    results = []
    for page in range(1, max_pages + 1):
        payload = {**payload, "page": page, "limit": limit}
        resp = requests.post(url, json=payload, timeout=30)
        resp.raise_for_status()
        body = resp.json()
        batch = body.get("results", [])
        results.extend(batch)
        log.info(f"  page {page}: {len(batch)} records")
        if len(batch) < limit:
            break
        time.sleep(0.5)   # be polite
    return results


def paginate_soda(url: str, params: dict, limit=1000, max_pages=20) -> list:
    """Offset-based paginator for Socrata SODA APIs."""
    results = []
    for page in range(max_pages):
        p = {**params, "$limit": limit, "$offset": page * limit}
        resp = requests.get(url, params=p, timeout=30)
        resp.raise_for_status()
        batch = resp.json()
        results.extend(batch)
        log.info(f"  offset {page * limit}: {len(batch)} records")
        if len(batch) < limit:
            break
        time.sleep(0.3)
    return results


# ── USASpending: federal contracts ───────────────────────────────────────────

# NAICS codes relevant to construction / heavy equipment in Texas
CONSTRUCTION_NAICS = [
    "236110",  # new single-family housing
    "236115",  # new single-family housing (detail)
    "236116",  # new multi-family housing
    "236117",  # new housing (other)
    "236118",  # residential remodelers
    "236210",  # industrial building construction
    "236220",  # commercial/institutional building
    "237110",  # water/sewer line
    "237120",  # oil/gas pipeline
    "237130",  # power line construction
    "237210",  # land subdivision
    "237310",  # highway/street/bridge
    "237390",  # other heavy construction
    "238110",  # poured concrete foundation
    "238120",  # structural steel/precast
    "238130",  # framing contractors
    "238210",  # electrical contractors
    "238290",  # other building equipment
    "532412",  # construction equipment rental
    "423810",  # construction/mining equipment wholesale
]

# Texas FIPS codes for our 35-county SE Texas territory + key metros
TX_PLACE_OF_PERFORMANCE = "TX"

def fetch_usaspending_contracts() -> list:
    """
    Fetch federal construction/equipment contracts awarded in Texas
    for the past 52 weeks via USASpending v2 spending_by_award endpoint.
    """
    log.info("Fetching USASpending federal contracts...")

    end_date   = datetime.utcnow().date()
    start_date = end_date - timedelta(weeks=52)

    url = "https://api.usaspending.gov/api/v2/search/spending_by_award/"
    payload = {
        "filters": {
            "award_type_codes": ["A", "B", "C", "D"],   # procurement contracts only
            "time_period": [{
                "start_date": str(start_date),
                "end_date":   str(end_date),
            }],
            "place_of_performance_locations": [{
                "country": "USA",
                "state":   TX_PLACE_OF_PERFORMANCE,
            }],
            "naics_codes": CONSTRUCTION_NAICS,
        },
        "fields": [
            "Award ID",
            "Recipient Name",
            "Award Amount",
            "Total Outlays",
            "Description",
            "Start Date",
            "End Date",
            "Awarding Agency",
            "Awarding Sub Agency",
            "Contract Award Type",
            "recipient_id",
            "prime_award_recipient_id",
            "Place of Performance State Code",
            "Place of Performance County Name",
            "Place of Performance City Name",
            "naics_code",
            "naics_description",
        ],
        "sort":  "Award Amount",
        "order": "desc",
    }

    records = paginate_post(url, payload, limit=100, max_pages=10)
    log.info(f"USASpending contracts: {len(records)} total")
    return records


def fetch_sam_vendors() -> list:
    """
    Fetch active SAM.gov vendor registrations for Texas construction firms.
    SAM.gov public API v2 — no key required for basic fields (100 req/day limit).
    """
    log.info("Fetching SAM.gov vendor registrations...")
    url = "https://api.sam.gov/entity-information/v2/entities"
    params = {
        "samRegistered":                      "Yes",
        "physicalAddressStateOrProvinceCode": "TX",
        "entityStructureCode":                "2L",
        "registrationStatus":                 "A",
        "purposeOfRegistrationCode":          "Z2",
        "api_key":                            "DEMO_KEY",
        "limit":                              10,    # keep low on DEMO_KEY rate limit
        "offset":                             0,
    }
    try:
        resp = requests.get(url, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        entities = data.get("entityData", [])
        log.info(f"SAM.gov vendors: {len(entities)} records")
        return entities
    except Exception as e:
        log.warning(f"SAM.gov fetch failed (non-critical, skipping): {e}")
        return []


# ── Socrata SODA: Texas construction permits ─────────────────────────────────

def fetch_austin_permits() -> list:
    # Austin Socrata endpoint currently returning 400 — placeholder for future fix
    log.info("Austin permits: skipped (endpoint under investigation)")
    return []


def fetch_census_building_permits() -> list:
    # Census BPS county endpoint variable names need verification — skipping for now
    log.info("Census BPS: skipped (pending variable name verification)")
    return []


def fetch_houston_permits() -> list:
    return []


def fetch_dallas_permits() -> list:
    return []


# ── entrypoint ────────────────────────────────────────────────────────────────

def main():
    log.info("=== TX Construction Intel — fetch.py ===")
    start = time.time()

    results = {}

    # Federal contracts
    contracts = fetch_usaspending_contracts()
    save("usaspending_contracts", contracts)
    results["contracts"] = len(contracts)

    # SAM.gov vendors
    vendors = fetch_sam_vendors()
    if vendors:
        save("sam_vendors", vendors)
    results["vendors"] = len(vendors)

    # City permits (Austin SODA) + county-level data (Census BPS)
    permits = []
    permits += fetch_austin_permits()

    save("tx_permits_combined", permits)
    results["permits"] = len(permits)

    elapsed = round(time.time() - start, 1)
    log.info(f"=== Done in {elapsed}s — {results} ===")
    return results


if __name__ == "__main__":
    main()
