from __future__ import annotations

import csv
import json
from pathlib import Path

from unified.catalog import build_catalog


def _write_csv(root: Path, relative: str, rows: list[dict]) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _write_json(root: Path, relative: str, payload: dict) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _filing(name: str, cik: str, **overrides) -> dict:
    row = {
        "company": name,
        "cik": cik,
        "city": "Newark",
        "zip": "07102",
        "industry": "Other Technology",
        "incorporated": "2024",
        "young_company": "True",
        "revenue_range": "Decline to Disclose",
        "num_offerings": "1",
        "total_raised": "1250000",
        "largest_round": "1250000",
        "raised_last_24mo": "1250000",
        "total_investors": "4",
        "first_raise": "2025-01-02",
        "last_raise": "2025-01-02",
        "related_people": "Alex Rivera (Executive Officer/Director)",
        "edgar_url": f"https://www.sec.gov/cgi-bin/browse-edgar?CIK={cik}",
    }
    row.update(overrides)
    return row


def _offering(name: str, cik: str, **overrides) -> dict:
    row = {
        "company": name,
        "cik": cik,
        "filing_date": "2025-01-03",
        "total_offering": "2000000",
        "amount_sold": "1250000",
        "file_num": f"021-{cik}",
        "filing_url": f"https://www.sec.gov/Archives/edgar/data/{cik}/filing/",
    }
    row.update(overrides)
    return row


def _team(name: str, ceo: str = "Jamie Chen", url: str = "https://example.com/team") -> dict:
    return {
        "id": "L01",
        "company": name,
        "ceo_name": ceo,
        "ceo_source_url": url,
        "source_checked_on": "2026-09-25",
    }


def _company(payload: dict, name: str) -> dict:
    matches = [item for item in payload["companies"] if item["name"] == name]
    assert len(matches) == 1
    return matches[0]


def _research_card(name: str, **overrides) -> dict:
    card = {
        "name": name,
        "aliases": [],
        "description": f"Research profile for {name}.",
        "nj_presence": {"status": "unclear", "evidence": []},
        "signals": [],
        "limitations": [],
    }
    card.update(overrides)
    return card


def test_exact_legal_name_and_explicit_alias_keep_id_and_dedupe_evidence(tmp_path: Path) -> None:
    _write_csv(
        tmp_path,
        "business-and-market-potential/data/nj_formd_companies.csv",
        [_filing("SunRay Scientific Inc.", "2030956")],
    )
    _write_csv(
        tmp_path,
        "business-and-market-potential/data/nj_formd_offerings.csv",
        [_offering("SunRay Scientific Inc.", "2030956")],
    )
    _write_csv(tmp_path, "startups.csv", [_team("SunRay Scientific")])

    before = build_catalog(tmp_path)
    baseline = _company(before, "SunRay Scientific")
    assert len(before["companies"]) == 1

    captured = {
        "source_id": "R1",
        "url": "https://njeda.example/sunray",
        "title": "NJEDA company profile",
        "quote": "SunRay Scientific operates a materials facility in New Jersey.",
        "published_at": "2026-04-10",
        "observed_at": "2026-09-20T12:00:00Z",
        "source_family": "njeda",
    }
    card = {
        "name": "SunRay Materials",
        "aliases": ["SunRay Scientific"],
        "sector": "Advanced materials",
        "description": "Electronic materials company",
        "nj_presence": {
            "status": "operations",
            "location": "Newark, NJ",
            "evidence": [captured],
        },
        "signals": [
            {
                "statement": "NJEDA documents New Jersey operations.",
                "evidence": [captured],
            }
        ],
        "limitations": [],
    }
    job = {
        "mode": "sample",
        "status": "completed",
        "updated_at": "2099-01-01T00:00:00Z",
        "cards": [card],
        "review_cards": [],
    }
    after = build_catalog(tmp_path, jobs=[job, job])
    merged = _company(after, "SunRay Scientific")

    assert len(after["companies"]) == 1
    assert merged["id"] == baseline["id"]
    assert merged["record_type"] == "research"
    reputation_quotes = [
        item["quote"]
        for item in merged["evidence"]
        if item["pillar"] == "reputation"
    ]
    assert reputation_quotes == [captured["quote"]]
    # Job persistence time must not masquerade as source verification time.
    assert merged["updated_at"] == "2026-09-25"


