"""College Scorecard (data.gov) — institution-level facts for a school a
founder attended: size, admission rate, etc. This is descriptive context for
an education row, not a prestige score — don't turn it into "good school = +N".

Works with the shared "DEMO_KEY" at low volume; get a free key at
https://api.data.gov/signup/ and set COLLEGE_SCORECARD_API_KEY for real use.

Docs: https://collegescorecard.ed.gov/data/api-documentation/
"""

import os

import requests
from dotenv import load_dotenv

load_dotenv()

SCHOOLS_URL = "https://api.data.gov/ed/collegescorecard/v1/schools"

FIELDS = ",".join(
    [
        "school.name",
        "school.city",
        "school.state",
        "latest.student.size",
        "latest.admissions.admission_rate.overall",
        "school.school_url",
    ]
)


def lookup_school(name: str) -> dict | None:
    """Fetch descriptive stats for a school by (approximate) name."""
    api_key = os.getenv("COLLEGE_SCORECARD_API_KEY") or "DEMO_KEY"

    response = requests.get(
        SCHOOLS_URL,
        params={"school.name": name, "fields": FIELDS, "api_key": api_key, "per_page": 1},
        timeout=30,
    )
    response.raise_for_status()

    results = response.json().get("results", [])
    return results[0] if results else None
