# Shared product contract

The unified app lives in `unified/`, reuses the four responsibility folders, and runs on FastAPI. The product name is **Garden State**, with the descriptor **Startup intelligence**. It helps users discover, investigate, compare, and shortlist NJ companies using traceable evidence. Evidence coverage is not a prediction of success or an investment score.

## API

- `GET /api/catalog` → `{companies: Company[], sectors: string[], stats: {companies, nj_supported, with_reputation, team_reviewed, sources}, snapshot_date: string, notices: string[], sector_view: SectorView}`. All company records can be included; the browser paginates the directory.
- `GET /api/companies/{id}` → one Company, or 404.
- `GET /api/shortlist` → `{ids: string[], notes: {[company_id]: string}}`.
- `PUT /api/shortlist/{id}` with `{saved: boolean, note?: string}` → current shortlist payload. Notes and membership persist locally on the server.
- `GET /api/research/status` → `{live_available: boolean, gemini_configured: boolean, search_configured: boolean, model: string, message: string, sectors: string[]}`.
- `POST /api/research/jobs` with `{count: 1..5, sector: string, mode: "live" | "sample", request_id: string}` → existing reputation job payload. Sample means saved public research, not synthetic company data. Do not silently substitute sample for live.
- `GET /api/research/jobs` → `{jobs: object[]}`.
- `GET /api/research/jobs/{id}` → existing reputation job payload with `id`, `status`, `stage`, `cards`, `review_cards`, `warnings`, `events`, `metrics`, `error_code` where present. Terminal states are completed, partial, failed, interrupted. Refresh catalog after a terminal job.
- `GET /api/integrations` → safe module setup/status information, never credentials.

## Company

```
{
  id, name, description, sector, location,
  nj_status: "supported" | "unverified",
  record_type: "research" | "filing" | "lead",
  updated_at, source_count, coverage_count,
  tags: string[], why_surfaced: string,
  pillars: {
    founders: Pillar, business: Pillar,
    funding: Pillar, reputation: Pillar
  },
  people: [{name, role, source_url}],
  evidence: [{id, pillar, title, url, quote, published_at, observed_at, source_type}],
  limitations: string[]
}
Pillar = {
  status: "available" | "partial" | "missing",
  summary: string,
  metrics: [{label: string, value: string | number, detail?: string}],
  findings: string[], limitations: string[]
}
```

Company also carries `cluster` (sector cluster key), `region` (NJ ZIP region key or null) and `signal_score: {total 0–100, tier, tier_label, signals: string[], signal_count, components: [{key, label, points, max, detected, detail}], version}`. Components and weights: capital raised 20, recent raise 20, repeat raises 10, investor breadth 10, hiring 15, accelerator/program 10, IP & research partnerships 10, public grants 5. Undetected signals earn 0 and stay labeled; nothing is imputed. Implementation: `unified/signals.py`.

`SectorView = {clusters: [{key, label, rank, ranked, companies, elevated_companies, rounds_by_year, amount_by_year, rounds_recent, rounds_prior, momentum_pct, top, score: {total, components}}], regions: [{key, label, zip3, grid, companies, by_cluster}], years, partial_year, window_end, method: string[]}`. Sector score = signal depth 50 + funding momentum 30 + breadth 20. Likely non-startup records are excluded from sector and region totals.

`source_count` counts unique external URLs, `coverage_count` counts pillars with at least partial data. Preserve role distinctions: CEOs, founders, advisors, SEC related people are not interchangeable. Company IDs must be deterministic and survive catalog reloads. Match CIK/domain/explicit aliases conservatively; do not merge merely similar names. Unsupported NJ status stays unverified. Form D issuer location does not prove current startup status; fundraising is not revenue, cash runway, profitability, or company quality. Headcount divided by years since founding is not observed hiring growth. Analyst scores are labeled judgments. Source publication and observation dates remain separate.

## Experience

Responsive light interface: warm off-white background, dark forest-green navigation, restrained lime accent, strong typography, generous whitespace. No stock imagery is needed. Directory search, sector and NJ-evidence filters, sort, company profile with four pillars and sources, persistent shortlist and notes, comparison for up to three companies, JSON/CSV evidence export, and live research with honest progress/failure/partial states. Keep implementation details out of the main product flow. A concise data/methodology view explains provenance and limitations.
