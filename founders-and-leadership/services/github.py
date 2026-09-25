"""GitHub — technical track record for a founder: repos, stars, followers.

Unauthenticated requests work but are capped at 60/hr; set GITHUB_TOKEN
(a plain personal access token, no scopes needed for public data) to raise
that to 5,000/hr.

Docs: https://docs.github.com/en/rest
"""

import os

import requests
from dotenv import load_dotenv

load_dotenv()

API_ROOT = "https://api.github.com"


def _headers() -> dict:
    token = os.getenv("GITHUB_TOKEN")
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def get_user(username: str) -> dict | None:
    """Fetch a GitHub user's public profile by exact username (e.g. parsed
    out of a PDL github_url)."""
    response = requests.get(f"{API_ROOT}/users/{username}", headers=_headers(), timeout=30)
    if response.status_code == 404:
        return None
    response.raise_for_status()
    return response.json()


def get_top_repos(username: str, limit: int = 5) -> list[dict]:
    """Fetch this user's most-starred public repos."""
    response = requests.get(
        f"{API_ROOT}/users/{username}/repos",
        params={"sort": "pushed", "per_page": 100},
        headers=_headers(),
        timeout=30,
    )
    if response.status_code == 404:
        return []
    response.raise_for_status()

    repos = response.json()
    repos.sort(key=lambda r: r.get("stargazers_count", 0), reverse=True)
    return repos[:limit]


def to_achievement_row(user: dict, repos: list[dict]) -> dict | None:
    """Normalize a GitHub profile into one row for the `achievements` table
    (caller still needs to attach founder_id). Returns None for empty/near-
    empty accounts."""
    total_stars = sum(r.get("stargazers_count", 0) for r in repos)
    if not user.get("public_repos") and not total_stars:
        return None

    top_repo = repos[0]["name"] if repos else None
    summary = f"{user.get('public_repos', 0)} public repos, {total_stars} stars"
    if top_repo:
        summary += f" (top: {top_repo})"

    return {
        "achievement": summary,
        "issuer": "GitHub",
        "year": None,
        "source_name": "GitHub",
        "source_url": user.get("html_url"),
    }
