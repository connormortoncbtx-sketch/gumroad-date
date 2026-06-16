"""
clean.py — Texas Construction Intelligence
Normalizes raw fetched data into clean, typed, consistent schemas.
Outputs clean CSVs + JSON to data/clean/.

Run after fetch.py:
  python scripts/clean.py
"""

import json
import re
import logging
import pandas as pd
from datetime import datetime, date
from pathlib import Path
from glob import glob

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

RAW_DIR   = Path("data/raw")
CLEAN_DIR = Path("data/clean")
CLEAN_DIR.mkdir(parents=True, exist_ok=True)

TODAY = datetime.utcnow().strftime("%Y%m%d")


# ── helpers ───────────────────────────────────────────────────────────────────

def latest_raw(prefix: str) -> Path | None:
    files = sorted(RAW_DIR.glob(f"{prefix}_*.json"), reverse=True)
    return files[0] if files else None


def load_raw(prefix: str) -> list:
    path = latest_raw(prefix)
    if not path:
        log.warning(f"No raw file found for prefix '{prefix}'")
        return []
    log.info(f"Loading {path}")
    return json.loads(path.read_text())


def to_float(val) -> float | None:
    if val is None:
        return None
    try:
        return float(str(val).replace(",", "").replace("$", "").strip())
    except (ValueError, TypeError):
        return None


def to_date(val) -> str | None:
    if not val:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(str(val)[:19], fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return str(val)[:10]


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(text).lower()).strip("_")


# ── clean contracts ───────────────────────────────────────────────────────────

def clean_contracts(raw: list) -> pd.DataFrame:
    log.info(f"Cleaning {len(raw)} contract records...")
    rows = []
    for r in raw:
        rows.append({
            "award_id":         r.get("Award ID"),
            "recipient":        r.get("Recipient Name"),
            "amount_usd":       to_float(r.get("Award Amount")),
            "description":      r.get("Description"),
            "start_date":       to_date(r.get("Start Date")),
            "end_date":         to_date(r.get("End Date")),
            "agency":           r.get("Awarding Agency"),
            "sub_agency":       r.get("Awarding Sub Agency"),
            "award_type":       r.get("Contract Award Type"),
            "state":            r.get("Place of Performance State Code"),
            "county":           r.get("Place of Performance County Name"),
            "city":             r.get("Place of Performance City Name"),
            "naics_code":       r.get("naics_code"),
            "naics_desc":       r.get("naics_description"),
        })

    df = pd.DataFrame(rows)

    # Drop nulls on key fields
    df = df.dropna(subset=["award_id", "amount_usd"])

    # Normalize text
    for col in ["recipient", "description", "agency", "county", "city"]:
        df[col] = df[col].astype(str).str.strip().str.title()

    # Filter out tiny awards (noise below $10k)
    df = df[df["amount_usd"] >= 10_000]

    # Sort
    df = df.sort_values("amount_usd", ascending=False).reset_index(drop=True)

    log.info(f"Contracts after cleaning: {len(df)} rows, ${df['amount_usd'].sum():,.0f} total value")
    return df


# ── clean permits ─────────────────────────────────────────────────────────────

# Unified column mapping: source_field -> standard_field per city
PERMIT_MAPS = {
    "Austin": {
        # permit id variants
        "permit_num":               "permit_id",
        "permitnum":                "permit_id",
        "permit_number":            "permit_id",
        # type variants
        "permit_type_desc":         "permit_type",
        "permit_type":              "permit_type",
        # description variants
        "description":              "description",
        "work_desc":                "description",
        # date variants
        "issued_date":              "issued_date",
        "issue_date":               "issued_date",
        # valuation variants
        "total_job_valuation":      "valuation_usd",
        "total_valuation":          "valuation_usd",
        "job_value":                "valuation_usd",
        # sqft variants
        "total_new_add_sqft":       "sq_ft",
        "total_sq_ft":              "sq_ft",
        "sq_ft":                    "sq_ft",
        "total_existing_bldg_sqft": "sq_ft",
        # location
        "latitude":                 "lat",
        "longitude":                "lon",
        "original_address_1":       "address",
        "address":                  "address",
        "original_zip":             "zip",
        "zip":                      "zip",
        "council_district":         "district",
        "permit_class_mapped":      "permit_class",
        "permit_class":             "permit_class",
    },
    "Houston": {
        "permit_number":        "permit_id",
        "permit_type":          "permit_type",
        "work_description":     "description",
        "date_issued":          "issued_date",
        "declared_valuation":   "valuation_usd",
        "proj_area":            "sq_ft",
        "latitude":             "lat",
        "longitude":            "lon",
        "address":              "address",
        "zip_code":             "zip",
        "council_district":     "district",
    },
    "Dallas": {
        "permit_num":           "permit_id",
        "permit_type":          "permit_type",
        "description":          "description",
        "issueddate":           "issued_date",
        "valuation":            "valuation_usd",
        "sqfeet":               "sq_ft",
        "latitude":             "lat",
        "longitude":            "lon",
        "address":              "address",
        "zipcode":              "zip",
    },
}

# Permit types to keep (construction-relevant only)
KEEP_KEYWORDS = [
    "commercial", "industrial", "new construct", "addition",
    "demolition", "mechanical", "electrical", "foundation",
    "grading", "site work", "paving", "bridge", "structure",
    "warehouse", "manufacturing", "office", "retail",
]

