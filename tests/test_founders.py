from __future__ import annotations

import httpx
import pytest

import unified.founders as founders_module
from unified.founders import (
    FounderConfigurationError,
    FounderDataLimitError,
    FounderReader,
    FounderReaderError,
    TABLE_SELECTS,
    aggregate_founder_rows,
)


def _rows(**overrides):
    rows = {
        "startups": [
            {"id": "s1", "name": "Alpha Labs", "description": "Alpha description", "created_at": "2026-01-01T00:00:00Z"},
            {"id": "s2", "name": "Beta Works", "description": "Beta description", "created_at": "2026-01-02T00:00:00Z"},
        ],
        "founders": [
            {"id": "f1", "startup_id": "s1", "name": "Alex Same", "title": "Advisor & CEO", "created_at": "2026-01-03T00:00:00Z", "birth_year": 1970, "linkedin_url": "private"},
            {"id": "f2", "startup_id": "s2", "name": "Blair Founder", "title": "Co-Founder", "created_at": "2026-01-04T00:00:00Z"},
        ],
        "education": [
            {"id": "ed1", "founder_id": "f1", "institution": "State U", "degree": "MS", "field": "Robotics", "start_year": 2018, "end_year": 2020, "source_name": "People Data Labs", "source_url": None, "created_at": "2026-02-01T00:00:00Z"},
            {"id": "ed-orphan", "founder_id": "missing", "institution": "Nowhere", "source_name": "People Data Labs"},
        ],
        "companies": [
            {"id": "c1", "founder_id": "f1", "company_name": "Previous Co", "role": "CEO", "start_date": "2020-01-01", "end_date": None, "status": "current", "source_name": "Team research (startups.csv)", "source_url": "https://source.example/company", "created_at": "2026-02-02T00:00:00Z"},
        ],
        "achievements": [
            {"id": "a1", "founder_id": "f1", "achievement": "Three publications", "issuer": "Index", "year": 2025, "description": "Name-search result", "source_name": "Semantic Scholar", "source_url": "https://source.example/achievement", "created_at": "2026-02-03T00:00:00Z"},
        ],
        "grants": [
            {"id": "g1", "startup_id": "s1", "founder_id": "f1", "program": "Program 1", "agency": "Agency", "amount": 100, "award_date": "2025-01-01", "source_name": "NSF Award Search", "source_url": "https://source.example/g1", "created_at": "2026-02-04T00:00:00Z"},
            {"id": "g2", "startup_id": "s1", "founder_id": None, "program": "Program 2", "agency": "Agency", "amount": 200, "award_date": "2025-02-01", "source_name": "USAspending.gov", "source_url": "https://source.example/g2", "created_at": "2026-02-05T00:00:00Z"},
            {"id": "g3", "startup_id": "s2", "founder_id": "f1", "program": "Conflicting", "agency": "Agency", "amount": 300, "award_date": None, "source_name": "NIH RePORTER", "source_url": None, "created_at": "2026-02-06T00:00:00Z"},
            {"id": "g-orphan", "startup_id": "missing", "founder_id": "missing", "program": "Orphan"},
        ],
        "evidence": [
            {"id": "ev1", "entity_type": "education", "entity_id": "ed1", "claim": "Alex Same attended State U", "source_name": "People Data Labs", "source_url": None, "source_date": "2020-01-01", "retrieved_at": "2026-03-01T00:00:00Z", "confidence": 0.7},
            {"id": "ev2", "entity_type": "company", "entity_id": "c1", "claim": "Alex Same worked at Previous Co", "source_name": "Team research (startups.csv)", "source_url": "https://source.example/company", "source_date": None, "retrieved_at": "2026-03-02T00:00:00Z", "confidence": 1},
            {"id": "ev-orphan", "entity_type": "achievement", "entity_id": "missing", "claim": "Unknown"},
        ],
    }
    rows.update(overrides)
    return rows


