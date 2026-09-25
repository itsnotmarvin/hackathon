# Status

Updated: 2026-09-25. Owner: Marvin. Branch: `marvin`.

## Current implementation

The module now has a working Python backend and responsive local website at
`http://127.0.0.1:8787`. Run `python3 -m reputation` from this folder. Gemini
3.5 Flash-Lite interprets pages retrieved by Monid/TinyFish; the coordinator runs
targeted follow-ups, validates quotes and source attribution, ranks companies,
and preserves partial results. Provider access is explicitly implemented in code.

Implemented: sector filters, company cards, separate NJ review candidates, dated
evidence, exact quotations/source links, JSON export, SQLite history/page cache,
bounded research, server-side credentials, local-only preview and protected
external WSGI mounting. The application does not measure public-interest growth.

Verification: 46 runtime tests and the 8 existing extractor tests pass. The original
benchmark verifier passes (10 cases, 11 snapshots, 19 exact excerpts, 5 queries).
Python compilation and JavaScript syntax checks pass. Chrome testing exercised
the saved-research button, live-search button, progress polling and a 390px mobile
viewport without horizontal document overflow.

Live testing reached source retrieval, Gemini discovery/extraction, follow-up
research and ranked output. One early bounded run requested two companies and
returned Cecilia Energy as a shortlist candidate, with three candidates in review.
Google 503/high-demand failures also occurred and were preserved as failed/partial
runs, rather than being substituted with sample data. The original Gemini 3.8 Flash
choice was replaced with the available free-tier Gemini 3.5 Flash-Lite model.

The live review exposed and prompted fixes for legal-name search suffixes,
overstated headquarters claims, proposal language, false investor categorization,
date precision, source-family changes through CDN redirects, and evidence lost
during follow-up extraction. Unit checks cover these failure cases. Real-company
research remains a heuristic assessment requiring review, not validated success
prediction or a complete map of the NJ ecosystem.

**Live verification limit:** the latest full run using the current structured-output
request and stricter checks reached Google's HTTP 503/high-demand error after three
bounded attempts. A preceding JSON-mode attempt returned a schema-invalid record
and was correctly rejected; structured output is now required as well as local
validation. The latest code has not completed a successful full live run. Saved
research works under the current rules and is explicitly labeled. Earlier live
outputs use earlier rule versions and are flagged accordingly in the API/UI.
Provider reliability and a fresh quality evaluation remain requirements before
calling this production-ready. See the implementation smoke report in `research/`.

**Backend reliability update (pipeline 1.1.0):** Gemini now retries transient HTTP
and network failures and invalid/incomplete structured output up to five attempts;
search and batch fetch failures retry up to three attempts. All consume the
existing job budgets. Duplicate submission IDs persist in SQLite and return the
same job; conflicting parameters are rejected. A provider initialization failure
can no longer leave the worker stuck. Failure-injection tests verify recovery,
budget enforcement, permanent-error handling, preservation of partial evidence,
and active/completed/failed request deduplication. Saved-research backend mode
works without external calls. Further frontend work is paused per the user;
no merge, push, deployment or teammate-module changes were made.

Still outside this module build: the shared application's company matching and
combined rating, team interface agreement, hosting/deployment, end-user accounts,
multi-process job infrastructure, and comparable public-interest time series.
No public site was deployed. The user-supplied key is stored in ignored server
configuration with mode 0600; it is not included in committed/shareable files.

## Earlier benchmark status (historical)

The sections below record the work that preceded the web/backend implementation.

## Team handoff

Start with [startups.csv](../startups.csv): 12 unranked company leads from saved biographies, with relationship evidence, source links, and open questions tied to the ten product requirements. Eight historical/benchmark companies are listed separately. This handoff adds no new live research and does not establish that the leads are currently startups or based in NJ.

Our next priority is company-level evidence of operating progress and public attention. The relationship prototype is supporting research, not a startup-ranking system. The README now includes a file map so teammates can find the list without reading the benchmark internals.

## Completed

- Built the first manual public-relationship benchmark: 10 cases, 5 people, 11 full-text source snapshots, and 19 literal evidence excerpts.
- Froze the recovery protocol before running five investor-name searches without company names or answer URLs.
- Audited selected primary/affiliated results within the first five candidates: 8/10 relationships recovered, 7/10 with complete reference role/interval detail.
- Added four manually adjudicated false-attribution/date/stage/role controls and one unscored same-name discovery trap.
- Recorded TinyFish/Monid results, a separate Google spot check, per-page failures, and Firecrawl's existing quota block.
- Preserved first-observed timestamps, source metadata separately from event dates, exact quotes, and snapshot hashes.

## Verification

```sh
cd reputation-and-ecosystem-interest
python3 scripts/verify_benchmark.py
```

Passed: 10 cases, 11 snapshot hashes, 19 exact evidence excerpts, 5 query records, source membership within the declared cutoff, and aggregate counts. This verifies artifact integrity, not external truth or an AI extractor. A separate rules extraction baseline is now implemented; see the continuation below.

All task edits are inside this responsibility folder. No branch change, commit, push, dependency install, scheduled monitor, or shared-schema integration was performed.

## Findings / limits

- Person-level relationships are retrievable. Early entry and investment returns remain unverified.
- An SEC filing supplied historical details omitted by current biographies.
- Search cutoff and dead links caused misses; source metadata produced tempting but invalid appointment dates.
- Director/observer wording conflicts require review. Repeated biographies are not independent confirmation.
- This is a convenience sample and an unblinded manual audit, not predictive validation. Energy Focus is deliberately a public-company boundary case.
- Firecrawl returned HTTP 402 in the previous probe. TinyFish/Monid completed this collection; raw Google supplied one spot check. No controlled engine comparison was possible.

## Current next steps

1. Confirm each lead's identity, official website, current operating status, location, and stage.
2. Collect dated company-level evidence against the ten requirements in STARTUPS.md. Keep unknowns distinct from negative findings.
3. Combine operating milestones into company timelines and compare them with public attention; relationships alone cannot establish momentum or an attention gap.
4. Coordinate the funding and other shared records with the relevant owners before integration.
5. Improve the extractor only as needed for those records, using fresh labeled examples. Date extraction, founder/investor language, and issuer-relative attribution remain unsupported. Prospective monitoring remains pending.

No shared root changes are needed for this benchmark. Earlier numeric workspace `4/` was renamed to `reputation-and-ecosystem-interest/` during the session; the current root mapping agrees with branch `marvin`.

## Continuation: offline extractor baseline

Resumed from T3 thread `b65423b7-81c0-45a2-9145-4ef937fb4375`.

- Added `scripts/extract_relationships.py`: candidate-pair extraction from hashed
  snapshots, literal quotes with offsets, explicit abstention, role conflicts,
  and unknown dates/stage preserved.
- Added `scripts/evaluate_extractor.py` and saved `benchmark/extractor-results.json`.
  Supports relationship text for 8/10 supplied pairs; abstains on Energy Focus and
  TriNetX. This is an unblinded rules-development run, not held-out accuracy or
  the separate manual search-recovery score.
- Added eight failure-oriented regression tests covering attribution, role
  boundaries/conflicts, metadata dates, stage, negation, tables, and quote offsets.
- Dates are deliberately not extracted. Historical SEC interval recovery and
  issuer-relative attribution need further work. No model API is involved.
