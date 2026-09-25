#!/usr/bin/env python3
"""Offline evidence-integrity checks; does not claim to test an AI extractor."""
import hashlib
import json
from pathlib import Path
from urllib.parse import unquote, urlsplit

BASE = Path(__file__).resolve().parents[1] / "benchmark"


def read(name):
    return json.loads((BASE / name).read_text())


def canonical(url):
    parsed = urlsplit(url)
    return (parsed.hostname.removeprefix("www."), unquote(parsed.path).rstrip("/"))


def main():
    sources = read("sources.json")
    cases = read("cases.json")
    recovery = read("recovery.json")
    queries = read("search-results.json")
    controls = read("controls.json")
    summary = read("run-summary.json")
    protocol = read("frozen-protocol.json")
    assert len(cases) == 10 and len(queries) == 5
    assert len({c["id"] for c in cases}) == len(cases)
    assert len({s["id"] for s in sources}) == len(sources)
    assert {r["case_id"] for r in recovery} == {c["id"] for c in cases}
    assert [q["query"] for q in queries] == protocol["queries"]
    assert hashlib.sha256((BASE / "frozen-protocol.json").read_bytes()).hexdigest() == summary["protocol_sha256"]
    source_map = {s["id"]: s for s in sources}
    texts = {}
    for s in sources:
        path = BASE / s["snapshot_path"]
        assert path.resolve().is_relative_to(BASE.resolve())
        data = path.read_bytes()
        assert hashlib.sha256(data).hexdigest() == s["sha256"], s["id"]
        texts[s["id"]] = data.decode()
    quote_count = 0
    for c in cases:
        assert c["evidence"] and c["first_public_date"] is None
        for e in c["evidence"]:
            assert e["quote"] and e["quote"] in texts[e["source_id"]], c["id"]
            quote_count += 1
        assert not c["early_stage_verified"]
    query_map = {q["query"]: q for q in queries}
    for r in recovery:
        q = query_map[r["query"]]
        pool = {canonical(x["url"]) for x in q["results"] if x["position"] <= 5}
        assert r["relationship_recovered"] == bool(r["recovered_source_ids"])
        for sid in r["recovered_source_ids"]:
            assert canonical(source_map[sid]["url"]) in pool, (r["case_id"], sid)
        assert not r["complete_role_and_interval_recovered"] or r["relationship_recovered"]
    for q in queries:
        assert q["price"]["amount"]["value"] == 0
        assert q["reported_cost"]["value"] == 0
    for c in controls:
        assert all(sid in source_map for sid in c["source_ids"])
    found = sum(r["relationship_recovered"] for r in recovery)
    detailed = sum(r["complete_role_and_interval_recovered"] for r in recovery)
    assert found == summary["relationship_recovered"] == 8
    assert detailed == summary["complete_role_and_interval_recovered"] == 7
    assert sum(c["relationship_start"] is not None for c in cases) == summary["dated_start_in_reference_cases"] == 2
    assert summary["predictive_accuracy"] is None
    print(f"PASS: {len(cases)} cases, {len(sources)} snapshots, {quote_count} exact evidence excerpts, {len(queries)} queries")
    print(f"Manual recovery: {found}/10 relationships; {detailed}/10 reference role/interval detail")
    print("4 manually adjudicated controls; 1 unscored discovery trap. No automated extractor evaluated.")


if __name__ == "__main__":
    main()
