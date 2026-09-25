"""Pull SEC Form D filings and filter them down to New Jersey startups.

Form D is filed by a company when it raises a private round (Reg D). The SEC
publishes every filing as quarterly TSV data sets, which this script downloads,
joins, and filters to NJ-based operating companies (investment funds and real
estate vehicles are dropped by default).

Outputs (in --out):
    nj_formd_offerings.csv  one row per offering/round, latest amendment wins
    nj_formd_companies.csv  one row per company with funding totals and pace

Usage:
    python form_d_nj.py                      # 2021Q1 through the latest quarter
    python form_d_nj.py --start 2023q1 --end 2025q4
    python form_d_nj.py --young-only         # only companies incorporated <5 years before filing

Only uses the Python standard library. Set SEC_USER_AGENT to "Your Name you@email.com";
the SEC asks automated clients to identify themselves.
"""

import argparse
import csv
import io
import os
import sys
import time
import urllib.error
import urllib.request
import zipfile
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA_URL = "https://www.sec.gov/files/structureddata/data/form-d-data-sets/{q}_d.zip"
USER_AGENT = os.environ.get("SEC_USER_AGENT", "NJ Startup Signals hackathon research@example.com")

# INDUSTRYGROUPTYPE values that are funds, real estate, or other non-startup vehicles.
EXCLUDED_INDUSTRIES = {
    "Pooled Investment Fund",
    "Investing",
    "REITS and Finance",
    "Commercial",
    "Residential",
    "Other Real Estate",
    "Commercial Banking",
    "Investment Banking",
    "Insurance",
}
# Limited partnerships filing Form D are almost always fund or deal vehicles, not startups.
EXCLUDED_ENTITY_TYPES = {"Limited Partnership"}

csv.field_size_limit(sys.maxsize if sys.maxsize < 2**31 else 2**31 - 1)


def parse_quarter(s):
    s = s.lower().strip()
    year, q = s.split("q")
    return int(year), int(q)


def quarter_range(start, end):
    y, q = start
    while (y, q) <= end:
        yield f"{y}q{q}"
        y, q = (y + 1, 1) if q == 4 else (y, q + 1)


def current_quarter():
    today = date.today()
    return today.year, (today.month - 1) // 3 + 1


