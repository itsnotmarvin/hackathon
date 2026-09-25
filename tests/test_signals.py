from __future__ import annotations

from pathlib import Path

from tests.test_catalog import _company, _filing, _offering, _write_csv
from unified.catalog import build_catalog
from unified.signals import cluster_for, region_for, score_company

FORM_D = "business-and-market-potential/data"


def test_missing_signals_score_zero_and_are_labeled_not_detected() -> None:
    score = score_company({}, [])
    assert score["total"] == 0
    assert score["tier"] == "low"
    assert score["signals"] == []
    assert all(not item["detected"] and item["points"] == 0 for item in score["components"])
    assert sum(item["max"] for item in score["components"]) == 100


def test_observed_signals_add_bounded_points() -> None:
    raw = {"total_raised": 5e7, "months_since_last_raise": 3, "num_offerings": 4, "total_investors": 25, "growth_rate": 50, "grant_count": 1}
    score = score_company(raw, ["accelerator_participation", "technology_license", "research_collaboration"])
    assert score["total"] == 100
    assert score["tier"] == "high"
    assert set(score["signals"]) == {"capital", "momentum", "repeat", "investors", "hiring", "accelerator", "ip", "grants"}


def test_single_round_is_not_counted_as_repeat_signal() -> None:
    score = score_company({"num_offerings": 1}, [])
    repeat = next(item for item in score["components"] if item["key"] == "repeat")
    assert repeat["detected"] is False
    assert "repeat" not in score["signals"]


def test_cluster_and_region_mapping() -> None:
    assert cluster_for("Biotechnology") == "life"
    assert cluster_for("Other Technology") == "tech"
    assert cluster_for("Other") == "other"
    assert region_for("07102") == "urban"
    assert region_for("08540") == "mercer"
    assert region_for("19103") is None
    assert region_for("") is None


def test_catalog_attaches_scores_and_ranks_sector_clusters(tmp_path: Path) -> None:
    _write_csv(tmp_path, f"{FORM_D}/nj_formd_companies.csv", [
        _filing("Helix Bio Inc", "101", industry="Biotechnology", zip="08540", num_offerings="3", months_since_last_raise="2"),
        _filing("Byte Labs Inc", "102", zip="07030", months_since_last_raise="30"),
        _filing("Harbor Fund LP", "103", industry="Pooled Investment Fund"),
    ])
    _write_csv(tmp_path, f"{FORM_D}/nj_formd_offerings.csv", [
        _offering("Helix Bio Inc", "101", filing_date="2026-03-01"),
        _offering("Helix Bio Inc", "101", filing_date="2023-02-01", file_num="021-101b"),
        _offering("Byte Labs Inc", "102", filing_date="2023-06-01"),
        _offering("Harbor Fund LP", "103", filing_date="2026-01-01"),
    ])
    payload = build_catalog(tmp_path)

    helix = _company(payload, "Helix Bio Inc")
    assert helix["cluster"] == "life"
    assert helix["region"] == "mercer"
    assert "young company" in helix["tags"]
    assert {"capital", "momentum", "repeat", "investors"} <= set(helix["signal_score"]["signals"])
    assert helix["signal_score"]["total"] > _company(payload, "Byte Labs Inc")["signal_score"]["total"]

    view = payload["sector_view"]
    assert view["window_end"] == "2026-03-01"
    assert view["partial_year"] == "2026"
    assert view["startup_like_companies"] == 2
    ranked = [cluster for cluster in view["clusters"] if cluster["ranked"]]
    assert [cluster["key"] for cluster in ranked] == ["life", "tech"]
    assert ranked[0]["rank"] == 1
    life = ranked[0]
    assert life["rounds_by_year"]["2026"] == 1 and life["rounds_by_year"]["2023"] == 1
    assert life["rounds_recent"] == 1 and life["rounds_prior"] == 1
    assert sum(item["max"] for item in life["score"]["components"]) == 100
    regions = {region["key"]: region for region in view["regions"]}
    assert regions["mercer"]["companies"] == 1
    assert regions["urban"]["by_cluster"] == {"tech": 1}
