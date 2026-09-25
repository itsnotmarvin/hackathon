"""NSF Award Search — federal research grants by the actual person (PI),
not just by company. Complements SBIR/USAspending in services/grants.py,
which are company-level. No key required.

Docs: https://www.research.gov/common/webapi/awardapisearch-v1.htm
"""

import requests

NSF_AWARDS_URL = "https://www.research.gov/awardapi-service/v1/awards.json"

FIELDS = "id,title,agency,awardeeName,startDate,expDate,estimatedTotalAmt,piFirstName,piLastName"


def search_awards_by_pi(first_name: str, last_name: str, rows: int = 25) -> list[dict]:
    """Look up NSF awards where this person is listed as PI."""
    response = requests.get(
        NSF_AWARDS_URL,
        params={
            "pdPIName": f"{last_name}, {first_name}",
            "printFields": FIELDS,
            "rpp": rows,
        },
        timeout=30,
    )
    response.raise_for_status()
    return response.json().get("response", {}).get("award", []) or []


def to_grant_rows(awards: list[dict]) -> list[dict]:
    """Normalize NSF awards into rows for the `grants` table (caller still
    needs to attach startup_id/founder_id)."""
    rows = []
    for award in awards:
        rows.append(
            {
                "program": "NSF Award",
                "agency": "National Science Foundation",
                "amount": award.get("estimatedTotalAmt"),
                "award_date": award.get("startDate"),
                "source_name": "NSF Award Search",
                "source_url": f"https://www.nsf.gov/awardsearch/showAward?AWD_ID={award.get('id')}"
                if award.get("id")
                else None,
            }
        )
    return rows
