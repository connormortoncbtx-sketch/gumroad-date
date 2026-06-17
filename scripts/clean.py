"""
clean.py — Texas Construction Intelligence
Normalizes USASpending bulk download CSV into a clean, enriched dataset.

Download CSV field names differ from the API — they use human-readable
column headers like "Award Amount" and "Place of Performance City Name".

Run: python scripts/clean.py
"""

import json
import logging
import re
from datetime import datetime
from pathlib import Path

import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

RAW_DIR   = Path("data/raw")
CLEAN_DIR = Path("data/clean")
CLEAN_DIR.mkdir(parents=True, exist_ok=True)

TODAY = datetime.utcnow().strftime("%Y%m%d")

# Map download CSV headers → our standard column names
# USASpending download uses verbose human-readable column names
FIELD_MAP = {
    # Award identity
    "contract_award_unique_key":             "award_id",
    "award_id_piid":                         "piid",

    # Recipient
    "recipient_name":                        "recipient",
    "recipient_doing_business_as_name":      "recipient_dba",
    "recipient_uei":                         "recipient_uei",
    "recipient_parent_name":                 "recipient_parent",

    # Recipient location
    "recipient_city_name":                   "recipient_city",
    "recipient_county_name":                 "recipient_county",
    "recipient_state_code":                  "recipient_state",
    "recipient_zip_4_code":                  "recipient_zip",

    # Place of performance
    "primary_place_of_performance_city_name":       "perf_city",
    "primary_place_of_performance_county_name":     "perf_county",
    "primary_place_of_performance_state_code":      "perf_state",
    "primary_place_of_performance_zip_4":           "perf_zip",
    "primary_place_of_performance_congressional_di":"perf_congressional_district",

    # Amounts
    "federal_action_obligation":             "obligation_usd",
    "current_total_value_of_award":          "total_value_usd",
    "potential_total_value_of_award":        "potential_value_usd",

    # Dates
    "action_date":                           "action_date",
    "period_of_performance_start_date":      "start_date",
    "period_of_performance_current_end_date":"end_date",

    # Agency
    "awarding_agency_name":                  "agency",
    "awarding_sub_agency_name":              "sub_agency",
    "awarding_office_name":                  "office",
    "funding_agency_name":                   "funding_agency",

    # Classification
    "naics_code":                            "naics_code",
    "naics_description":                     "naics_desc",
    "product_or_service_code":               "psc_code",
    "product_or_service_code_description":   "psc_desc",
    "type_of_contract_pricing":              "pricing_type",
    "award_type":                            "award_type",
    "contract_award_type":                   "contract_type",

    # Competition
    "extent_competed":                       "competition",
    "number_of_offers_received":             "offers_received",
    "small_business_competitiveness_demonst":"small_biz_competitive",

    # Business type
    "contracting_officers_determination_of_b":"business_size",
    "small_disadvantaged_business":          "sdb",
    "women_owned_small_business":            "wosb",
    "veteran_owned_business":                "vob",
    "service_disabled_veteran_owned_small_b": "sdvosb",

    # Description
    "award_description":                     "description",
}


def to_float(val) -> float | None:
    if val is None or str(val).strip() in ("", "nan", "None"):
        return None
    try:
        return float(str(val).replace(",", "").replace("$", "").strip())
    except (ValueError, TypeError):
        return None


