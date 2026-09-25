# Public investor relationship benchmark — 25 September 2026

The pilot recovered **8 of 10 reference relationships** from manually selected primary or affiliated pages within the first five results of five investor-name searches. Seven retained all role/interval details required by the reference labels. Those are small-sample retrieval results, not predictive accuracy and not a comparison of search engines.

Public sources can support an evidence-backed relationship graph. They do not yet support a reputation score, a claim of early discovery, or a claim that these people reliably pick winners.

## What was done

1. Read official investor biographies, an SEC proxy statement, a company biography, a partner-firm announcement, and a dated interview to establish ten reference relationships.
2. Freeze the case list and five queries in `frozen-protocol.json` before the recovery pass. Queries contain the person's name plus `investments board portfolio`; they contain no company names or answer URLs.
3. Run each query once on TinyFish web search, page zero, through Monid's zero-price guard. Preserve every returned candidate in `search-results.json`.
4. Within the top five candidates, inspect selected primary/affiliated pages. Reuse exact page snapshots already read in this session rather than refetching them. Also fetch the new institutional/firm results. Do not treat snippets as evidence. Social profiles and commercial aggregators were not used as confirming evidence.
5. Compare full text with each reference label. Keep misses and missing intervals visible. Manually adjudicate four controls and record a fifth discovery-only identity trap as unscored.

The same researcher established the labels and assessed recovery, and the sample was selected from accessible sources. This is an **unblinded feasibility pilot**, not a held-out test. Top-five filtering plus selective source inspection is the evaluated procedure; the result is not exhaustive recall of all information on those five pages or on the internet. Several labels share a person, biography, and query. Ten cases are not ten independent trials.

## The ten reference cases

| ID | Person → company | Supported relationship | Recovery result | Important limit |
| --- | --- | --- | --- | --- |
| P01 | Dan Borok → BigCommerce | Led or co-led investment | Recovered | Seed stage and investment date unknown |
| P02 | Dan Borok → Janrain | Led or co-led investment | Recovered | Acquisition claim does not establish fund returns |
| P03 | Dan Borok → Yodle | Led or co-led investment | Recovered | Contemporary round attribution not established |
| P04 | Jim Gunton → InstaMed | Served as director | Recovered | Do not label the seat current |
| P05 | Jim Gunton → CytoSorbents | Served as director | Recovered | Start and end dates unknown |
| P06 | Stephen Socolof → SunRay Scientific | Director, including evidence as of 2023 | Recovered | Appointment date unknown |
| P07 | Stephen Socolof → Everspin | Director, 2008–2021 | Relationship recovered; interval missed | SEC supplied dates absent from the selected search pages |
| P08 | Stephen Socolof → Energy Focus | Director since May 2019, as of 2023 | Missed | Public-company boundary case, not an early startup investment |
| P09 | Vaughn Crowe → Toothio | Board member | Recovered | Repeated biography text is not independent corroboration |
| P10 | Jeremy Sohn → TriNetX | Founder with investment responsibility at MPM | Missed | Relevant rank-four page returned 404; usable reference evidence ranked sixth |

Five people cover commerce, identity software, marketing, healthcare payments, medical devices, materials, semiconductors, lighting, dental staffing, and clinical research software. Affiliations span NVP Capital, Millennium Technology Value Partners, Tech Council Ventures/New Venture Partners, Boston Millennia Partners, and MPM. These are professional relationships connected to the NJ research starting point, **not ten verified NJ-based startups**. Company geography still needs its own evidence.

All ten relationships have literal supporting excerpts. Evidence quality varies: some are retrospective, affiliated biographies; the SEC supplies stronger dated role evidence. No case is labeled a verified seed investment. Outcomes quoted in biographies remain attributed claims, not audited financial results.

## Measured results

| Measure | Result | Interpretation |
| --- | --- | --- |
| Full-text relationship recovery | 8/10 | Selected primary/affiliated results within top five |
| Reference role/interval detail recovery | 7/10 | Everspin's relationship was found but its 2008–2021 dates were missing |
| Reference cases with an explicit relationship start | 2/10 | Everspin: year precision; Energy Focus: month precision |
| First-ever public disclosure dates established | 0/10 | A dated page is not proof it was the first disclosure |
| Verified early-stage investment cases | 0/10 | No complete round/timing evidence yet |
| Manually adjudicated controls | 4 | Expected abstentions/conflict handling; no model was evaluated |
| Identity trap | 1 unscored | Search returned a same-name lawyer; page not fetched |
| Predictive accuracy, automated extraction precision, detection latency | Not measured | No claims are made about these |

No percentage here should be generalized to the NJ ecosystem. We have no full universe denominator and no representative sampling frame.

## Failures worth designing around

**Exact words can hide known relationships.** The preliminary query `"Jim Gunton" "joins" "board"` returned no TinyFish results. `Jim Gunton investments board portfolio` recovered his biography and another affiliated biography. Save query families and search aliases such as Steve/Stephen; do not interpret one empty result as absence of involvement.

**The cutoff matters.** Jeremy Sohn's usable Boston Millennia Partners announcement was at rank six. A Stony Brook result at rank four had a useful snippet but fetched as 404. A later system should expand the candidate pool after a failed fetch and log that expansion. We did not silently add the rank-six evidence to this run's score.

**Bios omit history that filings retain.** Socolof's current biographies support his Everspin directorship but omit its dates. Energy Focus's 2023 proxy specifies Everspin service from 2008 to 2021 and his own Energy Focus board appointment in May 2019. Filing retrieval deserves a separate path when time or role precision matters.

