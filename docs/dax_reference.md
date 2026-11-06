# DAX implementation reference

This reference contains all **58 measures** from the model independently reopened from the final saved PBIX: 33 retained measures, including the original 13, plus 25 additions. Expressions and format strings are preserved exactly. The documentation was consolidated on 6 November 2026; measure acceptance was recorded on 2 November 2026.

Read [KPI definitions](kpi_definitions.md) for populations and exclusions. [Runtime results](../reports/completion_20261101/runtime_20261102_165640_295/results.json) record 86 passed cases. This reference is descriptive; editing Markdown does not update the semantic model. Editable definitions live in the final `.SemanticModel/definition/tables/` TMDL files.

## FactOrderItems

### Item Revenue

Original validated measure (preserved). Format: `#,0.00`.

All-status item revenue. Do not add to FactOrders merchandise revenue: they represent the same revenue at different grains.

```dax
SUM(FactOrderItems[ItemPrice])
```

### Sales Revenue

Original validated measure (preserved). Format: `#,0.00`.

Sales-eligible item revenue. Supports product and seller slicing.

```dax
CALCULATE([Item Revenue], KEEPFILTERS(FactOrderItems[SalesEligible]=TRUE()))
```

### Orders With Items

Original validated measure (preserved). Format: `#,0`.

Distinct orders represented by the selected items. Supports product and seller filters; nonadditive across these groups.

```dax
DISTINCTCOUNT(FactOrderItems[OrderKey])
```

### Sales Orders With Items

Original validated measure (preserved). Format: `#,0`.

Distinct sales-eligible orders with selected items.

```dax
CALCULATE([Orders With Items], KEEPFILTERS(FactOrderItems[SalesEligible]=TRUE()))
```

### Average Sales Order Value

Original validated measure (preserved). Format: `#,0.00`.

Selected eligible item revenue divided by distinct eligible orders with selected items.

```dax
DIVIDE([Sales Revenue],[Sales Orders With Items])
```

### Item Freight

Original validated measure (preserved). Format: `#,0.00`.

Freight at item grain. Do not add to order-grain FreightAmount.

```dax
SUM(FactOrderItems[FreightValue])
```

### Total Items Sold

Previous dashboard measure (preserved). Format: `#,0`.

Eligible order-item records in the current context. One source row is one item; no invented quantity. Supports product, seller and customer geography filters.

```dax
CALCULATE(COUNTROWS(FactOrderItems), KEEPFILTERS(FactOrderItems[SalesEligible] = TRUE()))
```

### Average Revenue per Item

Previous dashboard measure (preserved). Format: `"R$" #,0.00`.

Eligible merchandise revenue divided by eligible item records. Excludes freight and is not average order value.

```dax
DIVIDE([Sales Revenue], [Total Items Sold])
```

### Selling Products

Previous dashboard measure (preserved). Format: `#,0`.

Distinct known products present in eligible selected item records. Excludes ProductKey=0, the source warehouse unknown dimension member; does not exclude its revenue from Sales Revenue.

```dax
CALCULATE(DISTINCTCOUNT(FactOrderItems[ProductKey]), KEEPFILTERS(FactOrderItems[SalesEligible] = TRUE()), KEEPFILTERS(FactOrderItems[ProductKey] > 0))
```

### Active Sellers

Previous dashboard measure (preserved). Format: `#,0`.

Distinct known sellers present in eligible selected item records. Excludes SellerKey=0, the source warehouse unknown dimension member. This is observed sales activity, not registered sellers.

```dax
CALCULATE(DISTINCTCOUNT(FactOrderItems[SellerKey]), KEEPFILTERS(FactOrderItems[SalesEligible] = TRUE()), KEEPFILTERS(FactOrderItems[SellerKey] > 0))
```

### Category Revenue Share

Previous dashboard measure (preserved). Format: `0.0%`.

Category revenue divided by all selected category revenue, preserving year and geography. Use in the all-category contribution table without a Top N visual filter, so the denominator is not renormalized to only winners.

```dax
DIVIDE([Sales Revenue], CALCULATE([Sales Revenue], ALLSELECTED(DimProduct[CategoryLabel])))
```

