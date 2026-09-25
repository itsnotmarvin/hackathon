# Scalability notes

## Method

- `current_headcount`: employees listed on the company's LinkedIn page where it was reachable (Vulcan Elements, HomeVision, Handspring Health, SunRay Scientific, Adrich). Otherwise, the most recent third-party figure (Tracxn/PitchBook/YC). Checked September 2026.
- `growth_rate`: **average employees added per year since founding** = headcount / (2026 - founding_year). This is a crude proxy because we don't have historical LinkedIn snapshots. Where a historical data point exists, it's listed below.
- `scales_with_headcount`: `yes` = revenue capacity grows roughly in step with people (manufacturing, R&D, clinicians). `no` = software/marketplace leverage. `partial` = hardware + software mix.

## Data caveats

| Company | Caveat |
| --- | --- |
| Compyl | LinkedIn shows the 51-200 band; used the 57 figure from a third-party source. Other sources say 31-38. |
| Toothio | 88 (Tracxn, May 2026), but LinkedIn's band says 11-50. May count contracted staff. Earlier data point: 17 employees. |
| Workgrounds | No reliable count. Estimated at ~10 from founder LinkedIn ("10+ people"). **Watch out:** `linkedin.com/company/workgrounds` is a different, German office provider. The right company is workgrounds.com (Nikhil Sethi, hotel room blocks). |
| Kintra Fibers | 8 (PitchBook), 5 (ZoomInfo). No LinkedIn page found. |
| Regenosine | 2 (PitchBook); LinkedIn band 2-10. |
| Handspring Health | Sources disagree on founding year (2021 vs 2022); used 2022. |

## Historical points (real growth signals)

- **Upscale.ai**: "100+ technologists" at its stealth launch (Sept 2025) → ~190 (May 2026). Roughly doubled in about 8 months, which fits $500M+ raised.
- **Vulcan Elements**: ~30 (2025) → 84 on LinkedIn (2026). Plans a factory with ~1,000 jobs, so headcount will jump with manufacturing capacity.
- **Toothio**: 17 → 88 across its funding rounds ($14M total).

## Reading growth rates by type

- **Deep tech / materials (Vulcan, SunRay, Kintra):** confirmed from their sites that these scale like services. Headcount follows R&D and production capacity. High growth (Vulcan) means capacity is coming online and is a good sign. Low growth (SunRay at ~1/yr over 14 years, Kintra at ~1/yr) means they haven't crossed from lab/pilot into production scale yet.
- **Adrich (partial):** each smart label is physical hardware, but the value is in the data platform. Low headcount growth here points to slow adoption, not efficiency.
- **Handspring (yes):** employs its therapists, so headcount is essentially revenue capacity. 85 staff after a $19M Series B is consistent with a growing clinic.
- **Software/marketplaces (HomeVision, Compyl, Toothio, Ryse, Workgrounds):** they should grow revenue faster than headcount. Moderate headcount growth here (~10/yr at HomeVision and Compyl) is healthy, not weak.
- **Upscale.ai (partial):** chip/system design is R&D-headcount heavy up front, but revenue per unit is high once shipping.
- **Regenosine (no):** biotech progress depends on capital and clinical milestones, and trials are usually outsourced to CROs. Headcount says little.
