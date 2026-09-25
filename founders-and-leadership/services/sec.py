"""SEC EDGAR — public-company history and Form D private-offering evidence.

No API key needed, but SEC requires every request to carry a descriptive
User-Agent identifying the caller (name + contact email) or it will start
rate-limiting/blocking. Set SEC_USER_AGENT_EMAIL in the environment.

Docs:
  Full text search: https://efts.sec.gov/LATEST/search-index?q=...
  Company facts:     https://data.sec.gov/submissions/CIK##########.json
  Fair access policy: https://www.sec.gov/os/webmaster-faq#developers
"""

import os

import requests
from dotenv import load_dotenv

load_dotenv()

FULL_TEXT_SEARCH_URL = "https://efts.sec.gov/LATEST/search-index"
COMPANY_SEARCH_URL = "https://www.sec.gov/cgi-bin/browse-edgar"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik10}.json"


def _headers() -> dict:
    email = os.getenv("SEC_USER_AGENT_EMAIL") or "contact@example.com"
    return {"User-Agent": f"1435Capital FounderEvidenceGraph ({email})"}


def search_filings(query: str, forms: str | None = None, limit: int = 20) -> list[dict]:
    """Full-text search across EDGAR filings. Pass forms="D" to find Form D
    private-offering filings mentioning a company or person."""
    params = {"q": query}
    if forms:
        params["forms"] = forms

    response = requests.get(
        FULL_TEXT_SEARCH_URL, params=params, headers=_headers(), timeout=30
    )
    response.raise_for_status()

    hits = response.json().get("hits", {}).get("hits", [])
    return hits[:limit]


def to_evidence_claims(hits: list[dict]) -> list[dict]:
    """Normalize full-text-search hits into evidence-ready dicts (caller
    still needs entity_type/entity_id)."""
    claims = []
    for hit in hits:
        source = hit.get("_source", {})
        cik = (source.get("ciks") or [None])[0]
        claims.append(
            {
                "claim": f"{source.get('display_names', ['Unknown'])[0]} filed {source.get('root_forms', ['?'])[0]} on {source.get('file_date')}",
                "source_name": "SEC EDGAR",
                "source_url": f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}"
                if cik
                else None,
                "source_date": source.get("file_date"),
            }
        )
    return claims


def search_ciks_by_state(state: str, start: int = 0, count: int = 100) -> list[str]:
    """List CIKs of companies whose registered address is in `state` (a
    2-letter code, e.g. "NJ"). This is EDGAR's company-search endpoint, not
    full-text search - it's paginated via `start`.

    Known bug in this endpoint (confirmed 2026-09-25, not something we can
    fix): the atom feed's company name fields come back as a literal
    "ARRAY(0x...)" placeholder instead of the real name - a long-standing
    SEC-side quirk. Use get_company_name(cik) for the real name per CIK.
    """
    response = requests.get(
        COMPANY_SEARCH_URL,
        params={"action": "getcompany", "State": state, "SIC": "", "start": start, "count": count, "output": "atom"},
        headers=_headers(),
        timeout=30,
    )
    response.raise_for_status()

    import re

    return re.findall(r"<cik>(\d+)</cik>", response.text)


def get_company_name(cik: str) -> dict | None:
    """Fetch a company's real name/details by CIK, working around the
    company-search endpoint's broken name field."""
    cik10 = str(cik).zfill(10)
    response = requests.get(
        SUBMISSIONS_URL.format(cik10=cik10),
        headers=_headers(),
        timeout=15,
    )
    if response.status_code == 404:
        return None
    response.raise_for_status()

    data = response.json()
    return {
        "cik": cik,
        "name": data.get("name"),
        "state": data.get("stateOfIncorporation"),
        "sic_description": data.get("sicDescription"),
        "url": f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}",
    }


def to_achievement_rows(hits: list[dict]) -> list[dict]:
    """Normalize full-text-search hits into rows for the `achievements`
    table (caller still needs to attach founder_id)."""
    rows = []
    for claim in to_evidence_claims(hits):
        rows.append(
            {
                "achievement": claim["claim"],
                "issuer": "SEC",
                "year": (claim.get("source_date") or "")[:4] or None,
                "source_name": claim["source_name"],
                "source_url": claim["source_url"],
            }
        )
    return rows
