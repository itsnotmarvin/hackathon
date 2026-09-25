# Does reputation research return worthwhile startup leads?

September 25, 2026. **Provisional grade: B.** The five-company review produced
three priorities for a closer look, one earlier lead, and one company needing a
location review. These are judgments about reputation and ecosystem evidence,
not predictions of business success.

The assistant performed this test using live search and source retrieval, plus
the earlier saved sources. The production pipeline and site were not run or
changed. No separate LLM extraction endpoint or existing regex extractor produced
these assessments.

## What we checked

1. Specific outside commitment: a license, actual research collaboration,
   development partnership, or documented accelerator participation.
2. Recognition: named institutions selecting or recognizing the company, with
   the exact nature of the selection preserved.
3. Breadth: different organizations and events, without counting syndicated
   announcements or affiliated organizations repeatedly.
4. Recency: dated activity within the last 24 months, with older relationships
   identified as historical.
5. Identity and geography: the right company and a supported NJ presence.

Public-interest growth requires comparable observations over time. It remains
unmeasured for all five. A website's logos, a directory entry, or attendance at an
event does not establish a partnership or endorsement.

## Sample and outcome

The sample was frozen before new searches: all three earlier picks, plus Canyon
Magnet Energy and CarbonDots, the first two companies in the saved NJEDA awardee
list. Weak results were not replaced. The sample favors clean tech and public
program awardees and is not representative of New Jersey startups.

| Company | Supported evidence | Review verdict |
| --- | --- | --- |
| Queens Carbon | Rutgers technology license; Buzzi development-partner confirmation; technology recognition; recent NJ program selection | **Priority.** Specific university and industrial commitments make this a worthwhile reputation lead. |
| Canyon Magnet Energy | HAX profile and 2026 showcase; federal research-program award records; industry conference presentation and interview; Newark address | **Priority.** Several identifiable organizations and forms of activity. |
| Cecilia / Cecilia Energy / Cecilia Materials | NETL describes actual joint research; NJEDA lists newer program selection; federal portfolio supports the Materials/Energy name association and NASA research awards | **Priority.** Substantive research connections, with historical/current status clearly separated. |
| CarbonDots | Cleantech Open confirms 2025 accelerator participation; NJEDA confirms 2026 selection and NJ location | **Earlier lead.** Credible program participation, but thinner evidence of substantial outside collaboration. |
| Chorah Labs | NJIT company projects and founder involvement; NJ AI Hub acceptance; another directory lists New York headquarters | **Location review.** NJ ecosystem activity is supported, but do not present NJ headquarters as established. |

Under the initial protocol, four pass the basic evidence screen and one remains
on the watchlist. Comparative review prioritizes three of the four passing
companies. **That exposes a weakness in the screen:** two organizations and recent
activity can qualify a company without establishing the depth of its relationships.
The comparative priority labels are post-test reviewer judgments, not a previously
calibrated score or a new claim of predictive accuracy.

## Findings that changed the assessment

- **Queens Carbon:** Buzzi's site explicitly says its article republishes the
  Queens Carbon press release. It confirms Buzzi's participation but adds no
  independent news event. Plans for a pilot are not proof of completed deployment.
- **Canyon Magnet Energy:** the newer SOSV showcase identifies Newark headquarters,
  alongside a federal Newark address and reporting on NJ operations. An older NY
  search listing should not automatically exclude it. HAX and SOSV are one source
  family. The federal Tulane collaboration abstract describes proposed work,
  not completed results. The industry interview establishes an appearance and
  coverage, not independent validation of technical claims.
- **Cecilia:** the federal company portfolio names Cecilia Materials and retains
  a NASA project description naming Cecilia Energy. This improves the alias
  connection and establishes research-program participation. It does not establish
  NASA endorsement, actual mission deployment, or current NETL agreement status.
  Formal legal continuity was not separately audited.
- **CarbonDots:** Rutgers lists it under “Industry in Attendance.” That establishes
  an event connection, not a university license or research partnership. The CSIT
  profile describes Rutgers-origin technology; a formal relationship still needs
  direct confirmation. The accelerator's alumni page separately confirms 2025
  participation, but its NJEDA news item repeats the original award event.
- **Chorah:** Deep Tech Week lists New York headquarters. This is a directory,
  so treat it as a conflict to resolve, not definitive proof of ineligibility.
  Its “0 UPCOMING · 0 PAST” event record also provides no evidence of conference
  activity or growing public interest.

## Grade and limits

**B for finding leads:** the workflow produced attributable reasons to investigate
three companies and exposed weaker evidence and a location conflict in the others.
It still relies on assistant judgment to prioritize relationship depth.

The process has not established whether it detects companies before others,
predicts success, measures rising attention, or works reliably without supervision.
The same assistant researched and reviewed the findings. There is no blinded
review, statewide recall measure, financial evaluation, or independent outcome
benchmark. One explicit adverse-news search covered Queens Carbon; comprehensive
reputation-risk searches remain untested. No allegation surfaced in that query,
which is not a clean bill of health.

The test made 16 provider attempts: nine successful searches, three successful
batch fetches, and four HTTP 504 failures. Shorter company-name searches recovered
useful results after restrictive queries or failures. All 12 successful responses
reported zero provider cost; failures did not return billing fields. Assistant
usage and hosting are outside these figures. Retrieval errors must remain separate
from “no evidence found.”

## Evidence and practical change

Saved artifacts include 13 newly fetched pages and 11 earlier sources, with 20
literal excerpts supporting the decisions. Snapshot hashes and quote offsets
passed validation. These checks establish artifact integrity, not external truth.

The next version of the research rules should retain a basic eligibility screen
and prioritize **substantial documented relationships** over program listings or
event attendance. It should display location conflicts, historical relationships,
and unmeasured attention explicitly. No production code was added in this test.

- [Frozen test protocol](PROTOCOL.md)
- [Structured assessments and call log](results.json)
- [Source index and snapshot hashes](sources.json)

Selected sources:

- [Rutgers: Queens Carbon license and NJ activity](https://research.rutgers.edu/news/queens-carbon-making-impact-concrete-industry-new-jersey-economy)
- [Buzzi: Queens Carbon development relationship](https://www.buzziunicemusa.com/w/buzzi-unicem-usa-partners-with-startup-to-pilot-zero-co2-scms-technology)
- [SOSV: 2026 HAX showcase, including Canyon Magnet](https://sosv.com/hax-2026-ny-deep-tech-week-investor-showcase/)
- [Federal Canyon Magnet portfolio](https://www.sbir.gov/portfolio/2651251)
- [Data Center Frontier: Canyon Magnet interview and event appearance](https://www.datacenterfrontier.com/featured/podcast/55327835/canyon-magnet-energy-the-superconducting-future-of-powering-ai-data-centers)
- [NETL: actual Cecilia research collaboration](https://netl.doe.gov/node/14075)
- [Federal Cecilia Materials portfolio](https://www.sbir.gov/portfolio/2246983)
- [Cleantech Open: alumni participation, including CarbonDots](https://www.cleantechopen.org/en/custom/blog/view/148754)
- [NJEDA: January 2026 company selection and locations](https://www.njeda.gov/csit-awards-nearly-1-3m-to-17-nj-startups-through-round-4-clean-tech-rd-seed-grant-program/)
- [NJIT: Chorah university activity](https://news.njit.edu/njits-first-global-entrepreneur-residence-turning-founder-pathway-student-opportunity)
- [Deep Tech Week: Chorah location conflict](https://www.deep-tech-week.com/organizations/chorah-labs)
