# Data quality and preparation

## Input policy

The nine raw CSVs are preserved byte-for-byte. Cleaning writes ten processed files: nine cleaned tables plus one representative ZIP lookup. Source identifiers, ZIP prefixes and sequence keys remain strings. Empty fields are missing; arbitrary strings are not silently converted to null. Dates, dimensions and financial amounts are not imputed.

Outer whitespace is trimmed. Optional review text retains case, accents, internal whitespace and line breaks; whitespace-only optional text becomes missing. Categories are normalized without inventing translations. Missing source categories and absent translations have separate flags; `Unknown` is a display label with preserved provenance.

All transactional rows remain. Only exact repeated geographic observations are removed from the processed copy. A repeated review ID or order ID alone is not a duplicate record.

## Raw source inventory

| File | Bytes | SHA-256 |
| --- | --- | --- |
| olist_customers_dataset.csv | 9033957 | 983a422239e1712ded753b3bf9ecf47dc73f144d306029dcfa99e70a226883d2 |
| olist_geolocation_dataset.csv | 61273883 | b514f6fc991b9566aeba02aa5d67e2c3630f034b60a0e05aa0d082a3b66d88d6 |
| olist_orders_dataset.csv | 17654914 | 8df58ef3d2d7e9944010f7beecd9b75367f5588ec6e3c91cec19ae3345ef9ecf |
| olist_order_items_dataset.csv | 15438671 | 0bc4d068c4fe38cbb01bd90e8746e3c613fe7b4baef75fab7b0e329701c3e279 |
| olist_order_payments_dataset.csv | 5777138 | 4f713964f2815dbbaa40b9488268c55aac3627bfce5aa96cf58d1f3616de3cc0 |
| olist_order_reviews_dataset.csv | 14451670 | 012b61c7593e34f51fa614efdf802b9c7056ce6aae5307ddb93236e7cfc797d7 |
| olist_products_dataset.csv | 2379446 | 3e6569628a17fbc75fd206ee357b59e20364b9afa90f5b6cd5b4d624c58aa9cc |
| olist_sellers_dataset.csv | 174703 | 1f643d2b950373b85735e7794b20986f528d7a000432e7c6f9bcbb44d0846a0e |
| product_category_name_translation.csv | 2613 | a81f0d1f27b27e7293f761bc79e3ce8f348ee39c4b3ed3e49bde38f478586278 |

## Processed row inventory

The raw geolocation file has 1,000,163 observations; 261,831 exact excess duplicates are removed, leaving 738,332 distinct observations. The 19,015-row ZIP lookup is a derived table. Other source row counts are retained.

| dataset | rows_before | rows_after | rows_removed |
| --- | --- | --- | --- |
| customers | 99441 | 99441 | 0 |
| orders | 99441 | 99441 | 0 |
| order_items | 112650 | 112650 | 0 |
| payments | 103886 | 103886 | 0 |
| reviews | 99224 | 99224 | 0 |
| products | 32951 | 32951 | 0 |
| sellers | 3095 | 3095 | 0 |
| category_translations | 71 | 71 | 0 |
| geolocation | 1000163 | 738332 | 261831 |
| geolocation_zip_lookup | 0 | 19015 | 0 |

## Processed export inventory

This seven-column inventory is also checked independently by the phase-two audit. Hashes and byte counts identify the actual accepted outputs.

| dataset | filename | rows | columns | bytes | sha256 | verified |
| --- | --- | --- | --- | --- | --- | --- |
| customers | customers_clean.csv | 99441 | 7 | 9779318 | dadd4167d59c0028dbce61ebd7282b6eb665ef776b79d7d0a000fbacb428575d | True |
| orders | orders_clean.csv | 99441 | 27 | 28735749 | 495c9c11e5e638d4c576d1a406e51a2180b5565ab9b31495ebcf72bbbedca6eb | True |
| order_items | order_items_clean.csv | 112650 | 16 | 20994520 | 34037964980e1fdb300d64448eef8dc3e42903bfe67750ecc2ecbd3a622b8770 | True |
| payments | payments_clean.csv | 103886 | 11 | 9373415 | 9441054e0298f27da1cb846cb8ac71378c32a1a855a8bdbb6c55fa971428e1c5 | True |
| reviews | reviews_clean.csv | 99224 | 14 | 18106274 | 1e9b833b7d2bc2420da63e63cdd836a741f7eb37a3fe82b3a5e5ec2867e2ea08 | True |
| products | products_clean.csv | 32951 | 24 | 6022937 | 2fe1d2904429ff2587266b690a26112446cd3ba4afe74bfe555029b56e823258 | True |
| sellers | sellers_clean.csv | 3095 | 6 | 201789 | f12eef90d97555e2c3c0a4634a6ffe0aa277e1511a4a43e4dc32a9fe6ffbca7e | True |
| category_translations | category_translations_clean.csv | 71 | 2 | 2540 | 5233473346639d5ff3da9b784385ba284778abfaac1062572abe99e8aba8b7e3 | True |
| geolocation | geolocation_clean.csv | 738332 | 9 | 61477686 | bb8cd9f785f156b091781677144c33ef7bbbc03fa06a7a14db0c51d8b9b2aec8 | True |
| geolocation_zip_lookup | geolocation_zip_lookup.csv | 19015 | 14 | 1736166 | f6bd7c09504f150764f8b0c10ad1288c0a92eee99735e1f94bf192536879172e | True |

## Geographic representation

Remove exact duplicate observations first. For each ZIP prefix, choose the modal state/city pair, breaking ties alphabetically by state then city. Within that pair, calculate coordinate medians, select an existing valid coordinate nearest the median in squared degree distance, and break remaining ties by latitude/longitude. Keep the prefix with missing coordinates if no valid representative exists.

Alternative source labels and ambiguity flags remain available. The lookup is an approximate representative location, not an authoritative address or a routing-distance calculation. Customer/seller lookup joins are many-to-one and preserve source row counts. Power BI uses derived geography roles; source-state Python analysis retains source labels.

## Missingness and chronology

The source has 2,965 missing actual-delivery timestamps, including eight delivered-status orders without that milestone. Delivered statuses total 96,478; SLA eligibility is 96,470. Duration eligibility is 95,097 because it applies purchase/delivery endpoint and chronology rules. These populations are separate and exclusions do not delete the orders.

Missing optional review text does not invalidate scores. Missing item/payment/review child records remain coverage conditions. Contradictory milestone chronology is flagged instead of silently corrected. Canceled or undelivered orders with dates are not reclassified as completed sales.

## Quality evidence and interpretation

[Cleaning actions](../reports/cleaning_summary.csv) record transformations and affected counts. [Missing-value comparison](../reports/missing_values_before_after.csv), [row-level flags](../reports/data_quality_flags.csv), [relationship checks](../reports/relationship_validation.csv) and [independent audit results](../reports/audit/phase_2_audit_results.csv) retain detailed diagnostics. Action/flag counts can overlap; their sum is not a count of unique bad records.

Input hashes are also stored in the raw manifest, processed warehouse contract and independent 19-file JSON baseline. Tests compare saved bytes and recompute transformations from source, including an in-memory reproducibility control. See [validation](validation.md) and [reproduction](reproduction_guide.md).

Authoritative geographic correctness and source timestamp timezone provenance remain unverified. No cleaning rule converts those limitations into verified facts.
