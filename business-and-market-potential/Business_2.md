# Form D data: column guide

The two CSVs in `data/` come from `form_d_nj.py`. The script downloads the SEC's quarterly Form D data sets (2021Q1 onward) and keeps only filings from companies based in New Jersey. Investment funds, real estate, banking and insurance filers, and limited partnerships are dropped.

A company files a **Form D** with the SEC when it raises a private round of money. That means this data only covers companies that raised money and filed. It says nothing about companies that were never funded.

| File | One row per | Sorted by |
|---|---|---|
| `nj_formd_offerings.csv` | offering (funding round) | company name, then first sale date |
| `nj_formd_companies.csv` | company | `total_raised`, highest first |

The two files join on `cik`.

## Where revenue comes from

`revenue_range` is the only revenue field. Form D asks for a revenue bracket, not an exact figure, and many companies pick "Decline to Disclose". The brackets are:

- No Revenues
- $1 - $1,000,000
- $1,000,001 - $5,000,000
- $5,000,001 - $25,000,000
- $25,000,001 - $100,000,000
- Over $100,000,000
- Decline to Disclose
- Not Applicable

Treat it as a rough size signal, not a real revenue number. For growth or traction, the funding columns (`total_raised`, `raised_last_24mo`, `num_offerings`) are usually more useful.

## `nj_formd_offerings.csv`

When a company amends a filing (Form D/A), only the most recent version is kept. The amounts in that row are therefore the latest cumulative totals for that round. `first_sale_date` is the exception: it keeps the earliest date reported in any version.

| Column | Meaning |
|---|---|
| `company` | Company's legal name as filed. |
| `cik` | SEC Central Index Key: the company's permanent SEC ID, with leading zeros removed. Read it as a string. |
| `city` | City of the company's business address. |
| `zip` | 5-digit ZIP code. Read it as a string so leading zeros (`07030`) are kept. |
| `entity_type` | Legal form, e.g. Corporation or Limited Liability Company. |
| `incorporated` | Year of incorporation when the company gave one. Otherwise a bucket: `overFiveYears`, `withinFiveYears` or `yetToBeFormed`. |
| `young_company` | `True` if incorporated within 5 years of the filing, or not yet formed. |
| `industry` | Industry group the company picked on the form, e.g. Other Technology, Biotechnology or Health Care. |
| `revenue_range` | Self-reported revenue bracket (see above). |
| `first_sale_date` | Date the first money in this round was sold (the round's start date). |
| `filing_date` | Date the SEC received the filing. |
| `is_amendment` | `True` if the kept row is an amendment (D/A) rather than the original filing. |
| `total_offering` | How much the company planned to raise in this round, in USD. Blank means "Indefinite". |
| `amount_sold` | How much has actually been raised in this round so far, in USD. |
| `num_investors` | Number of investors who have already invested in this round. |
| `equity` | `True` if the round sells equity (stock or ownership units). |
| `debt` | `True` if the round sells debt (e.g. notes). |
| `exemptions` | SEC exemptions the round relies on. Most common: `06b` = Rule 506(b), private with no public advertising; `06c` = Rule 506(c), which allows general solicitation but only accredited investors; `04` = Rule 504; `4a5` = Section 4(a)(5). |
| `related_people` | Executives, directors and promoters listed on the filing, each as `Name (Role/Role)`, separated by `; `. |
| `file_num` | SEC file number. It is shared by an original filing and its amendments, and is used to identify one round. |
| `accession` | Unique ID of the specific filing that was kept. |
| `filing_url` | Link to that filing on EDGAR. |

## `nj_formd_companies.csv`

Each row rolls up all of a company's offerings. The descriptive fields (`company`, `city`, `zip`, `industry`, `incorporated`, `young_company`, `revenue_range`, `related_people`) come from the company's **most recent** offering. A round's date is its `first_sale_date`, or its `filing_date` when there's no sale date.

| Column | Meaning |
|---|---|
| `company`, `cik`, `city`, `zip`, `industry`, `incorporated`, `young_company`, `revenue_range`, `related_people` | Same as in the offerings file, taken from the latest round. |
| `num_offerings` | Number of distinct rounds filed since 2021Q1. |
| `total_raised` | Sum of `amount_sold` across all rounds, in USD. |
| `largest_round` | Largest single round's `amount_sold`, in USD. |
| `raised_last_24mo` | Amount raised in rounds that started in the 24 months before the script was run. |
| `total_investors` | Sum of `num_investors` across rounds. The same investor can be counted more than once if they invested in several rounds. |
| `first_raise` | Date of the earliest round in the data. |
| `last_raise` | Date of the most recent round. |
| `months_since_last_raise` | Months from `last_raise` to the day the script was run. |
| `avg_months_between_raises` | Average gap between consecutive rounds, in months. Blank if the company has only one round. |
| `edgar_url` | Link to the company's list of Form D filings on EDGAR. |

## Things to watch for

- **Coverage starts in 2021.** Rounds before 2021Q1 aren't included, so `total_raised` and `first_raise` only cover 2021 onward.
- **Some values depend on the run date.** `months_since_last_raise` and `raised_last_24mo` are based on the day `form_d_nj.py` was last run. Re-run the script to refresh them.
- **Blank amounts count as zero.** A round with no reported `amount_sold` adds 0 to the company totals.
- **Location is where the company files from.** "New Jersey" means the business address on the Form D is in NJ.
