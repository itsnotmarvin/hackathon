from fastapi import APIRouter, HTTPException

from app.database import record_evidence, supabase
from services import github as github_service
from services import grants as grants_service
from services import nih as nih_service
from services import nsf as nsf_service
from services import opencorporates as opencorporates_service
from services import pdl as pdl_service
from services import scholar as scholar_service
from services import wikidata as wikidata_service

router = APIRouter()


def _get_founder(founder_id: str) -> dict:
    response = supabase.table("founders").select("*").eq("id", founder_id).execute()
    if not response.data:
        raise HTTPException(status_code=404, detail="Founder not found")
    return response.data[0]


@router.post("/founders")
def create_founder(founder: dict):
    """Create a bare founder record. Expected keys: startup_id, name, title,
    and optionally linkedin_url/github_url/location."""
    if not founder.get("startup_id") or not founder.get("name"):
        raise HTTPException(status_code=400, detail="startup_id and name are required")

    response = supabase.table("founders").insert(founder).execute()
    return response.data[0]


@router.get("/founders/{founder_id}")
def get_founder(founder_id: str):
    return _get_founder(founder_id)


@router.post("/founders/{founder_id}/enrich")
def enrich_founder(founder_id: str, company: str | None = None, location: str | None = None):
    """Pull identity/education/employment from People Data Labs and attach
    it to this founder, with an evidence row per fact."""
    founder = _get_founder(founder_id)

    person = pdl_service.enrich_person(
        name=founder["name"],
        company=company,
        location=location or founder.get("location"),
    )
    if person is None:
        return {"matched": False, "founder": founder}

    updates = pdl_service.to_founder_fields(person)
    updates = {k: v for k, v in updates.items() if v is not None}
    if updates:
        supabase.table("founders").update(updates).eq("id", founder_id).execute()

    education_rows = []
    for row in pdl_service.to_education_rows(person):
        row["founder_id"] = founder_id
        saved = supabase.table("education").insert(row).execute().data[0]
        education_rows.append(saved)
        if saved.get("institution"):
            record_evidence(
                entity_type="education",
                entity_id=saved["id"],
                claim=f"{founder['name']} attended {saved['institution']}",
                source_name="People Data Labs",
            )

    company_rows = []
    for row in pdl_service.to_company_rows(person):
        row["founder_id"] = founder_id
        saved = supabase.table("companies").insert(row).execute().data[0]
        company_rows.append(saved)
        if saved.get("company_name"):
            record_evidence(
                entity_type="company",
                entity_id=saved["id"],
                claim=f"{founder['name']} worked at {saved['company_name']} as {saved.get('role') or 'unknown role'}",
                source_name="People Data Labs",
            )

    return {
        "matched": True,
        "founder": _get_founder(founder_id),
        "education": education_rows,
        "companies": company_rows,
    }