### Show Top 10 Categories

Previous dashboard measure (preserved). Format: `0`.

Visual inclusion flag. Top min(10, available) categories by revenue, with category ascending as deterministic tie-breaker. Apply equals 1 only on the Top 10 category chart.

```dax
VAR CurrentCategory = SELECTEDVALUE(DimProduct[CategoryLabel]) VAR Candidates = FILTER(ADDCOLUMNS(ALLSELECTED(DimProduct[CategoryLabel]), "__Revenue", [Sales Revenue]), NOT ISBLANK([__Revenue])) VAR Winners = TOPN(10, Candidates, [__Revenue], DESC, DimProduct[CategoryLabel], ASC) RETURN IF(NOT ISBLANK(CurrentCategory) && CONTAINS(Winners, DimProduct[CategoryLabel], CurrentCategory), 1, 0)
```

### Show Top 10 Products

Previous dashboard measure (preserved). Format: `0`.

Visual inclusion flag. Top min(10, available) products by eligible revenue with ProductKey ascending tie-breaker. ProductKey is the categorical axis; use measure-only tooltips to avoid raw ProductID grouping filters.

```dax
VAR CurrentProduct = SELECTEDVALUE(DimProduct[ProductKey]) VAR Candidates = FILTER(ADDCOLUMNS(ALLSELECTED(DimProduct[ProductKey]), "__Revenue", [Sales Revenue]), NOT ISBLANK([__Revenue])) VAR Winners = TOPN(10, Candidates, [__Revenue], DESC, DimProduct[ProductKey], ASC) RETURN IF(NOT ISBLANK(CurrentProduct) && CONTAINS(Winners, DimProduct[ProductKey], CurrentProduct), 1, 0)
```

### Show Top 10 Sellers

Previous dashboard measure (preserved). Format: `0`.

Visual inclusion flag. Top min(10, available) sellers by eligible revenue with SellerKey ascending tie-breaker. Use the same equals-1 flag on the seller bar chart and comparison table.

```dax
VAR CurrentSeller = SELECTEDVALUE(DimSeller[SellerKey]) VAR Candidates = FILTER(ADDCOLUMNS(ALLSELECTED(DimSeller[SellerKey]), "__Revenue", [Sales Revenue]), NOT ISBLANK([__Revenue])) VAR Winners = TOPN(10, Candidates, [__Revenue], DESC, DimSeller[SellerKey], ASC) RETURN IF(NOT ISBLANK(CurrentSeller) && CONTAINS(Winners, DimSeller[SellerKey], CurrentSeller), 1, 0)
```

### Show Top 5 Trend Categories

Previous dashboard measure (preserved). Format: `0`.

Trend inclusion flag; ranks categories over the current selected period and removes the individual month axis filter. Requires YearMonth on the axis. Verify constant category membership across months after integration.

```dax
VAR CurrentCategory = SELECTEDVALUE(DimProduct[CategoryLabel]) VAR Candidates = FILTER(ADDCOLUMNS(ALLSELECTED(DimProduct[CategoryLabel]), "__PeriodRevenue", CALCULATE([Sales Revenue], ALLSELECTED(DimDate[YearMonth]))), NOT ISBLANK([__PeriodRevenue])) VAR Winners = TOPN(5, Candidates, [__PeriodRevenue], DESC, DimProduct[CategoryLabel], ASC) RETURN IF(NOT ISBLANK(CurrentCategory) && CONTAINS(Winners, DimProduct[CategoryLabel], CurrentCategory), 1, 0)
```

## FactOrders

### Order Count

Original validated measure (preserved). Format: `#,0`.

Order-grain count. Responds to customer, status, purchase date and order; product/seller filters apply only to item measures.

```dax
COUNTROWS(FactOrders)
```

### Sales Order Count

Original validated measure (preserved). Format: `#,0`.

Sales-eligible orders at order grain.

```dax
CALCULATE(COUNTROWS(FactOrders), KEEPFILTERS(FactOrders[SalesEligible]=TRUE()))
```