def test_cik_canonical_id_is_stable_regardless_of_source_arrival_order(tmp_path: Path) -> None:
    _write_csv(tmp_path, "startups.csv", [_team("StableCo")])
    job = {
        "pipeline_version": "1.1.0",
        "cards": [_research_card("StableCo", cik="1234567")],
        "review_cards": [],
    }

    learned_from_research = _company(
        build_catalog(tmp_path, jobs=[job]),
        "StableCo",
    )

    _write_csv(
        tmp_path,
        "business-and-market-potential/data/nj_formd_companies.csv",
        [_filing("StableCo", "1234567")],
    )
    loaded_from_filing = _company(
        build_catalog(tmp_path, jobs=[job]),
        "StableCo",
    )

    assert learned_from_research["id"] == "company-2dc49d425c10197f"
    assert loaded_from_filing["id"] == learned_from_research["id"]


def test_distinct_ciks_survive_suffix_collision_and_lead_stays_unresolved(tmp_path: Path) -> None:
    _write_csv(
        tmp_path,
        "business-and-market-potential/data/nj_formd_companies.csv",
        [_filing("Acme Inc.", "1001"), _filing("Acme LLC", "1002")],
    )
    _write_csv(
        tmp_path,
        "business-and-market-potential/data/nj_formd_offerings.csv",
        [_offering("Acme Inc.", "1001"), _offering("Acme LLC", "1002")],
    )
    _write_csv(tmp_path, "startups.csv", [_team("Acme", ceo="Robin Singh")])

    payload = build_catalog(tmp_path)
    assert len(payload["companies"]) == 3
    assert len({item["id"] for item in payload["companies"]}) == 3
    assert sum(item["record_type"] == "filing" for item in payload["companies"]) == 2

    lead = _company(payload, "Acme")
    assert lead["record_type"] == "lead"
    assert lead["nj_status"] == "unverified"
    assert lead["coverage_count"] == 1
    assert lead["pillars"]["business"]["status"] == "missing"
    assert lead["people"] == [
        {"name": "Robin Singh", "role": "CEO", "source_url": "https://example.com/team"}
    ]
    assert "founder" not in lead["people"][0]["role"].casefold()


def test_placeholder_ciks_and_non_ascii_names_keep_distinct_public_identities(tmp_path: Path) -> None:
    job = {
        "pipeline_version": "1.1.0",
        "cards": [
            _research_card("Alpha Research", cik="N/A"),
            _research_card("Beta Research", cik="N/A"),
            _research_card("星河科技"),
            _research_card("未来科技"),
        ],
        "review_cards": [],
    }

    payload = build_catalog(tmp_path, jobs=[job])

    assert {item["name"] for item in payload["companies"]} == {
        "Alpha Research",
        "Beta Research",
        "星河科技",
        "未来科技",
    }
    assert len({item["id"] for item in payload["companies"]}) == 4


def test_conflicting_name_and_domain_does_not_poison_domain_identity(tmp_path: Path) -> None:
    job = {
        "pipeline_version": "1.1.0",
        "cards": [
            _research_card("Alpha", description="Alpha profile."),
            _research_card(
                "Beta",
                description="Beta profile.",
                official_domain="b.example",
            ),
            _research_card(
                "Alpha",
                description="Conflicting Alpha profile.",
                official_domain="b.example",
            ),
            _research_card(
                "Beta Alias",
                description="Later Beta profile.",
                official_domain="b.example",
            ),
        ],
        "review_cards": [],
    }

    payload = build_catalog(tmp_path, jobs=[job])

    assert len(payload["companies"]) == 2
    alpha = _company(payload, "Alpha")
    beta = _company(payload, "Beta")
    assert any("official domain already belongs" in item for item in alpha["limitations"])
    assert beta["description"] == "Later Beta profile."


