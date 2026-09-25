# Reputation & Ecosystem Interest — search pipeline

Updated: 2026-09-25. Status: implemented module backend and local web preview;
shared-application integration and public deployment remain pending.

## Objective and ownership

Discover New Jersey startups with attributable reputation and ecosystem-interest
signals. Return company cards explaining who is engaging with each company,
what the relationship or recognition is, and how well the evidence supports it.
The shared application combines this output with the other three modules.

The user explicitly corrected the scope to Reputation & Ecosystem Interest.
Earlier whole-product pipeline proposals are superseded by this document.
No user-persona selection is needed to perform this work.

## What belongs in this module

- Accelerator/incubator acceptance, membership, and graduation, kept distinct.
- University and research-institution connections with the exact relationship.
- Documented investor, advisor, director, and strategic-partner affiliations.
- Industry recognition, competitions, awards, and meaningful event participation.
- Independent coverage and community activity, with source quality and duplication checked.
- Public attention over time, only when comparable dated observations exist.
- Public-program selection as institutional recognition, without duplicating financial analysis.

A patent award may provide recognition evidence. A patent count alone is not a
reputation score. A logo, grant application, accelerator invitation, membership,
and endorsement are different facts. Do not substitute one for another.

Funding amounts/financial health, hiring growth, founder assessment, and business
performance belong with the other owners. Sector and NJ identity are shared
metadata needed to group our results. Read relevant public sources when useful,
but do not change another module's schema or claim its work is complete.

## Search workflow

1. Discover company names through NJ accelerator cohorts, incubators, university
   venture announcements, award lists, attributable investor networks, industry
   events, and community coverage. Search for signals, not only famous people.
2. Resolve the company domain and name. Verify NJ presence. Distinguish headquarters,
   operating activity, and only participating in an NJ program. A mixed NJ/NY cohort
   does not establish that all of its members are NJ companies.
3. Read the source pages and collect exact affiliation, recognition, coverage, or
   community claims. Prefer the institution's own confirmation of its relationship.
4. Preserve source URLs, literal quotes, source dates, event dates when known,
   observation dates, source relationships, and access provenance.
5. Group by the assessed sector. The current implementation uses five broad sector
   categories, one per company. Multi-sector tagging remains future work.
6. Judge specificity, source quality, recency, and breadth of distinct relationships
   or events. Keep confidence in a fact separate from its potential significance.
7. Resolve consequential gaps through internal targeted searches. If a company is
   unsuitable or evidence is insufficient, examine another candidate while within
   configured limits. These follow-ups happen inside the run, not as repeated
   questions asking the user to continue.
8. Return company cards and modest sector groupings, with citations and explicit
   unknowns. A run finishes with supported results or an explained shortfall.

## Output contract to agree with the shared app

Each record should contain company ID/name/domain, NJ connection type, sector
cluster/tags, signal type, named institution/person, exact relationship, source
and quote, event/report/observation dates, provenance, conflicts, evidence-strength
explanation, public-interest state, and limitations.

Example states: supported ecosystem affiliations; emerging ecosystem visibility;
limited evidence; unresolved NJ eligibility. These are descriptive findings, not
calibrated investment ratings or predictions of company success.

Public attention should be unknown if no comparable time series was collected.
Several institutional affiliations can be established even when broader market
attention is unmeasured. Few search results do not establish that a company is
undiscovered. Repeated press releases are not independent public interest.

Public, permissioned, sample, and simulated data must be distinguished. Only use
permissioned data the team is authorized to access. Keep simulated evidence out
of real-company validation and real-company signal counts.

## Control loop and completion

The coordinator tracks pending actions, source results, per-company coverage,
request/time/spending limits, and terminal state. A relationship mention is a
reason to keep researching the company, not a terminal result.

Complete: return the configured number of distinct candidate cards with supported
NJ eligibility, sector, actual reputation/ecosystem evidence, citations, and clear
limits. A card can report unknown public-attention trend without inventing it.

Partial: the bounded search reaches its limits or cannot resolve enough candidates.
Return qualified cards and the reason for the shortfall; do not pad the list,
silently loosen NJ requirements, or ask the user to supervise each source lookup.

Only a material ambiguity in an explicit requirement should need a user question.
Source failures are recorded; transient model failures use bounded retries.
Progress and fetched pages persist. Interrupted jobs are marked explicitly;
starting a new job can reuse pages, without automatically replaying model requests.

## Implemented code and earlier research evidence

`reputation/` contains the provider adapters, SQLite store, research coordinator,
schema/quote/identity checks, deterministic ranking and WSGI API. `web/` provides
the responsive preview. `tests/` covers failures and API workflows. Gemini 3.5
Flash-Lite receives fetched pages and a required JSON schema; the backend validates
the returned structure and exact evidence quotations before ranking.

Current ranking requires supported NJ operations/headquarters, at least two
external organizations, two source families, and an event or source report dated
within 730 days. A verified technology license, research collaboration or industry
partnership can elevate the result to stronger evidence. Unknown/proposed work
does not receive that depth credit. Program participation alone is lower-depth
evidence. HAX/SOSV and NJEDA/CSIT are grouped into source families. Public interest
is not measured. These are evidence rules, not calibrated success probabilities.

Limits: 14 searches, 24 fetch attempts, 9 model HTTP attempts including retries,
approximately 10 minutes; one internal follow-up per candidate. Reserve candidates
are assessed until the requested shortlist or a research/provider limit is reached.
Source failures and lower-confidence candidates remain visible.

Pipeline 1.1.0 retries a Gemini assessment up to five total attempts and search/
batch retrieval up to three total attempts, with backoff and the same global
budgets. Authentication, setup and unverified pricing stop immediately. Invalid
model records are retried but never published. Submission IDs persist in SQLite
so a client retry retrieves the original job instead of rerunning providers.
Verified findings remain in partial results if later attempts are exhausted.

The existing Python extractor reads saved pages and supplied person/company pairs.
It has no LLM call, network collector, controller, database, or site integration.
It remains useful as one narrow relationship-evidence tool.

The new live, assistant-curated pilot is saved under
`research/nj-momentum-2026-09-25/`. The directory name reflects its initial broader
search; the final report is scoped to reputation and ecosystem interest. Initial
broader search captures are retained for audit and do not establish completed
funding, hiring, or commercial assessments.

Read `REPORT.md`, `results.json`, `sources.json`, and `search-protocol.json` in that
folder. The search protocol is a query plan, not executable application code.
The pilot uses real public evidence; no simulated or permissioned data was added.

## Quality and production implications

Evaluate fresh cases for wrong-company matches, false affiliation/endorsement,
role confusion, stale relationships presented as current, duplicate corroboration,
incorrect NJ eligibility, and unsupported attention trends. Measure useful
candidates returned as well as unresolved cases and cost per completed run.

The backend should use bounded search/fetch adapters, a saved evidence store,
validated extraction, and a coordinator. An LLM may interpret varied source
language and draft explanations; code should validate quotes, schema, duplicates,
limits, and provenance. Chat tool access is not an already deployed integration.

The shared frontend consumes these records as a Reputation & Ecosystem Interest
section. Application deployment, shared interfaces, and all-company ranking remain
separate implementation work coordinated with the other owners.
