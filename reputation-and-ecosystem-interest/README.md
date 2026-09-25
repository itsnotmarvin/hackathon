# Reputation & Ecosystem Interest

An implemented Python research backend and responsive web preview for the shared
NJ startup discovery application. All implementation stays in Marvin's folder on
branch `marvin`. No teammates' modules or shared root files were changed.

**Click Find NJ startups → search and fetch public pages → Gemini extracts claims
and suggests follow-ups → code verifies evidence and ranks → sourced company cards.**

## Run the website

Requires Python 3.11+, `certifi`, and an installed/authenticated Monid CLI for live
search. The current computer has these available. From a fresh checkout:

```sh
cd reputation-and-ecosystem-interest
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
cp .env.example .env.local  # first setup only; preserve an existing key
chmod 600 .env.local
# Set GEMINI_API_KEY in .env.local using your editor.
.venv/bin/python -m reputation --port 8787
```

Open **http://127.0.0.1:8787**. On the configured machine, `python3 -m reputation`
is sufficient. Environment variables override `.env.local`.

- **Find NJ startups** runs live research, including internal follow-up searches.
- **View saved research** loads real, previously curated public-source research.
  It is labeled as saved and makes no provider calls. It works without a model key.
- The UI includes sector filters, qualified/review separation, dated signals,
  exact quotations, source links, research history and JSON evidence export.
- Closing the browser does not stop research. Reopening reconnects to a running
  job. Server restart marks unfinished jobs interrupted; a new run reuses source
  caches without automatically replaying model requests.

## Providers and costs

**Gemini 3.5 Flash-Lite** interprets the fetched pages. The supplied key lives in
ignored `.env.local`, never in browser code, API responses or exports. Requests
use Gemini structured JSON output, a required schema and local schema validation. No Google
Search grounding is enabled. `GEMINI_MODEL` is configurable.

**Monid → TinyFish `/search` and `/fetch`** provide search and readable page text.
The backend invokes the CLI directly, independently of chat tools. A deployment
needs its own authorized Monid configuration. Before every call, fresh pricing
must confirm exactly $0 USD; unknown or changed prices stop collection. Reported
billing is checked too. There is no paid fallback.

