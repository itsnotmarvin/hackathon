"""Deterministic, read-only aggregation for the Garden State catalog.

This module deliberately does not import any of the responsibility-folder
applications.  In particular, it never initializes Supabase or calls a live
service.  It turns the repository's checked-in CSV/JSON evidence plus optional
already-persisted job/profile payloads into the shared API contract.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlsplit


_LEGAL_SUFFIXES = {"inc", "incorporated", "llc", "corp", "corporation"}
_PILLARS = ("founders", "business", "funding", "reputation")
_STATUS_RANK = {"missing": 0, "partial": 1, "available": 2}
_CURRENT_REPUTATION_PIPELINE_VERSION = "1.1.0"
_EARLIER_ASSESSMENT_WARNING = (
    "This saved run used an earlier assessment version. "
    "Start new research to apply current checks."
)
_DOMAIN_IDENTITY_CONFLICT = (
    "A supplied official domain already belongs to another catalog record; "
    "the conflicting domain was not used to merge identities."
)
_PUBLICATION_DATE_CONFLICT = (
    "Matching source evidence has conflicting publication dates; "
    "the first non-empty publication date was retained."
)
_MISSING_SUMMARIES = {
    "founders": "No founder or leadership evidence has been supplied.",
    "business": "No business-model or operating evidence has been supplied.",
    "funding": "No funding evidence has been supplied.",
    "reputation": "No reputation or ecosystem research has been supplied.",
}


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return "".join(ch for ch in text if ch in "\n\t" or ord(ch) >= 32)


def _normalized_name(value: Any) -> str:
    """Normalize an identity without doing fuzzy matching.

    Punctuation/case are normalized and only the explicitly permitted legal
    suffixes are removed.  Words such as Holdings, Fund, LP and Ventures stay
    in the identity because removing them can collapse unrelated SEC issuers.
    """

    text = unicodedata.normalize("NFKC", _clean_text(value)).casefold()
    # Keep letters, numbers and combining marks from every script.  Limiting
    # identity keys to ASCII collapses distinct names such as Chinese company
    # names to the same empty value and therefore the same public ID.
    normalized = "".join(
        character
        if unicodedata.category(character)[0] in {"L", "M", "N"}
        else " "
        for character in text
    )
    tokens = normalized.split()
    while tokens and tokens[-1] in _LEGAL_SUFFIXES:
        tokens.pop()
    return " ".join(tokens)


def _normalized_cik(value: Any) -> str:
    text = _clean_text(value)
    if re.fullmatch(r"[0-9]+", text):
        return str(int(text))
    # Placeholder values such as "N/A" are not identities.  Registering them
    # as CIKs merges every unrelated card carrying the same placeholder.
    return ""


def _safe_url(value: Any) -> str | None:
    """Return an external HTTP(S) URL, rejecting executable/local schemes."""

    raw = _clean_text(value)
    if not raw or any(ch.isspace() for ch in raw):
        return None
    try:
        parsed = urlsplit(raw)
        port = parsed.port  # force validation of malformed ports
        del port
    except ValueError:
        return None
    if parsed.scheme.casefold() not in {"http", "https"}:
        return None
    if not parsed.hostname or parsed.username is not None or parsed.password is not None:
        return None
    return raw


def _normalized_domain(value: Any) -> str:
    raw = _clean_text(value)
    if not raw:
        return ""
    candidate = raw if "://" in raw else f"https://{raw}"
    safe = _safe_url(candidate)
    if not safe:
        return ""
    host = (urlsplit(safe).hostname or "").casefold().rstrip(".")
    return host[4:] if host.startswith("www.") else host


def _stable_id(identity: str) -> str:
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]
    return f"company-{digest}"


def _evidence_id(company_id: str, item: dict[str, Any]) -> str:
    identity = "|".join(
        (
            company_id,
            _clean_text(item.get("pillar")),
            _clean_text(item.get("url")),
            _clean_text(item.get("quote")),
            _clean_text(item.get("title")),
        )
    )
    return "evidence-" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20]


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle, skipinitialspace=True)
        if reader.fieldnames:
            # Normalize header keys only.  Field values remain untouched here
            # and are cleaned by their typed consumers.
            reader.fieldnames = [
                field.strip() if isinstance(field, str) else field
                for field in reader.fieldnames
            ]
        return [dict(row) for row in reader]


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _as_float(value: Any) -> float | None:
    text = _clean_text(value).replace(",", "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _as_int(value: Any) -> int | None:
    number = _as_float(value)
    return int(number) if number is not None else None


def _usd(value: Any) -> str | None:
    number = _as_float(value)
    if number is None:
        return None
    if number.is_integer():
        return f"USD {int(number):,}"
    return f"USD {number:,.2f}"


def _bool_text(value: Any) -> str | None:
    text = _clean_text(value).casefold()
    if text in {"true", "yes", "1"}:
        return "Yes"
    if text in {"false", "no", "0"}:
        return "No"
    return None


def _append_unique(items: list[str], value: Any) -> None:
    text = _clean_text(value)
    if text and text not in items:
        items.append(text)


def _pillar() -> dict[str, Any]:
    return {
        "status": "missing",
        "summary": "",
        "metrics": [],
        "findings": [],
        "limitations": [],
    }


@dataclass
class _Company:
    id: str
    name: str
    identity_name: str
    cik: str | None = None
    description: str = ""
    description_priority: int = 0
    sector: str = "Unclassified"
    sector_priority: int = 0
    location: str = "Location unverified"
    location_priority: int = 0
    nj_status: str = "unverified"
    why_surfaced: str = ""
    why_priority: int = 0
    pillars: dict[str, dict[str, Any]] = field(
        default_factory=lambda: {name: _pillar() for name in _PILLARS}
    )
    tags: set[str] = field(default_factory=set)
    limitations: list[str] = field(default_factory=list)
    aliases: set[str] = field(default_factory=set)
    domains: set[str] = field(default_factory=set)
    people: dict[tuple[str, str], dict[str, Any]] = field(default_factory=dict)
    evidence: dict[tuple[str, str, str], dict[str, Any]] = field(default_factory=dict)
    dates: set[str] = field(default_factory=set)
    has_filing: bool = False
    has_team: bool = False
    has_reputation: bool = False
    has_founder_profile: bool = False

    def set_description(self, value: Any, priority: int) -> None:
        text = _clean_text(value)
        if text and priority >= self.description_priority:
            self.description = text
            self.description_priority = priority

    def set_sector(self, value: Any, priority: int) -> None:
        text = _clean_text(value)
        if text and priority >= self.sector_priority:
            self.sector = text
            self.sector_priority = priority

    def set_location(self, value: Any, priority: int) -> None:
        text = _clean_text(value)
        if text and priority >= self.location_priority:
            self.location = text
            self.location_priority = priority

    def set_why(self, value: Any, priority: int) -> None:
        text = _clean_text(value)
        if text and priority >= self.why_priority:
            self.why_surfaced = text
            self.why_priority = priority


class _Resolver:
    """Conservative entity resolver with explicit ambiguity handling."""

    def __init__(self) -> None:
        self.companies: list[_Company] = []
        self.by_cik: dict[str, _Company] = {}
        self.by_name: dict[str, set[int]] = defaultdict(set)
        self.by_domain: dict[str, set[int]] = defaultdict(set)

    def _register_name(self, company: _Company, name: Any) -> None:
        normalized = _normalized_name(name)
        if normalized:
            company.aliases.add(normalized)
            self.by_name[normalized].add(id(company))

    def _register_domain(self, company: _Company, domain: Any) -> bool:
        normalized = _normalized_domain(domain)
        if not normalized:
            return False
        owners = self.by_domain.get(normalized, set())
        if owners and id(company) not in owners:
            _append_unique(company.limitations, _DOMAIN_IDENTITY_CONFLICT)
            return False
        company.domains.add(normalized)
        self.by_domain[normalized].add(id(company))
        return True

    def _from_ids(self, identities: Iterable[int]) -> list[_Company]:
        wanted = set(identities)
        return [company for company in self.companies if id(company) in wanted]

    def _create(self, name: str, cik: str | None = None) -> _Company:
        normalized = _normalized_name(name) or "unnamed-company"
        identity = f"cik:{cik}" if cik else f"name:{normalized}"
        company = _Company(
            id=_stable_id(identity),
            name=_clean_text(name) or "Unnamed company",
            identity_name=normalized,
            cik=cik,
        )
        self.companies.append(company)
        self._register_name(company, name)
        if cik:
            self.by_cik[cik] = company
        return company

    def resolve(
        self,
        name: Any,
        *,
        cik: Any = None,
        aliases: Iterable[Any] = (),
        domain: Any = None,
    ) -> _Company:
        display_name = _clean_text(name) or "Unnamed company"
        normalized = _normalized_name(display_name)
        normalized_cik = _normalized_cik(cik)

        if normalized_cik and normalized_cik in self.by_cik:
            company = self.by_cik[normalized_cik]
            self._register_name(company, display_name)
            for alias in aliases:
                self._register_name(company, alias)
            self._register_domain(company, domain)
            return company

        identity_ids: set[int] = set()
        for candidate in (display_name, *list(aliases)):
            candidate_name = _normalized_name(candidate)
            if candidate_name:
                identity_ids.update(self.by_name.get(candidate_name, set()))
        normalized_domain = _normalized_domain(domain)
        if normalized_domain:
            identity_ids.update(self.by_domain.get(normalized_domain, set()))

        matches = self._from_ids(identity_ids)
        company: _Company | None = None
        if len(matches) == 1:
            company = matches[0]
        elif len(matches) > 1:
            # If several CIK records collapse to the same suffix-stripped
            # name, keep a single existing name-only lead as the unresolved
            # record.  Never guess which CIK it belongs to.
            exact_name_only = [
                item
                for item in matches
                if item.cik is None and item.identity_name == normalized
            ]
            if len(exact_name_only) == 1:
                company = exact_name_only[0]

        if normalized_cik:
            if company is not None and company.cik in {None, normalized_cik}:
                company.cik = normalized_cik
                # CIK is the canonical stable identity whenever it is known.
                # A name/team record may be created before a research card
                # supplies the CIK, so update the public ID during that
                # promotion rather than letting source arrival order decide it.
                company.id = _stable_id(f"cik:{normalized_cik}")
                self.by_cik[normalized_cik] = company
            else:
                company = self._create(display_name, normalized_cik)
        elif company is None:
            # Reuse an earlier name-only ambiguity record if there is one.
            existing = [
                item
                for item in self._from_ids(self.by_name.get(normalized, set()))
                if item.cik is None and item.identity_name == normalized
            ]
            company = existing[0] if len(existing) == 1 else self._create(display_name)

        self._register_name(company, display_name)
        for alias in aliases:
            self._register_name(company, alias)
        self._register_domain(company, domain)
        return company


def _mark_pillar(company: _Company, name: str, status: str, summary: str) -> None:
    pillar = company.pillars[name]
    if _STATUS_RANK[status] > _STATUS_RANK[pillar["status"]]:
        pillar["status"] = status
        pillar["summary"] = _clean_text(summary)
    elif status == pillar["status"] and not pillar["summary"]:
        pillar["summary"] = _clean_text(summary)


def _add_metric(
    company: _Company,
    pillar_name: str,
    label: str,
    value: Any,
    detail: str | None = None,
) -> None:
    if value is None or value == "":
        return
    metric: dict[str, Any] = {"label": _clean_text(label), "value": value}
    if detail:
        metric["detail"] = _clean_text(detail)
    existing = company.pillars[pillar_name]["metrics"]
    identity = (metric["label"], str(metric["value"]), metric.get("detail", ""))
    if not any(
        (item.get("label"), str(item.get("value")), item.get("detail", "")) == identity
        for item in existing
    ):
        existing.append(metric)


def _add_finding(company: _Company, pillar_name: str, value: Any) -> None:
    _append_unique(company.pillars[pillar_name]["findings"], value)


def _add_pillar_limitation(company: _Company, pillar_name: str, value: Any) -> None:
    _append_unique(company.pillars[pillar_name]["limitations"], value)


def _add_limitation(company: _Company, value: Any) -> None:
    _append_unique(company.limitations, value)


def _add_date(company: _Company, value: Any) -> None:
    text = _clean_text(value)
    match = re.match(r"^(\d{4}-\d{2}-\d{2})", text)
    if match:
        company.dates.add(match.group(1))


def _add_person(company: _Company, name: Any, role: Any, source_url: Any = None) -> None:
    person_name = _clean_text(name)
    person_role = _clean_text(role)
    if not person_name or not person_role:
        return
    key = (_normalized_name(person_name), person_role.casefold())
    safe = _safe_url(source_url)
    existing = company.people.get(key)
    if existing is None:
        company.people[key] = {
            "name": person_name,
            "role": person_role,
            "source_url": safe,
        }
    elif not existing.get("source_url") and safe:
        existing["source_url"] = safe


def _add_evidence(
    company: _Company,
    *,
    pillar: str,
    title: Any,
    url: Any = None,
    quote: Any = None,
    published_at: Any = None,
    observed_at: Any = None,
    source_type: Any,
) -> None:
    title_text = _clean_text(title) or "Source evidence"
    quote_text = _clean_text(quote)
    safe = _safe_url(url)
    dedupe_text = re.sub(r"\s+", " ", quote_text or title_text).strip().casefold()
    # The same source and wording may support more than one pillar.  Pillar is
    # therefore part of the evidence identity even though source_count still
    # counts unique URLs at finalization time.
    dedupe_key = (pillar, safe or "", dedupe_text)
    item = {
        "pillar": pillar,
        "title": title_text,
        "url": safe,
        "quote": quote_text,
        "published_at": _clean_text(published_at) or None,
        "observed_at": _clean_text(observed_at) or None,
        "source_type": _clean_text(source_type) or "source",
    }
    existing = company.evidence.get(dedupe_key)
    if existing is None:
        company.evidence[dedupe_key] = item
    else:
        for key in ("url", "quote"):
            if not existing.get(key) and item.get(key):
                existing[key] = item[key]
        existing_published = _clean_text(existing.get("published_at"))
        incoming_published = _clean_text(item.get("published_at"))
        if not existing_published and incoming_published:
            existing["published_at"] = incoming_published
        elif (
            existing_published
            and incoming_published
            and existing_published != incoming_published
        ):
            _add_pillar_limitation(company, pillar, _PUBLICATION_DATE_CONFLICT)

        existing_observed = _clean_text(existing.get("observed_at"))
        incoming_observed = _clean_text(item.get("observed_at"))
        if incoming_observed and (
            not existing_observed or incoming_observed > existing_observed
        ):
            existing["observed_at"] = incoming_observed
    _add_date(company, published_at)
    _add_date(company, observed_at)


def _parse_sector_notes(path: Path) -> tuple[dict[str, str], dict[str, list[str]]]:
    company_sectors: dict[str, str] = {}
    source_urls: dict[str, list[str]] = defaultdict(list)
    if not path.is_file():
        return company_sectors, source_urls

    text = path.read_text(encoding="utf-8")
    in_grouping = False
    for line in text.splitlines():
        if line.strip() == "## Sector grouping":
            in_grouping = True
            continue
        if in_grouping and line.startswith("## "):
            in_grouping = False
        if in_grouping and line.startswith("|"):
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            if len(cells) == 2 and cells[0] not in {"Sector", "---"}:
                for company in cells[1].split(","):
                    normalized = _normalized_name(company)
                    if normalized:
                        company_sectors[normalized] = cells[0]

        match = re.match(r"^\s{2,}-\s+([^:]+):\s+", line)
        if match:
            sector = match.group(1).strip(" *`")
            for url in re.findall(r"\[[^\]]+\]\((https?://[^)]+)\)", line):
                safe = _safe_url(url)
                if safe and safe not in source_urls[sector]:
                    source_urls[sector].append(safe)
    return company_sectors, source_urls


def _filing_classifications(name: str, industry: str) -> list[str]:
    normalized = _normalized_name(name)
    industry_lower = industry.casefold()
    classes: list[str] = []
    if "banking" in industry_lower or "financial services" in industry_lower:
        classes.append("financial services")
    if "insurance" in industry_lower:
        classes.append("insurance")
    patterns = {
        "investment or fund vehicle": r"\b(fund|capital management|capital ventures|asset management|investment fund|portfolio)\b",
        "holding or special-purpose entity": r"\b(holdings?|spv|special purpose|series|acquisition)\b",
        "real-estate or development entity": r"\b(realty|properties|property|real estate|development co)\b",
    }
    for label, pattern in patterns.items():
        if re.search(pattern, normalized):
            classes.append(label)
    return list(dict.fromkeys(classes))


def _add_related_people(company: _Company, raw: Any, source_url: Any) -> None:
    for entry in _clean_text(raw).split(";"):
        entry = entry.strip()
        if not entry:
            continue
        match = re.match(r"^(.*?)\s*\((.*?)\)\s*$", entry)
        if match:
            name, role = match.groups()
        else:
            name, role = entry, "SEC related person"
        _add_person(company, name, f"{role} (SEC filing)", source_url)


def _ingest_form_d_company(resolver: _Resolver, row: dict[str, Any]) -> None:
    name = _clean_text(row.get("company"))
    cik = _normalized_cik(row.get("cik"))
    if not name or not cik:
        return
    company = resolver.resolve(name, cik=cik)
    company.has_filing = True
    company.tags.update({"SEC Form D", "startup status unverified"})
    industry = _clean_text(row.get("industry")) or "Unclassified"
    company.set_sector(industry, 10)
    company.set_description(
        f"{industry} issuer with a New Jersey business address in SEC Form D data. "
        "Startup status has not been independently verified.",
        10,
    )
    city = _clean_text(row.get("city"))
    postal = _clean_text(row.get("zip"))
    location = ", ".join(part for part in (city, "NJ") if part)
    if postal:
        location = f"{location} {postal}".strip()
    company.set_location(location or "New Jersey Form D business address", 20)
    company.nj_status = "supported"
    company.set_why(
        "A New Jersey business address appears in SEC Form D filings; startup status remains unverified.",
        10,
    )

    _mark_pillar(
        company,
        "business",
        "partial",
        "SEC filing metadata supplies limited company context.",
    )
    _add_metric(company, "business", "SEC self-reported industry", industry)
    incorporated = _clean_text(row.get("incorporated"))
    if incorporated:
        incorporated_label = {
            "overFiveYears": "More than five years before the filing",
            "withinFiveYears": "Within five years of the filing",
            "yetToBeFormed": "Not yet formed when filed",
        }.get(incorporated, incorporated)
        _add_metric(
            company,
            "business",
            "Incorporation timing reported on latest Form D",
            incorporated_label,
            "A filing-time age indicator, not the company's current age.",
        )
    young = _bool_text(row.get("young_company"))
    if young:
        _add_metric(
            company,
            "business",
            "Young-company flag on latest Form D",
            young,
            "True means formed within five years of that filing (or not yet formed); it is not a current-age measure.",
        )
    revenue_range = _clean_text(row.get("revenue_range"))
    if revenue_range:
        _add_metric(
            company,
            "business",
            "SEC self-reported revenue bracket",
            revenue_range,
            "A rough Form D bracket, not verified or exact revenue.",
        )
    _add_pillar_limitation(
        company,
        "business",
        "Form D industry, age and revenue fields are issuer-reported filing metadata, not independent operating verification.",
    )

    _mark_pillar(
        company,
        "funding",
        "available",
        "SEC Form D filings report private-offering activity since 2021.",
    )
    money_fields = (
        (
            "total_raised",
            "Reported amount sold across Form D offerings since 2021",
            "Fundraising reported as amount sold; not revenue, valuation, cash runway, profitability or company quality.",
        ),
        (
            "largest_round",
            "Largest reported amount sold in one Form D offering",
            "Reported fundraising, not revenue or valuation.",
        ),
        (
            "raised_last_24mo",
            "Reported amount sold in the dataset's trailing 24-month window",
            "Window is relative to the dataset run date; reported fundraising is not revenue.",
        ),
    )
    for field_name, label, detail in money_fields:
        amount = _usd(row.get(field_name))
        if amount is not None:
            _add_metric(company, "funding", label, amount, detail)
    for field_name, label in (
        ("num_offerings", "Distinct Form D offerings since 2021"),
        ("total_investors", "Investor entries reported across offerings"),
    ):
        value = _as_int(row.get(field_name))
        if value is not None:
            detail = None
            if field_name == "total_investors":
                detail = "The same investor may be counted in more than one offering."
            _add_metric(company, "funding", label, value, detail)
    for field_name, label in (
        ("first_raise", "Earliest offering date in dataset"),
        ("last_raise", "Latest offering date in dataset"),
    ):
        value = _clean_text(row.get(field_name))
        if value:
            _add_metric(company, "funding", label, value)
            _add_date(company, value)
    _add_pillar_limitation(
        company,
        "funding",
        "Coverage begins in 2021; Form D amounts are issuer-reported private-offering data and may be amended or incomplete.",
    )
    _add_pillar_limitation(
        company,
        "funding",
        "A Form D filing does not establish revenue, profitability, current cash, startup status or investment quality.",
    )

    edgar_url = _safe_url(row.get("edgar_url"))
    total = _usd(row.get("total_raised")) or "amount not disclosed"
    _add_evidence(
        company,
        pillar="funding",
        title=f"SEC Form D company history for {name}: {total} reported sold since 2021",
        url=edgar_url,
        quote="",
        published_at=row.get("last_raise"),
        source_type="sec_form_d_company_history",
    )
    _add_related_people(company, row.get("related_people"), edgar_url)
    if _clean_text(row.get("related_people")):
        _mark_pillar(
            company,
            "founders",
            "partial",
            "SEC filings list related executives or directors; founder status is not established.",
        )
        _add_pillar_limitation(
            company,
            "founders",
            "SEC related-person roles are filing roles; they do not establish founder status or current employment.",
        )

    classifications = _filing_classifications(name, industry)
    for classification in classifications:
        company.tags.add(f"non-startup classification: {classification}")
    if classifications:
        _add_limitation(
            company,
            "This filing resembles a " + ", ".join(classifications) + "; use classification filters before treating it as an operating startup.",
        )
    _add_limitation(
        company,
        "The New Jersey signal is the business address on a Form D filing; it does not prove current headquarters or operations.",
    )
    _add_limitation(
        company,
        "Inclusion in the filing directory does not establish that this issuer is an active startup.",
    )


def _ingest_form_d_offering(resolver: _Resolver, row: dict[str, Any]) -> None:
    cik = _normalized_cik(row.get("cik"))
    company = resolver.by_cik.get(cik)
    if company is None:
        # The checked-in files should join perfectly, but a future partial
        # export should still preserve an offering rather than drop it.
        name = _clean_text(row.get("company"))
        if not name or not cik:
            return
        company = resolver.resolve(name, cik=cik)
        company.has_filing = True
        company.tags.update({"SEC Form D", "startup status unverified"})
        _mark_pillar(
            company,
            "funding",
            "partial",
            "An individual SEC Form D offering is available without a matching company-history row.",
        )
        _add_pillar_limitation(
            company,
            "funding",
            "The offering could not be joined to a Form D company-history row, so aggregate fundraising coverage may be incomplete.",
        )

    amount_sold = _usd(row.get("amount_sold"))
    total_offering = _usd(row.get("total_offering"))
    filing_date = _clean_text(row.get("filing_date"))
    file_number = _clean_text(row.get("file_num"))
    parts = []
    if amount_sold is not None:
        parts.append(f"{amount_sold} reported sold")
    else:
        parts.append("amount sold not reported")
    if total_offering is not None:
        parts.append(f"{total_offering} total offering")
    filing_label = file_number or "without a file number"
    title = f"Form D offering {filing_label}: " + "; ".join(parts)
    _add_evidence(
        company,
        pillar="funding",
        title=title,
        url=row.get("filing_url"),
        quote="",
        published_at=filing_date,
        source_type="sec_form_d_filing",
    )
    _add_date(company, filing_date)


def _ingest_team_lead(
    resolver: _Resolver,
    row: dict[str, Any],
    company_sectors: dict[str, str],
) -> None:
    name = _clean_text(row.get("company"))
    if not name:
        return
    company = resolver.resolve(name)
    company.has_team = True
    company.name = name
    company.tags.add("team reviewed")
    company.set_why("Team-reviewed company with a sourced CEO lead.", 20)
    sector = company_sectors.get(_normalized_name(name))
    if sector:
        company.set_sector(sector, 30)

    ceo_name = _clean_text(row.get("ceo_name"))
    source_url = _safe_url(row.get("ceo_source_url"))
    checked = _clean_text(row.get("source_checked_on"))
    if ceo_name:
        company.tags.add("CEO identified")
        _add_person(company, ceo_name, "CEO", source_url)
        _mark_pillar(
            company,
            "founders",
            "partial",
            "A source identifies company leadership; CEO status does not establish founder status.",
        )
        _add_finding(company, "founders", f"{ceo_name} is listed as CEO.")
        _add_pillar_limitation(
            company,
            "founders",
            "A current CEO is not automatically a founder; founder identity remains unverified unless separately sourced.",
        )
        _add_evidence(
            company,
            pillar="founders",
            title=f"CEO source: {ceo_name} listed as CEO of {name}",
            url=source_url,
            quote="",
            observed_at=checked,
            source_type="team_leadership_source",
        )
    _add_date(company, checked)
    if company.nj_status != "supported":
        company.nj_status = "unverified"
        company.set_location("Location unverified", 1)
        _add_limitation(
            company,
            "The team lead list identifies a company for review but does not independently establish a New Jersey address or operation.",
        )


def _ingest_business_model(
    resolver: _Resolver,
    row: dict[str, Any],
    company_sectors: dict[str, str],
) -> None:
    name = _clean_text(row.get("company"))
    if not name:
        return
    company = resolver.resolve(name)
    company.set_description(row.get("one_line_description"), 30)
    sector = company_sectors.get(_normalized_name(name))
    if sector:
        company.set_sector(sector, 30)
    _mark_pillar(
        company,
        "business",
        "available",
        "Team analysis covers the business model, novelty and operating context.",
    )
    score = _clean_text(row.get("score"))
    if score:
        _add_metric(
            company,
            "business",
            "Business-model analyst judgment (1–5)",
            f"{score}/5",
            "A team-authored judgment, not an investment score or prediction.",
        )
    novelty_score = _clean_text(row.get("novelty_score"))
    if novelty_score:
        _add_metric(
            company,
            "business",
            "Novelty analyst judgment (1–5)",
            f"{novelty_score}/5",
            "A team-authored judgment, not an investment score or prediction.",
        )
    if _clean_text(row.get("novelty_type")):
        _add_metric(company, "business", "Novelty category", row.get("novelty_type"))
    _add_finding(company, "business", row.get("justification"))
    _add_finding(company, "business", row.get("novelty_justification"))
    _add_pillar_limitation(
        company,
        "business",
        "Business-model and novelty judgments are analyst assessments, not an overall company ranking or forecast.",
    )
    _add_evidence(
        company,
        pillar="business",
        title=f"Team business-model analysis for {name}",
        quote="",
        source_type="team_analysis",
    )


def _ingest_headcount(resolver: _Resolver, row: dict[str, Any]) -> None:
    name = _clean_text(row.get("company"))
    if not name:
        return
    company = resolver.resolve(name)
    _mark_pillar(
        company,
        "business",
        "partial",
        "Team research supplies point-in-time headcount and operating-model context.",
    )
    headcount = _as_int(row.get("current_headcount"))
    if headcount is not None:
        _add_metric(
            company,
            "business",
            "Current headcount estimate",
            headcount,
            "Point-in-time LinkedIn or third-party estimate checked in September 2026; not payroll data.",
        )
    founding_year = _as_int(row.get("founding_year"))
    if founding_year is not None:
        _add_metric(company, "business", "Reported founding year", founding_year)
    growth_rate = _as_float(row.get("growth_rate"))
    if growth_rate is not None:
        _add_metric(
            company,
            "business",
            "Average employees added per year since founding (proxy)",
            growth_rate,
            "Headcount divided by years since founding; not observed hiring growth or a historical time series.",
        )
    scale = _clean_text(row.get("scales_with_headcount"))
    if scale:
        _add_metric(
            company,
            "business",
            "Operating model scales with headcount",
            scale,
            "Team classification of operating-model dependence, not a measured performance metric.",
        )
    _add_pillar_limitation(
        company,
        "business",
        "Headcount divided by company age is a rough proxy and must not be described as observed hiring growth.",
    )


def _apply_sector_metrics(
    companies: Iterable[_Company],
    sector_rows: list[dict[str, Any]],
    sector_sources: dict[str, list[str]],
) -> None:
    rows_by_sector: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in sector_rows:
        sector = _clean_text(row.get("sector"))
        if sector:
            rows_by_sector[sector].append(row)
    for rows in rows_by_sector.values():
        rows.sort(key=lambda item: _clean_text(item.get("date")))

    for company in companies:
        rows = rows_by_sector.get(company.sector, [])
        if not rows:
            continue
        _mark_pillar(
            company,
            "business",
            "partial",
            "Broader sector indicators provide market context.",
        )
        for row in rows:
            period = _clean_text(row.get("date"))
            funding = _as_float(row.get("funding_total"))
            if funding is not None:
                value = f"USD {funding:,.1f}B"
                _add_metric(
                    company,
                    "business",
                    f"Broader sector venture-funding proxy ({period})",
                    value,
                    "Sector-level proxy; not this company's funding, revenue, valuation or performance.",
                )
        latest = rows[-1]
        latest_period = _clean_text(latest.get("date"))
        latest_funding = _as_float(latest.get("funding_total"))
        for url in sector_sources.get(company.sector, []):
            amount_label = (
                f": {latest_period} proxy is USD {latest_funding:,.1f}B"
                if latest_funding is not None
                else ""
            )
            _add_evidence(
                company,
                pillar="business",
                title=f"Source for {company.sector} sector proxy{amount_label}",
                url=url,
                quote="",
                published_at=latest_period,
                source_type="sector_proxy_source",
            )
        _add_pillar_limitation(
            company,
            "business",
            "Sector funding figures are broader market proxies and must not be attributed to the company.",
        )


def _card_cik(card: dict[str, Any]) -> Any:
    identity = card.get("identity") if isinstance(card.get("identity"), dict) else {}
    return card.get("cik") or card.get("sec_cik") or identity.get("cik")


def _iter_card_evidence(card: dict[str, Any]) -> Iterable[dict[str, Any]]:
    nj_presence = card.get("nj_presence")
    if isinstance(nj_presence, dict):
        evidence = nj_presence.get("evidence")
        if isinstance(evidence, list):
            yield from (item for item in evidence if isinstance(item, dict))
    signals = card.get("signals")
    if isinstance(signals, list):
        for signal in signals:
            if not isinstance(signal, dict):
                continue
            evidence = signal.get("evidence")
            if isinstance(evidence, list):
                yield from (item for item in evidence if isinstance(item, dict))


def _ingest_reputation_card(
    resolver: _Resolver,
    card: dict[str, Any],
    job: dict[str, Any],
    *,
    review: bool,
) -> None:
    name = _clean_text(card.get("name"))
    if not name:
        return
    aliases_raw = card.get("aliases") if isinstance(card.get("aliases"), list) else []
    aliases = [_clean_text(alias) for alias in aliases_raw if _clean_text(alias)]
    company = resolver.resolve(
        name,
        cik=_card_cik(card),
        aliases=aliases,
        domain=card.get("official_domain"),
    )
    was_only_filing = company.has_filing and not (company.has_team or company.has_reputation)
    company.has_reputation = True
    if not company.has_team and was_only_filing:
        # Keep the legal filing name for CIK-backed records.
        pass
    elif not company.has_team and company.description_priority == 0:
        company.name = name
    company.tags.add("reputation researched")
    if review:
        company.tags.add("reputation review needed")
    company.set_description(card.get("description"), 20 if company.has_team else 40)
    company.set_sector(card.get("sector"), 20 if company.has_team else 40)
    company.set_why(
        card.get("why_surfaced")
        or ("Saved reputation evidence requires review." if review else "Saved public reputation research is available."),
        40 if not review else 35,
    )

    reputation_status = "partial" if review else "available"
    reputation_summary = (
        "Saved reputation and ecosystem evidence requires review."
        if review
        else "Saved public research documents reputation and ecosystem signals."
    )
    _mark_pillar(company, "reputation", reputation_status, reputation_summary)

    nj_presence = card.get("nj_presence") if isinstance(card.get("nj_presence"), dict) else {}
    nj_signal = _clean_text(nj_presence.get("status")).casefold()
    if nj_signal in {"headquarters", "operations"}:
        company.nj_status = "supported"
        company.set_location(nj_presence.get("location") or "New Jersey presence supported by cited research", 40)
    elif nj_signal in {"outside_nj", "conflicting", "unclear", "ecosystem_only"}:
        # Saved jobs arrive newest-first from Store.recent and are ingested in
        # chronological order below.  A newer explicit non-supporting result
        # must be able to supersede an older operations assessment while the
        # older evidence remains available for review.
        company.nj_status = "unverified"
        fallback_location = {
            "outside_nj": "Outside New Jersey in the latest saved assessment",
            "conflicting": "Location conflicts across cited research",
            "unclear": "Location unverified",
            "ecosystem_only": "New Jersey ecosystem connection only",
        }[nj_signal]
        company.set_location(nj_presence.get("location") or fallback_location, 40)
        _add_limitation(
            company,
            "Reputation research does not establish New Jersey headquarters or operations for this record.",
        )
    elif company.nj_status != "supported":
        company.nj_status = "unverified"
        if _clean_text(nj_presence.get("location")):
            company.set_location(nj_presence.get("location"), 10)
        _add_limitation(
            company,
            "Reputation research does not establish New Jersey headquarters or operations for this record.",
        )

    signals = card.get("signals") if isinstance(card.get("signals"), list) else []
    for signal in signals:
        if not isinstance(signal, dict):
            continue
        _add_finding(company, "reputation", signal.get("statement"))

    for evidence in _iter_card_evidence(card):
        _add_evidence(
            company,
            pillar="reputation",
            title=evidence.get("title") or evidence.get("source_id") or "Reputation research source",
            url=evidence.get("url"),
            quote=evidence.get("quote"),
            published_at=evidence.get("published_at"),
            observed_at=evidence.get("observed_at"),
            source_type=evidence.get("source_family") or "reputation_research",
        )

    summary = card.get("evidence_summary") if isinstance(card.get("evidence_summary"), dict) else {}
    external_orgs = _as_int(summary.get("external_organizations"))
    if external_orgs is not None:
        # Do not sum this across repeated persisted copies of the bundled
        # sample.  The metric is a property of the card, not another vote.
        existing = company.pillars["reputation"]["metrics"]
        label = "External organizations represented in saved research"
        previous = next((item for item in existing if item.get("label") == label), None)
        if previous is None:
            _add_metric(company, "reputation", label, external_orgs)
        elif isinstance(previous.get("value"), int):
            previous["value"] = max(previous["value"], external_orgs)

    for limitation in card.get("limitations") or []:
        _add_pillar_limitation(company, "reputation", limitation)
    for warning in job.get("warnings") or []:
        _add_pillar_limitation(company, "reputation", f"Research job warning: {_clean_text(warning)}")
    mode = _clean_text(job.get("mode"))
    if mode == "sample":
        _add_pillar_limitation(
            company,
            "reputation",
            "This is saved historical public research, not a fresh live search.",
        )
    if _clean_text(job.get("pipeline_version")) != _CURRENT_REPUTATION_PIPELINE_VERSION:
        _add_pillar_limitation(
            company,
            "reputation",
            _EARLIER_ASSESSMENT_WARNING,
        )
    # Company freshness follows source publication/observation dates added
    # above.  A job's persistence timestamp is orchestration metadata and
    # must not make saved research look freshly verified.


def _ingest_reputation_job(resolver: _Resolver, job: dict[str, Any]) -> None:
    cards = job.get("cards") if isinstance(job.get("cards"), list) else []
    reviews = job.get("review_cards") if isinstance(job.get("review_cards"), list) else []
    for card in cards:
        if isinstance(card, dict):
            _ingest_reputation_card(resolver, card, job, review=False)
    for card in reviews:
        if isinstance(card, dict):
            _ingest_reputation_card(resolver, card, job, review=True)


def _founder_fact_text(prefix: str, row: dict[str, Any], fields: Iterable[str]) -> str:
    values = [_clean_text(row.get(field)) for field in fields]
    values = [value for value in values if value]
    return f"{prefix}: " + " — ".join(values) if values else ""


def _ingest_founder_profiles(
    resolver: _Resolver,
    founder_profiles: dict[str, Any] | None,
) -> None:
    if not founder_profiles:
        return
    for company_name, raw_profiles in founder_profiles.items():
        raw_items = raw_profiles if isinstance(raw_profiles, list) else [raw_profiles]
        profiles = [profile for profile in raw_items if isinstance(profile, dict) and profile]
        if not profiles:
            # An empty integration result is not evidence and must not create a
            # phantom company with partial founder coverage.
            continue

        company = resolver.resolve(company_name)
        company.has_founder_profile = True
        company.tags.add("leadership identity review needed")
        company.set_why("Sourced leadership-profile evidence is available and requires identity review.", 30)
        _mark_pillar(
            company,
            "founders",
            "partial",
            "Sourced leadership profiles are available but require identity confirmation.",
        )
        _add_pillar_limitation(
            company,
            "founders",
            "Name-matched leadership data requires identity review before it is treated as confirmed.",
        )

        unique_grants: dict[tuple[str, ...], dict[str, Any]] = {}
        grant_qualifications: list[str] = []
        for profile in profiles:
            for row in profile.get("grants") or []:
                if not isinstance(row, dict):
                    continue
                grant_id = _clean_text(row.get("id"))
                if grant_id:
                    identity = ("id", grant_id)
                else:
                    # Current database profiles always carry IDs.  This
                    # content fallback keeps hand-authored/imported profiles
                    # from double-counting an identical copied record.
                    identity = (
                        "record",
                        *(
                            _clean_text(row.get(field_name))
                            for field_name in (
                                "program",
                                "agency",
                                "amount",
                                "award_date",
                                "source_url",
                            )
                        ),
                    )
                existing_grant = unique_grants.get(identity)
                if existing_grant is None:
                    unique_grants[identity] = dict(row)
                else:
                    # Preserve the first conflicting value while allowing a
                    # later copied profile to fill fields that were empty.
                    for key, value in row.items():
                        if not _clean_text(existing_grant.get(key)) and _clean_text(value):
                            existing_grant[key] = value
                qualification = _clean_text(row.get("qualification"))
                if qualification and qualification not in grant_qualifications:
                    grant_qualifications.append(qualification)

        for profile in profiles:
            founder = profile.get("founder") if isinstance(profile.get("founder"), dict) else {}
            person_name = _clean_text(founder.get("name"))
            # Preserve the source title.  Missing titles stay neutral rather
            # than being upgraded to "Founder".
            person_role = _clean_text(founder.get("title")) or "Leadership profile"
            person_url = founder.get("linkedin_url") or founder.get("github_url")
            _add_person(company, person_name, person_role, person_url)
            if person_name:
                _add_finding(company, "founders", f"Leadership profile: {person_name} — {person_role}.")

            for row in profile.get("education") or []:
                if not isinstance(row, dict):
                    continue
                text = _founder_fact_text("Education", row, ("degree", "field", "institution"))
                _add_finding(company, "founders", text)
                if text:
                    _add_evidence(
                        company,
                        pillar="founders",
                        title=text,
                        url=row.get("source_url"),
                        quote="",
                        source_type=row.get("source_name") or "founder_profile",
                    )
            for row in profile.get("companies") or []:
                if not isinstance(row, dict):
                    continue
                text = _founder_fact_text("Experience", row, ("role", "company_name"))
                _add_finding(company, "founders", text)
                if text:
                    _add_evidence(
                        company,
                        pillar="founders",
                        title=text,
                        url=row.get("source_url"),
                        quote="",
                        source_type=row.get("source_name") or "founder_profile",
                    )
            for row in profile.get("achievements") or []:
                if not isinstance(row, dict):
                    continue
                text = _clean_text(row.get("achievement"))
                _add_finding(company, "founders", text)
                if text:
                    _add_evidence(
                        company,
                        pillar="founders",
                        title=text,
                        url=row.get("source_url"),
                        quote="",
                        published_at=row.get("year"),
                        source_type=row.get("source_name") or "founder_profile",
                    )

            for evidence in profile.get("evidence") or []:
                if not isinstance(evidence, dict):
                    continue
                entity_type = _clean_text(evidence.get("entity_type")).casefold()
                pillar_name = "funding" if entity_type == "grant" else "founders"
                _add_evidence(
                    company,
                    pillar=pillar_name,
                    title=evidence.get("claim") or "Leadership profile evidence",
                    url=evidence.get("source_url"),
                    quote="",
                    published_at=evidence.get("source_date"),
                    observed_at=evidence.get("retrieved_at"),
                    source_type=evidence.get("source_name") or "founder_profile",
                )
            for limitation in profile.get("limitations") or []:
                _add_pillar_limitation(company, "founders", limitation)

        grants = list(unique_grants.values())
        if grants:
            _mark_pillar(
                company,
                "funding",
                "partial",
                "Name-matched leadership profiles contain grant records requiring identity review.",
            )
            _add_metric(company, "funding", "Founder/leader-linked grant records", len(grants))
            amounts = [_as_float(row.get("amount")) for row in grants]
            known_amounts = [amount for amount in amounts if amount is not None]
            if known_amounts:
                _add_metric(
                    company,
                    "funding",
                    "Reported value of name-matched grant records",
                    _usd(sum(known_amounts)),
                    "Unique grant records linked through person or company IDs; not company revenue and not confirmed until identity review.",
                )
            _add_pillar_limitation(
                company,
                "funding",
                "Person- or company-linked grants may belong to a namesake, another institution, or a different award recipient and are not company revenue.",
            )
            for qualification in grant_qualifications:
                _add_pillar_limitation(company, "funding", qualification)
            for row in grants:
                quote = _founder_fact_text("Grant", row, ("program", "agency", "amount"))
                _add_evidence(
                    company,
                    pillar="funding",
                    title=quote or "Name-matched grant source",
                    url=row.get("source_url"),
                    quote="",
                    published_at=row.get("award_date"),
                    source_type=row.get("source_name") or "founder_profile",
                )


def _finalize_company(company: _Company) -> dict[str, Any]:
    for pillar_name in _PILLARS:
        pillar = company.pillars[pillar_name]
        if not pillar["summary"]:
            pillar["summary"] = _MISSING_SUMMARIES[pillar_name]
        pillar["metrics"].sort(key=lambda item: (item["label"].casefold(), str(item["value"])))
        pillar["findings"].sort(key=str.casefold)
        pillar["limitations"].sort(key=str.casefold)

    if not company.description:
        company.description = "Evidence record; a verified company description is not yet available."
    if not company.why_surfaced:
        company.why_surfaced = "Evidence is available for review."

    evidence = list(company.evidence.values())
    for item in evidence:
        item["id"] = _evidence_id(company.id, item)
    pillar_order = {name: index for index, name in enumerate(_PILLARS)}
    evidence.sort(
        key=lambda item: (
            pillar_order.get(item["pillar"], 99),
            item.get("published_at") or item.get("observed_at") or "",
            item["title"].casefold(),
            item.get("url") or "",
        )
    )
    people = sorted(
        company.people.values(),
        key=lambda item: (item["name"].casefold(), item["role"].casefold()),
    )
    source_urls = {item["url"] for item in evidence if item.get("url")}
    source_urls.update(item["source_url"] for item in people if item.get("source_url"))

    if company.has_reputation or company.has_founder_profile:
        record_type = "research"
    elif company.has_team:
        record_type = "lead"
    else:
        record_type = "filing"

    updated_at = max(company.dates) if company.dates else "unknown"
    return {
        "id": company.id,
        "name": company.name,
        "description": company.description,
        "sector": company.sector,
        "location": company.location,
        "nj_status": company.nj_status,
        "record_type": record_type,
        "updated_at": updated_at,
        "source_count": len(source_urls),
        "coverage_count": sum(
            1 for name in _PILLARS if company.pillars[name]["status"] != "missing"
        ),
        "tags": sorted(company.tags, key=str.casefold),
        "why_surfaced": company.why_surfaced,
        "pillars": company.pillars,
        "people": people,
        "evidence": evidence,
        "limitations": sorted(company.limitations, key=str.casefold),
    }


def build_catalog(
    root: Path,
    jobs: list[dict] | None = None,
    founder_profiles: dict | None = None,
) -> dict[str, Any]:
    """Build the Garden State catalog from checked-in data and saved inputs.

    ``root`` is the repository root.  Optional ``jobs`` are already-persisted
    reputation job dictionaries; optional ``founder_profiles`` is keyed by
    exact company name.  Neither input triggers live research or database IO.
    """

    root = Path(root)
    resolver = _Resolver()
    business_root = root / "business-and-market-potential"
    notes_path = business_root / "market-timing" / "sector-momentum-notes.md"
    company_sectors, sector_sources = _parse_sector_notes(notes_path)

    company_rows = _read_csv(business_root / "data" / "nj_formd_companies.csv")
    offering_rows = _read_csv(business_root / "data" / "nj_formd_offerings.csv")
    for row in company_rows:
        _ingest_form_d_company(resolver, row)
    for row in offering_rows:
        _ingest_form_d_offering(resolver, row)

    for row in _read_csv(root / "startups.csv"):
        _ingest_team_lead(resolver, row, company_sectors)
    for row in _read_csv(business_root / "business-model" / "business-model-scores.csv"):
        _ingest_business_model(resolver, row, company_sectors)
    for row in _read_csv(business_root / "scalability" / "headcount-data.csv"):
        _ingest_headcount(resolver, row)

    _ingest_founder_profiles(resolver, founder_profiles)

    bundled = _read_json(root / "reputation-and-ecosystem-interest" / "web" / "demo.json")
    if bundled:
        _ingest_reputation_job(resolver, bundled)
    # Store.recent returns newest-first.  Equal-priority display fields use
    # last-write-wins semantics, so ingest persisted runs oldest-first and let
    # the newest assessment determine the current description/location while
    # retaining evidence and limitations from every run.
    for job in reversed(jobs or []):
        if isinstance(job, dict):
            _ingest_reputation_job(resolver, job)

    sector_rows = _read_csv(business_root / "market-timing" / "sector-data.csv")
    _apply_sector_metrics(resolver.companies, sector_rows, sector_sources)

    internal_by_id = {company.id: company for company in resolver.companies}
    companies = [_finalize_company(company) for company in resolver.companies]

    def sort_key(item: dict[str, Any]) -> tuple[int, str, str]:
        internal = internal_by_id[item["id"]]
        if internal.has_reputation or internal.has_founder_profile:
            group = 0
        elif internal.has_team:
            group = 1
        else:
            group = 2
        return (group, item["name"].casefold(), item["id"])

    companies.sort(key=sort_key)
    sectors = sorted(
        {company["sector"] for company in companies if company["sector"]},
        key=str.casefold,
    )
    all_sources = {
        evidence["url"]
        for company in companies
        for evidence in company["evidence"]
        if evidence.get("url")
    }
    all_sources.update(
        person["source_url"]
        for company in companies
        for person in company["people"]
        if person.get("source_url")
    )
    known_dates = [
        company["updated_at"] for company in companies if company["updated_at"] != "unknown"
    ]
    snapshot_date = max(known_dates) if known_dates else "unknown"

    notices = [
        "Evidence coverage describes available sources; it is not a prediction, recommendation or investment score.",
        "The directory includes Form D issuers and team/research leads. A filing does not by itself establish active startup status.",
        "Form D amounts are reported private-offering fundraising, not revenue, valuation, profitability or cash runway.",
        "Form D coverage begins in 2021 and New Jersey support reflects the issuer business address reported in the filing.",
        "Team-list inclusion alone does not verify a New Jersey address; saved reputation research supports NJ only for headquarters or operations evidence.",
        "Headcount-per-year values are age-normalized proxies, not observed hiring growth.",
        "CEO, founder, advisor, director and SEC related-person roles remain distinct and may require identity review.",
    ]
    if len(company_rows) != 778 and company_rows:
        notices.append(
            f"This snapshot contains {len(company_rows)} Form D company rows; the checked-in reference snapshot contains 778."
        )

    return {
        "companies": companies,
        "sectors": sectors,
        "stats": {
            "companies": len(companies),
            "nj_supported": sum(company["nj_status"] == "supported" for company in companies),
            "with_reputation": sum(
                internal_by_id[company["id"]].has_reputation for company in companies
            ),
            "team_reviewed": sum(
                internal_by_id[company["id"]].has_team for company in companies
            ),
            "sources": len(all_sources),
        },
        "snapshot_date": snapshot_date,
        "notices": notices,
    }


__all__ = ["build_catalog"]
