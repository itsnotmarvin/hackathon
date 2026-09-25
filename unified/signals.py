"""Transparent signal scoring, sector clusters and NJ region rollups.

Every point in a score traces to one observed input.  A signal that was not
observed earns no points and is reported as "not detected", never imputed.
"""

from __future__ import annotations

import math
from collections import defaultdict
from datetime import date, timedelta
from typing import Any, Iterable

SCORE_VERSION = "1.0"

CLUSTERS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("tech", "Software, AI & tech", (
        "Other Technology", "Computers", "Telecommunications",
        "Enterprise software & security", "AI infrastructure", "Software & AI",
    )),
    ("life", "Life sciences & health", (
        "Biotechnology", "Pharmaceuticals", "Other Health Care", "Hospitals and Physicians",
        "Digital health", "Life sciences", "Biotech",
    )),
    ("climate", "Climate, energy & materials", (
        "Other Energy", "Energy Conservation", "Environmental Services", "Climate & materials",
        "Advanced materials & manufacturing", "Hardware & energy",
    )),
    ("industrial", "Manufacturing & construction", ("Manufacturing", "Construction")),
    ("fintech", "Financial services & fintech", (
        "Other Banking and Financial Services", "Commercial Banking", "Insurance",
    )),
    ("consumer", "Consumer, food & retail", (
        "Retailing", "Restaurants", "Lodging and Conventions", "Other Travel", "Agriculture",
    )),
    ("services", "Business & property services", ("Business Services", "Proptech")),
)
OTHER_CLUSTER = ("other", "Other / unclassified")
_CLUSTER_BY_SECTOR = {sector.casefold(): key for key, _, sectors in CLUSTERS for sector in sectors}
CLUSTER_LABELS = {key: label for key, label, _ in CLUSTERS} | {OTHER_CLUSTER[0]: OTHER_CLUSTER[1]}

# USPS three-digit ZIP (sectional center) areas grouped into NJ regions.
# grid = (column, row, row_span) in a schematic two-column tile layout.
REGIONS: tuple[dict[str, Any], ...] = (
    {"key": "northwest", "label": "Morris · Sussex · Warren", "zip3": ("078", "079"), "grid": (1, 1, 2)},
    {"key": "bergen", "label": "Bergen · Passaic", "zip3": ("074", "075", "076"), "grid": (2, 1, 1)},
    {"key": "urban", "label": "Essex · Union · Hudson", "zip3": ("070", "071", "072", "073"), "grid": (2, 2, 1)},
    {"key": "mercer", "label": "Mercer · Princeton", "zip3": ("085", "086"), "grid": (1, 3, 1)},
    {"key": "middlesex", "label": "Middlesex · Somerset", "zip3": ("088", "089"), "grid": (2, 3, 1)},
    {"key": "south", "label": "South Jersey", "zip3": ("080", "081", "082", "083", "084"), "grid": (1, 4, 2)},
    {"key": "shore", "label": "Monmouth · Ocean", "zip3": ("077", "087"), "grid": (2, 4, 2)},
)
_REGION_BY_ZIP3 = {zip3: region["key"] for region in REGIONS for zip3 in region["zip3"]}

TIERS = ((50, "high", "High signal"), (35, "elevated", "Elevated"), (15, "moderate", "Moderate"), (0, "low", "Low"))
ELEVATED = 35

SIGNAL_LABELS = {
    "capital": "Capital raised",
    "momentum": "Recent raise",
    "repeat": "Repeat raises",
    "investors": "Investor breadth",
    "hiring": "Hiring",
    "accelerator": "Accelerator / program",
    "ip": "IP & research partnerships",
    "grants": "Public grants",
}


def cluster_for(sector: str) -> str:
    return _CLUSTER_BY_SECTOR.get((sector or "").strip().casefold(), OTHER_CLUSTER[0])


