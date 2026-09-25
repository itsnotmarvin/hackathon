"""Recompute derived metrics and validate the business-and-market-potential CSVs.

The raw inputs (headcount, founding year, scores, sector funding totals) were
collected by hand from company websites, LinkedIn, and public funding reports;
see scalability/scalability-notes.md and market-timing/sector-momentum-notes.md
for sources. This script only handles the parts that are computable:

  * headcount-data.csv: growth_rate = current_headcount / (as_of_year - founding_year)
  * business-model-scores.csv: checks every company from startups.csv is scored 1-5
  * sector-data.csv: prints year-over-year funding change per sector

Usage (from the repository root):
    python business-and-market-potential/scripts/compute_metrics.py [--as-of 2026] [--write]

Without --write it only reports; with --write it rewrites growth_rate in place.
"""

import argparse
import csv
from collections import defaultdict
from pathlib import Path

FOLDER = Path(__file__).resolve().parent.parent
ROOT = FOLDER.parent
STARTUPS = ROOT / "startups.csv"
HEADCOUNT = FOLDER / "scalability" / "headcount-data.csv"
SCORES = FOLDER / "business-model" / "business-model-scores.csv"
SECTORS = FOLDER / "market-timing" / "sector-data.csv"


def read_csv(path):
    """Read a CSV into (header, rows), tolerating spaces after commas in the header."""
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.reader(f, skipinitialspace=True)
        header = next(reader)
        rows = [dict(zip(header, row)) for row in reader if row]
    return header, rows


def startup_companies():
    _, rows = read_csv(STARTUPS)
    return [r["company"] for r in rows]


def growth_rate(headcount, founding_year, as_of):
    years = max(as_of - founding_year, 1)
    return round(headcount / years, 1)


def update_headcount(as_of, write):
    header, rows = read_csv(HEADCOUNT)
    changed = 0
    for r in rows:
        new = growth_rate(int(r["current_headcount"]), int(r["founding_year"]), as_of)
        if r["growth_rate"] != f"{new}":
            changed += 1
        r["growth_rate"] = f"{new}"
        print(f"  {r['company']:<20} {r['current_headcount']:>4} staff since "
              f"{r['founding_year']} -> {new:>5}/yr  scales_with_headcount={r['scales_with_headcount']}")

    if write and changed:
        with open(HEADCOUNT, "w", newline="", encoding="utf-8") as f:
            f.write(", ".join(header) + "\n")
            writer = csv.writer(f, lineterminator="\n")
            for r in rows:
                writer.writerow([r[h] for h in header])
    print(f"  {changed} growth_rate value(s) differ from file"
          + (" (written)" if write and changed else ""))
    return rows


def check_coverage(name, rows, companies):
    listed = {r["company"] for r in rows}
    missing = [c for c in companies if c not in listed]
    extra = sorted(listed - set(companies))
    ok = not missing and not extra
    print(f"  {name}: {'OK' if ok else 'MISMATCH'}"
          + (f" missing={missing}" if missing else "")
          + (f" extra={extra}" if extra else ""))
    return ok


def check_scores(companies):
    _, rows = read_csv(SCORES)
    ok = check_coverage("business-model-scores coverage", rows, companies)
    for r in rows:
        if r["score"] not in {"1", "2", "3", "4", "5"}:
            print(f"  bad score for {r['company']}: {r['score']!r}")
            ok = False
        elif not r["justification"].strip():
            print(f"  missing justification for {r['company']}")
            ok = False
    counts = defaultdict(int)
    for r in rows:
        counts[r["score"]] += 1
    print("  score distribution: " + ", ".join(f"{s}={counts[s]}" for s in sorted(counts)))
    return ok


def sector_momentum():
    _, rows = read_csv(SECTORS)
    by_sector = defaultdict(dict)
    for r in rows:
        if r["funding_total"]:
            by_sector[r["sector"]][r["date"]] = float(r["funding_total"])
    for sector, points in by_sector.items():
        if "2024" in points and "2025" in points:
            change = (points["2025"] - points["2024"]) / points["2024"] * 100
            print(f"  {sector:<36} ${points['2024']:>6.1f}B -> ${points['2025']:>6.1f}B  {change:+.0f}%")
    empty = [c for c in ("patent_filings", "job_postings") if not any(r[c] for r in rows)]
    if empty:
        print(f"  note: no data yet for {', '.join(empty)}")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--as-of", type=int, default=2026, help="year headcounts were observed")
    parser.add_argument("--write", action="store_true", help="rewrite growth_rate in headcount-data.csv")
    args = parser.parse_args()

    companies = startup_companies()
    print(f"Headcount growth (as of {args.as_of}):")
    headcount_rows = update_headcount(args.as_of, args.write)
    print("Validation:")
    ok = check_coverage("headcount-data coverage", headcount_rows, companies)
    ok = check_scores(companies) and ok
    print("Sector funding momentum (2024 -> 2025):")
    sector_momentum()
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