### On Time Delivery Rate

Original validated measure (preserved). Format: `0.00%`.

Eligible on-time orders divided by eligible delivered orders; excludes missing/ineligible delivery records.

```dax
DIVIDE(CALCULATE(COUNTROWS(FactOrders),KEEPFILTERS(FactOrders[OnTimeEligible]=TRUE()),KEEPFILTERS(FactOrders[IsOnTime]=TRUE())),CALCULATE(COUNTROWS(FactOrders),KEEPFILTERS(FactOrders[OnTimeEligible]=TRUE())))
```

### Average Delivery Days

Original validated measure (preserved). Format: `0.00`.

Average duration over duration-eligible orders only.

```dax
CALCULATE(AVERAGE(FactOrders[DeliveryDurationDays]),KEEPFILTERS(FactOrders[DurationEligible]=TRUE()))
```

### Unique Sales Customers

Previous dashboard measure (preserved). Format: `#,0`.

Distinct known CustomerUniqueID identities with sales-eligible orders in the current selection. Filters FactOrders first, then transfers its customer keys to DimCustomer with TREATAS. Not distinct CustomerID, not unfiltered dimension population.

```dax
VAR EligibleCustomerKeys = CALCULATETABLE(VALUES(FactOrders[CustomerKey]), KEEPFILTERS(FactOrders[SalesEligible] = TRUE())) RETURN COALESCE(CALCULATE(DISTINCTCOUNT(DimCustomer[CustomerUniqueID]), KEEPFILTERS(TREATAS(EligibleCustomerKeys, DimCustomer[CustomerKey])), KEEPFILTERS(DimCustomer[CustomerKey] <> 0), KEEPFILTERS(NOT ISBLANK(DimCustomer[CustomerUniqueID]))), 0)
```

### Repeat Sales Customers

Previous dashboard measure (preserved). Format: `#,0`.

Known customer identities with at least two distinct sales-eligible OrderKey values within the current selected dates and geography. Observed repeat purchasing, not cohort retention or lifetime behavior.

```dax
VAR IdentityOrders = CALCULATETABLE(SUMMARIZE(FactOrders, DimCustomer[CustomerUniqueID], "__Orders", DISTINCTCOUNT(FactOrders[OrderKey])), KEEPFILTERS(FactOrders[SalesEligible] = TRUE()), KEEPFILTERS(DimCustomer[CustomerKey] <> 0), KEEPFILTERS(NOT ISBLANK(DimCustomer[CustomerUniqueID]))) RETURN COALESCE(COUNTROWS(FILTER(IdentityOrders, [__Orders] >= 2)), 0)
```

### One-Time Sales Customers

Previous dashboard measure (preserved). Format: `#,0`.

Identities with exactly one eligible purchase in the current selection. One-time refers only to this selected observation window, not first-ever purchase or churn.

```dax
[Unique Sales Customers] - [Repeat Sales Customers]
```

### Repeat Customer Rate

Previous dashboard measure (preserved). Format: `0.00%`.

Repeat eligible identities divided by all known eligible identities within the current selection. Nonadditive across geography and time; not a retention rate.

```dax
DIVIDE([Repeat Sales Customers], [Unique Sales Customers])
```

### Customer Order Frequency

Previous dashboard measure (preserved). Format: `0.00`.

Sales-eligible order count for known identities divided by unique eligible identities, within the selected observation window.

```dax
DIVIDE(CALCULATE([Sales Order Count], KEEPFILTERS(DimCustomer[CustomerKey] <> 0), KEEPFILTERS(NOT ISBLANK(DimCustomer[CustomerUniqueID]))), [Unique Sales Customers])
```

### Sales Revenue per Customer

Previous dashboard measure (preserved). Format: `"R$" #,0.00`.

Eligible item revenue associated with known customer identities divided by distinct eligible identities. Preserves item-grain Sales Revenue; never sums order revenue into item revenue.

```dax
DIVIDE(CALCULATE([Sales Revenue], KEEPFILTERS(DimCustomer[CustomerKey] <> 0), KEEPFILTERS(NOT ISBLANK(DimCustomer[CustomerUniqueID]))), [Unique Sales Customers])
```

