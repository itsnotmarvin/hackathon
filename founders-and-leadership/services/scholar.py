"""Semantic Scholar — publication/citation record for research-oriented
founders (deep-tech, biotech, hardware). No key required for light use;
set SEMANTIC_SCHOLAR_API_KEY to raise the rate limit.

Docs: https://api.semanticscholar.org/api-docs/graph
"""

import os

import requests
from dotenv import load_dotenv

load_dotenv()

AUTHOR_SEARCH_URL = "https://api.semanticscholar.org/graph/v1/author/search"


def search_author(name: str) -> list[dict]:
    """Search for an author by name. Returns candidate matches — names are
    not unique, so treat multiple hits as ambiguous rather than picking one
    blindly (cross-check with the founder's known field/company if possible)."""
    api_key = os.getenv("SEMANTIC_SCHOLAR_API_KEY")
    headers = {"x-api-key": api_key} if api_key else {}

    response = requests.get(
        AUTHOR_SEARCH_URL,
        params={"query": name, "fields": "authorId,name,paperCount,citationCount,hIndex,affiliations"},
        headers=headers,
        timeout=30,
    )
    response.raise_for_status()
    return response.json().get("data", []) or []


def to_achievement_row(author: dict) -> dict | None:
    """Normalize one author match into a row for the `achievements` table
    (caller still needs to attach founder_id). Returns None if there's
    nothing worth recording (no papers)."""
    if not author.get("paperCount"):
        return None

    return {
        "achievement": (
            f"{author.get('paperCount')} publications, "
            f"{author.get('citationCount')} citations, h-index {author.get('hIndex')}"
        ),
        "issuer": "Semantic Scholar",
        "year": None,
        "source_name": "Semantic Scholar",
        "source_url": f"https://www.semanticscholar.org/author/{author.get('authorId')}"
        if author.get("authorId")
        else None,
    }
