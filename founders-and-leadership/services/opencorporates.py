"""OpenCorporates — officer search for a founder's previous/current companies.

Docs: https://api.opencorporates.com/documentation/API-Reference

Confirmed live 2026-09-25: the officers/search endpoint returns 401
Unauthorized without a token — OpenCorporates locked most search endpoints
behind a paid API token years ago, there is no usable free tier for this
call. Get a token (or apply for their free tier for journalists/nonprofits/
open-data projects) and set OPENCORPORATES_API_KEY.
"""

import os

import requests
from dotenv import load_dotenv

load_dotenv()

OFFICER_SEARCH_URL = "https://api.opencorporates.com/v0.4/officers/search"


class OpenCorporatesError(RuntimeError):
    pass


def search_officers(name: str, jurisdiction_code: str | None = None, per_page: int = 30) -> list[dict]:
    """Search officers/directors/managers by name. `jurisdiction_code` narrows
    to a state, e.g. "us_nj" for New Jersey."""

    api_key = os.getenv("OPENCORPORATES_API_KEY")
    if not api_key:
        raise OpenCorporatesError(
            "OPENCORPORATES_API_KEY is missing — the officers/search endpoint "
            "requires a paid token, it 401s without one"
        )

    params = {"q": name, "per_page": per_page, "api_token": api_key}
    if jurisdiction_code:
        params["jurisdiction_code"] = jurisdiction_code

    response = requests.get(OFFICER_SEARCH_URL, params=params, timeout=30)
    response.raise_for_status()

    results = response.json().get("results", {})
    return [item["officer"] for item in results.get("officers", [])]


def to_company_rows(officers: list[dict]) -> list[dict]:
    """Normalize officer-search hits into rows for the `companies` table
    (caller still needs to attach founder_id)."""
    rows = []
    for officer in officers:
        company = officer.get("company") or {}
        rows.append(
            {
                "company_name": company.get("name"),
                "role": officer.get("position"),
                "start_date": officer.get("start_date"),
                "end_date": officer.get("end_date"),
                "status": company.get("current_status") or company.get("inactive") and "inactive",
                "source_name": "OpenCorporates",
                "source_url": officer.get("opencorporates_url"),
            }
        )
    return rows