def test_founder_profile_preserves_title_and_requires_identity_review(tmp_path: Path) -> None:
    _write_csv(tmp_path, "startups.csv", [_team("TitleCo", ceo="Current Executive")])
    profiles = {
        "TitleCo": [
            {
                "founder": {
                    "name": "Research Candidate",
                    "title": "Chief Scientist",
                    "linkedin_url": "https://linkedin.com/in/candidate",
                },
                "education": [],
                "companies": [],
                "achievements": [],
                "grants": [
                    {
                        "program": "Research award",
                        "agency": "Agency",
                        "amount": 50000,
                        "source_url": "https://agency.example/award",
                    }
                ],
                "evidence": [],
                "limitations": ["Candidate match has not been manually confirmed."],
            }
        ]
    }

    company = _company(build_catalog(tmp_path, founder_profiles=profiles), "TitleCo")
    roles = {person["name"]: person["role"] for person in company["people"]}
    assert roles == {
        "Current Executive": "CEO",
        "Research Candidate": "Chief Scientist",
    }
    assert "leadership identity review needed" in company["tags"]
    assert company["record_type"] == "research"
    assert company["pillars"]["founders"]["status"] == "partial"
    assert any("identity review" in text.casefold() for text in company["pillars"]["founders"]["limitations"])
    grant_metric = next(
        metric
        for metric in company["pillars"]["funding"]["metrics"]
        if metric["label"] == "Reported value of name-matched grant records"
    )
    assert grant_metric["value"] == "USD 50,000"
    assert "not company revenue" in grant_metric["detail"]


def test_empty_founder_profile_collection_does_not_create_phantom_company(tmp_path: Path) -> None:
    payload = build_catalog(tmp_path, founder_profiles={"GhostCo": []})

    assert payload["companies"] == []
    assert payload["stats"]["companies"] == 0


def test_founder_grants_are_unioned_by_id_across_company_profiles(tmp_path: Path) -> None:
    shared = {
        "id": "grant-shared",
        "program": "Shared company award",
        "agency": "Agency",
        "amount": 100,
        "source_url": "https://grants.example/shared",
        "qualification": "Shared company-level award attribution requires review.",
    }
    profiles = {
        "GrantCo": [
            {
                "founder": {"name": "Founder A", "title": "CEO"},
                "grants": [
                    shared,
                    {
                        "id": "grant-a",
                        "program": "Person A award",
                        "agency": "Agency",
                        "amount": 10,
                        "source_url": "https://grants.example/a",
                        "qualification": "Person A identity requires review.",
                    },
                ],
            },
            {
                "founder": {"name": "Founder B", "title": "CTO"},
                "grants": [
                    dict(shared),
                    {
                        "id": "grant-b",
                        "program": "Person B award",
                        "agency": "Agency",
                        "amount": 20,
                        "source_url": "https://grants.example/b",
                        "qualification": "Person B identity requires review.",
                    },
                ],
            },
        ]
    }

    company = _company(build_catalog(tmp_path, founder_profiles=profiles), "GrantCo")
    metrics = {
        item["label"]: item for item in company["pillars"]["funding"]["metrics"]
    }

    assert metrics["Founder/leader-linked grant records"]["value"] == 3
    assert metrics["Reported value of name-matched grant records"]["value"] == "USD 130"
    assert len(
        [item for item in company["evidence"] if item["pillar"] == "funding"]
    ) == 3
    assert "Shared company-level award attribution requires review." in company["pillars"]["funding"]["limitations"]


def test_same_source_claim_is_retained_once_per_supported_pillar(tmp_path: Path) -> None:
    source_url = "https://source.example/shared-claim"
    profiles = {
        "CrossPillar": [
            {
                "founder": {"name": "Casey", "title": "CEO"},
                "evidence": [
                    {
                        "entity_type": "founder",
                        "claim": "Shared source claim",
                        "source_url": source_url,
                    }
                ],
            }
        ]
    }
    job = {
        "pipeline_version": "1.1.0",
        "cards": [
            _research_card(
                "CrossPillar",
                signals=[
                    {
                        "statement": "The same source also supports reputation context.",
                        "evidence": [
                            {
                                "title": "Shared source claim",
                                "quote": "",
                                "url": source_url,
                            }
                        ],
                    }
                ],
            )
        ],
        "review_cards": [],
    }

    company = _company(
        build_catalog(tmp_path, jobs=[job], founder_profiles=profiles),
        "CrossPillar",
    )
    matching = [
        item for item in company["evidence"] if item["title"] == "Shared source claim"
    ]

    assert {item["pillar"] for item in matching} == {"founders", "reputation"}
    assert len({item["id"] for item in matching}) == 2
    assert company["source_count"] == 1


