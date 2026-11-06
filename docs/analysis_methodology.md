# Analytical methodology

## Scope and common population

The five notebooks progress through data understanding, cleaning, EDA, customer analysis and cohorts. Reusable calculations live in `src/analysis/eda.py` and `src/analysis/customer_analytics.py`. Charts are generated from those calculations rather than manually entered values.

Sales and customer analyses use delivered orders with recorded items. Merchandise excludes freight. Monetary aggregation uses exact decimal values or integer cents. An order-level analytical view aggregates items, payments and reviews independently before joining them to orders. No synthetic quantity, profit, refund completeness or lifetime-value assumption is added.

## Exploratory analysis

EDA covers revenue and order trends; product/category contribution; purchasing frequency and geography; payment methods/installments; delivery SLA/duration; and review coverage/ratings. Seven aggregate analytical CSVs and 22 high-resolution figures support these themes. Missing child records remain visible in coverage and reconciliation.

Payment amount is not equated with merchandise revenue. Recorded payments can differ from merchandise plus freight; mismatches are reported rather than forced to zero. Category order counts overlap, and category review association uses one order mean per distinct order-category membership.

Historical notebook outputs and source-state EDA remain a record of their original analytical stage. Current cross-stage definitions, caveats and next actions are maintained in this documentation set.

## Customer identity and geographic assignment

`customer_unique_id` identifies an observed purchaser. Frequency is the number of distinct eligible orders; one-order and repeat customers partition that selected population. Monthly activity labels purchases in the identity's first observed eligible month as **First observed month** and activity in later months as **Returning month**. An identity is counted once per month.

For a mutually exclusive customer geographic split, the latest eligible order supplies the customer's source state; order ID breaks timestamp ties. Revenue for that group includes all eligible in-window purchases of the assigned customers. This differs from order-location revenue and from approximate ZIP-state Power BI charts.

## RFM segmentation

The reference date is **2018-08-30**, the day after the latest eligible purchase in this snapshot.

| Component | Calculation | Scoring |
|---|---|---|
| Recency | Calendar days since the last eligible purchase | Average percentile ranks mapped to 1–5; more recent scores higher |
| Frequency | Distinct eligible orders per identity | Explicit 1, 2, 3, 4 and 5+ order groups |
| Monetary | Sum eligible merchandise cents per identity | Average percentile ranks mapped to 1–5; greater value scores higher |

Ties retain the same score. Explicit frequency bands avoid pretending that the very large one-order group can form five distinct equal-sized frequency quantiles. Segment rules combine recent (`R>=4`), repeat (`F>=2`) and high monetary value (`M>=4`) conditions. The exact mutually exclusive branches are implemented in [customer_analytics.py](../src/analysis/customer_analytics.py).

Segments describe observed behavior. They have not been validated as response, future-value or churn predictors. Individual customer-level frames stay in notebook memory; saved outputs are aggregate tables and charts.

## Cohort retention

Each customer's first observed eligible purchase month defines its cohort. At age `k`, the numerator is distinct cohort customers with at least one eligible purchase in that specific later calendar month; the denominator is the cohort's original eligible customer count. Repeated purchases within a month contribute once.

Month zero is 100%. An observed month with no returning purchasers is zero. Unobserved future ages remain missing, rather than zero. The heatmap respects this mask.

Pooled age-specific retention sums active customers and eligible original cohort customers across cohorts observed at that age. It excludes activity in the potentially incomplete August 2018 snapshot tail. It does not average cohort percentages. At age one, **390 / 81,265 = 0.4799114%**, using 21 eligible earlier cohorts; 23 cohort months exist overall. Tail exclusion does not prove that every earlier month has complete coverage.

Cohort retention measures purchases in one specific later month. It differs from the 3.00028% all-window repeat-customer rate. First observed purchase is not verified lifetime acquisition; inactivity is not verified churn in this noncontractual marketplace.

## Validation and artifacts

Focused regression cases cover unique identity, exact money totals, tied scores, deterministic geography, same-month deduplication and future-period masking. Notebook assertions check cohort sizes, month-zero values, bounded rates and valid masks.

Outputs are retained under [customer analytics](../reports/completion_20261101/customer_analytics/), including the customer summary, segment/frequency/geographic/monthly tables, cohort count/rate/long/pooled tables and charts. [Execution evidence](../reports/completion_20261101/customer_analytics/execution_evidence.json) records source fingerprints and notebook runs. [Reproduction](reproduction_guide.md) explains regeneration.

## Interpretation limits

The project is descriptive. Historical correlations do not establish intervention effects. Snapshot boundaries, delivered-status selection, uneven review coverage, approximate geography and changing cohort exposure affect interpretation. Financial or operational benefits require additional data and controlled evaluation.