def region_for(postal: str) -> str | None:
    digits = "".join(ch for ch in (postal or "") if ch.isdigit())
    return _REGION_BY_ZIP3.get(digits[:3]) if len(digits) >= 3 else None


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def _log_scale(value: float, low: float, high: float) -> float:
    if value <= low:
        return 0.0
    return _clamp(math.log10(value / low) / math.log10(high / low))


def _tier(total: int) -> tuple[str, str]:
    for floor, key, label in TIERS:
        if total >= floor:
            return key, label
    return TIERS[-1][1], TIERS[-1][2]


def _usd_short(amount: float) -> str:
    for size, suffix in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if amount >= size:
            return f"${amount / size:,.1f}{suffix}"
    return f"${amount:,.0f}"


def score_company(raw: dict[str, Any], signal_types: Iterable[str]) -> dict[str, Any]:
    """Score observed signals out of 100 with a per-component breakdown."""

    types = set(signal_types)
    components: list[dict[str, Any]] = []

    def add(key: str, maximum: int, points: float, detected: bool, detail: str) -> None:
        components.append({
            "key": key,
            "label": SIGNAL_LABELS[key],
            "points": round(points, 1) if detected else 0,
            "max": maximum,
            "detected": detected,
            "detail": detail,
        })

    raised = raw.get("total_raised")
    if raised:
        add("capital", 20, 20 * _log_scale(raised, 5e4, 5e7), True,
            f"{_usd_short(raised)} reported sold on Form D since 2021 (log scale; $50M+ earns full points).")
    else:
        add("capital", 20, 0, False, "No reported Form D amount sold.")

    months = raw.get("months_since_last_raise")
    if months is not None:
        points = 20 if months <= 6 else 16 if months <= 12 else 10 if months <= 24 else 4 if months <= 36 else 0
        add("momentum", 20, points, points > 0,
            f"Latest Form D offering {months:.0f} months before the dataset run date.")
    else:
        add("momentum", 20, 0, False, "No dated Form D offering.")

    rounds = raw.get("num_offerings")
    if rounds:
        add("repeat", 10, 3 if rounds == 1 else 7 if rounds == 2 else 10, rounds >= 2,
            f"{rounds} distinct Form D offering{'s' if rounds != 1 else ''} since 2021.")
    else:
        add("repeat", 10, 0, False, "No Form D offerings.")

    investors = raw.get("total_investors")
    if investors:
        add("investors", 10, 10 * _clamp(math.log(1 + investors) / math.log(26)), True,
            f"{investors} investor entries across offerings (25+ earns full points).")
    else:
        add("investors", 10, 0, False, "No investor count reported.")

    growth = raw.get("growth_rate")
    if growth is not None:
        add("hiring", 15, 15 * _clamp(math.log(1 + growth) / math.log(51)), growth > 0,
            f"About {growth:g} employees added per year since founding (headcount ÷ age proxy).")
    else:
        add("hiring", 15, 0, False, "No headcount observation.")

    accelerator = [t for t in ("accelerator_participation", "program_selection") if t in types]
    award = "award" in types
    if accelerator or award:
        points = min(10, (10 if accelerator else 0) + (5 if award else 0))
        found = [t.replace("_", " ") for t in accelerator] + (["award"] if award else [])
        add("accelerator", 10, points, True, "Sourced research found: " + ", ".join(found) + ".")
    else:
        add("accelerator", 10, 0, False, "No sourced accelerator, program or award signal.")

    ip_types = [t for t in ("technology_license", "research_collaboration", "industrial_partnership") if t in types]
    if ip_types:
        add("ip", 10, min(10, 5 * len(ip_types)), True,
            "Sourced research found: " + ", ".join(t.replace("_", " ") for t in ip_types) + ".")
    else:
        add("ip", 10, 0, False, "No sourced license, research collaboration or partnership.")

    grants = raw.get("grant_count") or 0
    if grants:
        add("grants", 5, 5, True, f"{grants} name-matched public grant record{'s' if grants != 1 else ''} (identity review needed).")
    else:
        add("grants", 5, 0, False, "No linked public grant records.")

    total = int(round(sum(item["points"] for item in components)))
    tier, tier_label = _tier(total)
    detected = [item["key"] for item in components if item["detected"]]
    return {
        "total": total,
        "tier": tier,
        "tier_label": tier_label,
        "signals": detected,
        "signal_count": len(detected),
        "components": components,
        "version": SCORE_VERSION,
    }