**“On the board” is not precise enough.** Tech Council Ventures says Socolof is on the boards of Adrich and Kintra. Energy Focus's SEC filing and TranscendAP's biography specify observer roles. We cannot tell from these sources whether wording is loose or the role changed. Store both claims and their dates; flag the conflict rather than manufacture a single current title.

**Metadata can manufacture momentum.** NVP's team page has provider publication metadata of 13 October 2023, but it does not say Crowe joined Toothio that day. The Boston Millennia announcement is dated 15 October 2015 in the body while provider metadata says 14 December 2015. Keep event date, source date, first observed date, and first public date separate.

**Multiple domains may copy one biography.** Simon Quick and NVP repeat essentially the same Crowe board list. They are two accessible pages, but should be treated as one evidence family for that claim.

**Search snippets and fetched pages can disagree.** Google's EpiBone result described Gunton as “Lead Investor, Board Observer.” The fetched page places his biography under Advisors without preserving that precise title. EpiBone was excluded from the ten reference cases. A snippet alone should not upgrade a role.

## Controls

| Claim | Manual result | Required collector behavior |
| --- | --- | --- |
| Jennifer Solomon led BigCommerce's investment | Unsupported attribution | Keep Dan Borok's deal list scoped to his own biography |
| Socolof is definitively a voting director of Kintra | Conflicting / insufficient | Preserve dated observer evidence and flag the conflicting board wording |
| Crowe joined Toothio on 13 October 2023 | Unsupported date | Leave appointment date null |
| Borok was a seed investor in BigCommerce | Unsupported stage | Leave stage unknown |

These controls mean “the supplied evidence does not establish this claim,” not “the relationship cannot exist anywhere.” They are manually reviewed fixtures for a future extractor, not a measured model false-positive rate.

## Tools and source coverage

- **TinyFish through Monid:** worked for search and full-page fetch. Each guarded call was checked for zero price/cost. One enrichment call produced empty output and its batch stopped; no result was inferred. A successful batch fetch also contained an explicit per-page 404, which was retained as a failure.
- **Google in Chrome:** used for one company-specific Gunton/InstaMed spot check, which surfaced EpiBone and a Boston Millennia source. Different queries and purposes mean this is not a matched Google/TinyFish comparison.
- **Firecrawl:** HTTP 402 in the preceding probe; unavailable for this benchmark. No attempt to claim equivalent coverage or bypass quota.
- **Coverage not tested:** inaccessible social engagement, private communities, historical archives, systematic company-side announcements, patents/funding APIs, and the full NJ startup population.

Monid is the access layer for TinyFish, not another independent search engine.

## Sources used

The source manifest records retrieval timestamps, URLs, run IDs, and hashes. Local snapshots make the audit replayable even if live pages change.

| ID | Source | Use |
| --- | --- | --- |
| S01 | [Jim Gunton, Tech Council Ventures](https://techcouncilventures.com/team-members/jim-gunton/) | Historical boards |
| S02 | [Steve Socolof, Tech Council Ventures](https://techcouncilventures.com/team-members/steve-socolof/) | Relationships and role conflict |
| S03 | [NVP Capital team](https://nvpcap.com/nvp-capital-team/) | Person-specific deal attribution; Crowe boards |
| S04 | [Stephen Socolof, TranscendAP](https://transcendap.com/stephen-socolof/) | Director/observer distinction and prior roles |
| S05 | [Energy Focus 2023 proxy, SEC](https://www.sec.gov/Archives/edgar/data/924168/000092416823000048/a2023efoiproxystatementdef.htm) | Explicit historical intervals and as-of evidence |
| S06 | [EpiBone team](https://www.epibone.com/team) | Snippet/extraction mismatch; excluded from labels |
| S07 | [FinSMEs interview, 24 May 2016](https://www.finsmes.com/2016/05/newark-venture-partners-interview-with-managing-partner-tom-wisniewski.html) | Earlier attribution of Borok investments |
| S08 | [Boston Millennia affiliate announcement](https://www.bostonmillenniapartners.com/news/boston-millennia-partners-expands-venture-affiliate-program/) | Sohn/TriNetX reference; body/metadata date mismatch |
| S09 | [Vaughn Crowe, Simon Quick](https://simonquickadvisors.com/advisory-board/vaughn-crowe/) | Repeated biography evidence family |
| S10 | [Jim Gunton, Boston Millennia](https://www.bostonmillenniapartners.com/venture-affiliate/jim-gunton/) | Historical director corroboration |
| S11 | [Jeremy Sohn, BenevolentAI](https://www.benevolent.com/about-us/our-leadership/jeremy-sohn/) | Retrieved, but does not support TriNetX label |

## Decision for the collector

Proceed with a narrow **relationship-evidence collector**: discover candidates, fetch original pages, resolve identities, extract exact roles with quotes, retain dates and uncertainty, and group repeated evidence. Keep identity aliases, director/observer distinctions, and source snapshots in the first version. Give incomplete or conflicting records a review state.

Do not introduce a “successful investor” score yet. Before evaluating early momentum, add dated company-side investment/appointment announcements, a failure/non-success comparison cohort, and a historical or prospective observation window. Begin prospective snapshots to measure detection delay; a current biography cannot reconstruct when its contents first became public.

The next bounded engineering task is an extractor over these saved snapshots, evaluated against the reference labels and controls. Split any later held-out evaluation by person/source family, not random rows, so shared biographies do not leak answers across train/test sets. Add a separate, broader company sample before generalizing to startup discovery.
