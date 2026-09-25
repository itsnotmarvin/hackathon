from fastapi import APIRouter, HTTPException

from app.database import record_evidence, supabase
from services import college_scorecard as college_scorecard_service
from services import gdelt as gdelt_service
from services import github as github_service
from services import grants as grants_service
from services import nih as nih_service
from services import nsf as nsf_service
from services import orcid as orcid_service
from services import pdl as pdl_service
from services import scholar as scholar_service
from services import sec as sec_service
from services import wikidata as wikidata_service
from services import wikipedia as wikipedia_service

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
    it to this founder, with an evidence row per fact. This is the only
    source of `education` rows - if PDL_API_KEY isn't set, education stays
    empty everywhere in the app, by design (see services/pdl.py)."""
    founder = _get_founder(founder_id)

    try:
        person = pdl_service.enrich_person(
            name=founder["name"],
            company=company,
            location=location or founder.get("location"),
        )
    except pdl_service.PDLError as exc:
        raise HTTPException(status_code=424, detail=str(exc)) from exc

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
            # Descriptive school context (size, admit rate) — not a prestige
            # score, just facts to show alongside the claim above.
            try:
                school = college_scorecard_service.lookup_school(saved["institution"])
            except Exception:  # noqa: BLE001 - best-effort enrichment, never blocks the enrich flow
                school = None
            if school:
                size = school.get("latest.student.size")
                admit_rate = school.get("latest.admissions.admission_rate.overall")
                parts = []
                if size:
                    parts.append(f"{size} students")
                if admit_rate is not None:
                    parts.append(f"{admit_rate:.1%} admit rate")
                if parts:
                    record_evidence(
                        entity_type="education",
                        entity_id=saved["id"],
                        claim=f"{saved['institution']}: {', '.join(parts)}",
                        source_name="College Scorecard",
                        source_url=school.get("school.school_url"),
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
def research_founder(founder_id: str):
    """Pull every public signal we have for this founder's name/company and
    save each hit with an evidence row:

      - Wikidata         -> notable-person awards (achievements)
      - Wikipedia        -> bio summary, if notable enough to have a page (achievements)
      - Semantic Scholar -> publication/citation record (achievements)
      - ORCID            -> registered researcher identity (achievements)
      - GDELT            -> news/press mentions, high-recall (achievements)
      - GitHub           -> public repo/star track record (achievements)
      - SEC EDGAR        -> full-text filing mentions, e.g. Form D (achievements)
      - USAspending      -> company-level federal grants (grants)
      - NSF Award Search -> person-level NSF grants as PI (grants)
      - NIH RePORTER     -> person-level NIH grants as PI (grants)

    Removed: OpenCorporates (officer/company-history search) — its API
    requires a paid token with no usable free tier, confirmed 401
    Unauthorized on every request without one. No free public API currently
    fills the "previous business ownership" gap this left; SEC EDGAR's
    Form D search is the closest available substitute.

    Deliberately NOT called here: SBIR.gov's award API (returns 403
    Forbidden for every request as of 2026-09-25, not just unkeyed ones —
    see services/grants.py), arXiv (its API is real but returns 406 to
    every `requests` call regardless of headers, confirmed against the
    live endpoint — works via curl, not from this stack), and USPTO's
    Assignment API (assignment-api.uspto.gov does not resolve, publicly or
    locally — likely retired/moved). All three are documented in their
    modules rather than silently wired in here to fail every time.

    Every remaining source here is best-effort and independent: one failing
    (rate limit, no match, missing key, network hiccup) is recorded as a
    warning rather than failing the whole request.

    Name-based lookups (Wikidata, Wikipedia, Semantic Scholar, ORCID, GDELT,
    NSF, NIH, SEC) match on name alone and can be ambiguous for common
    names — treat hits as leads to confirm, not settled fact, the same way
    the `evidence` table is meant to be read for every signal here.
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

    def _natural_key(table: str, row: dict):
        """What makes two rows in this table 'the same fact' — used so
        re-running /research doesn't pile up duplicates every time."""
        if table == "companies":
            return (row.get("company_name"), row.get("role"))
        if table == "achievements":
            return row.get("achievement")
        if table == "grants":
            return (row.get("program"), row.get("agency"), row.get("amount"))
        return None

    # Load what's already stored for this founder once, so repeated
    # /research calls are idempotent instead of accumulating duplicates.
    seen_keys: dict[str, set] = {}
    for table in entity_types:
        rows = supabase.table(table).select("*").eq("founder_id", founder_id).execute().data
        seen_keys[table] = {_natural_key(table, r) for r in rows}

    def _save(table: str, rows: list[dict], bucket: list[dict], claim_fn, source_name: str):
        for row in rows:
            key = _natural_key(table, row)
            if key in seen_keys[table]:
                continue
            seen_keys[table].add(key)
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

    # --- Wikipedia bio summary (only if notable enough to have a page) ---
    try:
        summary = wikipedia_service.get_summary(name)
        row = wikipedia_service.to_achievement_row(summary) if summary else None
        if row:
            _save("achievements", [row], achievement_rows, lambda r: r["achievement"], "Wikipedia")
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"Wikipedia: {exc}")

    # --- ORCID registered-researcher identity ---
    if first_name:
        try:
            orcid_matches = orcid_service.search_person(first_name, last_name)
            rows = [orcid_service.to_achievement_row(m) for m in orcid_matches[:3]]
            _save("achievements", rows, achievement_rows, lambda r: r["achievement"], "ORCID")
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"ORCID: {exc}")

    # --- GDELT news/press mentions (noisy, high-recall) ---
    try:
        articles = gdelt_service.search_articles(f'"{name}"', max_records=5)
        _save(
            "achievements",
            gdelt_service.to_achievement_rows(articles),
            achievement_rows,
            lambda r: r["achievement"],
            "GDELT",
        )
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"GDELT: {exc}")

    # --- SEC EDGAR full-text filing mentions (e.g. Form D private offerings) ---
    try:
        hits = sec_service.search_filings(f'"{name}"', forms="D")
        _save(
            "achievements",
            sec_service.to_achievement_rows(hits),
            achievement_rows,
            lambda r: r["achievement"],
            "SEC EDGAR",
        )
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"SEC EDGAR: {exc}")

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
                lambda r: f"{startup_name} received a ${r.get('amount'):,.0f} award from {r.get('agency')}"
                if r.get("amount")
                else f"{startup_name} received an award from {r.get('agency')}",
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

    # Observable business-experience signals, per-fact counts only — no age
    # or personal-wealth inference, and no single blended "score": see
    # services/pdl.py and the earlier design note on why those two aren't
    # derivable from public data.
    signals = {
        "previous_company_count": len(companies),
        "grant_count": len(grants_rows),
        "total_grant_amount": sum(g["amount"] for g in grants_rows if g.get("amount")) or None,
        "achievement_count": len(achievements),
        "education_count": len(education),
        "birth_year": founder.get("birth_year"),
    }

    result = {
        "founder": founder,
        "education": education,
        "companies": companies,
        "achievements": achievements,
        "grants": grants_rows,
        "evidence": evidence,
        "signals": signals,
    }
    if evidence_error:
        result["evidence_error"] = evidence_error
    return result
