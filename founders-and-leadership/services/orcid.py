"""ORCID public API — academic identity for research-oriented founders:
confirms a persistent researcher ID exists for this name. No key required
for the public API tier.

Confirmed live 2026-09-25.

Docs: https://info.orcid.org/documentation/api-tutorials/api-tutorial-searching-the-orcid-registry/
"""

import requests

SEARCH_URL = "https://pub.orcid.org/v3.0/expanded-search/"


def search_person(first_name: str, last_name: str) -> list[dict]:
    """Search ORCID's public registry by exact given/family name."""
    query = f'family-name:{last_name} AND given-names:{first_name}'
    response = requests.get(
        SEARCH_URL,
        params={"q": query},
        headers={"Accept": "application/json"},
        timeout=15,
    )
    response.raise_for_status()

    return response.json().get("expanded-result") or []


def to_achievement_row(result: dict) -> dict:
    """Normalize one ORCID match into a row for the `achievements` table
    (caller still needs to attach founder_id)."""
    orcid_id = result.get("orcid-id")
    return {
        "achievement": f"Has a registered ORCID researcher iD ({orcid_id})",
        "issuer": "ORCID",
        "year": None,
        "source_name": "ORCID",
        "source_url": f"https://orcid.org/{orcid_id}" if orcid_id else None,
    }
