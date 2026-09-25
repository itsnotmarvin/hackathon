"""People Data Labs — founder identity, education, and employment enrichment.

Docs: https://docs.peopledatalabs.com/docs/person-enrichment-api
Requires PDL_API_KEY in the environment.
"""

import os

import requests
from dotenv import load_dotenv

load_dotenv()

PDL_ENRICH_URL = "https://api.peopledatalabs.com/v5/person/enrich"


class PDLError(RuntimeError):
    pass


def enrich_person(
    name: str,
    company: str | None = None,
    location: str | None = None,
    school: str | None = None,
    profile: str | None = None,
    min_likelihood: int = 6,
) -> dict | None:
    """Look up one person. Returns the PDL `data` payload, or None if no
    confident match was found (PDL returns HTTP 404 in that case)."""

    api_key = os.getenv("PDL_API_KEY")
    if not api_key:
        raise PDLError("PDL_API_KEY is missing")

    payload = {"name": name, "min_likelihood": min_likelihood}
    if company:
        payload["company"] = company
    if location:
        payload["location"] = location
    if school:
        payload["school"] = school
    if profile:
        payload["profile"] = profile

    response = requests.post(
        PDL_ENRICH_URL,
        headers={"X-Api-Key": api_key, "Content-Type": "application/json"},
        json=payload,
        timeout=30,
    )

    if response.status_code == 404:
        return None

    response.raise_for_status()
    return response.json().get("data")


def to_founder_fields(person: dict) -> dict:
    """Normalize a PDL person record into the columns on `founders`.

    Note on `birth_year`: this is a raw, sparsely-populated PDL field kept
    as context for a human reader, not an input to any "risk score" — there
    is no reliable public source for age, and none at all for personal
    wealth prior to founding, so don't try to derive either.
    """
    return {
        "linkedin_url": person.get("linkedin_url"),
        "github_url": person.get("github_url"),
        "location": person.get("location_name"),
        "identity_confidence": person.get("likelihood"),
        "birth_year": person.get("birth_year"),
    }


def to_education_rows(person: dict) -> list[dict]:
    """Normalize PDL `education` entries into rows for the `education` table
    (caller still needs to attach founder_id)."""
    rows = []
    for edu in person.get("education") or []:
        school = edu.get("school") or {}
        degrees = edu.get("degrees") or []
        majors = edu.get("majors") or []
        rows.append(
            {
                "institution": school.get("name"),
                "degree": degrees[0] if degrees else None,
                "field": majors[0] if majors else None,
                "start_year": edu.get("start_date"),
                "end_year": edu.get("end_date"),
                "source_name": "People Data Labs",
            }
        )
    return rows


def to_company_rows(person: dict) -> list[dict]:
    """Normalize PDL `experience` entries into rows for the `companies`
    table (caller still needs to attach founder_id)."""
    rows = []
    for job in person.get("experience") or []:
        org = job.get("company") or {}
        rows.append(
            {
                "company_name": org.get("name"),
                "role": job.get("title", {}).get("name") if isinstance(job.get("title"), dict) else job.get("title"),
                "start_date": job.get("start_date"),
                "end_date": job.get("end_date"),
                "status": "current" if job.get("is_primary") and not job.get("end_date") else None,
                "source_name": "People Data Labs",
            }
        )
    return rows