def test_aggregation_uses_id_joins_and_qualifies_roles_grants_and_sources():
    result = aggregate_founder_rows(**_rows())

    assert list(result.profiles) == ["Alpha Labs", "Beta Works"]
    alpha = result.profiles["Alpha Labs"][0]
    beta = result.profiles["Beta Works"][0]
    assert set(alpha) == {"founder", "education", "companies", "achievements", "grants", "evidence", "limitations"}
    assert alpha["founder"]["relationship_status"] == "founder_not_established"
    assert "does not establish founder status" in alpha["founder"]["qualification"]
    assert alpha["founder"]["company_description"] == "Alpha description"
    assert "birth_year" not in alpha["founder"]
    assert "linkedin_url" not in alpha["founder"]
    assert beta["founder"]["relationship_status"] == "founder_role_recorded"

    assert [row["id"] for row in alpha["education"]] == ["ed1"]
    assert alpha["education"][0]["verification_status"] == "unverified_identity_match"
    assert alpha["companies"][0]["role"] == "CEO"
    assert "does not by itself establish" in alpha["companies"][0]["qualification"]
    assert alpha["achievements"][0]["description"] == "Name-search result"
    assert alpha["achievements"][0]["verification_status"] == "unverified_identity_match"
    assert beta["education"] == []
    assert beta["achievements"] == []

    grants = {row["id"]: row for row in alpha["grants"]}
    assert grants["g1"]["association_scope"] == "person_and_company"
    assert grants["g2"]["association_scope"] == "company"
    assert grants["g3"]["association_scope"] == "conflicting_ids"
    assert "attribution is ambiguous" in grants["g3"]["qualification"]
    assert beta["grants"] == []

    evidence = {row["id"]: row for row in alpha["evidence"]}
    assert evidence["ev1"]["source_date"] == "2020-01-01"
    assert evidence["ev1"]["retrieved_at"] == "2026-03-01T00:00:00Z"
    assert evidence["ev1"]["verification_status"] == "unverified_identity_match"
    assert any("orphan education" in message for message in result.limitations)
    assert any("orphan grant" in message for message in result.limitations)
    assert any("orphan evidence" in message for message in result.limitations)


def test_duplicate_names_stay_separate_and_orphan_people_are_not_name_joined():
    data = _rows(
        startups=[{"id": "s1", "name": "Alpha Labs", "description": None, "created_at": None}],
        founders=[
            {"id": "f1", "startup_id": "s1", "name": "Jordan Lee", "title": "CEO", "created_at": None},
            {"id": "f2", "startup_id": "s1", "name": "Jordan Lee", "title": "Adviser", "created_at": None},
            {"id": "f3", "startup_id": "missing", "name": "Jordan Lee", "title": "Founder", "created_at": None},
        ],
        education=[{"id": "ed2", "founder_id": "f2", "institution": "Exact ID University", "source_name": "People Data Labs"}],
        companies=[],
        achievements=[],
        grants=[],
        evidence=[],
    )
    result = aggregate_founder_rows(**data)

    profiles = result.profiles["Alpha Labs"]
    assert [profile["founder"]["id"] for profile in profiles] == ["f1", "f2"]
    assert profiles[0]["education"] == []
    assert profiles[1]["education"][0]["institution"] == "Exact ID University"
    assert all(any("same name" in item for item in profile["limitations"]) for profile in profiles)
    assert any("person without a matching startup" in item for item in result.limitations)


def test_reader_uses_get_only_safe_selects_and_returns_exact_company_keys():
    table_rows = _rows(
        startups=[{"id": "s1", "name": "Exact Company, Inc.", "description": "Useful", "created_at": "2026-01-01T00:00:00Z"}],
        founders=[{"id": "f1", "startup_id": "s1", "name": "Person", "title": "CEO", "created_at": "2026-01-02T00:00:00Z"}],
        education=[],
        companies=[],
        achievements=[],
        grants=[],
        evidence=[],
    )
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        table = request.url.path.rsplit("/", 1)[-1]
        values = table_rows[table]
        content_range = f"0-{len(values) - 1}/{len(values)}" if values else "*/0"
        return httpx.Response(200, json=values, headers={"Content-Range": content_range})

    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)
    reader = FounderReader(
        "https://project.supabase.co", "READONLY-SECRET", credential_source="readonly", client=client
    )
    profiles = reader.fetch_profiles()

    assert list(profiles) == ["Exact Company, Inc."]
    assert reader.configured is True
    assert reader.credential_source == "readonly"
    assert len(requests) == len(TABLE_SELECTS)
    for request in requests:
        assert request.method == "GET"
        assert request.url.path in {f"/rest/v1/{table}" for table in TABLE_SELECTS}
        assert "/founders/" not in request.url.path
        assert not request.url.path.endswith(("/research", "/enrich", "/reset"))
        assert "READONLY-SECRET" not in str(request.url)
        assert request.headers["apikey"] == "READONLY-SECRET"
        assert request.headers["authorization"] == "Bearer READONLY-SECRET"
        selected = request.url.params["select"]
        assert "birth_year" not in selected
        assert "linkedin_url" not in selected
        assert "github_url" not in selected
        assert "location" not in selected
        assert set(request.url.params) == {"select", "order"}
    client.close()