def download_quarter(q, cache_dir):
    """Return the path to the cached zip for quarter q, or None if the SEC hasn't published it."""
    path = cache_dir / f"{q}_d.zip"
    if path.exists():
        return path
    req = urllib.request.Request(DATA_URL.format(q=q), headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = resp.read()
    except urllib.error.HTTPError as e:
        if e.code in (403, 404):
            return None
        raise
    path.write_bytes(data)
    time.sleep(0.2)  # stay well under the SEC's 10 requests/second limit
    return path


def read_tsv(zf, name):
    member = next(m for m in zf.namelist() if m.upper().endswith(name))
    with zf.open(member) as f:
        text = io.TextIOWrapper(f, encoding="utf-8", errors="replace", newline="")
        yield from csv.DictReader(text, delimiter="\t", quoting=csv.QUOTE_NONE)


def to_amount(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None  # "Indefinite" or blank


def to_date(v, fmt):
    try:
        return datetime.strptime(v.strip(), fmt).date()
    except (AttributeError, ValueError):
        return None


def load_quarter(zip_path, include_all_industries):
    """Return {accession: filing dict} for NJ primary issuers in one quarter."""
    with zipfile.ZipFile(zip_path) as zf:
        issuers = {}
        for r in read_tsv(zf, "ISSUERS.TSV"):
            if r["IS_PRIMARYISSUER_FLAG"] == "YES" and r["STATEORCOUNTRY"] == "NJ":
                issuers[r["ACCESSIONNUMBER"]] = r
        if not issuers:
            return {}

        subs = {r["ACCESSIONNUMBER"]: r for r in read_tsv(zf, "FORMDSUBMISSION.TSV")
                if r["ACCESSIONNUMBER"] in issuers}

        people = defaultdict(list)
        for r in read_tsv(zf, "RELATEDPERSONS.TSV"):
            if r["ACCESSIONNUMBER"] in issuers:
                name = " ".join(p for p in (r["FIRSTNAME"], r["LASTNAME"]) if p).strip()
                roles = "/".join(x for x in (r["RELATIONSHIP_1"], r["RELATIONSHIP_2"], r["RELATIONSHIP_3"]) if x)
                if name:
                    people[r["ACCESSIONNUMBER"]].append(f"{name} ({roles})" if roles else name)

        filings = {}
        for o in read_tsv(zf, "OFFERING.TSV"):
            acc = o["ACCESSIONNUMBER"]
            if acc not in issuers:
                continue
            i, s = issuers[acc], subs.get(acc, {})
            if not include_all_industries and (o["INDUSTRYGROUPTYPE"] in EXCLUDED_INDUSTRIES
                                               or i["ENTITYTYPE"] in EXCLUDED_ENTITY_TYPES):
                continue
            filings[acc] = {
                "company": i["ENTITYNAME"].strip(),
                "cik": i["CIK"].lstrip("0"),
                "city": i["CITY"].strip().title(),
                "zip": i["ZIPCODE"].strip()[:5],
                "entity_type": i["ENTITYTYPE"],
                "incorporated": i["YEAROFINC_VALUE_ENTERED"] or i["YEAROFINC_TIMESPAN_CHOICE"],
                "young_company": i["YEAROFINC_TIMESPAN_CHOICE"] in ("withinFiveYears", "yetToBeFormed"),
                "industry": o["INDUSTRYGROUPTYPE"],
                "revenue_range": o["REVENUERANGE"],
                "first_sale_date": to_date(o["SALE_DATE"], "%Y-%m-%d"),
                "filing_date": to_date(s.get("FILING_DATE"), "%d-%b-%Y"),
                "is_amendment": o["ISAMENDMENT"] == "true",
                "total_offering": to_amount(o["TOTALOFFERINGAMOUNT"]),
                "amount_sold": to_amount(o["TOTALAMOUNTSOLD"]),
                "num_investors": int(o["TOTALNUMBERALREADYINVESTED"] or 0),
                "equity": o["ISEQUITYTYPE"] == "true",
                "debt": o["ISDEBTTYPE"] == "true",
                "exemptions": o["FEDERALEXEMPTIONS_ITEMS_LIST"],
                "related_people": "; ".join(people.get(acc, [])),
                "file_num": s.get("FILE_NUM", "").strip(),
                "accession": acc,
            }
        return filings


def dedupe_offerings(filings):
    """Amendments (D/A) share a file number with the original. Keep the latest filing per offering,
    since it carries the cumulative amount sold, but keep the earliest known first-sale date."""
    by_offering = {}
    for f in filings:
        key = f["file_num"] or f["accession"]
        prev = by_offering.get(key)
        if prev is None:
            by_offering[key] = f
            continue
        first_sale = min(d for d in (prev["first_sale_date"], f["first_sale_date"]) if d) \
            if (prev["first_sale_date"] or f["first_sale_date"]) else None
        newer = f if (f["filing_date"] or date.min) >= (prev["filing_date"] or date.min) else prev
        newer = dict(newer, first_sale_date=first_sale)
        by_offering[key] = newer
    return list(by_offering.values())


def months_between(a, b):
    return round((b - a).days / 30.44, 1)


def summarize_companies(offerings, as_of):
    by_cik = defaultdict(list)
    for o in offerings:
        by_cik[o["cik"]].append(o)

    rows = []
    for cik, offs in by_cik.items():
        offs.sort(key=lambda o: o["first_sale_date"] or o["filing_date"] or date.min)
        latest = offs[-1]
        dates = [o["first_sale_date"] or o["filing_date"] for o in offs]
        dates = [d for d in dates if d]
        raised = [o["amount_sold"] or 0 for o in offs]
        gaps = [months_between(a, b) for a, b in zip(dates, dates[1:])]
        recent_cutoff = date(as_of.year - 2, as_of.month, min(as_of.day, 28))
        rows.append({
            "company": latest["company"],
            "cik": cik,
            "city": latest["city"],
            "zip": latest["zip"],
            "industry": latest["industry"],
            "incorporated": latest["incorporated"],
            "young_company": latest["young_company"],
            "revenue_range": latest["revenue_range"],
            "num_offerings": len(offs),
            "total_raised": sum(raised),
            "largest_round": max(raised),
            "raised_last_24mo": sum(r for o, r in zip(offs, raised)
                                    if (o["first_sale_date"] or o["filing_date"] or date.min) >= recent_cutoff),
            "total_investors": sum(o["num_investors"] for o in offs),
            "first_raise": dates[0] if dates else None,
            "last_raise": dates[-1] if dates else None,
            "months_since_last_raise": months_between(dates[-1], as_of) if dates else None,
            "avg_months_between_raises": round(sum(gaps) / len(gaps), 1) if gaps else None,
            "related_people": latest["related_people"],
            "edgar_url": f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}&type=D",
        })
    rows.sort(key=lambda r: r["total_raised"], reverse=True)
    return rows


def write_csv(path, rows):
    if not rows:
        return
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--start", default="2021q1", help="first quarter, e.g. 2021q1")
    ap.add_argument("--end", default=None, help="last quarter (default: current quarter)")
    ap.add_argument("--out", default=str(HERE / "data"), help="output folder")
    ap.add_argument("--cache", default=str(HERE / "data" / "raw"), help="where downloaded zips are kept")
    ap.add_argument("--young-only", action="store_true", help="only companies incorporated within 5 years")
    ap.add_argument("--all-industries", action="store_true", help="keep funds and real estate")
    args = ap.parse_args()

    out_dir, cache_dir = Path(args.out), Path(args.cache)
    cache_dir.mkdir(parents=True, exist_ok=True)
    end = parse_quarter(args.end) if args.end else current_quarter()

    filings = []
    for q in quarter_range(parse_quarter(args.start), end):
        path = download_quarter(q, cache_dir)
        if path is None:
            print(f"{q}: not published yet, skipping")
            continue
        found = load_quarter(path, args.all_industries)
        filings.extend(found.values())
        print(f"{q}: {len(found)} NJ filings")

    offerings = dedupe_offerings(filings)
    if args.young_only:
        offerings = [o for o in offerings if o["young_company"]]
    offerings.sort(key=lambda o: (o["company"], o["first_sale_date"] or date.min))
    for o in offerings:
        o["filing_url"] = (f"https://www.sec.gov/Archives/edgar/data/{o['cik']}/"
                           f"{o['accession'].replace('-', '')}/")

    companies = summarize_companies(offerings, date.today())
    write_csv(out_dir / "nj_formd_offerings.csv", offerings)
    write_csv(out_dir / "nj_formd_companies.csv", companies)
    print(f"\n{len(offerings)} offerings from {len(companies)} NJ companies -> {out_dir}")


if __name__ == "__main__":
    main()
