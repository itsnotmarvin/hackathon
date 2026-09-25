# Garden State

One shared workspace for discovering and researching New Jersey companies. The application combines the team's company leads, business assessments, SEC funding filings, leadership records, and reputation research into company profiles with inspectable sources.

## Run locally

Python 3.11 or newer is required. From the repository root:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock
.venv/bin/python -m unified
```

Open **http://127.0.0.1:8000**. The directory, filters, company profiles, comparison, saved shortlist, notes, exports, and saved public research work without API keys. Shortlists and notes persist in `.runtime/workspace.sqlite3`; research jobs and source caches persist in `.runtime/reputation.sqlite3`.

Use another port with `python -m unified --port 8001`. Run exactly one application process. The server takes a lock on its runtime directory so another process cannot interrupt active research. To run an independent second workspace, set a different `GARDEN_RUNTIME_DIR`.

## What the app connects

| Research area | Shared product integration |
| --- | --- |
| Founders & leadership | The root company's source-linked CEO records; optional read-only import of the existing Supabase founder evidence graph. Titles remain explicit: a CEO, director, or advisor is not automatically a founder. |
| Business & market potential | Team business model and novelty assessments, headcount observations, and sector funding context. Analyst judgments and broad sector proxies are labeled. |
| Funding & financial health | Existing NJ Form D company and offering data, joined by SEC CIK. Recorded fundraising is separate from revenue, cash on hand, runway, and profitability. |
| Reputation & ecosystem interest | The existing research service, its evidence checks, saved public research, live discovery, job progress, and persisted partial results. |

The company catalog joins exact normalized legal names and explicit aliases conservatively. It does not use fuzzy person/company matches to manufacture complete profiles. A source-backed NJ filing address is a dated location signal, not proof that an issuer is still an independent startup. The directory includes company leads and historical issuers; examine eligibility and source dates before making a shortlist.

Evidence coverage means how many research areas have some data. It is not a company quality score, a prediction, or an investment rating. No missing metric is replaced with an invented zero or an average. Several modules citing the same URL do not create several independent sources.

## Live discovery

Live discovery reuses Marvin's `reputation/` backend. It needs an authenticated **Monid CLI** on the server and a **Gemini API key**. You can point the server to the existing reputation configuration:

```sh
.venv/bin/python -m unified --env-file /absolute/path/to/reputation-and-ecosystem-interest/.env.local
```

Alternatively, export `GEMINI_API_KEY`, optional `GEMINI_MODEL`, and optional `MONID_BIN` before starting. The `--env-file` loader accepts only the reputation module's allowlisted settings. Export the Garden State and Supabase settings separately in the server environment.

The **Research** flow explicitly distinguishes live discovery from saved public research. Provider failures preserve available findings and show the reason. The app never substitutes saved results for a failed live search. Existing search price guards, request budgets, retries, caching, and idempotency are retained. Gemini quota and any billing depend on the configured Google project; the application does not change billing settings.

## Connect the founder database

The directory already includes the team's twelve source-linked CEO records. For deeper profiles, export these server-only variables:

```sh
export SUPABASE_URL='https://your-project.supabase.co'
export SUPABASE_READONLY_KEY='your-read-capable-key'
```

The key must have SELECT access to the relevant existing tables. The original `SUPABASE_SERVICE_ROLE_KEY` is supported as a fallback; a restricted read-only credential is preferable. No credential is sent to the browser. Open **Methodology** and refresh the founder connection. The adapter sends only GET requests to the existing database and saves the returned profiles locally. It does not call enrichment, seed, reset, or database-writing endpoints.

Imported name-based enrichment remains a research lead until identity is checked. The old verification report is not imported as current company facts. Failed refreshes preserve the prior local cache.

## Hosting and access

The default server listens on loopback and rejects unrelated Host headers. To expose the app through a trusted HTTPS host, set a strong `GARDEN_ACCESS_TOKEN` and run behind an HTTPS reverse proxy:

```sh
export GARDEN_ACCESS_TOKEN='a-long-random-secret'
.venv/bin/python -m unified --host 0.0.0.0 --port 8000
```

The UI asks for the token and holds it only in memory. Reloading requires reentry. The token protects all private API routes; source keys remain server-only. Preserve the `.runtime` directory on durable private storage and run one worker. This is a shared team workspace: its shortlist and notes are shared by everyone with access. Separate user accounts and per-user workspaces are not implemented.

## Validation

All unified tests use local data or mocked transports; they do not write to the team's remote database or make paid research calls.

```sh
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q
.venv/bin/python business-and-market-potential/scripts/compute_metrics.py
cd reputation-and-ecosystem-interest
../.venv/bin/python scripts/verify_benchmark.py
```

The root pytest configuration includes the unified integration tests and the existing reputation/extractor tests. It intentionally does not collect the legacy founder scripts that require a remote database or can write to it.

`PRODUCT-CONTRACT.md` describes the shared API and evidence semantics. Implementation lives in `unified/`; the original responsibility folders remain the source modules.