def to_date(val) -> str | None:
    if not val or str(val).strip() in ("", "nan", "None"):
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(str(val).strip()[:10], fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return str(val).strip()[:10]


def clean_text(val) -> str:
    if not val or str(val).strip() in ("", "nan", "None"):
        return ""
    return str(val).strip().title()


def load_raw(prefix: str) -> list:
    files = sorted(RAW_DIR.glob(f"{prefix}_*.json"), reverse=True)
    if not files:
        log.warning(f"No raw file found for {prefix}")
        return []
    log.info(f"Loading {files[0]}")
    return json.loads(files[0].read_text())


def clean_contracts(raw: list) -> pd.DataFrame:
    log.info(f"Cleaning {len(raw):,} raw contract records...")

    if not raw:
        return pd.DataFrame()

    df = pd.DataFrame(raw)

    # Normalize column names: lowercase + underscores
    df.columns = [c.lower().strip().replace(" ", "_").replace("-", "_")
                  .replace("(", "").replace(")", "").replace("/", "_")
                  .replace(".", "").replace(",", "") for c in df.columns]

    log.info(f"Raw columns sample: {list(df.columns)[:10]}")

    # Apply field mapping
    rename = {k: v for k, v in FIELD_MAP.items() if k in df.columns}
    df = df.rename(columns=rename)
    log.info(f"Mapped {len(rename)} columns")

    # Keep only our standard columns that exist
    keep = list(set(FIELD_MAP.values()))
    df   = df[[c for c in keep if c in df.columns]].copy()

    # Type conversions
    for col in ["obligation_usd", "total_value_usd", "potential_value_usd"]:
        if col in df.columns:
            df[col] = df[col].apply(to_float)

    for col in ["action_date", "start_date", "end_date"]:
        if col in df.columns:
            df[col] = df[col].apply(to_date)

    for col in ["recipient", "recipient_dba", "recipient_parent",
                "recipient_city", "recipient_county",
                "perf_city", "perf_county", "agency", "sub_agency",
                "office", "description"]:
        if col in df.columns:
            df[col] = df[col].apply(clean_text)

    # Filter by NAICS — construction and heavy equipment codes
    CONSTRUCTION_NAICS = {
        "236110","236115","236116","236117","236118",
        "236210","236220","237110","237120","237130",
        "237210","237310","237390","238110","238120",
        "238130","238210","238290","532412","423810",
    }
    if "naics_code" in df.columns:
        before = len(df)
        mask = df["naics_code"].astype(str).str.strip().isin(CONSTRUCTION_NAICS)
        df = df[mask]
        log.info(f"NAICS filter: kept {len(df):,} of {before:,} records")

    # Filter: keep only positive obligations >= $10k
    if "obligation_usd" in df.columns:
        before = len(df)
        df = df[df["obligation_usd"].fillna(0) >= 10_000]
        log.info(f"Filtered {before - len(df)} records below $10k threshold")

    # Sort by obligation
    if "obligation_usd" in df.columns:
        df = df.sort_values("obligation_usd", ascending=False)

    df = df.reset_index(drop=True)
    log.info(f"Contracts after cleaning: {len(df):,} rows")
    if "perf_county" in df.columns:
        nonblank = (df["perf_county"].str.strip() != "").sum()
        log.info(f"perf_county populated: {nonblank}/{len(df)} rows")
    if "perf_city" in df.columns:
        nonblank = (df["perf_city"].str.strip() != "").sum()
        log.info(f"perf_city populated: {nonblank}/{len(df)} rows")
    if "obligation_usd" in df.columns:
        log.info(f"Total obligation value: ${df['obligation_usd'].sum():,.0f}")

    return df


def compute_summary(df: pd.DataFrame) -> dict:
    if df.empty:
        return {"generated_at": datetime.utcnow().isoformat(), "contracts": {}}

    c = {}
    val_col = "obligation_usd" if "obligation_usd" in df.columns else None

    c["total_count"] = int(len(df))

    if val_col:
        c["total_value"]  = float(df[val_col].sum())
        c["avg_value"]    = float(df[val_col].mean())
        c["median_value"] = float(df[val_col].median())

    if "recipient" in df.columns and val_col:
        top_r = df.groupby("recipient")[val_col].sum().sort_values(ascending=False).head(15)
        c["by_recipient"] = top_r.to_dict()
        c["top_recipient"] = top_r.index[0] if len(top_r) else ""
        c["top_recipient_value"] = float(top_r.iloc[0]) if len(top_r) else 0

    for col, key in [("perf_county", "by_county"), ("perf_city", "by_city"),
                     ("naics_desc", "by_naics"), ("agency", "by_agency"),
                     ("psc_desc", "by_psc")]:
        if col in df.columns and val_col:
            grp = df.groupby(col)[val_col].sum().sort_values(ascending=False).head(15)
            # Drop blank keys
            grp = grp[grp.index.str.strip() != ""]
            c[key] = grp.to_dict()

    if "perf_county" in df.columns and val_col:
        c["top_county"] = list(c.get("by_county", {}).keys())[:1]

    # Top 25 contracts for the PDF
    display_cols = [col for col in [
        "award_id", "recipient", "obligation_usd", "description",
        "perf_city", "perf_county", "perf_state", "perf_zip",
        "agency", "sub_agency", "naics_code", "naics_desc",
        "psc_code", "action_date", "start_date", "end_date",
        "contract_type", "competition", "offers_received",
    ] if col in df.columns]

    c["top_contracts"] = df[display_cols].head(25).to_dict(orient="records")

    return {
        "generated_at": datetime.utcnow().isoformat(),
        "contracts":    c,
        "permits":      {},
    }


def main():
    log.info("=== TX Construction Intel — clean.py ===")

    raw       = load_raw("usaspending_contracts")
    contracts = clean_contracts(raw)

    if not contracts.empty:
        path = CLEAN_DIR / f"tx_contracts_{TODAY}.csv"
        contracts.to_csv(path, index=False)
        log.info(f"Saved → {path}")

    summary = compute_summary(contracts)
    path    = CLEAN_DIR / f"summary_{TODAY}.json"
    path.write_text(json.dumps(summary, indent=2, default=str))
    log.info(f"Saved → {path}")

    log.info("=== clean.py done ===")
    return contracts, summary


if __name__ == "__main__":
    main()
