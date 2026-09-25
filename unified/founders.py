"""Read-only access to the founder evidence tables in Supabase.

The original founder service includes mutation and enrichment routes.  The
unified product deliberately bypasses those routes and reads a small allowlist
of columns from PostgREST with GET requests only.  Aggregation joins records by
database IDs; person or company names are never used as join keys.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import os
import re
import time
from typing import Any, Mapping, Sequence
from urllib.parse import urlsplit

import httpx


MAX_TABLE_ROWS = 10_000
DEFAULT_PAGE_SIZE = 500
DEFAULT_OPERATION_TIMEOUT_SECONDS = 45.0
_UNSET = object()


TABLE_SELECTS: dict[str, tuple[str, ...]] = {
    "startups": ("id", "name", "description", "created_at"),
    "founders": ("id", "startup_id", "name", "title", "created_at"),
    "education": (
        "id", "founder_id", "institution", "degree", "field", "start_year",
        "end_year", "source_name", "source_url", "created_at",
    ),
    "companies": (
        "id", "founder_id", "company_name", "role", "start_date", "end_date",
        "status", "source_name", "source_url", "created_at",
    ),
    "achievements": (
        "id", "founder_id", "achievement", "issuer", "year", "description",
        "source_name", "source_url", "created_at",
    ),
    "grants": (
        "id", "startup_id", "founder_id", "program", "agency", "amount",
        "award_date", "source_name", "source_url", "created_at",
    ),
    "evidence": (
        "id", "entity_type", "entity_id", "claim", "source_name", "source_url",
        "source_date", "retrieved_at", "confidence",
    ),
}


NAME_SEARCH_SOURCES = {
    "people data labs",
    "wikidata",
    "wikipedia",
    "semantic scholar",
    "orcid",
    "gdelt",
    "sec edgar",
    "nsf award search",
    "nih reporter",
}
COMPANY_SEARCH_SOURCES = {"usaspending.gov", "usaspending"}


class FounderReaderError(RuntimeError):
    """A safe, user-displayable founder integration failure."""


class FounderConfigurationError(FounderReaderError):
    """The optional integration has no usable server configuration."""


class FounderDataLimitError(FounderReaderError):
    """A table exceeded the bounded read limit."""


@dataclass(frozen=True)
class FounderAggregation:
    """Pure aggregation output plus diagnostics for records we cannot attach."""

    profiles: dict[str, list[dict[str, Any]]]
    limitations: tuple[str, ...]


def _value(row: Mapping[str, Any], key: str) -> Any:
    """Return a JSON value while keeping missing and explicit null equivalent."""

    return row.get(key)


def _source_status(source_name: Any) -> tuple[str, str]:
    source = str(source_name or "").strip().casefold()
    if source in NAME_SEARCH_SOURCES:
        return (
            "unverified_identity_match",
            "This record came from a name-based lookup and may describe a different person; confirm identity before relying on it.",
        )
    if source in COMPANY_SEARCH_SOURCES:
        return (
            "unverified_company_match",
            "This record came from a company-name lookup; confirm the recipient identity before relying on it.",
        )
    if source:
        return (
            "sourced_record",
            "This is a stored source record. It supports what the cited source says, not independent truth or founder status.",
        )
    return (
        "requires_source_review",
        "No source name is stored for this record; review its linked evidence before relying on it.",
    )


def _append_once(values: list[str], message: str) -> None:
    if message not in values:
        values.append(message)


def _row_source_fields(row: Mapping[str, Any]) -> dict[str, Any]:
    status, qualification = _source_status(row.get("source_name"))
    return {
        "source_name": _value(row, "source_name"),
        "source_url": _value(row, "source_url"),
        "verification_status": status,
        "qualification": qualification,
    }


def _education_record(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": _value(row, "id"),
        "institution": _value(row, "institution"),
        "degree": _value(row, "degree"),
        "field": _value(row, "field"),
        "start_year": _value(row, "start_year"),
        "end_year": _value(row, "end_year"),
        "created_at": _value(row, "created_at"),
        **_row_source_fields(row),
    }


def _company_record(row: Mapping[str, Any]) -> dict[str, Any]:
    source = _row_source_fields(row)
    source["qualification"] = (
        source["qualification"]
        + " The recorded role is an employment or association claim; it does not by itself establish that this person founded the company."
    )
    return {
        "id": _value(row, "id"),
        "company_name": _value(row, "company_name"),
        "role": _value(row, "role"),
        "start_date": _value(row, "start_date"),
        "end_date": _value(row, "end_date"),
        "status": _value(row, "status"),
        "created_at": _value(row, "created_at"),
        **source,
    }


def _achievement_record(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": _value(row, "id"),
        "achievement": _value(row, "achievement"),
        "issuer": _value(row, "issuer"),
        "year": _value(row, "year"),
        "description": _value(row, "description"),
        "created_at": _value(row, "created_at"),
        **_row_source_fields(row),
    }


def _grant_record(row: Mapping[str, Any], association_scope: str) -> dict[str, Any]:
    source = _row_source_fields(row)
    association_qualification = {
        "person_and_company": (
            "The row links both database IDs, but the source identity and award attribution still require review."
        ),
        "person": (
            "The row is associated with this person record; it does not establish an award to the displayed company."
        ),
        "company": (
            "The row is associated with the company record; it does not establish a personal award or founder status."
        ),
        "company_with_unmatched_person": (
            "The company ID matches, but the row's person ID does not; only the company-level association is retained."
        ),
        "conflicting_ids": (
            "The person and company IDs point to different home-company records; attribution is ambiguous."
        ),
    }[association_scope]
    source["qualification"] = source["qualification"] + " " + association_qualification
    return {
        "id": _value(row, "id"),
        "program": _value(row, "program"),
        "agency": _value(row, "agency"),
        "amount": _value(row, "amount"),
        "award_date": _value(row, "award_date"),
        "created_at": _value(row, "created_at"),
        "association_scope": association_scope,
        **source,
    }


def _evidence_record(row: Mapping[str, Any]) -> dict[str, Any]:
    status, qualification = _source_status(row.get("source_name"))
    return {
        "id": _value(row, "id"),
        "entity_type": _value(row, "entity_type"),
        "entity_id": _value(row, "entity_id"),
        "claim": _value(row, "claim"),
        "source_name": _value(row, "source_name"),
        "source_url": _value(row, "source_url"),
        "source_date": _value(row, "source_date"),
        "retrieved_at": _value(row, "retrieved_at"),
        "confidence": _value(row, "confidence"),
        "verification_status": status,
        "qualification": qualification,
    }


def aggregate_founder_rows(
    *,
    startups: Sequence[Mapping[str, Any]],
    founders: Sequence[Mapping[str, Any]],
    education: Sequence[Mapping[str, Any]],
    companies: Sequence[Mapping[str, Any]],
    achievements: Sequence[Mapping[str, Any]],
    grants: Sequence[Mapping[str, Any]],
    evidence: Sequence[Mapping[str, Any]],
) -> FounderAggregation:
    """Join Supabase rows by IDs without guessing identities from names.

    Orphaned rows are omitted and counted in ``limitations``. Duplicate person
    names remain separate profile objects, keyed internally by their IDs.
    """

    diagnostics: list[str] = []
    dropped: defaultdict[str, int] = defaultdict(int)

    startup_by_id: dict[str, Mapping[str, Any]] = {}
    startup_name_ids: defaultdict[str, set[str]] = defaultdict(set)
    for startup in startups:
        startup_id = str(startup.get("id") or "")
        name = startup.get("name")
        if not startup_id or not isinstance(name, str) or not name.strip():
            dropped["startup"] += 1
            continue
        if startup_id in startup_by_id:
            dropped["duplicate startup"] += 1
            continue
        startup_by_id[startup_id] = startup
        startup_name_ids[name].add(startup_id)

    profiles: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    profile_by_founder_id: dict[str, dict[str, Any]] = {}
    startup_profiles: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    founder_startup: dict[str, str] = {}
    normalized_names: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)

    for founder in founders:
        founder_id = str(founder.get("id") or "")
        startup_id = str(founder.get("startup_id") or "")
        startup = startup_by_id.get(startup_id)
        name = founder.get("name")
        if not founder_id or founder_id in profile_by_founder_id:
            dropped["duplicate or invalid person"] += 1
            continue
        if startup is None:
            dropped["person without a matching startup"] += 1
            continue
        if not isinstance(name, str) or not name.strip():
            dropped["person without a name"] += 1
            continue

        company_name = str(startup["name"])
        title = founder.get("title")
        founder_role_recorded = bool(
            isinstance(title, str) and re.search(r"\bfounder\b", title, re.IGNORECASE)
        )
        relationship_status = "founder_role_recorded" if founder_role_recorded else "founder_not_established"
        relationship_qualification = (
            "The stored title explicitly includes founder, but this remains a recorded claim that should be checked against its source."
            if founder_role_recorded
            else "Placement in the database's founders table does not establish founder status; use the recorded title and source evidence."
        )
        profile: dict[str, Any] = {
            "founder": {
                "id": founder_id,
                "name": name,
                "title": title,
                "created_at": founder.get("created_at"),
                "company_record_id": startup_id,
                "company_name": company_name,
                "company_description": startup.get("description"),
                "company_created_at": startup.get("created_at"),
                "relationship_status": relationship_status,
                "qualification": relationship_qualification,
            },
            "education": [],
            "companies": [],
            "achievements": [],
            "grants": [],
            "evidence": [],
            "limitations": [
                "Name-search enrichment remains unverified until the source identity is confirmed.",
                relationship_qualification,
            ],
        }
        profiles[company_name].append(profile)
        profile_by_founder_id[founder_id] = profile
        startup_profiles[startup_id].append(profile)
        founder_startup[founder_id] = startup_id
        normalized_names[name.casefold().strip()].append(profile)

    for same_name_profiles in normalized_names.values():
        if len(same_name_profiles) > 1:
            for profile in same_name_profiles:
                _append_once(
                    profile["limitations"],
                    "Another person record uses the same name. Records remain separate by ID and require identity review.",
                )

    for company_name, startup_ids in startup_name_ids.items():
        if len(startup_ids) > 1:
            for profile in profiles.get(company_name, []):
                _append_once(
                    profile["limitations"],
                    "Multiple startup records use this exact company name. Their person records remain separated by startup ID.",
                )

    # Map each source entity to the profiles that own it. The entity type is
    # part of the key so an accidental cross-table UUID collision cannot join.
    entity_profiles: defaultdict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for founder_id, profile in profile_by_founder_id.items():
        entity_profiles[("founder", founder_id)].append(profile)

    def attach_person_rows(
        rows: Sequence[Mapping[str, Any]],
        *,
        output_key: str,
        entity_type: str,
        transform,
    ) -> None:
        seen_ids: set[str] = set()
        for row in rows:
            row_id = str(row.get("id") or "")
            founder_id = str(row.get("founder_id") or "")
            profile = profile_by_founder_id.get(founder_id)
            if not row_id or row_id in seen_ids:
                dropped[f"duplicate or invalid {entity_type}"] += 1
                continue
            seen_ids.add(row_id)
            if profile is None:
                dropped[f"orphan {entity_type}"] += 1
                continue
            record = transform(row)
            profile[output_key].append(record)
            entity_profiles[(entity_type, row_id)].append(profile)
            if record.get("verification_status") in {
                "unverified_identity_match", "unverified_company_match", "requires_source_review"
            }:
                _append_once(profile["limitations"], record["qualification"])

    attach_person_rows(
        education, output_key="education", entity_type="education", transform=_education_record
    )
    attach_person_rows(
        companies, output_key="companies", entity_type="company", transform=_company_record
    )
    attach_person_rows(
        achievements,
        output_key="achievements",
        entity_type="achievement",
        transform=_achievement_record,
    )

    seen_grants: set[str] = set()
    for grant in grants:
        grant_id = str(grant.get("id") or "")
        if not grant_id or grant_id in seen_grants:
            dropped["duplicate or invalid grant"] += 1
            continue
        seen_grants.add(grant_id)
        founder_id = str(grant.get("founder_id") or "")
        startup_id = str(grant.get("startup_id") or "")
        founder_profile = profile_by_founder_id.get(founder_id)
        company_profiles = startup_profiles.get(startup_id, [])

        targets: list[dict[str, Any]]
        if founder_profile is not None:
            targets = [founder_profile]
            if startup_id and founder_startup[founder_id] != startup_id:
                association_scope = "conflicting_ids"
            elif startup_id:
                association_scope = "person_and_company"
            else:
                association_scope = "person"
        elif company_profiles:
            targets = list(company_profiles)
            association_scope = "company_with_unmatched_person" if founder_id else "company"
        else:
            dropped["orphan grant"] += 1
            continue

        for profile in targets:
            record = _grant_record(grant, association_scope)
            profile["grants"].append(record)
            entity_profiles[("grant", grant_id)].append(profile)
            if association_scope in {"conflicting_ids", "company_with_unmatched_person"}:
                _append_once(profile["limitations"], record["qualification"])
            if record["verification_status"] != "sourced_record":
                _append_once(profile["limitations"], record["qualification"])

    seen_evidence: set[str] = set()
    for item in evidence:
        evidence_id = str(item.get("id") or "")
        entity_type = str(item.get("entity_type") or "").strip().casefold()
        entity_id = str(item.get("entity_id") or "")
        if not evidence_id or evidence_id in seen_evidence:
            dropped["duplicate or invalid evidence"] += 1
            continue
        seen_evidence.add(evidence_id)
        targets = entity_profiles.get((entity_type, entity_id), [])
        if not targets:
            dropped["orphan evidence"] += 1
            continue
        record = _evidence_record(item)
        for profile in targets:
            profile["evidence"].append(dict(record))
            if record["verification_status"] != "sourced_record":
                _append_once(profile["limitations"], record["qualification"])

    for label, count in sorted(dropped.items()):
        noun = "row" if count == 1 else "rows"
        diagnostics.append(f"Omitted {count} {label} {noun} because it could not be joined safely.")

    result: dict[str, list[dict[str, Any]]] = {}
    for company_name in sorted(profiles, key=str.casefold):
        company_profiles = profiles[company_name]
        for profile in company_profiles:
            for key in ("education", "companies", "achievements", "grants", "evidence"):
                profile[key].sort(key=lambda row: str(row.get("id") or ""))
        result[company_name] = sorted(
            company_profiles,
            key=lambda profile: (
                str(profile["founder"].get("name") or "").casefold(),
                str(profile["founder"].get("id") or ""),
            ),
        )
    return FounderAggregation(result, tuple(diagnostics))


_CONTENT_RANGE = re.compile(r"^(?:(\d+)-(\d+)|\*)/(\d+|\*)$")


def _parse_content_range(value: str | None) -> tuple[int | None, int | None, int | None]:
    if not value:
        return None, None, None
    match = _CONTENT_RANGE.fullmatch(value.strip())
    if not match:
        raise FounderReaderError("Founder integration returned invalid pagination metadata.")
    start = int(match.group(1)) if match.group(1) is not None else None
    end = int(match.group(2)) if match.group(2) is not None else None
    total = int(match.group(3)) if match.group(3) != "*" else None
    return start, end, total


class FounderReader:
    """Bounded, GET-only PostgREST reader for the optional founder module."""

    def __init__(
        self,
        supabase_url: str | None | object = _UNSET,
        api_key: str | None | object = _UNSET,
        *,
        credential_source: str | None = None,
        client: httpx.Client | None = None,
        page_size: int = DEFAULT_PAGE_SIZE,
        max_rows: int = MAX_TABLE_ROWS,
        operation_timeout_seconds: float = DEFAULT_OPERATION_TIMEOUT_SECONDS,
    ) -> None:
        if supabase_url is _UNSET and api_key is _UNSET:
            supabase_url = os.environ.get("SUPABASE_URL")
            readonly_key = os.environ.get("SUPABASE_READONLY_KEY", "").strip()
            service_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
            api_key = readonly_key or service_key
            credential_source = (
                "readonly" if readonly_key else "service_role" if service_key else None
            )
        else:
            # Passing one explicit value never causes the other credential to be
            # filled from ambient state. This keeps tests and custom hosts
            # deterministic.
            supabase_url = None if supabase_url is _UNSET else supabase_url
            api_key = None if api_key is _UNSET else api_key
        self._url = (supabase_url or "").strip().rstrip("/")
        self._key = (api_key or "").strip()
        self.credential_source = credential_source if self._key else None
        self.page_size = page_size
        self.max_rows = max_rows
        self.operation_timeout_seconds = float(operation_timeout_seconds)
        self.last_limitations: tuple[str, ...] = ()

        if not 1 <= page_size <= 1_000:
            raise ValueError("page_size must be between 1 and 1000")
        if not 1 <= max_rows <= MAX_TABLE_ROWS:
            raise ValueError(f"max_rows must be between 1 and {MAX_TABLE_ROWS}")
        if not 0 < self.operation_timeout_seconds <= 300:
            raise ValueError("operation_timeout_seconds must be between 0 and 300")
        if self._url and not self._safe_base_url(self._url):
            raise FounderConfigurationError("SUPABASE_URL must be HTTPS (or loopback HTTP for local development).")

        self._owns_client = client is None
        self._client = client or httpx.Client(
            timeout=httpx.Timeout(20.0, connect=5.0, read=20.0, write=5.0, pool=5.0),
            follow_redirects=False,
        )

    @classmethod
    def from_env(
        cls,
        environ: Mapping[str, str] | None = None,
        **kwargs: Any,
    ) -> "FounderReader":
        values = os.environ if environ is None else environ
        readonly_key = values.get("SUPABASE_READONLY_KEY", "").strip()
        service_key = values.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
        key = readonly_key or service_key
        source = "readonly" if readonly_key else "service_role" if service_key else None
        return cls(values.get("SUPABASE_URL"), key, credential_source=source, **kwargs)

    @staticmethod
    def _safe_base_url(value: str) -> bool:
        try:
            parsed = urlsplit(value)
            if parsed.username or parsed.password or not parsed.hostname or parsed.query or parsed.fragment:
                return False
            if parsed.scheme == "https":
                return True
            return parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1", "::1"}
        except ValueError:
            return False

    @property
    def configured(self) -> bool:
        return bool(self._url and self._key)

    def __repr__(self) -> str:
        return (
            f"FounderReader(configured={self.configured}, "
            f"credential_source={self.credential_source!r})"
        )

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> "FounderReader":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    def _request_page(
        self,
        table: str,
        columns: Sequence[str],
        start: int,
        end: int,
        *,
        deadline: float,
    ) -> tuple[list[dict[str, Any]], tuple[int | None, int | None, int | None]]:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise FounderReaderError("Founder sync exceeded its total time limit.")
        headers = {
            "Accept": "application/json",
            "apikey": self._key,
            "Authorization": "Bearer " + self._key,
            "Prefer": "count=exact",
            "Range-Unit": "items",
            "Range": f"{start}-{end}",
        }
        try:
            response = self._client.get(
                f"{self._url}/rest/v1/{table}",
                params={"select": ",".join(columns), "order": "id.asc"},
                headers=headers,
                # Bound every socket phase by the remaining operation budget.
                # The deadline is checked again after the request and parse so
                # an overrun can never be committed as a successful sync.
                timeout=min(20.0, remaining),
            )
        except httpx.TimeoutException:
            raise FounderReaderError(f"Timed out while reading founder table '{table}'.") from None
        except httpx.RequestError:
            raise FounderReaderError(f"Could not connect while reading founder table '{table}'.") from None

        if time.monotonic() >= deadline:
            raise FounderReaderError("Founder sync exceeded its total time limit.")

        content_range = _parse_content_range(response.headers.get("content-range"))
        if response.status_code == 416:
            total = content_range[2]
            if total is not None and start >= total:
                return [], content_range
        if response.status_code not in (200, 206):
            # Do not include response text, request headers, or provider error
            # details: they can echo server credentials or private records.
            raise FounderReaderError(
                f"Founder table '{table}' could not be read (HTTP {response.status_code})."
            )
        try:
            data = response.json()
        except (ValueError, TypeError):
            raise FounderReaderError(
                f"Founder table '{table}' returned an unreadable response."
            ) from None
        if not isinstance(data, list) or any(not isinstance(row, dict) for row in data):
            raise FounderReaderError(
                f"Founder table '{table}' returned an unexpected response shape."
            )
        if time.monotonic() >= deadline:
            raise FounderReaderError("Founder sync exceeded its total time limit.")
        return data, content_range

    def _fetch_table(
        self,
        table: str,
        columns: Sequence[str],
        *,
        deadline: float | None = None,
    ) -> list[dict[str, Any]]:
        deadline = deadline or time.monotonic() + self.operation_timeout_seconds
        rows: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        known_total: int | None = None

        while len(rows) < self.max_rows:
            start = len(rows)
            end = min(start + self.page_size - 1, self.max_rows - 1)
            page, (range_start, range_end, reported_total) = self._request_page(
                table, columns, start, end, deadline=deadline
            )
            if reported_total is not None:
                if reported_total > self.max_rows:
                    raise FounderDataLimitError(
                        f"Founder table '{table}' has more than the supported {self.max_rows} rows; sync was aborted."
                    )
                if known_total is not None and known_total != reported_total:
                    raise FounderReaderError(
                        f"Founder table '{table}' changed while it was being read; retry the sync."
                    )
                known_total = reported_total
            if page and range_start is not None and range_start != start:
                raise FounderReaderError(
                    f"Founder table '{table}' returned inconsistent pagination metadata."
                )
            if page and range_end is not None and range_start is not None:
                if range_end - range_start + 1 != len(page):
                    raise FounderReaderError(
                        f"Founder table '{table}' returned inconsistent pagination metadata."
                    )
            if len(page) > end - start + 1:
                raise FounderReaderError(
                    f"Founder table '{table}' exceeded the requested page size."
                )
            if not page:
                if known_total is not None and len(rows) != known_total:
                    raise FounderReaderError(
                        f"Founder table '{table}' returned an incomplete page set."
                    )
                return rows

            for row in page:
                row_id = str(row.get("id") or "")
                if not row_id or row_id in seen_ids:
                    raise FounderReaderError(
                        f"Founder table '{table}' returned a missing or duplicate row ID."
                    )
                seen_ids.add(row_id)
                rows.append(row)

            if known_total is not None:
                if len(rows) > known_total:
                    raise FounderReaderError(
                        f"Founder table '{table}' returned more rows than its reported total."
                    )
                if len(rows) == known_total:
                    return rows
            elif len(page) < end - start + 1:
                return rows

        # A server that omits an exact total must prove there is no row beyond
        # the cap. This one-row GET prevents a full final page from being
        # silently mistaken for a complete table.
        if known_total is None:
            probe, (_, _, probe_total) = self._request_page(
                table, columns, self.max_rows, self.max_rows, deadline=deadline
            )
            if probe or (probe_total is not None and probe_total > self.max_rows):
                raise FounderDataLimitError(
                    f"Founder table '{table}' has more than the supported {self.max_rows} rows; sync was aborted."
                )
        return rows

    def fetch_profiles(self) -> dict[str, list[dict[str, Any]]]:
        """Fetch and aggregate all configured founder records.

        The result is keyed by the exact startup name and contains one profile
        per person row. No remote mutation or enrichment endpoint is called.
        """

        if not self.configured:
            raise FounderConfigurationError("Founder integration is not configured.")
        deadline = time.monotonic() + self.operation_timeout_seconds
        tables = {
            table: self._fetch_table(table, columns, deadline=deadline)
            for table, columns in TABLE_SELECTS.items()
        }
        if time.monotonic() >= deadline:
            raise FounderReaderError("Founder sync exceeded its total time limit.")
        aggregated = aggregate_founder_rows(**tables)
        if time.monotonic() >= deadline:
            raise FounderReaderError("Founder sync exceeded its total time limit.")
        self.last_limitations = aggregated.limitations
        return aggregated.profiles
