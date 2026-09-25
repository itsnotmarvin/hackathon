"""Discover NJ companies from free, keyless government data sources.

IMPORTANT - read before running: this does NOT give you "all NJ companies."
No free API does; that requires OpenCorporates' paid tier or NJ's own
business registry, which has no public API at all (web search form only).
What this actually gives you is two specific, real, free slices:

  1. SEC EDGAR  - companies registered with the SEC whose address is in NJ
                  (public companies and SEC-reporting private ones only -
                  most NJ startups will never appear here)
  2. USAspending - organizations located in NJ that have received a
                  federal grant or contract (heuristically filtered to
                  exclude government/university recipients - not perfect)

Output goes to a local CSV in this folder for review, NOT auto-merged into
the shared root startups.csv - that's a shared team file, and dumping
hundreds of SEC filers into it without review would be disruptive to
everyone else's work.

Usage (from founders-and-leadership/):
    .venv/Scripts/python scripts/discover_nj_companies.py --sec-limit 50
"""

import argparse
import csv
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services import grants, sec  # noqa: E402

OUTPUT_PATH = Path(__file__).resolve().parent.parent / "nj_companies_discovered.csv"


def discover_sec(limit: int) -> list[dict]:
    print(f"Fetching up to {limit} NJ-registered CIKs from SEC EDGAR...")
    ciks = sec.search_ciks_by_state("NJ", count=limit)
    print(f"  got {len(ciks)} CIKs, looking up real names (one call per CIK, this is slow by design - SEC rate-limits)...")

    companies = []
    for i, cik in enumerate(ciks, 1):
        info = sec.get_company_name(cik)
        if info and info.get("name"):
            companies.append(
                {
                    "company": info["name"],
                    "source": "SEC EDGAR",
                    "source_url": info["url"],
                    "detail": info.get("sic_description") or "",
                }
            )
        if i % 10 == 0:
            print(f"    {i}/{len(ciks)} looked up...")
        time.sleep(0.15)  # be polite to SEC's rate limits, we've hit them before this session
    return companies


def discover_usaspending(limit: int) -> list[dict]:
    print(f"Fetching up to {limit} NJ federal-award recipients from USAspending...")
    recipients = grants.search_nj_recipients(limit=limit)
    return [
        {
            "company": r["Recipient Name"],
            "source": "USAspending.gov",
            "source_url": "",
            "detail": r.get("Awarding Agency", ""),
        }
        for r in recipients
    ]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sec-limit", type=int, default=50, help="max SEC EDGAR companies to look up (one API call each)")
    parser.add_argument("--usaspending-limit", type=int, default=100, help="max USAspending awards to scan for NJ recipients")
    args = parser.parse_args()

    rows = discover_sec(args.sec_limit) + discover_usaspending(args.usaspending_limit)

    seen = set()
    unique_rows = []
    for row in rows:
        key = row["company"].strip().upper()
        if key in seen:
            continue
        seen.add(key)
        unique_rows.append(row)

    with open(OUTPUT_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["company", "source", "source_url", "detail"])
        writer.writeheader()
        writer.writerows(unique_rows)

    print(f"\n{len(unique_rows)} unique companies written to {OUTPUT_PATH}")
    print("Review this file, then manually add anything relevant to the shared startups.csv.")


if __name__ == "__main__":
    main()