def test_money_sector_and_headcount_metrics_keep_their_real_semantics(tmp_path: Path) -> None:
    _write_csv(
        tmp_path,
        "business-and-market-potential/data/nj_formd_companies.csv",
        [_filing("MetricCo Inc.", "3001", revenue_range="$1 - $1,000,000")],
    )
    _write_csv(
        tmp_path,
        "business-and-market-potential/data/nj_formd_offerings.csv",
        [_offering("MetricCo Inc.", "3001")],
    )
    _write_csv(tmp_path, "startups.csv", [_team("MetricCo")])
    _write_csv(
        tmp_path,
        "business-and-market-potential/business-model/business-model-scores.csv",
        [
            {
                "company": "MetricCo",
                "one_line_description": "Security workflow software.",
                "score": "4",
                "justification": "Recurring subscription model.",
                "novelty_type": "1-n",
                "novelty_score": "2",
                "novelty_justification": "Known category with workflow differentiation.",
            }
        ],
    )
    _write_csv(
        tmp_path,
        "business-and-market-potential/scalability/headcount-data.csv",
        [
            {
                "company": "MetricCo",
                "current_headcount": "42",
                "founding_year": "2022",
                "growth_rate": "10.5",
                "scales_with_headcount": "no",
            }
        ],
    )
    notes = tmp_path / "business-and-market-potential/market-timing/sector-momentum-notes.md"
    notes.parent.mkdir(parents=True, exist_ok=True)
    notes.write_text(
        """## Sector grouping

| Sector | Companies |
| --- | --- |
| Enterprise software & security | MetricCo |

  - Enterprise software & security: proxy ([Source](https://market.example/report)).
""",
        encoding="utf-8",
    )
    _write_csv(
        tmp_path,
        "business-and-market-potential/market-timing/sector-data.csv",
        [{"sector": "Enterprise software & security", "date": "2025", "funding_total": "14.3"}],
    )

    company = _company(build_catalog(tmp_path), "MetricCo")
    business_metrics = {item["label"]: item for item in company["pillars"]["business"]["metrics"]}
    funding_metrics = {item["label"]: item for item in company["pillars"]["funding"]["metrics"]}

    assert business_metrics["Current headcount estimate"]["value"] == 42
    growth = business_metrics["Average employees added per year since founding (proxy)"]
    assert growth["value"] == 10.5
    assert "not observed hiring growth" in growth["detail"]
    sector = business_metrics["Broader sector venture-funding proxy (2025)"]
    assert sector["value"] == "USD 14.3B"
    assert "not this company's funding" in sector["detail"]
    reported = funding_metrics["Reported amount sold across Form D offerings since 2021"]
    assert reported["value"] == "USD 1,250,000"
    assert "not revenue" in reported["detail"]
    revenue = business_metrics["SEC self-reported revenue bracket"]
    assert revenue["value"] == "$1 - $1,000,000"
    assert "not verified or exact revenue" in revenue["detail"]
    assert not any("overall" in label.casefold() for label in business_metrics | funding_metrics)


def test_spaced_csv_headers_feed_business_headcount_and_sector_metrics(tmp_path: Path) -> None:
    _write_csv(tmp_path, "startups.csv", [_team("SpacedCo")])

    business_path = (
        tmp_path
        / "business-and-market-potential/business-model/business-model-scores.csv"
    )
    business_path.parent.mkdir(parents=True, exist_ok=True)
    business_path.write_text(
        " company , one_line_description , score , justification , novelty_type , novelty_score , novelty_justification \n"
        "SpacedCo,Workflow software,4,Recurring model,1-n,2,Known category\n",
        encoding="utf-8",
    )

    headcount_path = (
        tmp_path / "business-and-market-potential/scalability/headcount-data.csv"
    )
    headcount_path.parent.mkdir(parents=True, exist_ok=True)
    headcount_path.write_text(
        "company, current_headcount , founding_year , growth_rate , scales_with_headcount \n"
        "SpacedCo,42,2022,10.5,no\n",
        encoding="utf-8",
    )

    notes = tmp_path / "business-and-market-potential/market-timing/sector-momentum-notes.md"
    notes.parent.mkdir(parents=True, exist_ok=True)
    notes.write_text(
        "## Sector grouping\n\n"
        "| Sector | Companies |\n"
        "| --- | --- |\n"
        "| Enterprise software & security | SpacedCo |\n",
        encoding="utf-8",
    )
    sector_path = tmp_path / "business-and-market-potential/market-timing/sector-data.csv"
    sector_path.write_text(
        " sector , date , funding_total \n"
        "Enterprise software & security,2025,14.3\n",
        encoding="utf-8",
    )

    company = _company(build_catalog(tmp_path), "SpacedCo")
    metrics = {
        item["label"]: item["value"]
        for item in company["pillars"]["business"]["metrics"]
    }

    assert metrics["Business-model analyst judgment (1–5)"] == "4/5"
    assert metrics["Current headcount estimate"] == 42
    assert metrics["Broader sector venture-funding proxy (2025)"] == "USD 14.3B"


