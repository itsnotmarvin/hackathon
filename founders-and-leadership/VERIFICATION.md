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
script is idempotent — it reuses the same startup/founder row by name
instead of creating duplicates each run.

It uses a real person from the team's shared [`startups.csv`](../startups.csv)
(row `L09`: Stephen Socolof / SunRay Scientific), not a throwaway fixture,
so the data this produces is real project data, not test noise.

## Real output, captured 2026-09-25

```
Startup: SunRay Scientific  (f7905e67-e172-4a07-9304-43e45a86979b)
Founder: Stephen Socolof  (6c27ee2b-8afe-4ea6-bdbf-37161d738352)

Calling POST /founders/{id}/research against every live source...

  companies found this run:    0
  achievements found this run: 2
  grants found this run:       27

Calling GET /founders/{id}/profile -- reads back from Supabase fresh, no cache...

================================================================
WHAT'S ACTUALLY STORED IN SUPABASE RIGHT NOW
================================================================
  education rows:   0
  company rows:     0
  achievement rows: 2
  grant rows:       27
  evidence rows:    29  <- one per sourced fact, this is the proof trail
  signals:          {'previous_company_count': 0, 'grant_count': 27, 'total_grant_amount': 34563014.0, 'achievement_count': 2, 'education_count': 0, 'birth_year': None}

Sample evidence rows (claim -> source), pulled straight from the `evidence` table:
  - "6 publications, 45 citations, h-index 2"  [Semantic Scholar]
  - "1 publications, 2 citations, h-index 1"  [Semantic Scholar]
  - "SunRay Scientific received a federal award from Department of Energy"  [USAspending.gov]
  - "SunRay Scientific received a federal award from Department of Energy"  [USAspending.gov]
  - "Stephen Socolof is PI on an NSF award (750000)"  [NSF Award Search]
  - "Stephen Socolof is PI on an NSF award (2000000)"  [NSF Award Search]

Per-API status this run:
  [FAILED] OpenCorporates
  [  OK  ] Wikidata
  [  OK  ] Semantic Scholar
  [  OK  ] GitHub
  [  OK  ] USAspending.gov
  [  OK  ] NSF Award Search
  [  OK  ] NIH RePORTER

Warnings (full detail):
  - OpenCorporates: OPENCORPORATES_API_KEY is missing - the officers/search endpoint requires a paid token, it 401s without one

See it yourself in the Supabase Table Editor:
  https://supabase.com/dashboard/project/<your-project-ref>/editor
  -> founders table, id = 6c27ee2b-8afe-4ea6-bdbf-37161d738352
  -> evidence table, filter entity_id to any id printed above
```

(The dashboard URL line is genericized here — the script prints your real
project's link when you run it, read from your own `.env`.)

## Reading this

- **6 of 7 wired-in sources returned real data or a clean "no match," 1 failed for the documented reason** (OpenCorporates needs a paid key — see `services/opencorporates.py`).
- **29 evidence rows** for 29 facts (2 achievements + 27 grants) means every single fact that got stored has a traceable source — that's the whole point of the `evidence` table, and it's confirmed working end to end (this was broken until the `evidence` table was created in Supabase; see git history).
- `$34,563,014` in `total_grant_amount` is not invented — it's the sum of real NSF/NIH/USAspending award amounts returned by those APIs for this specific person/company, each individually backed by its own evidence row.
- The `[FAILED]` line isn't swallowed silently — it's exactly the same warning you'd see in a live `POST /founders/{id}/research` call, so a stakeholder never has to take "it's failing" on faith.

## Re-running for a different founder

Point the script at any `startups.csv` row, or hit the live endpoints directly and inspect the response the same way `verify_pipeline.py` does:

```
POST /startups
POST /founders
POST /founders/{id}/research
GET  /founders/{id}/profile   <- check the "evidence" and "signals" keys
```
