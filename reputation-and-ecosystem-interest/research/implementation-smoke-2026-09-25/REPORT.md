# Implementation smoke test — September 25, 2026

The backend, website and saved-research path work. Live search, page retrieval and
Gemini interpretation have executed with real providers. **The final implementation
has not completed a successful full live run: Google's availability errors blocked
the last attempt.** This is a working prototype with unresolved live reliability,
not a production or predictive-accuracy sign-off.

## What was exercised

- Real user-supplied Gemini credential; successful model-list and generation calls.
- Monid/TinyFish public search and fetch, with exact zero-USD price checks.
- Browser-driven saved-research and live-search buttons, progress and results.
- Desktop and 390px mobile layouts, without horizontal document overflow.
- 37 runtime tests plus the 8 existing offline-extractor tests: all pass.
- Existing benchmark integrity: 10 cases, 11 snapshots, 19 exact excerpts, 5 queries.
- Python compilation, JavaScript syntax, ignored credential/runtime paths and a
  credential scan of shareable repository files: pass. Private key file mode: 0600.

## Observed runs

See [run-summaries.json](run-summaries.json) for exact status and usage records.

1. Development version 1.0.1 requested two companies. It used 13 searches, 19 fetch
   attempts, 9 cached pages and 9 model HTTP attempts, returning Cecilia Energy as
   one qualified candidate plus three review candidates. This run finished partial.
   Inspection found a government research proposal incorrectly classified as an
   investor affiliation. That claim is not accepted as a verified investment.
2. Development version 1.0.2 returned Canyon Magnet Energy before a later model
   connection failure. Its qualification relied partly on proposed work. Current
   rules keep that evidence visible but do not count proposed work toward qualifying
   external relationships. This old ranking is not a current recommendation.
3. Version 1.0.3 in JSON mode rejected a schema-invalid model record. The provider
   request now requires Gemini structured output as well as local validation.
4. The final live attempt retrieved/reused six pages, then received Google
   high-demand/unavailable responses on all three bounded model attempts. It
   returned an explicit failure and no fabricated or substituted live cards.
5. Saved research under current checks completes with Cecilia as a stronger-evidence
   card, Queens Carbon as limited evidence and Chorah Labs in location review.
   It makes zero searches/model requests. The original manually curated report has
   broader judgments; conservative automatic quote checks do not recover all of
   those signals, so this also exposes a recall limitation.

## Quality changes driven by inspection

Legal suffixes no longer narrow every search to the full incorporated name.
Quotes must identify the company; a name elsewhere on a directory page is
insufficient. City-only grant listings do not establish headquarters. CDN IP
redirects do not create an extra institution. Follow-up extraction retains
previous verified evidence, while current versions of repeated events take
precedence. Proposal wording cannot receive actual-execution credit, government
proposal text cannot establish investor affiliation, and event-date precision
cannot exceed its quote. Old reporting is labeled historical. Regression tests
cover these failures.

## Assessment

The implementation demonstrates a button-triggered, bounded research workflow
with source checks and honest failure/partial states. It does **not** demonstrate
reliable shortlist completion, broad NJ coverage or validated discovery accuracy.
The convenience-sample research and fixture tests cannot supply precision/recall
rates for new companies. Strict quotation checks reduce unsupported claims but
also lose valid signals. The next quality gate is a successful live run on the
current version followed by a fresh, manually reviewed company sample.

The website runs locally only. Shared-site integration, public hosting, per-user
controls and sustained production reliability remain separate work.

## Backend reliability verification: version 1.1.0

Further frontend work was paused at the user's request to prioritize the shared
backend handoff. No push or merge was performed.

- 46 runtime tests and 8 existing extractor tests pass; benchmark integrity,
  Python compilation and JavaScript syntax checks pass.
- Controlled faults verify recovery after repeated HTTP 503s, timeouts, network
  failures, invalid schema output and a short 429 Retry-After. Permanent errors,
  long Retry-After, expired deadlines and global budgets stop additional attempts.
- Search and batch fetch retries recover; exhausted fetch/search budgets cannot
  be bypassed. A failed follow-up retains the previously verified company card.
- Repeated submission IDs reuse active, completed and failed jobs; conflicting
  parameters return 409. IDs also persist when a completed cached job is reused.
- Provider initialization failure returns a safe failed job and releases the
  worker so the next run can complete.
- The restarted local server passed a real HTTP saved-research job and duplicate
  POST check: one qualified card, two review cards, zero provider calls.
- A fresh, small structured-output Gemini probe remained unavailable after two
  attempts. This is not a successful live research run. Provider availability
  remains the live-demo limitation; explicitly labeled saved mode is available.
- Credential scan passed: the supplied key does not occur in shareable files;
  ignored server configuration retains mode 0600.