Google documents a free tier for this model. **Actual Gemini quota and billing
follow your Google project**; an API key alone does not identify its billing tier.
This application does not enable billing. See [Google pricing and data-use terms](https://ai.google.dev/gemini-api/docs/pricing).
Only public pages are sent by this version.

Each run has limits of 14 searches, 24 page-fetch attempts, 9 model HTTP attempts
(including retries), and an approximately 10-minute time budget. A pending request
can overrun the time check. One job runs at a time, with 10 live starts/hour at most.
Identical completed runs are reused for 15 minutes; source pages cache for 6 hours.
There is no scheduled background research or paid-provider fallback.

Temporary Gemini failures retry up to **5 total attempts per assessment**, with
exponential backoff and jitter; all attempts count toward the 9-call job limit.
Timeouts, HTTP 408/429/5xx transient errors, and malformed/incomplete model records
are retried. Authentication/configuration errors stop immediately. Short numeric
`Retry-After` values are respected; long or unparsed values stop the run rather
than retrying too early. Each model request has a 45-second socket timeout, bounded
by remaining job time. Search and batch page retrieval retry up to **3 total
attempts**, consuming the existing search/page limits. Unreadable individual pages
are reported and excluded. Pricing/setup failures do not retry.

Progress, verified cards and fetched evidence survive a later provider failure.
The API returns `partial` when cards exist, or `failed` with `error_code` when they
do not. It never represents saved/sample research as a successful live run.

## Shared-app integration

Mount `reputation.web.create_app()` as a WSGI application, or use `ResearchService`
from the eventual shared server's adapter. This checkout had no shared web stack
to integrate into at build time. This is a module preview, not another team's app.

| Endpoint | Purpose |
| --- | --- |
| `GET /api/reputation/status` | Safe setup flags, model and sectors |
| `POST /api/reputation/jobs` | Start with `{"count":2,"sector":"All sectors","mode":"live","request_id":"client-generated-uuid"}` |
| `GET /api/reputation/jobs/{id}` | Progress, cards, sources, warnings and usage |
| `GET /api/reputation/jobs` | Recent run metadata |

POST returns 202 and a run ID, or 200 for a reused run. Poll until
`completed`, `partial`, `failed`, or `interrupted`. HTTP 409 supplies the already
active job ID. Partial jobs preserve findings and explain shortfalls.

Use the same optional `request_id` (16–64 ASCII letters/digits/hyphens) when
retrying a lost POST response. Its durable mapping returns the same active or
terminal job without duplicate provider work. Reusing that ID with different
parameters returns HTTP 409 and `code: "request_conflict"`. A deliberate new
attempt after a failed run needs a new request ID. HTTP 429 means the hourly
start limit; setup failures return HTTP 503 with a safe error code. Polling an
existing failed job returns HTTP 200: inspect the job's `status` and `error_code`.

For a provider-independent demo, start `mode: "sample"` through the same backend
API. It verifies saved source hashes and quotes, returns dated public research,
and makes zero provider calls. Live mode still depends on provider availability.

Company records include `company_id`, name/aliases/domain, sector, `nj_presence`,
signals, `assessment`, `why_surfaced`, evidence counts and limitations. Evidence
includes exact quotes, URLs, character offsets, separate publication/observation
dates, source families and snapshot hashes. Signal event dates are separate.
`public_interest_trend` remains explicitly `not_measured`.

The local company ID hashes name/domain. **Shared identity matching and the other
three modules' interfaces still require coordination.** This module does not produce
the combined application's overall startup rating.

For public hosting: use HTTPS, persistent private storage, authorized Monid
configuration and a Gemini project. Set `REPUTATION_ACCESS_TOKEN` to protect the
research/history API when mounted externally; the UI keeps that token in memory.
The development server binds only to localhost. The SQLite coordinator supports
one application process. Multiple WSGI workers need a shared job queue first.
User accounts, per-user quotas, team integration and public deployment are pending.

## Quality and verification

```sh
python3 -m unittest discover -s tests -v
python3 -m unittest discover -s scripts -p 'test_*.py'
python3 scripts/verify_benchmark.py
node --check web/app.js
```

Tests cover attribution, invented quotes, legal-name variants, dates, duplicate
source families, internal follow-ups, partial results, API failures, caching,
restart recovery, access controls and price guards. Fictional test fixtures never
enter the real research store.

Exact quotations verify provenance, **not external truth**. Gemini still interprets
relationship type, source role, identity and NJ presence. Name matching and
deduplication are heuristics. Recent reporting does not prove a partnership is
still active. The UI groups sectors; it does not measure statewide sector growth
or public-attention trends. There is no held-out discovery-accuracy or predictive
investment-performance claim.

See [PIPELINE-DESIGN.md](PIPELINE-DESIGN.md) and [STATUS.md](STATUS.md).
The [three-company pilot](research/nj-momentum-2026-09-25/REPORT.md) and
[five-company manual evaluation](research/reputation-evaluation-2026-09-25/REPORT.md)
are separately labeled earlier research artifacts.

## Earlier research and offline extractor

Marvin's responsibility area on branch `marvin`. This folder was formerly workspace `4/`; the shared project now uses responsibility names.

We are testing whether public evidence about credible investors, advisors, operators, and communities can help identify startups worth investigating. A documented relationship is not proof of early involvement, investment returns, or future startup success.

**Team handoff: start with [startups.csv](../startups.csv).** It contains 12 company leads, the public relationships that surfaced them, source links, and the checks still needed against our ten requirements. These are unranked leads; current startup status, NJ location, operating momentum, and an attention gap remain unverified.

| File or folder | What it contains | Who needs it |
| --- | --- | --- |
| [startups.csv](../startups.csv) | Company list, exact supporting excerpts, research questions, historical reference companies | Everyone reviewing company leads |
| [STATUS.md](STATUS.md) | What is done, limitations, and current next steps | Teammates picking up the work |
| README.md | Folder guide, commands, and technical limits | Anyone using this folder |
| [benchmark/REPORT.md](benchmark/REPORT.md) | Findings from the original manual search benchmark | Anyone checking the research method |
| benchmark/*.json | Reference cases, source records, queries, manual judgments, controls, and extractor output | Research/engineering audit |
| benchmark/evidence/ | Eleven saved source pages | Anyone checking a claim |
| scripts/ | Extractor, evaluation runner, regression tests, evidence verifier | Developers |
| .gitignore | Excludes raw provider captures and Python caches | Repository maintenance |

The original research tested retrieval of ten known relationships. Its results remain in the benchmark folder; the earlier unranked handoff is the root CSV linked above.

## Run the offline verification

Requires Python 3.9 or newer; no packages, API keys, or network calls:

```sh
cd reputation-and-ecosystem-interest
python3 scripts/verify_benchmark.py
```

The verifier checks evidence hashes, exact quotations, case/source references, search-result membership, and reported counts. It does **not** test an extraction model or establish the truth of external claims.

## Files

- `benchmark/cases.json`: ten reference relationships, precise labels, dates, limitations, and literal evidence excerpts.
- `benchmark/sources.json` and `benchmark/evidence/`: eleven public-page snapshots and their provenance.
- `benchmark/frozen-protocol.json`: reference case list and five company-blind investor-name queries, frozen before the recovery pass.
- `benchmark/search-results.json`: all returned search candidates, including those outside the first-five cutoff.
- `benchmark/recovery.json`: manual recovery judgments and the supporting sources.
- `benchmark/controls.json`: four adjudicated attribution/date/role controls and one unscored identity trap.
- `benchmark/run-summary.json`: counts and limits in machine-readable form.
- `benchmark/google-observation.json`: a separate Chrome spot check; not comparable engine-level recall.
- `benchmark/captures/`: ignored local provider responses retained for audit. The offline verifier does not depend on them.

## Collection and credentials

The original benchmark used TinyFish `/search` and `/fetch` through the installed Monid CLI's zero-price guard. Monid authenticates using its local key store; no environment variable is required for the saved benchmark. Firecrawl was unavailable with HTTP 402. Google was checked manually through Chrome. No credentials are committed.

Live collection is now automated in `reputation/`; the old `scripts/` extractor remains offline. Search results and extracted text are untrusted evidence, and original page dates must not be substituted for relationship dates.

## Proposed interface for the shared app

The earlier person-level proposal below is retained for context. The implemented company-level API is described above; team-wide integration is still pending.

```json
{
  "person": "Example Investor",
  "company": "Example Startup",
  "relationship": "board_observer",
  "relationship_start": null,
  "first_public_date": null,
  "source_as_of": "2026-09-25",
  "first_observed_at": "2026-09-25T15:00:00Z",
  "evidence": [{"source_id": "S01", "quote": "Literal supporting text"}],
  "early_stage_verified": false
}
```

Date precision is preserved (`YYYY`, `YYYY-MM`, or `YYYY-MM-DD`). Unknown values remain null. Relationship types distinguish an investor, founder, director, observer, advisor, and general association. Actual money and round facts may belong to `funding-and-financial-health/`; this area adds attributable relationships and changes in ecosystem interest. Coordinate with that owner before sharing a schema or duplicating collection.

## Offline extraction baseline

A dependency-free rules baseline now searches the saved snapshots for a supplied
person/company pair. It checks snapshot hashes and returns literal paragraph
quotes, character offsets, URLs, observed timestamps, and separate role claims.
It does not use the reference quotations or labels to extract evidence.

```sh
python3 scripts/extract_relationships.py --person "Dan Borok" --company "BigCommerce"
python3 scripts/extract_relationships.py --person "Stephen Socolof" --person-alias "Steve Socolof" --person-alias "Stephen J. Socolof" --company "Kintra Fibers"
python3 -m unittest discover -s scripts -p 'test_*.py'
python3 scripts/evaluate_extractor.py
```

The saved development run is `benchmark/extractor-results.json`: 8 of 10 supplied
pairs have supporting relationship text; Energy Focus and TriNetX abstain.
This is **not** the earlier 8/10 search recovery measurement. Here every saved
snapshot is available, identities are supplied, and rules were developed with
knowledge of the sample. Role wording is preserved rather than forced into the
reference label. No held-out precision or discovery accuracy is established.

The four adjudicated controls have corresponding regression checks: Jennifer
Solomon cannot inherit Dan Borok’s investment attribution; Kintra retains conflicting
board/observer claims; Toothio gets no appointment date from page metadata; and
BigCommerce gets no seed-stage claim from an investment mention. The homonym trap
remains unscored: this baseline cannot verify identities.

Limitations: supported templates cover a small subset of biography language.
Markdown tables are skipped to avoid crossing between people; issuer-relative
phrases such as “our Board” and founder/investor combinations remain unsupported.
All relationship dates, end dates, and first-public dates remain null—even where
a human reference has dated evidence. Date extraction is not implemented.
Negation checks and clause/heading boundaries are conservative heuristics, not a
general attribution guarantee. Quotes establish what a page says, not external
truth. Repeated text and multiple URLs do not establish independent corroboration.
The baseline is an inspectable starting point for a future extractor and has no
shared-app integration, network collection, or scheduled monitoring.
