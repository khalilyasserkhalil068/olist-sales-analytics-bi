# Validation, evidence and limitations

## Acceptance chronology

The five-page PBIX was accepted on **2 November 2026** after native save, close and independent reopen. Cleanup/documentation work on **6 November 2026** preserved that PBIX and the raw/processed CSVs. Historical numerical tests are reported as historical; current maintenance checks are recorded separately.

## Recorded analytical and report acceptance

| Layer | Executed outcome | Evidence |
|---|---|---|
| Foundation | 118 passed, one explicit skip, zero failures/errors | [JUnit results](../reports/completion_20261101/qa/foundation_tests.xml) |
| SQL/Python reconciliation | 3,948 assertions passed | [Warehouse reconciliation](../reports/completion_20261101/qa/warehouse_reconciliation.json) |
| DAX runtime | 86 cases passed, 248 numeric comparisons | [Final reopened-model results](../reports/completion_20261101/runtime_20261102_165640_295/results.json) |
| Dashboard queries | 39 batches passed, 36 numeric Difference checks | [Page query results](../reports/completion_20261101/dashboard_batches_20261102_165644_157/results.json) |
| New Top-10 gates | Four SQL-backed ranking cases passed | [Gate results](../reports/completion_20261101/top10_20261102_165648_208/results.json) |
| Model regression | Seven checks passed | [Comparison](../reports/completion_20261101/model_regression_20261102_165649_017/comparison.json) |
| Original report source QA | 20 offline checks passed across 112 report JSON files | [Historical static results](../reports/completion_20261101/static_validation.json) |
| Customer edge cases | Two focused regression tests passed | [Customer JUnit](../reports/completion_20261101/customer_analytics/regression_tests.xml) |
| Saved PBIX | Native package, corrected bounds and independent reopen accepted | [Saved-report acceptance](../reports/completion_20261101/saved_pbix_acceptance_20261102.json) |
| Visual inspection | All five pages inspected from actual native export | [Native PDF](../power_bi/final/OlistSalesDW_Final_5_Dashboards.pdf) |
| Desktop captures | Delivery window and Reviews canvas captured and verified | [Capture evidence](../reports/completion_20261101/desktop_screenshots_20261102.json) |
| Representative UI | User reported instructed slicer/chart/reset/navigation flow working | [User UI evidence](../reports/completion_20261101/user_ui_validation_20261102.json) |

[Final acceptance summary](../reports/completion_20261101/final_acceptance_20261102.json) records the scope. References inside historical JSON may name pre-cleanup workspaces, logs or backup files; those paths describe the original run and are preserved in the external snapshot. Active verification entry points are listed in [reproduction](reproduction_guide.md).

## What was independently checked

Foundation checks cover input fingerprints, cleaning transformations, missing/duplicate handling, key uniqueness, referential integrity, report quantities and notebook execution metadata. SQL comparisons cover fact/dimension counts, money, business eligibility and selected slices. Foreign keys were checked as enabled/trusted.

DAX expectations are computed independently from SQL/Python populations. Counts use exact/declared comparisons; monetary and floating-point results use explicit case tolerances. Empty count results may be interpreted as zero only for specified count measures. Undefined rate denominators are not silently treated as successful zero rates.

Regression compares the 33 retained measure definitions/formats and values, all 37 relationships, four fact counts and partition definitions. The final model adds 25 measures for a total of 58. Category/state gate tests validate exact group membership and order, including ties.

## Corrections verified before final acceptance

Three new review rates initially returned BLANK for empty numerators under nonempty score selections. Their numerators now use `COALESCE`; `KEEPFILTERS` preserves the selected population and an empty denominator remains undefined. Score-slicer edge cases passed after correction.

Actual PDF review exposed title/footer overflow and constrained slicer controls. Thirty-four bounds were adjusted, all five pages were exported/reviewed again, and saved-PBIX bounds were compared. Native table/chart scroll viewports remain intentional.

## Current cleanup verification

The maintenance result is saved in [cleanup validation](../reports/cleanup_validation.json). It records current file/link/model checks, Python test outcomes, canonical notebook execution and preservation of final data/report assets. The accepted project assets are listed in [project integrity](../reports/project_integrity.json).

| Check on 6 November 2026 | Outcome |
|---|---|
| Full current Python suite | 106 passed, 15 skipped, zero failures/errors |
| Skip scope | 14 live SQL tests disabled for this local run; one geographic/timezone-provenance limitation |
| Canonical customer/cohort notebooks | Re-executed, five code cells each, zero errors |
| Current local structural/integrity checks | Nine passed, zero failed |
| Local Markdown links | 120 checked, zero broken |
| Documented DAX vs final editable model | All 58 expressions match |
| Input CSVs and final report/source | Recorded fingerprints unchanged |

The current Python run is saved in [cleanup JUnit](../reports/cleanup_tests.xml); static details are in [project structure validation](../reports/project_structure_validation.json). This run did not repeat historical live SQL or Desktop DAX acceptance.

`scripts/validate_project.py` verifies curated SHA-256 fingerprints, PBIX ZIP integrity, all local documentation links, native page/visual inventory, field/interaction references, canvas bounds, relationship topology and executed notebook validity. It does not execute DAX, revalidate remote JSON schemas or automate the Desktop UI. Historical 20-check source acceptance has a broader preservation/schema context and is not relabeled as this new verifier.

## Known limits and unverified areas

- The foundation skip concerns authoritative geography and original timestamp timezone provenance. ZIP geography is an approximation.
- UI evidence covers a representative user-tested flow, not exhaustive combinations or automated clicks.
- A recorded DAX timing run had median 22.5 ms and maximum 299 ms. It was neither a controlled cold-cache benchmark nor visual-render timing.
- Scrollable charts/tables can contain data outside a static PDF viewport. Some preserved baseline series share a teal palette and require tooltips for identification.
- The historical baseline whole-file PBIX hash differs from its earlier recorded checkpoint. Live definitions, relationships and values reconcile; this remains a provenance limitation rather than a hidden equality claim.
- Snapshot boundaries, review coverage and delivered-status selection limit retention and causal interpretation. Category populations and distinct counts can overlap.
- The exact downloaded-package license notice was not recovered. Retained publisher metadata indicates CC BY-NC-SA 4.0; see [attribution](dataset_attribution.md).
- Power BI Service publication and scheduled refresh were not demonstrated. GitHub source publication is a separate owner-authorized release, with data inputs, PBIX and caches excluded.

## GitHub source validation

Use `python scripts/validate_project.py --source-only` on a checkout. It excludes only manifest entries explicitly marked local-only and checks all published assets, Markdown links, semantic/report structure and notebook validity. It does not claim PBIX package acceptance without the omitted local binary. `--source-only` is distinct from the full local verification recorded above.

## Revalidation after edits

Inspect changes before updating fingerprints. Run relevant Python checks and the local project validator; for semantic/report edits, rerun Desktop DAX comparisons and native save/close/reopen plus visual/UI review. A freshly generated source file is not equivalent to an accepted saved report. Preserve evidence in a new run directory rather than silently replacing historical acceptance.