### Customer States with Sales

Previous dashboard measure (preserved). Format: `#,0`.

Distinct nonblank approximate ZIP-lookup states with known eligible customer identities in the current selection. Unknown geography is retained in other visuals but is not counted as a state.

```dax
COALESCE(COUNTROWS(FILTER(VALUES(DimCustomerGeography[ApproximateState]), NOT ISBLANK(DimCustomerGeography[ApproximateState]) && [Unique Sales Customers] > 0)), 0)
```

### Top Customer State

Previous dashboard measure (preserved). Format: ``.

Approximate customer state with the highest eligible item revenue in the current selection; deterministic alphabetical tie-break. Blank when there are no positive-revenue known states.

```dax
VAR StateRevenue = FILTER(ADDCOLUMNS(VALUES(DimCustomerGeography[ApproximateState]), "__Revenue", [Sales Revenue]), NOT ISBLANK(DimCustomerGeography[ApproximateState]) && [__Revenue] > 0) RETURN CONCATENATEX(TOPN(1, StateRevenue, [__Revenue], DESC, DimCustomerGeography[ApproximateState], ASC), DimCustomerGeography[ApproximateState], ", ")
```

### Top Customer State Revenue

Previous dashboard measure (preserved). Format: `"R$" #,0.00`.

Revenue of the top nonblank approximate customer state in the current selection; supporting tooltip for Top Customer State.

```dax
MAXX(FILTER(VALUES(DimCustomerGeography[ApproximateState]), NOT ISBLANK(DimCustomerGeography[ApproximateState])), [Sales Revenue])
```

### Customer Region Revenue Share

Previous dashboard measure (preserved). Format: `0.0%`.

Regional eligible revenue divided by revenue across the selected visible regions, preserving purchase-date, state and city slicers. Requires the proposed Customer Region display attribute.

```dax
DIVIDE([Sales Revenue], CALCULATE([Sales Revenue], ALLSELECTED(DimCustomerGeography[Customer Region])))
```

### Show Top 10 Customer Cities

Previous dashboard measure (preserved). Format: `0`.

Visual-only exact Top 10 city/state groups by eligible Sales Revenue within slicer selection, alphabetical tie-break. Use filter equals1 only on city visual, never page/report. Do not add other geography fields as tooltip grouping columns.

```dax
VAR Candidates = FILTER(ADDCOLUMNS(ALLSELECTED(DimCustomerGeography[Customer City State]), "__Revenue", [Sales Revenue]), [__Revenue] > 0) VAR Leaders = TOPN(10, Candidates, [__Revenue], DESC, DimCustomerGeography[Customer City State], ASC) VAR ThisCity = SELECTEDVALUE(DimCustomerGeography[Customer City State]) RETURN IF(ISINSCOPE(DimCustomerGeography[Customer City State]) && CONTAINS(Leaders, DimCustomerGeography[Customer City State], ThisCity), 1, 0)
```

### Delivered Orders

New final-report measure. Format: `#,0`.

All orders whose status is delivered. This includes delivered orders missing actual delivery dates; SLA eligibility is a separate denominator.

```dax
CALCULATE(COUNTROWS(FactOrders), KEEPFILTERS(DimOrderStatus[OrderStatus] = "delivered"))
```

### Timeliness Eligible Orders

New final-report measure. Format: `#,0`.

Delivered orders with actual and estimated delivery timestamps, using the preserved warehouse eligibility contract.

```dax
CALCULATE(COUNTROWS(FactOrders), KEEPFILTERS(FactOrders[OnTimeEligible] = TRUE()))
```

### On Time Deliveries

New final-report measure. Format: `#,0`.

Eligible orders delivered on or before estimated calendar date; preserves the original KPI.

```dax
CALCULATE([Timeliness Eligible Orders], KEEPFILTERS(FactOrders[IsOnTime] = TRUE()))
```

### Late Deliveries

New final-report measure. Format: `#,0`.

Eligible delivered orders after the estimated calendar date. Undelivered orders never enter this count.

