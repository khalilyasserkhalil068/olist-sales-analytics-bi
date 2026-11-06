# Dataset attribution and release boundaries

## Source

**Dataset:** Brazilian E-Commerce Public Dataset by Olist. **Publisher:** Olist and the collaborators listed on its publisher page. **Source:** [Kaggle dataset page](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce).

The preserved local snapshot has nine raw CSVs. [Source manifest](../data/DATASET_MANIFEST.json) records filenames, sizes and SHA-256 hashes. Findings refer to that snapshot and should not be presented as current Olist performance.

## Recorded license evidence

The 2 November 2026 publisher-page metadata review recorded **CC BY-NC-SA 4.0**. The exact license notice shipped with the downloaded package was not recovered. This is a description of retained metadata evidence, rather than a new verification of current terms. [License review record](../reports/completion_20261101/dataset_license_review_20261102.json).

The [Creative Commons license summary](https://creativecommons.org/licenses/by-nc-sa/4.0/) links to the applicable terms. Confirm the snapshot's terms before a data-bearing release. The project has not assigned a license to the owner's original code.

## Transformations to disclose

The project trims outer whitespace, parses types, creates quality flags, removes exact duplicate geographic observations in a processed copy, creates an approximate representative ZIP lookup, loads warehouse facts/dimensions, calculates KPIs and produces aggregate charts/customer/cohort analysis. Missing milestones and transactional records remain subject to documented flags and eligibility rather than invented values.

Retain dataset name, publisher/source, applicable license reference and transformation description when distributing approved derived material. Methodology and observed limitations are documented in [data quality](data_quality.md) and [analysis methodology](analysis_methodology.md).

## Release selection

Raw/processed inputs, PBIX files and ABF caches contain data. They are excluded by `.gitignore`, together with environments, local settings, database files and backups. PBIP source can still contain machine-specific connection expressions. Aggregate charts, screenshots and PDFs also require an intentional release decision.

No public upload, Power BI Service publication, Git commit or push was performed during cleanup. Review the proposed release selection and local paths before sharing. External recovery snapshots contain the original full project and are for local recovery.

## Authorized GitHub edition

The owner authorized public portfolio publication on 6 November 2026. This edition includes source code, executed notebooks, aggregate outputs, screenshots, the native PDF and editable report/model definitions. It excludes raw/processed input CSVs, PBIX, ABF cache, credentials, environments and backups. Attribution and the recorded license uncertainty remain disclosed above.
