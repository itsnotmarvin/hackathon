"""Wikidata — notable-person lookup: awards received, birth date, education.

Public SPARQL endpoint, no key required. Only returns something for people
notable enough to have a Wikidata item, so this will miss most early-stage
founders — treat a hit as a bonus signal, not an absence-of-hit penalty.

Docs: https://www.wikidata.org/wiki/Wikidata:SPARQL_query_service
"""

import requests

SPARQL_URL = "https://query.wikidata.org/sparql"

_PERSON_QUERY = """
SELECT ?person ?personLabel ?birthDate ?awardLabel ?educatedAtLabel WHERE {{
  ?person rdfs:label "{name}"@en.
  ?person wdt:P31 wd:Q5.
  OPTIONAL {{ ?person wdt:P569 ?birthDate. }}
  OPTIONAL {{ ?person wdt:P166 ?award. }}
  OPTIONAL {{ ?person wdt:P69 ?educatedAt. }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
}}
LIMIT 25
"""


def search_person(name: str) -> list[dict]:
    """Exact-label match on a person's name. Returns one row per
    award/education fact found (a real person can produce several rows)."""
    query = _PERSON_QUERY.format(name=name.replace('"', ""))

    response = requests.get(
        SPARQL_URL,
        params={"query": query, "format": "json"},
        headers={"User-Agent": "1435Capital-FounderEvidenceGraph/1.0"},
        timeout=30,
    )
    response.raise_for_status()

    bindings = response.json().get("results", {}).get("bindings", [])
    rows = []
    for b in bindings:
        rows.append(
            {
                "wikidata_id": b.get("person", {}).get("value"),
                "name": b.get("personLabel", {}).get("value"),
                "birth_date": b.get("birthDate", {}).get("value"),
                "award": b.get("awardLabel", {}).get("value"),
                "educated_at": b.get("educatedAtLabel", {}).get("value"),
            }
        )
    return rows


def to_achievement_rows(rows: list[dict]) -> list[dict]:
    """Normalize award facts into rows for the `achievements` table (caller
    still needs to attach founder_id). Skips rows with no award."""
    out = []
    for row in rows:
        if not row.get("award"):
            continue
        out.append(
            {
                "achievement": row["award"],
                "issuer": None,
                "year": None,  # award date needs a qualifier-level SPARQL query; not fetched here
                "source_name": "Wikidata",
                "source_url": row.get("wikidata_id"),
            }
        )
    return out
