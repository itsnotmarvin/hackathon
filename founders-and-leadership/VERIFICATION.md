# Pipeline verification

Proof that the founder-evidence pipeline actually calls external APIs and
persists the results in Supabase — not just that the code imports cleanly.

## How to check this yourself

```
cd founders-and-leadership
.venv/Scripts/python scripts/verify_pipeline.py --refresh
```

`--refresh` forces a fresh call to every API even if this founder already
has data stored; omit it to just re-read what's already in the DB. The
script (and the underlying `/research` endpoint) is idempotent — re-running
it repeatedly does not create duplicate rows, proven below.

It uses a real person from the team's shared [`startups.csv`](../startups.csv)
(row `L09`: Stephen Socolof / SunRay Scientific), not a throwaway fixture,
so the data this produces is real project data, not test noise.

## Real output, captured 2026-09-25

```
Startup: SunRay Scientific  (9ae475a4-038f-408d-86fb-5459d3dd7ed6)
Founder: Stephen Socolof  (f8fdefc5-e716-4667-9eee-ee140463c270)

Calling POST /founders/{id}/research against every live source...

  companies found this run:    0
  achievements found this run: 0
  grants found this run:       0

Calling GET /founders/{id}/profile -- reads back from Supabase fresh, no cache...

================================================================
WHAT'S ACTUALLY STORED IN SUPABASE RIGHT NOW
================================================================
  education rows:   0
  company rows:     0
  achievement rows: 22
  grant rows:       27
  evidence rows:    49  <- one per sourced fact, this is the proof trail
  signals:          {'previous_company_count': 0, 'grant_count': 27, 'total_grant_amount': 34563014.0, 'achievement_count': 22, 'education_count': 0, 'birth_year': None}

Sample evidence rows (claim -> source), pulled straight from the `evidence` table:
  - "6 publications, 45 citations, h-index 2"  [Semantic Scholar]
  - "1 publications, 2 citations, h-index 1"  [Semantic Scholar]
  - "Tech Council Ventures III-AI LP  (CIK 0002030082) filed D on 2024-08-27"  [SEC EDGAR]
  - "Tech Council Ventures III LP  (CIK 0002030046) filed D on 2024-08-26"  [SEC EDGAR]
  - "ENERGY FOCUS, INC/DE  (EFOI)  (CIK 0000924168) filed D on 2022-06-17"  [SEC EDGAR]
  - "GainSpan Corp  (CIK 0001423458) filed D on 2011-10-04"  [SEC EDGAR]

Per-API status this run:
  [  OK  ] Wikidata
  [  OK  ] Wikipedia
  [  OK  ] Semantic Scholar
  [  OK  ] ORCID
  [FAILED] GDELT
  [  OK  ] GitHub
  [  OK  ] SEC EDGAR
  [  OK  ] USAspending.gov
  [  OK  ] NSF Award Search
  [  OK  ] NIH RePORTER

Warnings (full detail):
  - GDELT: 429 Client Error: Too Many Requests for url: https://api.gdeltproject.org/api/v2/doc/doc?query=%22Stephen+Socolof%22&mode=artlist&format=json&maxrecords=5

See it yourself in the Supabase Table Editor:
  https://supabase.com/dashboard/project/<your-project-ref>/editor
  -> founders table, id = f8fdefc5-e716-4667-9eee-ee140463c270
  -> evidence table, filter entity_id to any id printed above
```

(The dashboard URL line is genericized here — the script prints your real
project's link when you run it, read from your own `.env`.)

## Idempotency: run three times in a row

The counts above (22 achievements, 27 grants, 49 evidence rows) are
**identical across three consecutive `--refresh` runs**, run back to back
right after a full data reset. Before this was fixed, re-running `/research`
duplicated every row (27 grants became 54, then 71, on repeat calls) because
NSF's API returns `estimatedTotalAmt` as a **string** ("199968") while
Supabase reads it back as a **number** on the next call, so the dedup
check's equality comparison silently never matched. Fixed in
[`services/nsf.py`](services/nsf.py) by casting the amount to `float` before
it's ever compared or stored — see the commit history for the before/after.

## Reading this

- **9 of 10 wired-in sources returned real data or a clean "no match," 1 hit a rate limit** (GDELT 429 — transient, not a code defect; it's a free public API without an auth mechanism to raise the limit).
- **49 evidence rows for 22+27=49 facts** — every single stored fact has a traceable source, 1:1.
- SEC EDGAR's Form D hits are the closest available replacement for what OpenCorporates (removed — paid-only, no usable free tier) would have provided: **Tech Council Ventures III / III-AI LP** and **GainSpan Corp** filings, plus **Energy Focus, Inc.** which independently confirms the SEC source URL already listed for this person in the team's own `startups.csv`.
- `$34,563,014` in `total_grant_amount` is the real sum of NSF/NIH/USAspending award amounts for this person/company, each backed by its own evidence row.

## Sources removed and why (see `.env.example` and each module's docstring for detail)

| Source | Reason |
|---|---|
| OpenCorporates | Requires a paid API token; 401 Unauthorized on every request without one, no usable free tier |
| SBIR.gov awards API | Returns 403 Forbidden on every request (AWS API Gateway block), including unkeyed/bare requests |
| arXiv | Real API, but returns 406 to every `requests` call from this stack regardless of headers (works via curl — a WAF/fingerprint block, not fixable with headers alone) |
| PatentsView / USPTO Assignment API | Hostnames used previously do not resolve, publicly or locally — dead endpoints, not wired in |

## Re-running for a different founder

Point the script at any `startups.csv` row, or hit the live endpoints directly and inspect the response the same way `verify_pipeline.py` does:

```
POST /startups
POST /founders
POST /founders/{id}/research
GET  /founders/{id}/profile   <- check the "evidence" and "signals" keys
```
