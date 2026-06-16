"""
fetch.py — Texas Construction Intelligence
Uses the USASpending bulk download endpoint to get full contract data
with no row limits and complete geographic fields.

No API keys required.
Run: python scripts/fetch.py
"""

import csv
import io
import json
import logging
import time
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

RAW_DIR   = Path("data/raw")
RAW_DIR.mkdir(parents=True, exist_ok=True)

TODAY = datetime.utcnow().strftime("%Y%m%d")

# Construction + heavy equipment NAICS codes
CONSTRUCTION_NAICS = [
    "236110","236115","236116","236117","236118",
    "236210","236220","237110","237120","237130",
    "237210","237310","237390","238110","238120",
    "238130","238210","238290","532412","423810",
]


def fetch_usaspending_download() -> list:
    """
    Request a bulk download from USASpending, poll until ready,
    then parse the contracts CSV from the ZIP.
    Returns a list of dicts with full geographic and contractor fields.
    """
    log.info("Requesting USASpending bulk download...")

    end_date   = datetime.utcnow().date()
    start_date = end_date - timedelta(weeks=26)

    # Step 1: Request the download
    # agencies is required — "all" means no agency filter applied
    resp = requests.post(
        "https://api.usaspending.gov/api/v2/bulk_download/awards/",
        json={
            "file_format": "csv",
            "filters": {
                "agencies": [{"type": "awarding", "tier": "toptier", "name": "All"}],
                "prime_award_types": ["A", "B", "C", "D"],
                "date_type": "action_date",
                "date_range": {
                    "start_date": str(start_date),
                    "end_date":   str(end_date),
                },
                "place_of_performance_locations": [{"country": "USA", "state": "TX"}],
                "keyword": "construction",
            },
        },
        timeout=60,
    )
    resp.raise_for_status()
    body       = resp.json()
    file_url   = body.get("file_url")
    status_url = body.get("status_url")
    log.info(f"Download requested — status: {body.get('status')} | url: {file_url}")

    # Step 2: Poll until the file is ready (max 10 minutes)
    if status_url:
        for attempt in range(80):
            time.sleep(15)
            sr = requests.get(status_url, timeout=30)
            sr.raise_for_status()
            sb    = sr.json()
            state = sb.get("status", "")
            log.info(f"  Poll {attempt+1}: {state}")
            if state == "finished":
                file_url = sb.get("file_url", file_url)
                break
            if state in ("failed", "error"):
                raise RuntimeError(f"Download failed: {sb}")
        else:
            raise RuntimeError("Download timed out after 10 minutes")

    # Step 3: Download and unzip
    log.info(f"Downloading ZIP from {file_url}")
    dl = requests.get(file_url, timeout=300, stream=True)
    dl.raise_for_status()

    zip_bytes = io.BytesIO(dl.content)
    records   = []

    with zipfile.ZipFile(zip_bytes) as zf:
        # Find the contracts CSV (usually named Contracts_Prime_Awards_*.csv)
        csv_files = [n for n in zf.namelist() if n.endswith(".csv") and "contract" in n.lower()]
        if not csv_files:
            csv_files = [n for n in zf.namelist() if n.endswith(".csv")]
        log.info(f"ZIP contents: {zf.namelist()}")

        for csv_name in csv_files[:1]:   # take the first contracts CSV
            log.info(f"Parsing {csv_name}...")
            with zf.open(csv_name) as f:
                reader = csv.DictReader(io.TextIOWrapper(f, encoding="utf-8-sig"))
                for row in reader:
                    records.append(dict(row))

    log.info(f"Parsed {len(records):,} records from download")
    return records


def save_raw(name: str, data: list) -> Path:
    path = RAW_DIR / f"{name}_{TODAY}.json"
    path.write_text(json.dumps(data, indent=2, default=str))
    log.info(f"Saved {len(data):,} records → {path}")
    return path


def main():
    log.info("=== TX Construction Intel — fetch.py ===")
    start = time.time()

    contracts = fetch_usaspending_download()
    save_raw("usaspending_contracts", contracts)

    elapsed = round(time.time() - start, 1)
    log.info(f"=== Done in {elapsed}s — {len(contracts):,} contracts ===")
    return contracts


if __name__ == "__main__":
    main()