def test_orphan_form_d_offering_marks_funding_partial(tmp_path: Path) -> None:
    _write_csv(
        tmp_path,
        "business-and-market-potential/data/nj_formd_offerings.csv",
        [_offering("Orphan Offering LLC", "7654321")],
    )

    company = _company(build_catalog(tmp_path), "Orphan Offering LLC")

    assert company["record_type"] == "filing"
    assert company["pillars"]["funding"]["status"] == "partial"
    assert any(
        item["source_type"] == "sec_form_d_filing"
        for item in company["evidence"]
    )
    assert any(
        "company-history row" in item
        for item in company["pillars"]["funding"]["limitations"]
    )


def test_newest_reputation_job_wins_and_duplicate_evidence_keeps_date_history(tmp_path: Path) -> None:
    old_evidence = {
        "title": "Repeated source",
        "quote": "The company has a location under review.",
        "url": "https://source.example/repeated",
        "published_at": "2025-01-01",
        "observed_at": "2026-01-01T00:00:00Z",
    }
    new_evidence = {
        **old_evidence,
        "published_at": "2025-02-01",
        "observed_at": "2026-02-01T00:00:00Z",
    }
    older = {
        "created_epoch": 1,
        "pipeline_version": "1.1.0",
        "cards": [
            _research_card(
                "RecencyCo",
                description="Older description.",
                nj_presence={
                    "status": "operations",
                    "location": "Newark, NJ",
                    "evidence": [old_evidence],
                },
                limitations=["Older assessment limitation."],
            )
        ],
        "review_cards": [],
    }
    newer = {
        "created_epoch": 2,
        "pipeline_version": "1.1.0",
        "cards": [
            _research_card(
                "RecencyCo",
                description="Newer description.",
                nj_presence={
                    "status": "unclear",
                    "location": "Current location unresolved",
                    "evidence": [new_evidence],
                },
                limitations=["Newer assessment limitation."],
            )
        ],
        "review_cards": [],
    }

    # This matches Store.recent(): newest persisted job first.
    company = _company(build_catalog(tmp_path, jobs=[newer, older]), "RecencyCo")
    repeated = [
        item for item in company["evidence"] if item["title"] == "Repeated source"
    ]

    assert company["description"] == "Newer description."
    assert company["nj_status"] == "unverified"
    assert company["location"] == "Current location unresolved"
    assert len(repeated) == 1
    assert repeated[0]["published_at"] == "2025-01-01"
    assert repeated[0]["observed_at"] == "2026-02-01T00:00:00Z"
    assert {
        "Older assessment limitation.",
        "Newer assessment limitation.",
    }.issubset(company["pillars"]["reputation"]["limitations"])
    assert any(
        "conflicting publication dates" in item
        for item in company["pillars"]["reputation"]["limitations"]
    )


def test_older_pipeline_cards_surface_current_assessment_warning(tmp_path: Path) -> None:
    job = {
        "pipeline_version": "1.0.3",
        "cards": [_research_card("LegacyCo")],
        "review_cards": [],
    }

    company = _company(build_catalog(tmp_path, jobs=[job]), "LegacyCo")

    assert (
        "This saved run used an earlier assessment version. "
        "Start new research to apply current checks."
        in company["pillars"]["reputation"]["limitations"]
    )


