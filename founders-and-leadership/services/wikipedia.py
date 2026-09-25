"""Wikipedia — short bio context for a notable founder, complementing
Wikidata's structured facts with the actual summary text. No key required.

Confirmed live 2026-09-25.

Docs: https://en.wikipedia.org/api/rest_v1/
"""

import requests

SUMMARY_URL = "https://en.wikipedia.org/api/rest_v1/page/summary/{title}"


def get_summary(name: str) -> dict | None:
    """Fetch the summary for a Wikipedia page matching this name exactly
    (spaces become underscores). Returns None if there's no such page —
    most founders won't have one, which is expected, not an error."""
    title = name.strip().replace(" ", "_")
    response = requests.get(
        SUMMARY_URL.format(title=title),
        headers={"User-Agent": "1435Capital-FounderEvidenceGraph/1.0"},
        timeout=15,
    )
    if response.status_code == 404:
        return None
    response.raise_for_status()

    data = response.json()
    if data.get("type") == "disambiguation":
        return None  # ambiguous name, not a confident match
    return data


def to_achievement_row(summary: dict) -> dict | None:
    """Normalize a Wikipedia summary into one row for the `achievements`
    table (caller still needs to attach founder_id)."""
    extract = summary.get("extract")
    if not extract:
        return None

    return {
        "achievement": extract[:500],
        "issuer": "Wikipedia",
        "year": None,
        "source_name": "Wikipedia",
        "source_url": summary.get("content_urls", {}).get("desktop", {}).get("page"),
    }