@router.post("/founders/{founder_id}/research")
def research_founder(founder_id: str, jurisdiction_code: str | None = "us_nj"):
    """Pull every public signal we have for this founder's name/company and
    save each hit with an evidence row:

      - OpenCorporates   -> previous/current officer roles (companies)
                            [requires OPENCORPORATES_API_KEY - paid, 401s without it]
      - Wikidata         -> notable-person awards (achievements)
      - Semantic Scholar -> publication/citation record (achievements)
      - GitHub           -> public repo/star track record (achievements)
      - NSF Award Search -> person-level NSF grants as PI (grants)
      - NIH RePORTER     -> person-level NIH grants as PI (grants)

    Deliberately NOT called here: SBIR.gov's award API (returns 403
    Forbidden for every request as of 2026-09-25, not just unkeyed ones —
    see services/grants.py) and any patent/inventor search (the endpoint
    this used to call, search.patentsview.org, does not exist — see
    services/uspto.py). Both are documented in their modules rather than
    silently wired in here to fail every time.

    Every remaining source here is best-effort and independent: one failing
    (rate limit, no match, missing key, network hiccup) is recorded as a
    warning rather than failing the whole request.

    Name-based lookups (Wikidata, Semantic Scholar, NSF, NIH) match on name
    alone and can be ambiguous for common names — treat hits as leads to
    confirm, not settled fact, the same way the `evidence` table is meant
    to be read for every signal here.
    """
    founder = _get_founder(founder_id)
    name = founder["name"]
    name_parts = name.split()
    first_name, last_name = (name_parts[0], name_parts[-1]) if len(name_parts) >= 2 else (None, None)

    startup_id = founder.get("startup_id")
    startup_name = None
    if startup_id:
        startup = supabase.table("startups").select("name").eq("id", startup_id).execute().data
        startup_name = startup[0]["name"] if startup else None

    company_rows: list[dict] = []
    achievement_rows: list[dict] = []
    grant_rows: list[dict] = []
    warnings: list[str] = []

    entity_types = {"companies": "company", "achievements": "achievement", "grants": "grant"}

    def _save(table: str, rows: list[dict], bucket: list[dict], claim_fn, source_name: str):
        for row in rows:
            row["founder_id"] = founder_id
            saved = supabase.table(table).insert(row).execute().data[0]
            bucket.append(saved)
            record_evidence(
                entity_type=entity_types[table],
                entity_id=saved["id"],
                claim=claim_fn(saved),
                source_name=source_name,
                source_url=saved.get("source_url"),
            )

    # --- Previous companies / officer roles ---
    try:
        officers = opencorporates_service.search_officers(name, jurisdiction_code=jurisdiction_code)
        _save(
            "companies",
            opencorporates_service.to_company_rows(officers),
            company_rows,
            lambda r: f"{name} is listed as {r.get('role') or 'an officer'} of {r.get('company_name')}",
            "OpenCorporates",
        )
    except Exception as exc:  # noqa: BLE001 - one flaky public API shouldn't fail the request
        warnings.append(f"OpenCorporates: {exc}")

    # --- Wikidata notable-person awards ---
    try:
        wd_rows = wikidata_service.search_person(name)
        _save(
            "achievements",
            wikidata_service.to_achievement_rows(wd_rows),
            achievement_rows,
            lambda r: r["achievement"],
            "Wikidata",
        )
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"Wikidata: {exc}")

    # --- Semantic Scholar publication record ---
    try:
        authors = scholar_service.search_author(name)
        scholar_rows = [
            row for author in authors[:3] if (row := scholar_service.to_achievement_row(author))
        ]
        _save("achievements", scholar_rows, achievement_rows, lambda r: r["achievement"], "Semantic Scholar")
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"Semantic Scholar: {exc}")

    # --- GitHub track record (only if we already have a github_url from PDL) ---
    try:
        github_url = founder.get("github_url")
        if github_url:
            username = github_url.rstrip("/").split("/")[-1]
            user = github_service.get_user(username)
            if user:
                repos = github_service.get_top_repos(username)
                row = github_service.to_achievement_row(user, repos)
                if row:
                    _save("achievements", [row], achievement_rows, lambda r: r["achievement"], "GitHub")
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"GitHub: {exc}")

    # --- Company-level federal grants (USAspending; broad catch-all) ---
    if startup_name:
        try:
            usa_awards = grants_service.search_federal_awards(startup_name)
            rows = grants_service.to_grant_rows_from_usaspending(usa_awards)
            for row in rows:
                row["startup_id"] = startup_id
            _save(
                "grants",
                rows,
                grant_rows,
                lambda r: f"{startup_name} received a federal award from {r.get('agency')}",
                "USAspending.gov",
            )
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"USAspending.gov: {exc}")

    # --- Person-level NSF grants (as PI) ---
    if first_name:
        try:
            nsf_awards = nsf_service.search_awards_by_pi(first_name, last_name)
            rows = nsf_service.to_grant_rows(nsf_awards)
            for row in rows:
                row["startup_id"] = startup_id
            _save(
                "grants",
                rows,
                grant_rows,
                lambda r: f"{name} is PI on an NSF award ({r.get('amount')})",
                "NSF Award Search",
            )
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"NSF Award Search: {exc}")

    # --- Person-level NIH grants (as PI) ---
    if first_name:
        try:
            nih_projects = nih_service.search_projects_by_pi(first_name, last_name)
            rows = nih_service.to_grant_rows(nih_projects)
            for row in rows:
                row["startup_id"] = startup_id
            _save(
                "grants",
                rows,
                grant_rows,
                lambda r: f"{name} is PI on an NIH project: {r.get('program')}",
                "NIH RePORTER",
            )
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"NIH RePORTER: {exc}")

    return {
        "founder": founder,
        "companies": company_rows,
        "achievements": achievement_rows,
        "grants": grant_rows,
        "warnings": warnings,
    }


@router.get("/founders/{founder_id}/profile")
def founder_profile(founder_id: str):
    """Aggregate everything known about a founder, each fact carrying its
    source via the evidence table."""
    founder = _get_founder(founder_id)

    education = supabase.table("education").select("*").eq("founder_id", founder_id).execute().data
    companies = supabase.table("companies").select("*").eq("founder_id", founder_id).execute().data
    achievements = supabase.table("achievements").select("*").eq("founder_id", founder_id).execute().data
    grants_rows = supabase.table("grants").select("*").eq("founder_id", founder_id).execute().data

    entity_ids = (
        [founder_id]
        + [row["id"] for row in education]
        + [row["id"] for row in companies]
        + [row["id"] for row in achievements]
        + [row["id"] for row in grants_rows]
    )
    evidence: list[dict] = []
    evidence_error: str | None = None
    if entity_ids:
        try:
            evidence = supabase.table("evidence").select("*").in_("entity_id", entity_ids).execute().data
        except Exception as exc:  # noqa: BLE001 - don't let a missing/misconfigured evidence table 500 the whole profile
            evidence_error = str(exc)

    result = {
        "founder": founder,
        "education": education,
        "companies": companies,
        "achievements": achievements,
        "grants": grants_rows,
        "evidence": evidence,
    }
    if evidence_error:
        result["evidence_error"] = evidence_error
    return result