def test_default_constructor_reads_process_env_without_loading_repo_files(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://project.supabase.co")
    monkeypatch.setenv("SUPABASE_READONLY_KEY", "READONLY")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "SERVICE")
    reader = FounderReader()
    try:
        assert reader.configured is True
        assert reader.credential_source == "readonly"
        assert "READONLY" not in repr(reader)
        assert "SERVICE" not in repr(reader)
    finally:
        reader.close()


def test_truncation_is_detected_even_when_server_omits_total():
    ranges: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested = request.headers["range"]
        ranges.append(requested)
        if requested == "0-1":
            return httpx.Response(
                206,
                json=[{"id": "1"}, {"id": "2"}],
                headers={"Content-Range": "0-1/*"},
            )
        return httpx.Response(
            206, json=[{"id": "3"}], headers={"Content-Range": "2-2/*"}
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    reader = FounderReader(
        "https://project.supabase.co", "SECRET", client=client, page_size=2, max_rows=2
    )
    with pytest.raises(FounderDataLimitError, match="more than the supported 2 rows"):
        reader._fetch_table("startups", ("id", "name"))
    assert ranges == ["0-1", "2-2"]
    client.close()


def test_exact_cap_without_total_is_accepted_only_after_empty_probe():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.headers["range"] == "0-1":
            return httpx.Response(
                206,
                json=[{"id": "1"}, {"id": "2"}],
                headers={"Content-Range": "0-1/*"},
            )
        return httpx.Response(416, json={"private": "do not expose"}, headers={"Content-Range": "*/2"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    reader = FounderReader(
        "https://project.supabase.co", "SECRET", client=client, page_size=2, max_rows=2
    )
    assert [row["id"] for row in reader._fetch_table("startups", ("id",))] == ["1", "2"]
    client.close()


def test_reported_total_over_cap_stops_immediately():
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            206,
            json=[{"id": "1"}, {"id": "2"}],
            headers={"Content-Range": "0-1/3"},
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    reader = FounderReader(
        "https://project.supabase.co", "SECRET", client=client, page_size=2, max_rows=2
    )
    with pytest.raises(FounderDataLimitError):
        reader._fetch_table("startups", ("id",))
    assert calls == 1
    client.close()


def test_provider_errors_are_sanitized_and_never_echo_key_or_body():
    secret = "SERVICE-ROLE-SUPER-SECRET"

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        return httpx.Response(500, text=f"provider body leaked {secret}")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    reader = FounderReader("https://project.supabase.co", secret, client=client)
    with pytest.raises(FounderReaderError) as caught:
        reader._fetch_table("founders", ("id",))
    message = str(caught.value)
    assert secret not in message
    assert "provider body" not in message
    assert "HTTP 500" in message
    assert secret not in repr(reader)
    client.close()


def test_total_operation_deadline_aborts_before_remaining_tables(monkeypatch):
    requests: list[httpx.Request] = []
    clock = iter([0.0, 0.0, 0.25, 1.25])
    monkeypatch.setattr(founders_module.time, "monotonic", lambda: next(clock))

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=[], headers={"Content-Range": "*/0"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    reader = FounderReader(
        "https://project.supabase.co",
        "SECRET",
        client=client,
        operation_timeout_seconds=1,
    )
    with pytest.raises(FounderReaderError, match="total time limit"):
        reader.fetch_profiles()
    assert len(requests) == 1
    assert all(request.method == "GET" for request in requests)
    client.close()


def test_environment_prefers_readonly_key_and_unconfigured_reader_fails_closed():
    client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(500)))
    reader = FounderReader.from_env(
        {
            "SUPABASE_URL": "https://project.supabase.co",
            "SUPABASE_READONLY_KEY": "READONLY",
            "SUPABASE_SERVICE_ROLE_KEY": "SERVICE",
        },
        client=client,
    )
    assert reader.configured is True
    assert reader.credential_source == "readonly"
    assert "READONLY" not in repr(reader)

    unconfigured = FounderReader.from_env({}, client=client)
    assert unconfigured.configured is False
    with pytest.raises(FounderConfigurationError, match="not configured"):
        unconfigured.fetch_profiles()
    client.close()