```dax
CALCULATE([Timeliness Eligible Orders], KEEPFILTERS(FactOrders[IsOnTime] = FALSE()))
```

### Late Delivery Rate

New final-report measure. Format: `0.00%`.

Late deliveries / timeliness-eligible deliveries under the current filters.

```dax
DIVIDE([Late Deliveries], [Timeliness Eligible Orders])
```

### Delivered Freight Amount

New final-report measure. Format: `"R$" #,0.00`.

Sum the once-per-order aggregated freight for delivered orders. Never join freight to reviews or items for this measure.

```dax
CALCULATE(SUM(FactOrders[FreightAmount]), KEEPFILTERS(DimOrderStatus[OrderStatus] = "delivered"))
```

### Average Freight per Delivered Order

New final-report measure. Format: `"R$" #,0.00`.

Delivered order freight divided by all delivered orders, including zero-freight orders.

```dax
DIVIDE([Delivered Freight Amount], [Delivered Orders])
```

### Average Late Delay Days

New final-report measure. Format: `0.00`.

Mean calendar-day lateness among eligible late orders. Different from elapsed purchase-to-delivery duration.

```dax
AVERAGEX(FILTER(FactOrders, FactOrders[OnTimeEligible] = TRUE() && FactOrders[IsOnTime] = FALSE()), INT(FactOrders[ActualDeliveryTimestamp]) - INT(FactOrders[EstimatedDeliveryTimestamp]))
```

### Duration Eligible Orders

New final-report measure. Format: `#,0`.

Delivered orders with valid chronology and usable purchase and actual timestamps, matching the existing duration contract.

```dax
CALCULATE(COUNTROWS(FactOrders), KEEPFILTERS(FactOrders[DurationEligible] = TRUE()))
```

### Category On Time Delivery Rate

New final-report measure. Format: `0.00%`.

Distinct order-key semijoin from items to orders. A multi-category order contributes once to each applicable category; categories are non-additive.

```dax
VAR OrdersInCategory = VALUES(FactOrderItems[OrderKey]) RETURN CALCULATE([On Time Delivery Rate], KEEPFILTERS(TREATAS(OrdersInCategory, FactOrders[OrderKey])))
```

### Category Eligible Deliveries

New final-report measure. Format: `#,0`.

Timeliness denominator within each category using a distinct order-key semijoin.

```dax
VAR OrdersInCategory = VALUES(FactOrderItems[OrderKey]) RETURN CALCULATE([Timeliness Eligible Orders], KEEPFILTERS(TREATAS(OrdersInCategory, FactOrders[OrderKey])))
```

### Show Delivery Top 10 States

New final-report measure. Format: `0`.

Visual-only exact Top 10 by selected population volume; alphabetical tie-break. Never apply at page/report level.

```dax
VAR Candidates = FILTER(ADDCOLUMNS(ALLSELECTED(DimCustomerGeography[ApproximateState]), "__Volume", [Delivered Orders]), NOT ISBLANK(DimCustomerGeography[ApproximateState]) && [__Volume] > 0) VAR Leaders = TOPN(10, Candidates, [__Volume], DESC, DimCustomerGeography[ApproximateState], ASC) VAR CurrentGroup = SELECTEDVALUE(DimCustomerGeography[ApproximateState]) RETURN IF(ISINSCOPE(DimCustomerGeography[ApproximateState]) && CONTAINS(Leaders, DimCustomerGeography[ApproximateState], CurrentGroup), 1, 0)
```

### Show Delivery Top 10 Categories

New final-report measure. Format: `0`.

Visual-only exact Top 10 by selected population volume; alphabetical tie-break. Never apply at page/report level.

```dax
VAR Candidates = FILTER(ADDCOLUMNS(ALLSELECTED(DimProduct[CategoryLabel]), "__Volume", [Category Eligible Deliveries]), NOT ISBLANK(DimProduct[CategoryLabel]) && [__Volume] > 0) VAR Leaders = TOPN(10, Candidates, [__Volume], DESC, DimProduct[CategoryLabel], ASC) VAR CurrentGroup = SELECTEDVALUE(DimProduct[CategoryLabel]) RETURN IF(ISINSCOPE(DimProduct[CategoryLabel]) && CONTAINS(Leaders, DimProduct[CategoryLabel], CurrentGroup), 1, 0)
```

