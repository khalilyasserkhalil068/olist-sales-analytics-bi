# Maintenance and cleanup record

## Current project state

Local portfolio delivery is complete. The final five-page PBIX, editable PBIP source and imported cache, native PDF, page assets, source data, code, SQL and tests remain in the active project. This maintained `docs/` set and the root README replace the previous fragmented Markdown documentation.

The report's analytical acceptance was recorded on **2 November 2026**. Cleanup and documentation consolidation were performed on **6 November 2026** at the owner's request. Cleanup did not run ETL, change the SQL schema, publish, commit or push.

## What was removed from the active project

- Superseded PBIX files, report backups and intermediate build/recovery/visual-QA workspaces.
- One-time authoring, completion-documentation, report-fix and promotion utilities.
- Repeated or failed intermediate validation runs, temporary pytest fixtures, duplicate renders and terminal logs.
- Obsolete page specifications and duplicated theme/planning outputs already represented by the final native source.
- Installation/checkpoint/handoff documents and previous documentation drafts.
- Empty placeholders and reproducible Python/pytest caches.

The final saved PBIX and its source were retained. The semantic model's ABF import cache was retained because it supports the editable imported snapshot. The working `.venv` and `.git` directory were preserved. User editor settings were preserved.

The two completed customer/cohort notebooks replaced their old empty placeholders under canonical `04_customer_analysis.ipynb` and `05_cohort_analysis.ipynb` names. The generation script now writes those names. Original placeholder and completed copies remain in the external recovery snapshot.

The reviewed cleanup selected **698 old files for removal or replacement**, totaling approximately **559 MiB**, plus reproducible cache directories. Fifteen maintained Markdown documents now cover the project. The active tree has approximately 356 project files, excluding the environment, Git internals and local editor settings. Retained native report definitions and validation evidence account for much of that count. The external snapshot remains on disk for recovery; this is an active-tree cleanup, not a claim of net disk-space savings.

## Recovery

Before deletion/replacement, a full project snapshot was copied outside the active project and verified file-by-file with SHA-256. It contains **1,037 files / 1,009,900,708 bytes**, excluding `.git`, `.venv` and reproducible caches.

Recovery folder:

```text
E:\Projects CV\_project_backups\olist_before_cleanup_20261106_000915
```

`inventory.json` records original relative paths, sizes and hashes. `cleanup_plan.json` records each selected removal and its reason. `cleanup_execution.json` records execution. The `project/` subdirectory preserves the original tree. The adjacent `olist_latest_cleanup_backup.txt` points to the recovery folder.

Restore individual files by matching their original relative paths; review dependencies before restoring an obsolete verifier or build script. A wholesale restore would also restore old documentation and duplicates. Do not overwrite the accepted report during routine recovery.

## Dependency maintenance

The phase-two audit now reads the maintained data-quality inventory instead of deleted phase summaries. EDA fingerprint tests read the independent JSON baseline instead of parsing an old Markdown report. The Phase 4 launcher checks the maintained KPI guide. The preservation manifest was deliberately pruned/reissued for the curated file set; its original is in the external snapshot. All raw/processed CSV fingerprints remain unchanged.

`scripts/validate_project.py` replaces historical workspace-dependent offline verifiers. Reusable Desktop runtime and SQL expectation tools remain. Historical machine-readable evidence is retained unchanged, including recorded path names and test scope; historical paths may refer to archived artifacts.

## Routine workflow

1. Read the architecture, KPI and reproduction guides before changing calculations.
2. Edit a working copy and preserve the accepted PBIX fingerprint.
3. Run relevant Python/source checks; for model/report edits, run Desktop DAX and native save/close/reopen/visual checks.
4. Record evidence in a new run directory and update documentation for intentional behavior changes.
5. Reissue `reports/project_integrity.json` only after reviewing intentional changes. A failing fingerprint is a review signal, not a reason to reset expectations automatically.

Keep documentation in root `README.md` and `docs/*.md`. Keep aggregate outputs and machine-readable evidence under `reports/`. Avoid recreating dated narrative/checkpoint copies across several folders. Data-bearing release and service deployment remain separate owner decisions.

## GitHub source edition

The owner authorized publication on 6 November 2026. The source edition omits data inputs and imported binary/cache files, removes hyperlinks to omitted binaries and supports `scripts/validate_project.py --source-only`. `.gitattributes` preserves accepted bytes across platforms so SHA-256 fingerprints remain portable. Historical acceptance remains local-delivery evidence; source-only checks have a separately stated scope.
