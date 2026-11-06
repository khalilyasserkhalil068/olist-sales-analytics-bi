# Business insights and proposed actions

These findings describe the preserved historical Olist snapshot. Monetary values are BRL merchandise unless specified otherwise. Independent SQL/Python results and executed customer notebooks support the figures; the final imported Power BI model was reconciled against them. Recommendations are proposed investigations and experiments, not claimed realized outcomes.

## Executive assessment

Eligible merchandise totals **R$13,221,498.11 across 96,478 delivered orders**, with average order value **R$137.04**. **6.7731%** of SLA-eligible deliveries are late. Late-order review records average **2.27103 / 5**, compared with **4.28998** for on-time orders. Repeat purchasing is limited within the observation window: **2,801 of 93,358 identities**, or **3.00028%**, place multiple eligible orders.

The clearest priorities are to investigate late-delivery concentrations, monitor high-value merchandise/customer groups and evaluate repeat-purchase experiments. The dataset cannot establish the causal benefit or profitability of those actions. [Sales queries](../reports/completion_20261101/business_sql_evidence.json), [delivery/review reconciliation](../reports/completion_20261101/qa/warehouse_reconciliation.json), [customer results](../reports/completion_20261101/customer_analytics/customer_summary.json).

## Sales performance

November 2017 produced **R$987,765.37 from 7,289 eligible orders**, compared with **R$648,247.65 from 4,478 orders** in October. This identifies a substantial increase in observed volume and sales. It does not identify a promotion or external event as the cause. Incomplete boundary periods should not be compared as complete months. Evidence: `sales` and `monthly_sales` in [business SQL evidence](../reports/completion_20261101/business_sql_evidence.json).

Monitor revenue together with order volume and AOV to distinguish basket-value changes from purchasing-volume changes. Keep freight and payments separate from merchandise.

## Product and seller contribution

| Leading category | Eligible merchandise revenue |
|---|---:|
| health_beauty | R$1,233,131.72 |
| watches_gifts | R$1,166,176.98 |
| bed_bath_table | R$1,023,434.76 |

These are revenue rankings, not margin rankings. Category merchandise sums reconcile to total eligible sales; distinct category order counts overlap. The five largest seller groups contribute **7.7094%** of revenue, and the largest group contributes **R$226,987.93**. Warehouse seller surrogate keys are local identifiers. Evidence: `category_sales` and `seller_sales` in [business SQL evidence](../reports/completion_20261101/business_sql_evidence.json).

Prioritize availability and service-quality monitoring for important categories/sellers. Margin, inventory availability, service cost and seller capacity are needed before committing operational or marketing spend.

## Customer behavior and concentration

There are **90,557 single-order** and **2,801 repeat** eligible purchasing identities. Average orders per identity is **1.03342**; median customer merchandise is **R$89.73**. The highest-revenue tenth contributes **41.0999%** of observed sales. These are in-window figures, rather than lifetime value or profit concentration. [Customer summary](../reports/completion_20261101/customer_analytics/customer_summary.json).

The descriptive recent/high-value/repeat RFM segment contains **931 customers**, using the historical **2018-08-30** anchor. Month-one pooled cohort activity is **390 / 81,265 = 0.4799114%** after excluding the snapshot tail. It measures purchases in one particular later month and differs from all-window repeat purchasing. [Segments](../reports/completion_20261101/customer_analytics/customer_segments.csv), [pooled cohort results](../reports/completion_20261101/customer_analytics/cohort_pooled.csv), [methodology](analysis_methodology.md).

Evaluate a narrowly scoped repeat-purchase experiment with a holdout. Segment labels do not predict response or churn, and the data does not quantify expected uplift.

## Geographic exposure

Using the report's **approximate ZIP-derived customer geography**, SP contributes **R$5,065,820.02 from 40,487 eligible orders**, RJ **R$1,758,005.01**, and MG **R$1,551,718.06**. Source-state EDA and latest-order customer-state assignments use different definitions and may differ. Evidence: `approximate_state_sales` in [business SQL evidence](../reports/completion_20261101/business_sql_evidence.json).

Use geographic distribution to prioritize investigation, while retaining unmatched/ambiguous ZIP caveats. A representative ZIP coordinate is not a verified customer address or shipping route.

## Delivery performance

| Population | Result |
|---|---:|
| Delivered orders | 96,478 |
| SLA-eligible delivered orders | 96,470 |
| On-time orders | 89,936 — 93.2269% |
| Late orders | 6,534 — 6.7731% |
| Duration-eligible orders | 95,097 |
| Average elapsed duration | 12.61849 days |
| Average positive late delay | 10.62014 calendar days |
| Average freight per delivered order | R$22.785253 |

Missing-date and undelivered orders do not become late orders. SLA and duration denominators differ. Freight is summed once at order grain. These rules are reconciled in the `delivery` query of [warehouse evidence](../reports/completion_20261101/qa/warehouse_reconciliation.json).

Investigate late-delivery state/category/seller groups with sufficient volume and valid dates. Compare service outcomes using the same denominator before and after a controlled pilot.

## Customer satisfaction

Across **99,224 valid review records**, average score is **4.0864206**. Positive scores account for **77.06805%**, negative scores **14.68899%**, and five-star scores **57.77634%**. Score 3 is neutral; positive plus negative need not equal 100%. Multiple review records per order are retained. [Review reconciliation](../reports/completion_20261101/qa/warehouse_reconciliation.json), queries `reviews` and `review_timeliness`.

On-time orders have **89,944 associated valid reviews**, averaging **4.28998**; late orders have **6,409**, averaging **2.27103**. Timeliness-ineligible orders account for another **2,871** reviews, averaging **1.76176**. These are review-record populations and must not replace delivery-order denominators.

The difference is an observational association. Review coverage, product mix, seller behavior and other factors may also matter. Category ratings describe reviews associated with orders containing a category, rather than identified product-specific feedback.

## Decision priorities and measurement plan

| Priority | Proposed action | Measure before drawing conclusions |
|---|---|---|
| Delivery reliability | Diagnose high-volume late segments and missing milestones | SLA eligibility, late count/rate, delay and associated review coverage |
| Repeat purchasing | Test a defined offer with a randomized holdout | Subsequent eligible purchases, incremental value and campaign cost |
| Revenue concentration | Monitor high-value customer/category groups | Merchandise, margin, stockouts and service costs from additional sources |
| Measurement quality | Keep grains, date roles and geographic definitions explicit | Reconciliation exceptions, unmatched ZIPs and changing coverage |

Profit, causal uplift, verified churn and lifetime acquisition are not established by this dataset. See [limitations and test scope](validation.md).
