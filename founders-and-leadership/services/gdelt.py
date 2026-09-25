"""GDELT DOC 2.0 API — global news-article search, for the award/press-
mention signals that Wikidata and PDL don't capture (most founders will
never be notable enough for Wikidata, but a local news writeup or an
industry-award announcement is exactly what this catches). No key required.

Confirmed live 2026-09-25. Responses can be genuinely slow (10-20s), hence
the longer timeout below — don't shorten it without re-testing.

Docs: https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/
"""

import requests

DOC_SEARCH_URL = "https://api.gdeltproject.org/api/v2/doc/doc"


def search_articles(query: str, max_records: int = 10) -> list[dict]:
    """Full-text news search. Quote multi-word names/phrases yourself if you
    want an exact phrase match, e.g. '"Jane Smith" award'."""
    response = requests.get(
        DOC_SEARCH_URL,
        params={"query": query, "mode": "artlist", "format": "json", "maxrecords": max_records},
        timeout=30,
    )
    response.raise_for_status()

    if not response.text.strip():
        return []
    return response.json().get("articles", []) or []


def to_achievement_rows(articles: list[dict]) -> list[dict]:
    """Normalize news hits into rows for the `achievements` table (caller
    still needs to attach founder_id). This is a noisy, high-recall signal —
    a headline mentioning someone is a lead to check, not confirmed fact."""
    rows = []
    for article in articles:
        title = article.get("title")
        if not title:
            continue
        rows.append(
            {
                "achievement": f"News mention: {title}",
                "issuer": article.get("domain"),
                "year": (article.get("seendate") or "")[:4] or None,
                "source_name": "GDELT",
                "source_url": article.get("url"),
            }
        )
    return rows
