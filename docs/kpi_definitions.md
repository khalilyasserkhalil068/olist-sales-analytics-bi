# KPI definitions and population boundaries

All monetary values are Brazilian real (BRL). Merchandise, freight and recorded payments are separate concepts. Rates below are displayed as percentages; DAX generally stores their fractional values. Snapshot values correspond to the final accepted imported model and reconciled inputs.

## Sales, products and customers

| KPI | Calculation and eligible population | Snapshot |
|---|---|---:|
| Order Count | Rows in `FactOrders`, all statuses | 99,441 |
| Sales Order Count | Orders marked `SalesEligible`: delivered with at least one item | 96,478 |
| Item Revenue | Sum item price, all statuses | R$13,591,643.70 |
| Sales Revenue | Sum item price where `SalesEligible=true`; freight excluded | R$13,221,498.11 |
| Average Sales Order Value | Selected eligible item revenue / distinct eligible orders represented by those items | R$137.0416 |
| Total Items Sold | Eligible item rows; no separate quantity field is invented | 110,197 |
| Average Revenue per Item | Sales Revenue / eligible item rows | R$119.98 |
| Unique Sales Customers | Distinct known `CustomerUniqueID` among eligible orders | 93,358 |
| Repeat Sales Customers | Identities with at least two distinct eligible orders in the current selection | 2,801 |
| Repeat Customer Rate | Repeat Sales Customers / Unique Sales Customers | 3.00028% |
| Customer Order Frequency | Eligible orders with known identities / eligible purchasing identities | 1.03342 |
| Sales Revenue per Customer | Eligible merchandise for known identities / purchasing identities | R$141.62148 |
| Selling Products | Distinct known product keys in eligible selected items | 32,216 |
| Active Sellers | Distinct known seller keys in eligible selected items | 2,970 |

`customer_id` is an order-associated customer record; `customer_unique_id` is the identity used for repeat purchasing. A distinct customer may appear in several category, month or state groups. Repeat rate is selection-dependent observed purchasing, rather than retention or churn.

`Orders With Items` and `Sales Orders With Items` use the selected item population. Product/category/seller slicing can therefore change their order denominator. Do not substitute the all-orders count when calculating selected-item AOV.

## Delivery and logistics

| KPI | Rule | Snapshot |
|---|---|---:|
| Delivered Orders | Orders whose status is delivered | 96,478 |
| Timeliness Eligible Orders | Delivered orders with actual and estimated delivery dates | 96,470 |
| On Time Deliveries | Timeliness-eligible, actual calendar date on/before estimated date | 89,936 |
| Late Deliveries | Timeliness-eligible, actual calendar date after estimated date | 6,534 |
| On Time Delivery Rate | On Time Deliveries / Timeliness Eligible Orders | 93.2269% |
| Late Delivery Rate | Late Deliveries / Timeliness Eligible Orders | 6.7731% |
| Duration Eligible Orders | Delivered, usable purchase/delivery endpoints and no known contradictory chronology | 95,097 |
| Average Delivery Days | Mean elapsed purchase-to-delivery days among duration-eligible orders | 12.61849 days |
| Average Late Delay Days | Mean positive actual-calendar-date minus estimated-calendar-date difference among late orders | 10.62014 days |
| Average Freight per Delivered Order | Order freight summed once / delivered orders with recorded freight | R$22.785253 |

Delivery on the estimated day is on time. Undelivered orders are excluded from the SLA denominator. Duration and SLA have different eligibility rules. Missing intermediate milestones alone do not invalidate an available end-to-end duration; known contradictory chronology does.

Elapsed duration uses fractional days; late delay uses calendar days. They answer different questions. In this snapshot every delivered order has items, so delivered-order and eligible-sales freight populations coincide. Preserve the explicit formula if a future snapshot changes this property.

Duration bands are under 7, 7 to under 14, 14 to under 21, 21 to under 30, and 30+ elapsed days. Records outside duration eligibility have no band.

## Reviews and satisfaction

| KPI | Rule | Snapshot |
|---|---|---:|
| Total Valid Reviews | Review/order records with integer score 1–5 across all order statuses | 99,224 |
| Average Review Score | Record-weighted mean valid score | 4.0864206 / 5 |
| Positive Review Rate | Valid scores 4–5 / selected valid reviews | 76,470 / 99,224 = 77.06805% |
| Negative Review Rate | Valid scores 1–2 / selected valid reviews | 14,575 / 99,224 = 14.68899% |
| Five Star Review Rate | Valid score 5 / selected valid reviews | 57,328 / 99,224 = 57.77634% |
| On-time review average | Valid review records associated with on-time orders | 4.2899804 over 89,944 records |
| Late review average | Valid review records associated with late orders | 2.2710251 over 6,409 records |

Score 3 is neutral, so positive and negative rates need not total 100%. Optional missing review text does not invalidate a score. `ReviewID` alone is not a unique record key; retain the composite review/order grain and multiple reviews on one order.

The score slicer changes the selected valid-review denominator. Under score 1, Positive = 0%, Negative = 100%, and Five-star = 0%. The three rate numerators use `COALESCE` for an empty numerator with a positive denominator. A genuinely empty denominator remains undefined.

The satisfaction page uses review creation dates. The eligible-sales EDA review population contains 96,361 records and averages 4.15572; it deliberately differs from the all-status Power BI average. EDA delivery associations first average within each order; the final on-time/late review measures are record-weighted. These definitions must not be interchanged.

## Category attribution and Top-10 gates

Category delivery/review charts use distinct order-category membership before transferring order keys to the corresponding fact. A review associated with an order containing a category is not necessarily a product-specific review. Multi-category groups overlap and must not be summed.

The four new state/category charts retain ten groups ranked by the chart's selected population volume, with alphabetical tie-breaking. Ranking by volume avoids interpreting small, extreme averages as the largest business exposure. The exact gates are included in [DAX reference](dax_reference.md) and [SQL-backed gate cases](../reports/completion_20261101/top10_cases.json).

## Aggregation and interpretation rules

- Aggregate child facts separately before joining order-level results. Do not multiply money or freight through item/payment/review joins.
- Recompute ratios from numerators/denominators; do not average subgroup percentages without weighting.
- Distinct counts, AOV, rates and overlapping category populations are nonadditive.
- Power BI state fields use approximate ZIP geography. Source-state analysis and latest-order customer-state assignments answer different questions.
- Purchase and review dates have separate roles. Month names sort by month number; year-month avoids pooling different years.
- Source timestamp timezone provenance is unverified. No timezone conversion is inferred.

The complete implementation is documented in [all 58 DAX measures](dax_reference.md). Expected results and tolerance rules are retained in [runtime cases](../reports/completion_20261101/runtime_cases.json); executed outcomes are linked in [validation](validation.md).