## FactPayments

### Payment Amount

Original validated measure (preserved). Format: `#,0.00`.

Payment-grain amount. Includes its own business scope; not product/seller-attributed revenue.

```dax
SUM(FactPayments[PaymentAmount])
```

## FactReviews

### Review Count

Original validated measure (preserved). Format: `#,0`.

Count of loaded review rows. ReviewID is not unique; no deduplication was applied.

```dax
COUNTROWS(FactReviews)
```

### Average Review Score

Original validated measure (preserved). Format: `0.00`.

Average across valid review rows. Not an average of customer or order averages.

```dax
CALCULATE(AVERAGE(FactReviews[ReviewScore]), KEEPFILTERS(FactReviews[ValidScore]=TRUE()))
```

### Total Valid Reviews

New final-report measure. Format: `#,0`.

All valid loaded review rows, all order statuses. Retains multiple reviews per order and transfers order timeliness selections without item-row expansion. Referential integrity requires every review order to exist.

```dax
CALCULATE(COUNTROWS(FactReviews), KEEPFILTERS(FactReviews[ValidScore] = TRUE()), KEEPFILTERS(TREATAS(VALUES(FactOrders[OrderKey]), FactReviews[OrderKey])))
```

### Satisfaction Average Review Score

New final-report measure. Format: `0.00`.

Mean valid review row score across all statuses; order-key semijoin makes timeliness cross-filtering explicit. Same unfiltered population as the original Average Review Score.

```dax
CALCULATE(AVERAGE(FactReviews[ReviewScore]), KEEPFILTERS(FactReviews[ValidScore] = TRUE()), KEEPFILTERS(TREATAS(VALUES(FactOrders[OrderKey]), FactReviews[OrderKey])))
```

### Positive Review Rate

New final-report measure. Format: `0.00%`.

Scores 4 or 5 / all valid reviews in current selection. Zero matching numerator rows returns 0%; an empty denominator remains undefined. A score slicer intentionally changes the denominator; score 3 is neutral.

```dax
DIVIDE(COALESCE(CALCULATE([Total Valid Reviews], KEEPFILTERS(FactReviews[ReviewScore] >= 4)), 0), [Total Valid Reviews])
```

### Negative Review Rate

New final-report measure. Format: `0.00%`.

Scores 1 or 2 / all valid reviews in current selection. Zero matching numerator rows returns 0%; an empty denominator remains undefined. A score slicer intentionally changes the denominator; score 3 is neutral.

```dax
DIVIDE(COALESCE(CALCULATE([Total Valid Reviews], KEEPFILTERS(FactReviews[ReviewScore] <= 2)), 0), [Total Valid Reviews])
```

### Five Star Review Rate

New final-report measure. Format: `0.00%`.

Score 5 / all valid reviews in current selection. Zero matching numerator rows returns 0%; an empty denominator remains undefined. A score slicer intentionally changes the denominator; score 3 is neutral.

```dax
DIVIDE(COALESCE(CALCULATE([Total Valid Reviews], KEEPFILTERS(FactReviews[ReviewScore] = 5)), 0), [Total Valid Reviews])
```

### On Time Average Review Score

New final-report measure. Format: `0.00`.

Average valid review row score for timeliness-eligible on-time orders, retaining review-date/geography/score filters.

```dax
CALCULATE([Satisfaction Average Review Score], KEEPFILTERS(FactOrders[OnTimeEligible] = TRUE()), KEEPFILTERS(FactOrders[IsOnTime] = TRUE()))
```

### Late Average Review Score

New final-report measure. Format: `0.00`.

Average valid review row score for timeliness-eligible late orders, retaining review-date/geography/score filters.

```dax
CALCULATE([Satisfaction Average Review Score], KEEPFILTERS(FactOrders[OnTimeEligible] = TRUE()), KEEPFILTERS(FactOrders[IsOnTime] = FALSE()))
```

