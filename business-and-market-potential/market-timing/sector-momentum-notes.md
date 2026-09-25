# Sector momentum notes

## Sector grouping

| Sector | Companies |
| --- | --- |
| AI infrastructure | Upscale.ai |
| Advanced materials & manufacturing | Vulcan Elements, SunRay Scientific, Kintra Fibers |
| Enterprise software & security | Compyl, Workgrounds, Adrich |
| Proptech | HomeVision, Ryse Marketplace |
| Digital health | Toothio, Handspring Health |
| Biotech | Regenosine |

## sector-data.csv fields

- `funding_total` is **US$ billions of venture funding for the sector** (a proxy for the sector, not these companies):
  - AI infrastructure: all AI venture funding, global ([Crunchbase](https://www.venturecapitaljournal.com/funding-for-ai-dominated-in-vc-in-2025-crunchbase/)). Broader than networking alone. For comparison, AI accelerator startups alone raised $13.0B in 2025.
  - Advanced materials & manufacturing: climate tech venture + growth funding ([Sightline Climate](https://www.sightlineclimate.com/research/40-5bn-and-8-uptick-as-power-demand-drives-25-investment)). A proxy: it fits Kintra and partly Vulcan, but not SunRay's electronics materials.
  - Enterprise software & security: cybersecurity funding ([Crunchbase](https://news.crunchbase.com/venture/cybersecurity-startup-investment-up-ye-2025/)). 2024 is back-calculated from the reported +26%. Fits Compyl best.
  - Proptech: global proptech funding ([CRETI](https://creti.org/insights/proptech-venture-capital-in-2025-end-of-year-report)). 2024 is back-calculated from the reported +68%.
  - Digital health: US digital health funding ([Rock Health 2024](https://rockhealth.com/rock-weekly/2024-year-end-market-overview-10-1b-raised-across-497-deals/), [2025](https://rockhealth.com/insights/2025-year-end-digital-health-funding-overview-a-tale-of-two-markets/), [H1 2026](https://rockhealth.com/insights/h1-2026-funding-and-market-overview-durable-roots-shifting-routes/)).
  - Biotech: global biotech venture funding (2025 ~$38B, 2024 $29.7B, per [IntuitionLabs](https://intuitionlabs.ai/articles/ai-biotech-funding-trends) and others; sources vary).
- `patent_filings` and `job_postings` are **still empty**. Filling them needs a patent database query (e.g. USPTO PatentsView by CPC class) and a job-posting source (LinkedIn/Indeed). I left them blank rather than guess.

## Momentum read (2024 → 2025)

| Sector | Funding change | Read |
| --- | --- | --- |
| AI infrastructure | +86% | Strongest tailwind. Hyperscaler capex topped $400B in 2025, and networking is now its own investment category (e.g. Nexthop AI $500M). Upscale is riding the peak. The risk is timing late in the cycle. |
| Proptech | +68% | Recovering after the 2022-23 slump. AI-centric proptech is growing ~2x faster than non-AI, which helps HomeVision. |
| Biotech | +28% | Recovery, but concentrated in fewer, bigger rounds. Hard for a 2-person preclinical company like Regenosine. |
| Enterprise software & security | +26% | Highest in 3 years. Series A/B security funding is up 63%, which fits Compyl's 2025 Series A. |
| Digital health | +41% | 2025 had the highest quarter since 2022, and H1 2026 is up again. Mental health has been the top-funded clinical area for 7 straight years, which directly favors Handspring. |
| Advanced materials & manufacturing | +8% | Flat overall. Deal counts fell 18%, and Series C is the "new valley of death." Critical minerals/rare earths are the exception, thanks to government money (DOE ~$1B programs, DoD deals) that Vulcan is capturing. Sustainable textiles (Kintra) are weaker. |

## Investor signals (soft signal, not hard numbers)

- **NVP Capital (Dan Borok): Vulcan, HomeVision, Compyl, Upscale.ai.** Spread across AI infrastructure, AI-enabled vertical SaaS, and onshoring/defense manufacturing. Common thread: AI + US industrial resilience, both current momentum themes.
- **NVP Capital / Simon Quick (Vaughn Crowe): Toothio, Handspring, Ryse, Workgrounds.** Two of four are healthcare workforce/access (staffing shortages, youth mental health). The other two are marketplaces/agents that turn a manual, fragmented process into a transaction. That suggests a thesis around **labor-constrained services + AI automation**.
- **Transcend / Tech Council Ventures (Stephen Socolof): SunRay, Kintra, Adrich, Regenosine.** All are NJ/NY-area lab-to-market deep tech (materials, IoT hardware, therapeutics), often university spinouts (Regenosine from NYU). This looks like a regional deep-tech mandate more than a bet on one hot sector. It also means these four sit in the slowest-momentum, most capital-intensive sectors of the set.