def test_unsafe_links_are_never_emitted_or_counted(tmp_path: Path) -> None:
    _write_csv(
        tmp_path,
        "business-and-market-potential/data/nj_formd_companies.csv",
        [_filing("Unsafe Inc.", "4001", edgar_url="file:///etc/passwd")],
    )
    _write_csv(
        tmp_path,
        "business-and-market-potential/data/nj_formd_offerings.csv",
        [_offering("Unsafe Inc.", "4001", filing_url="data:text/html,bad")],
    )
    _write_csv(tmp_path, "startups.csv", [_team("Unsafe", url="javascript:alert(1)")])
    bad_card = {
        "name": "Unsafe",
        "aliases": [],
        "nj_presence": {"status": "unclear", "evidence": []},
        "signals": [
            {
                "statement": "Untrusted source supplied.",
                "evidence": [
                    {
                        "title": "Bad link",
                        "quote": "Literal captured text.",
                        "url": "https://user:password@example.com/secret",
                    },
                    {
                        "title": "Safe link",
                        "quote": "Safe literal text.",
                        "url": "https://source.example/article",
                    },
                ],
            }
        ],
        "limitations": [],
    }
    company = _company(
        build_catalog(tmp_path, jobs=[{"cards": [bad_card], "review_cards": []}]),
        "Unsafe",
    )

    assert all(
        item["url"] is None or item["url"].startswith(("http://", "https://"))
        for item in company["evidence"]
    )
    assert all(
        person["source_url"] is None or person["source_url"].startswith(("http://", "https://"))
        for person in company["people"]
    )
    assert company["source_count"] == 1


def test_checked_in_snapshot_integrates_all_filings_offerings_and_review_cards() -> None:
    root = Path(__file__).resolve().parents[1]
    payload = build_catalog(root)

    assert payload["stats"] == {
        "companies": 792,
        "nj_supported": 780,
        "with_reputation": 3,
        "team_reviewed": 12,
        "sources": 1975,
    }
    evidence = [item for company in payload["companies"] for item in company["evidence"]]
    assert sum(item["source_type"] == "sec_form_d_company_history" for item in evidence) == 778
    assert sum(item["source_type"] == "sec_form_d_filing" for item in evidence) == 1171
    assert all(
        item["quote"] == ""
        for item in evidence
        if item["source_type"].startswith("sec_form_d")
    )

    assert [item["name"] for item in payload["companies"][:3]] == [
        "Cecilia / Cecilia Energy",
        "Chorah Labs",
        "Queens Carbon",
    ]
    queens = _company(payload, "Queens Carbon")
    chora = _company(payload, "Chorah Labs")
    sunray = _company(payload, "SunRay Scientific")
    adrich = _company(payload, "Adrich")
    assert queens["record_type"] == "research"
    assert queens["pillars"]["reputation"]["status"] == "partial"
    assert queens["nj_status"] == "supported"
    assert chora["nj_status"] == "unverified"
    assert sunray["record_type"] == "lead"
    assert sunray["pillars"]["funding"]["status"] == "available"
    assert "team reviewed" in sunray["tags"]

    assert sunray["description"] == (
        "NJ advanced electronic materials company making patented ZTACH ACE "
        "conductive adhesives, conductive inks and encapsulants for electronics packaging."
    )
    sunray_metrics = {
        item["label"]: item["value"]
        for item in sunray["pillars"]["business"]["metrics"]
    }
    assert sunray_metrics["Business-model analyst judgment (1–5)"] == "3/5"
    assert sunray_metrics["Novelty analyst judgment (1–5)"] == "4/5"
    assert sunray_metrics["Current headcount estimate"] == 16
    assert sunray_metrics["Reported founding year"] == 2012
    assert (
        sunray_metrics["Broader sector venture-funding proxy (2024)"]
        == "USD 37.5B"
    )
    assert (
        sunray_metrics["Broader sector venture-funding proxy (2025)"]
        == "USD 40.5B"
    )
    assert set(sunray["pillars"]["business"]["findings"]) == {
        "Patent-protected specialty materials can earn good gross margins, but long design-in cycles and a niche market explain slow growth (~16 staff after 14 years).",
        "Patented ZTACH ACE conductive epoxy (Bell Labs origin) is new core technology offering a cheaper route to fine-pitch interconnect than conventional anisotropic films.",
    }

    # These values come from the checked-in business CSVs whose headers contain
    # spaces after commas.  Keep this as a real-repository integration guard.
    adrich_metrics = {
        item["label"]: item["value"]
        for item in adrich["pillars"]["business"]["metrics"]
    }
    assert adrich_metrics["Business-model analyst judgment (1–5)"] == "2/5"
    assert adrich_metrics["Novelty analyst judgment (1–5)"] == "4/5"
    assert adrich_metrics["Current headcount estimate"] == 12
    assert (
        adrich_metrics["Broader sector venture-funding proxy (2025)"]
        == "USD 18.0B"
    )