def clean_permits(raw: list) -> pd.DataFrame:
    log.info(f"Cleaning {len(raw)} permit records...")
    frames = []

    for city, mapping in PERMIT_MAPS.items():
        city_raw = [r for r in raw if r.get("_source_city") == city]
        if not city_raw:
            continue

        df = pd.DataFrame(city_raw)
        log.info(f"  {city} raw columns: {list(df.columns)}")

        # Rename only columns that actually exist in this batch
        rename = {k: v for k, v in mapping.items() if k in df.columns}
        df = df.rename(columns=rename)

        # Keep standard columns that exist plus source city
        std_cols = list(set(mapping.values()) | {"_source_city"})
        df = df[[c for c in std_cols if c in df.columns]]
        df["city"] = city
        frames.append(df)

    if not frames:
        return pd.DataFrame()

    df = pd.concat(frames, ignore_index=True)

    # Type conversions
    df["valuation_usd"] = df.get("valuation_usd", pd.Series()).apply(to_float)
    df["sq_ft"]         = df.get("sq_ft", pd.Series()).apply(to_float)
    df["lat"]           = pd.to_numeric(df.get("lat", pd.Series()), errors="coerce")
    df["lon"]           = pd.to_numeric(df.get("lon", pd.Series()), errors="coerce")
    df["issued_date"]   = df.get("issued_date", pd.Series()).apply(to_date)

    # Filter: keep only construction-relevant permit types
    if "permit_type" in df.columns and "description" in df.columns:
        kw_pattern = "|".join(KEEP_KEYWORDS)
        mask = (
            df["permit_type"].str.lower().str.contains(kw_pattern, na=False) |
            df["description"].str.lower().str.contains(kw_pattern, na=False)
        )
        df = df[mask]

    # Filter: remove sub-$5k valuations (noise)
    df = df[df["valuation_usd"].fillna(0) >= 5_000]

    # Sort by valuation
    df = df.sort_values("valuation_usd", ascending=False).reset_index(drop=True)

    log.info(f"Permits after cleaning: {len(df)} rows, ${df['valuation_usd'].sum():,.0f} total valuation")
    return df


# ── summary stats (used by report generator) ─────────────────────────────────

def compute_summary(contracts_df: pd.DataFrame, permits_df: pd.DataFrame) -> dict:
    summary = {
        "generated_at": datetime.utcnow().isoformat(),
        "contracts": {},
        "permits": {},
    }

    if not contracts_df.empty:
        summary["contracts"] = {
            "total_count":   int(len(contracts_df)),
            "total_value":   float(contracts_df["amount_usd"].sum()),
            "avg_value":     float(contracts_df["amount_usd"].mean()),
            "top_recipient": contracts_df.iloc[0]["recipient"] if len(contracts_df) else None,
            "top_amount":    float(contracts_df.iloc[0]["amount_usd"]) if len(contracts_df) else 0,
            "by_naics": (
                contracts_df.groupby("naics_desc")["amount_usd"]
                .sum().sort_values(ascending=False).head(10).to_dict()
            ),
            "by_county": (
                contracts_df.groupby("county")["amount_usd"]
                .sum().sort_values(ascending=False).head(10).to_dict()
            ),
        }

    if not permits_df.empty:
        summary["permits"] = {
            "total_count":     int(len(permits_df)),
            "total_valuation": float(permits_df["valuation_usd"].sum()),
            "avg_valuation":   float(permits_df["valuation_usd"].mean()),
            "by_city": (
                permits_df.groupby("city")["valuation_usd"]
                .sum().sort_values(ascending=False).to_dict()
            ),
            "by_type": (
                permits_df.groupby("permit_type")["valuation_usd"]
                .sum().sort_values(ascending=False).head(10).to_dict()
            ),
            "top_projects": permits_df.head(20)[[
                "permit_id", "city", "address", "permit_type",
                "valuation_usd", "sq_ft", "issued_date"
            ]].to_dict(orient="records"),
        }

    return summary


# ── entrypoint ────────────────────────────────────────────────────────────────

def main():
    log.info("=== TX Construction Intel — clean.py ===")

    # Load raw
    contracts_raw = load_raw("usaspending_contracts")
    permits_raw   = load_raw("tx_permits_combined")

    # Clean
    contracts_df = clean_contracts(contracts_raw) if contracts_raw else pd.DataFrame()
    permits_df   = clean_permits(permits_raw)     if permits_raw   else pd.DataFrame()

    # Save clean CSVs (these are the product files)
    if not contracts_df.empty:
        path = CLEAN_DIR / f"tx_contracts_{TODAY}.csv"
        contracts_df.to_csv(path, index=False)
        log.info(f"Saved → {path}")

    if not permits_df.empty:
        path = CLEAN_DIR / f"tx_permits_{TODAY}.csv"
        permits_df.to_csv(path, index=False)
        log.info(f"Saved → {path}")

    # Save summary JSON (used by report generator)
    summary = compute_summary(contracts_df, permits_df)
    path = CLEAN_DIR / f"summary_{TODAY}.json"
    path.write_text(json.dumps(summary, indent=2, default=str))
    log.info(f"Saved → {path}")

    log.info("=== clean.py done ===")
    return contracts_df, permits_df, summary


if __name__ == "__main__":
    main()
