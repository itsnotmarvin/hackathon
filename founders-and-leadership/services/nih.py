"""NIH RePORTER — federal biomedical/health research grants by PI name.
Useful for biotech/health founders. No key required.

Docs: https://api.reporter.nih.gov/
"""

import requests

NIH_REPORTER_URL = "https://api.reporter.nih.gov/v2/projects/search"


def search_projects_by_pi(first_name: str, last_name: str, limit: int = 25) -> list[dict]:
    """Look up NIH-funded projects where this person is listed as PI."""
    payload = {
        "criteria": {
            "pi_names": [{"first_name": first_name, "last_name": last_name}],
        },
        "include_fields": [
            "ProjectTitle",
            "AwardAmount",
            "FiscalYear",
            "Organization",
            "AgencyIcAdmin",
            "ProjectNum",
        ],
        "limit": limit,
    }
    response = requests.post(NIH_REPORTER_URL, json=payload, timeout=30)
    response.raise_for_status()
    return response.json().get("results", []) or []


def to_grant_rows(projects: list[dict]) -> list[dict]:
    """Normalize NIH RePORTER results into rows for the `grants` table
    (caller still needs to attach startup_id/founder_id)."""
    rows = []
    for project in projects:
        agency = (project.get("agency_ic_admin") or {}).get("name") or "NIH"
        rows.append(
            {
                "program": project.get("project_title"),
                "agency": agency,
                "amount": project.get("award_amount"),
                "award_date": str(project.get("fiscal_year")) if project.get("fiscal_year") else None,
                "source_name": "NIH RePORTER",
                "source_url": f"https://reporter.nih.gov/project-details/{project.get('project_num')}"
                if project.get("project_num")
                else None,
            }
        )
    return rows