### Late vs On Time Review Score

New final-report measure. Format: ``.

Display late / on-time means; N/A if either comparison group is absent. Association does not establish causation.

```dax
VAR LateScore = [Late Average Review Score] VAR OnTimeScore = [On Time Average Review Score] RETURN IF(ISBLANK(LateScore) || ISBLANK(OnTimeScore), "N/A", FORMAT(LateScore, "0.00") & " / " & FORMAT(OnTimeScore, "0.00"))
```

### Category Average Review Score

New final-report measure. Format: `0.00`.

Valid review rows for orders containing a category; each review counted once per category using a distinct order-key semijoin. Multi-category orders can appear in several categories. No item-level attribution is claimed.

```dax
VAR OrdersInCategory = VALUES(FactOrderItems[OrderKey]) RETURN CALCULATE([Satisfaction Average Review Score], KEEPFILTERS(TREATAS(OrdersInCategory, FactReviews[OrderKey])))
```

### Category Valid Reviews

New final-report measure. Format: `#,0`.

Category review denominator using a distinct-order-key semijoin; category totals are non-additive.

```dax
VAR OrdersInCategory = VALUES(FactOrderItems[OrderKey]) RETURN CALCULATE([Total Valid Reviews], KEEPFILTERS(TREATAS(OrdersInCategory, FactReviews[OrderKey])))
```

### Show Review Top 10 States

New final-report measure. Format: `0`.

Visual-only exact Top 10 by selected population volume; alphabetical tie-break. Never apply at page/report level.

```dax
VAR Candidates = FILTER(ADDCOLUMNS(ALLSELECTED(DimCustomerGeography[ApproximateState]), "__Volume", [Total Valid Reviews]), NOT ISBLANK(DimCustomerGeography[ApproximateState]) && [__Volume] > 0) VAR Leaders = TOPN(10, Candidates, [__Volume], DESC, DimCustomerGeography[ApproximateState], ASC) VAR CurrentGroup = SELECTEDVALUE(DimCustomerGeography[ApproximateState]) RETURN IF(ISINSCOPE(DimCustomerGeography[ApproximateState]) && CONTAINS(Leaders, DimCustomerGeography[ApproximateState], CurrentGroup), 1, 0)
```

### Show Review Top 10 Categories

New final-report measure. Format: `0`.

Visual-only exact Top 10 by selected population volume; alphabetical tie-break. Never apply at page/report level.

```dax
VAR Candidates = FILTER(ADDCOLUMNS(ALLSELECTED(DimProduct[CategoryLabel]), "__Volume", [Category Valid Reviews]), NOT ISBLANK(DimProduct[CategoryLabel]) && [__Volume] > 0) VAR Leaders = TOPN(10, Candidates, [__Volume], DESC, DimProduct[CategoryLabel], ASC) VAR CurrentGroup = SELECTEDVALUE(DimProduct[CategoryLabel]) RETURN IF(ISINSCOPE(DimProduct[CategoryLabel]) && CONTAINS(Leaders, DimProduct[CategoryLabel], CurrentGroup), 1, 0)
```

## Calculated display columns

### FactOrders[Delivery Timeliness]

Calendar-date SLA classification. Not eligible includes undelivered or missing-date orders; never relabel them late.

```dax
IF(FactOrders[OnTimeEligible] = TRUE(), IF(FactOrders[IsOnTime] = TRUE(), "On time", "Late"), "Not eligible")
```

### FactOrders[Delivery Duration Band]

Elapsed-day duration bins, only for duration-eligible orders. Prefixes preserve chronological sort.

```dax
IF(FactOrders[DurationEligible] <> TRUE(), BLANK(), SWITCH(TRUE(), FactOrders[DeliveryDurationDays] < 7, "01 | Under 7 days", FactOrders[DeliveryDurationDays] < 14, "02 | 7 to <14 days", FactOrders[DeliveryDurationDays] < 21, "03 | 14 to <21 days", FactOrders[DeliveryDurationDays] < 30, "04 | 21 to <30 days", "05 | 30+ days"))
```