def _parse_date(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value or "")[:10])
    except ValueError:
        return None


def build_sector_view(
    companies: list[dict[str, Any]],
    offerings: list[tuple[str, str | None, float | None]],
) -> dict[str, Any]:
    """Roll companies and offerings up into ranked clusters, regions and trends.

    ``offerings`` holds (company_id, filing_date, amount_sold).  Records tagged
    as likely non-startups are excluded so funds and holding vehicles do not
    dominate sector totals.
    """

    def startup_like(company: dict[str, Any]) -> bool:
        return not any(tag.startswith("non-startup classification") for tag in company["tags"])

    eligible = {company["id"]: company for company in companies if startup_like(company)}
    dated = [(cid, _parse_date(day), amount) for cid, day, amount in offerings if cid in eligible]
    dated = [item for item in dated if item[1]]
    snapshot = max((item[1] for item in dated), default=None)
    years = sorted({item[1].year for item in dated})

    recent_start = prior_start = None
    if snapshot:
        recent_start = snapshot - timedelta(days=730)
        prior_start = snapshot - timedelta(days=1460)

    cluster_rows: dict[str, dict[str, Any]] = {}
    for key in [c[0] for c in CLUSTERS] + [OTHER_CLUSTER[0]]:
        cluster_rows[key] = {
            "key": key,
            "label": CLUSTER_LABELS[key],
            "ranked": key != OTHER_CLUSTER[0],
            "sectors": set(),
            "companies": 0,
            "young_companies": 0,
            "elevated_companies": 0,
            "scores": [],
            "rounds_by_year": {str(year): 0 for year in years},
            "amount_by_year": {str(year): 0.0 for year in years},
            "rounds_recent": 0,
            "rounds_prior": 0,
            "raised_recent": 0.0,
            "regions": defaultdict(int),
            "top": [],
        }

    region_rows = {
        region["key"]: {
            "key": region["key"],
            "label": region["label"],
            "zip3": list(region["zip3"]),
            "grid": list(region["grid"]),
            "companies": 0,
            "elevated_companies": 0,
            "raised_recent": 0.0,
            "by_cluster": defaultdict(int),
        }
        for region in REGIONS
    }

    for company in eligible.values():
        row = cluster_rows[company["cluster"]]
        score = company["signal_score"]["total"]
        row["companies"] += 1
        row["sectors"].add(company["sector"])
        row["scores"].append((score, company["name"], company["id"]))
        if score >= ELEVATED:
            row["elevated_companies"] += 1
        if "young company" in company["tags"]:
            row["young_companies"] += 1
        region_key = company.get("region")
        if region_key:
            row["regions"][region_key] += 1
            region = region_rows[region_key]
            region["companies"] += 1
            region["by_cluster"][company["cluster"]] += 1
            if score >= ELEVATED:
                region["elevated_companies"] += 1

    for cid, filed, amount in dated:
        company = eligible[cid]
        row = cluster_rows[company["cluster"]]
        year = str(filed.year)
        row["rounds_by_year"][year] += 1
        row["amount_by_year"][year] += amount or 0.0
        if filed > recent_start:
            row["rounds_recent"] += 1
            row["raised_recent"] += amount or 0.0
            if company.get("region"):
                region_rows[company["region"]]["raised_recent"] += amount or 0.0
        elif filed > prior_start:
            row["rounds_prior"] += 1

    clusters = []
    for row in cluster_rows.values():
        if not row["companies"]:
            continue
        scores = sorted(row.pop("scores"), key=lambda item: (-item[0], item[1].casefold()))
        top_scores = [item[0] for item in scores[:10]]
        depth_avg = sum(top_scores) / len(top_scores) if top_scores else 0.0
        prior, recent = row["rounds_prior"], row["rounds_recent"]
        momentum_pct = ((recent - prior) / prior * 100) if prior else None
        momentum_points = 30 * _clamp(((momentum_pct / 100) + 0.5) if momentum_pct is not None else 0.5)
        breadth_points = min(20, 2 * row["elevated_companies"])
        components = [
            {"key": "depth", "label": "Signal depth", "points": round(depth_avg * 0.5, 1), "max": 50,
             "detail": f"Average score of the top {len(top_scores)} companies is {depth_avg:.0f}/100."},
            {"key": "momentum", "label": "Funding momentum", "points": round(momentum_points, 1), "max": 30,
             "detail": (f"{recent} rounds in the latest 24 months vs {prior} in the 24 before "
                        f"({momentum_pct:+.0f}%)." if momentum_pct is not None
                        else f"{recent} rounds in the latest 24 months; no prior window to compare, scored neutral.")},
            {"key": "breadth", "label": "Breadth", "points": breadth_points, "max": 20,
             "detail": f"{row['elevated_companies']} companies score {ELEVATED}+ (2 points each, up to 20)."},
        ]
        total = int(round(sum(item["points"] for item in components)))
        row.update({
            "sectors": sorted(row["sectors"], key=str.casefold),
            "regions": dict(row["regions"]),
            "top": [{"id": cid, "name": name, "score": score} for score, name, cid in scores[:5]],
            "avg_top_score": round(depth_avg, 1),
            "momentum_pct": round(momentum_pct, 1) if momentum_pct is not None else None,
            "amount_by_year": {year: round(value, 2) for year, value in row["amount_by_year"].items()},
            "raised_recent": round(row["raised_recent"], 2),
            "score": {"total": total, "tier": _tier(total)[0], "tier_label": _tier(total)[1], "components": components},
        })
        clusters.append(row)

    clusters.sort(key=lambda item: (not item["ranked"], -item["score"]["total"], item["label"]))
    rank = 0
    for row in clusters:
        if row["ranked"]:
            rank += 1
            row["rank"] = rank
        else:
            row["rank"] = None

    regions = []
    for region in region_rows.values():
        region["by_cluster"] = dict(region["by_cluster"])
        region["raised_recent"] = round(region["raised_recent"], 2)
        regions.append(region)

    partial_year = None
    if snapshot and (snapshot.month, snapshot.day) != (12, 31):
        partial_year = str(snapshot.year)
    return {
        "clusters": clusters,
        "regions": regions,
        "years": [str(year) for year in years],
        "partial_year": partial_year,
        "window_end": snapshot.isoformat() if snapshot else None,
        "startup_like_companies": len(eligible),
        "method": [
            "Company signal score (0–100) adds points only for observed signals: capital raised 20, recent raise 20, repeat raises 10, investor breadth 10, hiring 15, accelerator/program 10, IP & research partnerships 10, public grants 5.",
            "Missing data earns zero points and is labeled not detected; it is never imputed. A low score can mean little public evidence rather than a weak company.",
            "Sector score (0–100) = signal depth (half the average of the top 10 company scores, 50) + funding momentum (rounds in the latest 24 months vs the prior 24, 30) + breadth (companies scoring 35+, 20).",
            "Records tagged as likely funds, holding, real-estate or financial vehicles are excluded from sector and region totals.",
            "Regions group USPS three-digit ZIP areas from the Form D business address; the tile map is schematic, not to scale.",
            "Scores rank the strength of public signals. They are not predictions of success or investment advice.",
        ],
    }


__all__ = ["build_sector_view", "cluster_for", "region_for", "score_company", "SCORE_VERSION"]
