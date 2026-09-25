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
