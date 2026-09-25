"""Government funding signals: SBIR/STTR awards and broader federal spending.

SBIR.gov's public awards endpoint (api.www.sbir.gov) is BROKEN/BLOCKED as of
2026-09-25: every request, including a bare one with no params, returns
403 Forbidden with an AWS API Gateway "ForbiddenException" body — this is a
server-side access change (WAF/API-Gateway policy), not a bug in the request
we send. No public key-signup flow for this endpoint is documented, so
`search_sbir_awards` is kept here (in case that changes) but is NOT called
from the live research pipeline — see app/routes/founders.py. Don't re-wire
it in without re-verifying the endpoint responds first.

USAspending is genuinely public/keyless and confirmed working: award type
codes must all come from ONE group (contracts, grants, loans, ... — mixing
groups is a 422) and `time_period` is required.

SBIR docs:        https://www.sbir.gov/api  (see caveat above)
USAspending docs: https://api.usaspending.gov/
"""

import time

import requests

SBIR_AWARDS_URL = "https://api.www.sbir.gov/public/api/awards"
USASPENDING_SEARCH_URL = "https://api.usaspending.gov/api/v2/search/spending_by_award/"


def search_sbir_awards(company: str, rows: int = 50) -> list[dict]:
    """Look up SBIR/STTR awards for a company name.

    Currently returns 403 Forbidden for every request (see module docstring).
    Left implemented, unused by the live pipeline, in case SBIR.gov restores
    open access or publishes a key.
    """
    response = requests.get(
        SBIR_AWARDS_URL,
        params={"company": company, "rows": rows},
        timeout=30,
    )
    response.raise_for_status()
    return response.json() or []


def search_federal_awards(recipient_name: str, limit: int = 50, start_date: str = "2008-01-01") -> list[dict]:
    """Look up federal grants for a recipient via USAspending.

    award_type_codes must all belong to one group — this uses the "grants"
    group (Block/Formula/Project Grant, Cooperative Agreement). Use
    services/grants.py's SBIR/NSF/NIH helpers for research-specific awards;
    this one is the broad catch-all.
    """
    payload = {
        "filters": {
            "recipient_search_text": [recipient_name],
            "award_type_codes": ["02", "03", "04", "05"],
            "time_period": [{"start_date": start_date, "end_date": "2026-12-31"}],
        },
        "fields": [
            "Award ID",
            "Recipient Name",
            "Awarding Agency",
            "Award Amount",
            "Start Date",
            "End Date",
        ],
        "page": 1,
        "limit": limit,
        "sort": "Award Amount",
        "order": "desc",
    }
    response = requests.post(USASPENDING_SEARCH_URL, json=payload, timeout=30)
    response.raise_for_status()
    return response.json().get("results", [])


# Not just government - also excludes universities/nonprofits, since the
# goal here is companies. This is a name-pattern heuristic, not a real
# classification (USAspending doesn't expose recipient type cleanly in
# this endpoint) - it will both over- and under-exclude sometimes.
_GOV_NAME_MARKERS = (
    "STATE OF", "COUNTY OF", "COUNTY", "TOWNSHIP", "BOROUGH", "CITY OF",
    "DEPARTMENT OF", "DEPT OF", "DEPT.", "MUNICIPAL", "SCHOOL DISTRICT",
    "BOARD OF EDUCATION", "HOUSING AUTHORITY", "TRANSIT", "TRUSTEES OF",
    "UNIVERSITY", "COLLEGE", "REGENTS OF", "NEW JERSEY DEPT",
)


def search_nj_recipients(limit: int = 100, start_date: str = "2015-01-01") -> list[dict]:
    """List federal-award recipients located in New Jersey. This surfaces
    companies (and other organizations) that have received a federal grant
    or contract while headquartered in NJ - a real, free, keyless data
    source, but not remotely all NJ companies, only ones with federal
    award history. Government entities are filtered out heuristically by
    name pattern (see _GOV_NAME_MARKERS) since USAspending doesn't expose
    recipient type cleanly in this endpoint's fields - this heuristic is
    not perfect, review results before treating them as ground truth.

    Queries grants and contracts separately and merges them - USAspending
    rejects award_type_codes that mix groups (02/03/04/05 = grants,
    A/B/C/D = contracts) with a 422.
    """
    results = []
    for group in (["02", "03", "04", "05"], ["A", "B", "C", "D"]):
        payload = {
            "filters": {
                "recipient_locations": [{"country": "USA", "state": "NJ"}],
                "award_type_codes": group,
                "time_period": [{"start_date": start_date, "end_date": "2026-12-31"}],
            },
            "fields": ["Recipient Name", "Awarding Agency", "Award Amount", "Start Date"],
            "page": 1,
            "limit": limit,
            "sort": "Award Amount",
            "order": "desc",
        }
        # A broad state-wide query with no recipient-name filter is visibly
        # less stable on USAspending's side than a narrow search (confirmed
        # by testing - repeated 502s and read timeouts here, not seen on
        # the narrower services.grants.search_federal_awards). Retry with
        # backoff rather than assume the first attempt reflects reality.
        for attempt in range(3):
            try:
                response = requests.post(USASPENDING_SEARCH_URL, json=payload, timeout=60)
                response.raise_for_status()
                results.extend(response.json().get("results", []))
                break
            except (requests.exceptions.ReadTimeout, requests.exceptions.HTTPError):
                if attempt == 2:
                    raise
                time.sleep(3 * (attempt + 1))

    seen = set()
    companies = []
    for r in results:
        name = (r.get("Recipient Name") or "").strip()
        if not name or name in seen:
            continue
        if any(marker in name.upper() for marker in _GOV_NAME_MARKERS):
            continue
        seen.add(name)
        companies.append(r)
    return companies


def to_grant_rows_from_sbir(awards: list[dict]) -> list[dict]:
    """Normalize SBIR awards into rows for the `grants` table (caller still
    needs to attach startup_id/founder_id)."""
    rows = []
    for award in awards:
        rows.append(
            {
                "program": f"SBIR/STTR {award.get('phase', '')}".strip(),
                "agency": award.get("agency"),
                "amount": award.get("award_amount"),
                "award_date": award.get("proposal_award_date") or award.get("award_year"),
                "source_name": "SBIR.gov",
                "source_url": award.get("award_link"),
            }
        )
    return rows


def to_grant_rows_from_usaspending(awards: list[dict]) -> list[dict]:
    """Normalize USAspending results into rows for the `grants` table
    (caller still needs to attach startup_id/founder_id)."""
    rows = []
    for award in awards:
        rows.append(
            {
                "program": award.get("Award ID"),
                "agency": award.get("Awarding Agency"),
                "amount": award.get("Award Amount"),
                "award_date": award.get("Start Date"),
                "source_name": "USAspending.gov",
            }
        )
    return rows
