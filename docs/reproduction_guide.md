# Reproduction and operations guide

## Choose the operation

| Goal | Required components | Writes |
|---|---|---|
| View final report | Power BI Desktop and final PBIX | No database change |
| Check project assets | Existing Python environment and local files | Optional validation JSON |
| Run Python tests | Python dependencies and raw/processed data | Temporary test fixtures; reports only if enabled |
| Regenerate customer/cohort analysis | Processed inputs, Python and Jupyter kernel | Canonical notebooks and aggregate outputs |
| Validate existing SQL warehouse | SQL access, ODBC driver and loaded `OlistSalesDW` | Local evidence; no ETL or committed database change |
| Run Desktop DAX checks | Correct open Desktop model and SSMS client libraries | Timestamped evidence |
| Build/reload warehouse | Authorized SQL instance and guarded ETL | Database schema/snapshot and audit metadata |

Run commands from the project root in Windows PowerShell. Keep a working copy for regeneration; do not mix report viewing with refresh or warehouse loading.

## Python environment

The recorded environment uses Python 3.13 on Windows. A working local `.venv` is retained and ignored by Git. For a fresh environment:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m ipykernel install --user --name ecommerce-sales-bi --display-name 'E-Commerce Sales BI (.venv)'
```

Requirements are the captured environment snapshot. Installation on another platform has not been demonstrated. SQL access additionally needs an installed compatible Microsoft ODBC driver. Desktop validation utilities use SSMS 20's .NET Framework TOM/ADOMD assemblies at the paths recorded in those scripts.

## Obtain and verify inputs

Download the source dataset from the [Olist publisher page](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce), observing its applicable terms. Place the nine original filenames under `data/raw/`. `data/DATASET_MANIFEST.json` records the expected raw hashes; a different dataset version can change results.

Run notebooks in numerical order when rebuilding preparation: `01_data_understanding.ipynb`, then `02_data_cleaning.ipynb`. Cleaning creates nine cleaned datasets plus the ZIP lookup. Its processed contract is `src/data_processing/warehouse_contract.json`. Preserve IDs, ZIP prefixes and sequence keys as strings and financial values as exact cents/decimal.

Notebooks regenerate reports. Their embedded stage summaries are historical execution context; the maintained cross-stage documentation is under `docs/`.

## Inspect or execute notebooks

```powershell
.\.venv\Scripts\python.exe -m jupyter notebook
```

Select the **E-Commerce Sales BI (.venv)** kernel. The five canonical notebooks are:

1. `01_data_understanding.ipynb` — source tables, quality and relationships.
2. `02_data_cleaning.ipynb` — typed processed inputs and quality flags.
3. `03_exploratory_analysis.ipynb` — sales, customers, payments, delivery and reviews.
4. `04_customer_analysis.ipynb` — observed identity, revenue distribution and RFM.
5. `05_cohort_analysis.ipynb` — monthly cohorts, masks and pooled retention.

To rebuild and execute only the last two from processed inputs:

```powershell
.\.venv\Scripts\python.exe -B scripts/complete_customer_analytics.py
```

This command replaces those two canonical notebooks and their aggregate outputs. It does not reload SQL or alter raw/processed inputs. Execution evidence records source fingerprints. Preserve valuable manual notebook edits before regeneration.

## Source-checkout and local validation

For a GitHub checkout without the excluded input CSVs, PBIX or cache, run `python scripts/validate_project.py --source-only`. It checks only the published asset fingerprints and source structure. Full local validation requires the documented inputs and accepted local PBIX.

```powershell
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PHASE2_AUDIT_WRITE = '0'
.\.venv\Scripts\python.exe -B scripts/validate_project.py
.\.venv\Scripts\python.exe -B -m pytest tests -q -p no:cacheprovider
```

The project validator checks recorded asset fingerprints, local Markdown links, PBIX ZIP integrity, notebook execution metadata and report/model structure. It does not compile DAX or test Desktop interaction. Live SQL tests skip unless `OLIST_SQL_TESTS=1`; a skip is not a successful SQL test.

`tests/test_eda.py` checks the independent 19-file JSON fingerprint baseline. The phase-two audit validates the maintained processed inventory in [data quality](data_quality.md). Database-preservation checks use the curated `reports/phase_4_protected_files.json`; its pre-cleanup original is in the external recovery snapshot.

## Existing SQL warehouse validation

The current local warehouse is `OlistSalesDW` on the recorded SQL Express instance. Configure a matching server before custom checks:

```powershell
$env:OLIST_SQL_SERVER = 'lpc:localhost\SQLEXPRESS'
$env:OLIST_SQL_DRIVER = 'ODBC Driver 18 for SQL Server'
$env:OLIST_SQL_AUTH = 'windows'
$env:OLIST_SQL_TRUST_CERTIFICATE = 'yes'
.\.venv\Scripts\python.exe -B scripts/validate_warehouse.py
```

The certificate setting above belongs to the local shared-memory SQL Express configuration; adapt connection policy to another environment. The validator performs SELECT-based SQL/Python reconciliation and saves warehouse evidence. It does not run ETL.

For the existing integrated SQL/safety suite:

```powershell
.\.venv\Scripts\python.exe -B run_phase4_tests_only.py --project (Get-Location).Path
```

That legacy local runner sets its own local SQL Express connection and writes a new timestamped evidence directory. It does not create/reload the warehouse. `RUN_PHASE4_TESTS_ONLY.bat` is its convenience wrapper. Read-only KPI/data-quality queries are also available in SQL scripts 06 and 07.

## Fresh warehouse setup or reload

Review SQL scripts 01–08, the processed contract and the loader before using a new database. The supported entry point is `python -m src.data_processing.sql_server_etl`; inspect its `--help` and the existing interactive `RUN_PHASE4.bat` launcher. The launcher asks for an explicit database-writing confirmation and is tied to the original Windows host.

The loader requires transaction ownership and a recognized warehouse ownership marker. Never run `08_load_warehouse.sql` as an independent convenience load. Setup/reload is not required to review the completed imported report and was not rerun during cleanup.

Supported ETL connection variables are `OLIST_SQL_SERVER`, `OLIST_SQL_DRIVER`, `OLIST_SQL_AUTH`, `OLIST_SQL_TRUST_CERTIFICATE`, and, for SQL authentication, `OLIST_SQL_USER`/`OLIST_SQL_PASSWORD`. Use environment configuration; do not commit credentials.

## Power BI editing and runtime checks

Open the final PBIX to view it, or the final PBIP to edit source. Keep the `.Report` and `.SemanticModel` directories together. The retained `.pbi/cache.abf` contains imported data; dropping it can require reloading the semantic model. Update local source expressions in a separate working copy before refreshing on another machine.

Desktop assigns a temporary local model port. Identify the workspace associated with the correct report process; do not reuse an old port blindly. Then run the read-only checks:

```powershell
powershell.exe -NoProfile -File power_bi/scripts/run_completion_runtime_validation.ps1 -Port <current-port>
powershell.exe -NoProfile -File power_bi/scripts/run_dashboard_batches_20261102.ps1 -Port <current-port>
powershell.exe -NoProfile -File power_bi/scripts/run_top10_checks_20261102.ps1 -Port <current-port>
```

Replace `<current-port>` with the discovered integer. These use retained SQL-backed expectations for the accepted snapshot. Regenerate expectations only when intentionally validating a changed input population: `scripts/validate_warehouse.py`, then `power_bi/scripts/prepare_completion_runtime_qa.py`, then `power_bi/scripts/prepare_top10_checks_20261102.py`. These scripts perform read-only queries but replace their expected-result files.

The baseline model and seven-check regression utility are retained under `power_bi/reports/` and `power_bi/scripts/`. Historical baseline values are available in the accepted model-regression evidence. The original baseline binary is in the external backup.

After report changes, save through Desktop to a working PBIX, close/reopen it, rerun relevant reconciliation, inspect all pages and repeat the representative UI flow in the [dashboard guide](dashboard_guide.md). Static checks do not replace this process.

## Troubleshooting

| Symptom | Check |
|---|---|
| Notebook kernel unavailable | Register/select the project's `ecommerce-sales-bi` kernel |
| Data fingerprint mismatch | Dataset version, exact filenames and whether inputs were edited |
| ODBC connection failure | Installed driver, SQL Express instance, authentication and connection policy |
| TOM/ADOMD assembly error | Windows PowerShell 5.1, installed SSMS version and library paths |
| Wrong Desktop model count/measure count | Report/process/port association and correct final PBIX |
| Blank percentage | Selected valid denominator and documented empty-population handling |
| Integrity check fails after intentional edits | Review diffs and evidence before deliberately issuing a new acceptance manifest |

## Public release

Review [attribution](dataset_attribution.md), local paths and release selection. Raw/processed data, PBIX, ABF caches, database files, virtual environments and private settings are ignored. Aggregate images/PDFs still require an intentional release decision. The owner authorized the GitHub source release on 6 November 2026. The published selection contains source, aggregate evidence, notebooks and report previews; data inputs, PBIX and caches stay local. Power BI Service deployment remains outside scope.
