# Data dictionary

## Scope and authority

This field inventory is derived from `warehouse_contract.json` and the retained SQL schema dictionary. It describes the accepted snapshot schema, rather than asserting that every optional upstream value is populated. The SQL DDL and source mappings are the executable authority. All money uses BRL decimal amounts; identifiers and ZIP prefixes preserve string semantics.

## Business grains

| Entity | Natural grain | Purpose |
| --- | --- | --- |
| FactOrders | OrderID | All order statuses, order totals and eligibility |
| FactOrderItems | OrderID + OrderItemID | Item merchandise, product, seller and freight |
| FactPayments | OrderID + PaymentSequential | Recorded payment sequence |
| FactReviews | ReviewID + OrderID | Review/order record; multiple reviews per order retained |
| DimCustomer | CustomerID | Source customer record; CustomerUniqueID links purchasing identity |
| DimProduct | ProductID | Category and physical metadata |
| DimSeller | SellerID | Source seller and geography role |
| DimGeography | ZipCodePrefix | Representative ZIP plus unmatched source prefixes |
| DimDate | DateKey | Calendar day; key 0 is unknown |
| DimOrderStatus | OrderStatus | Observed status, no inferred transition history |
| DimPaymentType | PaymentType | Recorded payment method |

## Derived concepts

| Field family | Meaning |
|---|---|
| SalesEligible | Delivered order with recorded items; propagated to children |
| OnTimeEligible / IsOnTime | Delivered with actual/estimated dates; compare calendar dates |
| DurationEligible / DeliveryDurationDays | Valid elapsed purchase-to-delivery endpoints with chronology rules |
| ValidScore | Integer review score 1–5; absent optional text does not invalidate it |
| MerchandiseRevenue / FreightAmount | Item amounts aggregated once per order; NULL when no items exist |
| SourceCity / SourceState | Preserved source labels |
| ApproximateCity / ApproximateState | Deterministic ZIP representative, not a verified address |
| CategoryMissing / CategoryUntranslated | Missing source category versus absent English translation |
| dq_* / SourceQualityFlagCount | Row/rule flags or overlapping flag counts |
| LoadID / SourceRow | Load lineage and one-based parsed input record position |
| HasTitle / HasMessage | Presence of optional review text; raw text is not stored in FactReviews |

Dimensions include surrogate unknown members at key 0. Timestamps have no verified original timezone. Physical SQL foreign keys do not imply active fact-to-fact relationships in Power BI. Read the [KPI dictionary](kpi_definitions.md) for calculation populations.

## Processed input fields

### customers

File: `data/processed/customers_clean.csv`. Expected rows: **99,441**. Key: **customer_id**.

| Column | SQL staging type | Nullable |
| --- | --- | --- |
| customer_id | varchar(32) | No |
| customer_unique_id | varchar(32) | No |
| customer_zip_code_prefix | varchar(5) | No |
| customer_city | nvarchar(128) | No |
| customer_state | varchar(2) | No |
| dq_unmatched_zip | bit | No |
| dq_invalid_zip_format | bit | No |

### orders

File: `data/processed/orders_clean.csv`. Expected rows: **99,441**. Key: **order_id**.

| Column | SQL staging type | Nullable |
| --- | --- | --- |
| order_id | varchar(32) | No |
| customer_id | varchar(32) | No |
| order_status | varchar(32) | No |
| order_purchase_timestamp | datetime2(0) | Yes |
| order_approved_at | datetime2(0) | Yes |
| order_delivered_carrier_date | datetime2(0) | Yes |
| order_delivered_customer_date | datetime2(0) | Yes |
| order_estimated_delivery_date | datetime2(0) | Yes |
| dq_invalid_order_purchase_timestamp | bit | No |
| dq_invalid_order_approved_at | bit | No |
| dq_invalid_order_delivered_carrier_date | bit | No |
| dq_invalid_order_delivered_customer_date | bit | No |
| dq_invalid_order_estimated_delivery_date | bit | No |
| dq_no_items | bit | No |
| dq_no_payments | bit | No |
| dq_no_reviews | bit | No |
| dq_missing_order_approved_at | bit | No |
| dq_delivered_missing_order_approved_at | bit | No |
| dq_missing_order_delivered_carrier_date | bit | No |
| dq_delivered_missing_order_delivered_carrier_date | bit | No |
| dq_missing_order_delivered_customer_date | bit | No |
| dq_delivered_missing_order_delivered_customer_date | bit | No |
| dq_approval_before_purchase | bit | No |
| dq_carrier_before_purchase | bit | No |
| dq_delivery_before_purchase | bit | No |
| dq_carrier_before_approval | bit | No |
| dq_delivery_before_carrier | bit | No |

### order_items

File: `data/processed/order_items_clean.csv`. Expected rows: **112,650**. Key: **order_id, order_item_id**.

| Column | SQL staging type | Nullable |
| --- | --- | --- |
| order_id | varchar(32) | No |
| order_item_id | varchar(10) | No |
| product_id | varchar(32) | No |
| seller_id | varchar(32) | No |
| shipping_limit_date | datetime2(0) | Yes |
| price | decimal(19,2) | No |
| freight_value | decimal(19,2) | No |
| dq_invalid_shipping_limit_date | bit | No |
| dq_invalid_price | bit | No |
| dq_invalid_freight_value | bit | No |
| dq_shipping_limit_before_purchase | bit | No |
| dq_shipping_limit_after_purchase_year_range | bit | No |
| dq_negative_price | bit | No |
| dq_zero_price | bit | No |
| dq_negative_freight_value | bit | No |
| dq_zero_freight_value | bit | No |

### payments

File: `data/processed/payments_clean.csv`. Expected rows: **103,886**. Key: **order_id, payment_sequential**.

| Column | SQL staging type | Nullable |
| --- | --- | --- |
| order_id | varchar(32) | No |
| payment_sequential | varchar(10) | No |
| payment_type | varchar(32) | No |
| payment_installments | int | Yes |
| payment_value | decimal(19,2) | No |
| dq_invalid_payment_installments | bit | No |
| dq_invalid_payment_value | bit | No |
| dq_negative_payment_value | bit | No |
| dq_zero_payment_value | bit | No |
| dq_nonpositive_installments | bit | No |
| dq_noninteger_payment_installments | bit | No |

### reviews

File: `data/processed/reviews_clean.csv`. Expected rows: **99,224**. Key: **review_id, order_id**.

| Column | SQL staging type | Nullable |
| --- | --- | --- |
| review_id | varchar(32) | No |
| order_id | varchar(32) | No |
| review_score | int | Yes |
| review_comment_title | nvarchar(200) | Yes |
| review_comment_message | nvarchar(2000) | Yes |
| review_creation_date | datetime2(0) | Yes |
| review_answer_timestamp | datetime2(0) | Yes |
| dq_invalid_review_creation_date | bit | No |
| dq_invalid_review_answer_timestamp | bit | No |
| dq_invalid_review_score | bit | No |
| dq_answer_before_creation | bit | No |
| dq_noninteger_review_score | bit | No |
| dq_score_out_of_range | bit | No |
| dq_repeated_review_id | bit | No |

### products

File: `data/processed/products_clean.csv`. Expected rows: **32,951**. Key: **product_id**.

| Column | SQL staging type | Nullable |
| --- | --- | --- |
| product_id | varchar(32) | No |
| product_category_name | nvarchar(128) | No |
| product_name_lenght | int | Yes |
| product_description_lenght | int | Yes |
| product_photos_qty | int | Yes |
| product_weight_g | int | Yes |
| product_length_cm | int | Yes |
| product_height_cm | int | Yes |
| product_width_cm | int | Yes |
| dq_invalid_product_name_lenght | bit | No |
| dq_invalid_product_description_lenght | bit | No |
| dq_invalid_product_photos_qty | bit | No |
| dq_invalid_product_weight_g | bit | No |
| dq_invalid_product_length_cm | bit | No |
| dq_invalid_product_height_cm | bit | No |
| dq_invalid_product_width_cm | bit | No |
| dq_category_missing | bit | No |
| dq_category_untranslated | bit | No |
| product_category_name_english | nvarchar(128) | No |
| dq_missing_attributes | bit | No |
| dq_nonpositive_product_weight_g | bit | No |
| dq_nonpositive_product_length_cm | bit | No |
| dq_nonpositive_product_height_cm | bit | No |
| dq_nonpositive_product_width_cm | bit | No |

### sellers

File: `data/processed/sellers_clean.csv`. Expected rows: **3,095**. Key: **seller_id**.

| Column | SQL staging type | Nullable |
| --- | --- | --- |
| seller_id | varchar(32) | No |
| seller_zip_code_prefix | varchar(5) | No |
| seller_city | nvarchar(128) | No |
| seller_state | varchar(2) | No |
| dq_unmatched_zip | bit | No |
| dq_invalid_zip_format | bit | No |

### category_translations

File: `data/processed/category_translations_clean.csv`. Expected rows: **71**. Key: **product_category_name**.

| Column | SQL staging type | Nullable |
| --- | --- | --- |
| product_category_name | nvarchar(128) | No |
| product_category_name_english | nvarchar(128) | No |

### geolocation

File: `data/processed/geolocation_clean.csv`. Expected rows: **738,332**. Key: **complete observation signature**.

| Column | SQL staging type | Nullable |
| --- | --- | --- |
| geolocation_zip_code_prefix | varchar(5) | No |
| geolocation_lat | decimal(28,20) | No |
| geolocation_lng | decimal(28,20) | No |
| geolocation_city | nvarchar(128) | No |
| geolocation_state | varchar(2) | No |
| dq_invalid_geolocation_lat | bit | No |
| dq_invalid_geolocation_lng | bit | No |
| dq_invalid_zip_format | bit | No |
| dq_invalid_coordinate | bit | No |

### geolocation_zip_lookup

File: `data/processed/geolocation_zip_lookup.csv`. Expected rows: **19,015**. Key: **zip_code_prefix**.

| Column | SQL staging type | Nullable |
| --- | --- | --- |
| zip_code_prefix | varchar(5) | No |
| geolocation_state | varchar(2) | No |
| geolocation_city | nvarchar(128) | No |
| geolocation_lat | decimal(28,20) | No |
| geolocation_lng | decimal(28,20) | No |
| distinct_observations | int | No |
| distinct_city_labels | int | No |
| distinct_states | int | No |
| distinct_coordinate_pairs | int | No |
| coordinate_repetitions_excess | int | No |
| source_rows | int | No |
| dq_conflicting_city_labels | bit | No |
| dq_conflicting_states | bit | No |
| dq_missing_coordinate | bit | No |

## Warehouse and audit fields

The following lists physical `dw` and `audit` fields. Staging fields are described by the input contract above. Source expressions are expanded in the [source-to-target mapping](../reports/phase_4_source_to_target_mapping.csv).

### audit.LoadFile

Grain: audit metadata. History: snapshot / load audit.

| Column | SQL type | Nullable | Identity | Source / meaning |
| --- | --- | --- | --- | --- |
| LoadID | uniqueidentifier | False | False | ETL load metadata |
| FileName | nvarchar(128) | False | False | ETL load metadata |
| SHA256 | char(64) | False | False | ETL load metadata |
| SourceRows | bigint | False | False | ETL load metadata |
| StagedRows | bigint | False | False | ETL load metadata |

### audit.LoadRun

Grain: audit metadata. History: snapshot / load audit.

| Column | SQL type | Nullable | Identity | Source / meaning |
| --- | --- | --- | --- | --- |
| LoadID | uniqueidentifier | False | False | ETL load metadata |
| StartedAtUTC | datetime2(3) | False | False | ETL load metadata |
| FinishedAtUTC | datetime2(3) | True | False | ETL load metadata |
| Status | varchar(20) | False | False | ETL load metadata |
| SourceFingerprint | char(64) | False | False | ETL load metadata |
| ErrorMessage | nvarchar(4000) | True | False | ETL load metadata |

### audit.ValidationResult

Grain: audit metadata. History: snapshot / load audit.

| Column | SQL type | Nullable | Identity | Source / meaning |
| --- | --- | --- | --- | --- |
| ValidationID | bigint | False | True | ETL load metadata |
| LoadID | uniqueidentifier | False | False | ETL load metadata |
| CheckName | nvarchar(200) | False | False | ETL load metadata |
| Status | varchar(20) | False | False | ETL load metadata |
| ActualValue | nvarchar(200) | True | False | ETL load metadata |
| ExpectedValue | nvarchar(200) | True | False | ETL load metadata |
| Details | nvarchar(2000) | True | False | ETL load metadata |
| CheckedAtUTC | datetime2(3) | False | False | ETL load metadata |

### audit.WarehouseMetadata

Grain: audit metadata. History: snapshot / load audit.

| Column | SQL type | Nullable | Identity | Source / meaning |
| --- | --- | --- | --- | --- |
| ProjectName | nvarchar(128) | False | False | ETL load metadata |
| SchemaVersion | int | False | False | ETL load metadata |
| CreatedAtUTC | datetime2(3) | False | False | ETL load metadata |

### dw.DimCustomer

Grain: one source customer_id; customer_unique_id is an identity attribute. History: Type 1 source snapshot.

| Column | SQL type | Nullable | Identity | Source / meaning |
| --- | --- | --- | --- | --- |
| CustomerKey | int | False | True | sql/08_load_warehouse.sql: DimCustomer explicit INSERT/UPDATE mapping |
| CustomerID | varchar(32) | False | False | s.customer_id; FROM stg.customers s LEFT JOIN dw.DimGeography g ON g.ZipCodePrefix=s.customer_zip_code_prefix |
| CustomerUniqueID | varchar(32) | True | False | s.customer_unique_id; FROM stg.customers s LEFT JOIN dw.DimGeography g ON g.ZipCodePrefix=s.customer_zip_code_prefix |
| SourceZipCodePrefix | varchar(5) | True | False | s.customer_zip_code_prefix; FROM stg.customers s LEFT JOIN dw.DimGeography g ON g.ZipCodePrefix=s.customer_zip_code_prefix |
| SourceCity | nvarchar(128) | True | False | s.customer_city; FROM stg.customers s LEFT JOIN dw.DimGeography g ON g.ZipCodePrefix=s.customer_zip_code_prefix |
| SourceState | varchar(2) | True | False | s.customer_state; FROM stg.customers s LEFT JOIN dw.DimGeography g ON g.ZipCodePrefix=s.customer_zip_code_prefix |
| GeographyKey | int | False | False | COALESCE(g.GeographyKey,0); FROM stg.customers s LEFT JOIN dw.DimGeography g ON g.ZipCodePrefix=s.customer_zip_code_prefix |
| UnmatchedZip | bit | False | False | s.dq_unmatched_zip; FROM stg.customers s LEFT JOIN dw.DimGeography g ON g.ZipCodePrefix=s.customer_zip_code_prefix |

### dw.DimDate

Grain: one calendar date; key 0 unknown. History: calendar.

| Column | SQL type | Nullable | Identity | Source / meaning |
| --- | --- | --- | --- | --- |
| DateKey | int | False | False | sql/08_load_warehouse.sql: DimDate explicit INSERT/UPDATE mapping |
| FullDate | date | True | False | sql/08_load_warehouse.sql: DimDate explicit INSERT/UPDATE mapping |
| Day | tinyint | True | False | sql/08_load_warehouse.sql: DimDate explicit INSERT/UPDATE mapping |
| Month | tinyint | True | False | sql/08_load_warehouse.sql: DimDate explicit INSERT/UPDATE mapping |
| MonthName | varchar(12) | False | False | sql/08_load_warehouse.sql: DimDate explicit INSERT/UPDATE mapping |
| Quarter | tinyint | True | False | sql/08_load_warehouse.sql: DimDate explicit INSERT/UPDATE mapping |
| Year | smallint | True | False | sql/08_load_warehouse.sql: DimDate explicit INSERT/UPDATE mapping |
| YearMonth | char(7) | True | False | sql/08_load_warehouse.sql: DimDate explicit INSERT/UPDATE mapping |
| DayOfWeek | tinyint | True | False | sql/08_load_warehouse.sql: DimDate explicit INSERT/UPDATE mapping |
| DayName | varchar(12) | False | False | sql/08_load_warehouse.sql: DimDate explicit INSERT/UPDATE mapping |
| IsWeekend | bit | True | False | sql/08_load_warehouse.sql: DimDate explicit INSERT/UPDATE mapping |

### dw.DimGeography

Grain: one ZIP prefix; key 0 unknown. History: Type 1 source snapshot.

| Column | SQL type | Nullable | Identity | Source / meaning |
| --- | --- | --- | --- | --- |
| GeographyKey | int | False | True | sql/08_load_warehouse.sql: DimGeography explicit INSERT/UPDATE mapping |
| ZipCodePrefix | varchar(5) | False | False | z.zip; FROM (SELECT zip_code_prefix zip FROM stg.geolocation_zip_lookup UNION SELECT customer_zip_code_prefix FROM stg.customers UNION SELECT seller_zip_code_prefix FROM stg.sellers) z LEFT JOIN stg.geolocation_zip_lookup g ON g.zip_code_prefix=z.zip |
| ApproximateCity | nvarchar(128) | True | False | g.geolocation_city; FROM (SELECT zip_code_prefix zip FROM stg.geolocation_zip_lookup UNION SELECT customer_zip_code_prefix FROM stg.customers UNION SELECT seller_zip_code_prefix FROM stg.sellers) z LEFT JOIN stg.geolocation_zip_lookup g ON g.zip_code_prefix=z.zip |
| ApproximateState | varchar(2) | True | False | g.geolocation_state; FROM (SELECT zip_code_prefix zip FROM stg.geolocation_zip_lookup UNION SELECT customer_zip_code_prefix FROM stg.customers UNION SELECT seller_zip_code_prefix FROM stg.sellers) z LEFT JOIN stg.geolocation_zip_lookup g ON g.zip_code_prefix=z.zip |
| Latitude | decimal(28,20) | True | False | g.geolocation_lat; FROM (SELECT zip_code_prefix zip FROM stg.geolocation_zip_lookup UNION SELECT customer_zip_code_prefix FROM stg.customers UNION SELECT seller_zip_code_prefix FROM stg.sellers) z LEFT JOIN stg.geolocation_zip_lookup g ON g.zip_code_prefix=z.zip |
| Longitude | decimal(28,20) | True | False | g.geolocation_lng; FROM (SELECT zip_code_prefix zip FROM stg.geolocation_zip_lookup UNION SELECT customer_zip_code_prefix FROM stg.customers UNION SELECT seller_zip_code_prefix FROM stg.sellers) z LEFT JOIN stg.geolocation_zip_lookup g ON g.zip_code_prefix=z.zip |
| LookupMatched | bit | False | False | CAST(CASE WHEN g.zip_code_prefix IS NULL THEN 0 ELSE 1 END AS bit); FROM (SELECT zip_code_prefix zip FROM stg.geolocation_zip_lookup UNION SELECT customer_zip_code_prefix FROM stg.customers UNION SELECT seller_zip_code_prefix FROM stg.sellers) z LEFT JOIN stg.geolocation_zip_lookup g ON g.zip_code_prefix=z.zip |
| ConflictingCities | bit | False | False | COALESCE(g.dq_conflicting_city_labels,0); FROM (SELECT zip_code_prefix zip FROM stg.geolocation_zip_lookup UNION SELECT customer_zip_code_prefix FROM stg.customers UNION SELECT seller_zip_code_prefix FROM stg.sellers) z LEFT JOIN stg.geolocation_zip_lookup g ON g.zip_code_prefix=z.zip |
| ConflictingStates | bit | False | False | COALESCE(g.dq_conflicting_states,0); FROM (SELECT zip_code_prefix zip FROM stg.geolocation_zip_lookup UNION SELECT customer_zip_code_prefix FROM stg.customers UNION SELECT seller_zip_code_prefix FROM stg.sellers) z LEFT JOIN stg.geolocation_zip_lookup g ON g.zip_code_prefix=z.zip |
| DistinctCityLabels | int | True | False | g.distinct_city_labels; FROM (SELECT zip_code_prefix zip FROM stg.geolocation_zip_lookup UNION SELECT customer_zip_code_prefix FROM stg.customers UNION SELECT seller_zip_code_prefix FROM stg.sellers) z LEFT JOIN stg.geolocation_zip_lookup g ON g.zip_code_prefix=z.zip |
| DistinctStateLabels | int | True | False | g.distinct_states; FROM (SELECT zip_code_prefix zip FROM stg.geolocation_zip_lookup UNION SELECT customer_zip_code_prefix FROM stg.customers UNION SELECT seller_zip_code_prefix FROM stg.sellers) z LEFT JOIN stg.geolocation_zip_lookup g ON g.zip_code_prefix=z.zip |

### dw.DimOrderStatus

Grain: one order_status. History: Type 1 source snapshot.

| Column | SQL type | Nullable | Identity | Source / meaning |
| --- | --- | --- | --- | --- |
| OrderStatusKey | int | False | True | sql/08_load_warehouse.sql: DimOrderStatus explicit INSERT/UPDATE mapping |
| OrderStatus | varchar(32) | False | False | order_status; FROM (SELECT DISTINCT order_status FROM stg.orders) s |

### dw.DimPaymentType

Grain: one payment_type. History: Type 1 source snapshot.

| Column | SQL type | Nullable | Identity | Source / meaning |
| --- | --- | --- | --- | --- |
| PaymentTypeKey | int | False | True | sql/08_load_warehouse.sql: DimPaymentType explicit INSERT/UPDATE mapping |
| PaymentType | varchar(32) | False | False | payment_type; FROM (SELECT DISTINCT payment_type FROM stg.payments) s |

### dw.DimProduct

Grain: one product_id. History: Type 1 source snapshot.

| Column | SQL type | Nullable | Identity | Source / meaning |
| --- | --- | --- | --- | --- |
| ProductKey | int | False | True | sql/08_load_warehouse.sql: DimProduct explicit INSERT/UPDATE mapping |
| ProductID | varchar(32) | False | False | s.product_id; FROM stg.products s |
| SourceCategory | nvarchar(128) | True | False | s.product_category_name; FROM stg.products s |
| EnglishCategory | nvarchar(128) | True | False | s.product_category_name_english; FROM stg.products s |
| CategoryLabel | nvarchar(160) | False | False | CASE WHEN s.dq_category_missing=1 THEN N'Unknown (missing category)' WHEN s.dq_category_untranslated=1 THEN N'Untranslated: '+s.product_category_name ELSE s.product_category_name_english END; FROM stg.products s |
| CategoryMissing | bit | False | False | s.dq_category_missing; FROM stg.products s |
| CategoryUntranslated | bit | False | False | s.dq_category_untranslated; FROM stg.products s |
| NameLength | int | True | False | s.product_name_lenght; FROM stg.products s |
| DescriptionLength | int | True | False | s.product_description_lenght; FROM stg.products s |
| PhotosQuantity | int | True | False | s.product_photos_qty; FROM stg.products s |
| WeightGrams | int | True | False | s.product_weight_g; FROM stg.products s |
| LengthCM | int | True | False | s.product_length_cm; FROM stg.products s |
| HeightCM | int | True | False | s.product_height_cm; FROM stg.products s |
| WidthCM | int | True | False | s.product_width_cm; FROM stg.products s |

### dw.DimSeller

Grain: one seller_id. History: Type 1 source snapshot.

| Column | SQL type | Nullable | Identity | Source / meaning |
| --- | --- | --- | --- | --- |
| SellerKey | int | False | True | sql/08_load_warehouse.sql: DimSeller explicit INSERT/UPDATE mapping |
| SellerID | varchar(32) | False | False | s.seller_id; FROM stg.sellers s LEFT JOIN dw.DimGeography g ON g.ZipCodePrefix=s.seller_zip_code_prefix |
| SourceZipCodePrefix | varchar(5) | True | False | s.seller_zip_code_prefix; FROM stg.sellers s LEFT JOIN dw.DimGeography g ON g.ZipCodePrefix=s.seller_zip_code_prefix |
| SourceCity | nvarchar(128) | True | False | s.seller_city; FROM stg.sellers s LEFT JOIN dw.DimGeography g ON g.ZipCodePrefix=s.seller_zip_code_prefix |
| SourceState | varchar(2) | True | False | s.seller_state; FROM stg.sellers s LEFT JOIN dw.DimGeography g ON g.ZipCodePrefix=s.seller_zip_code_prefix |
| GeographyKey | int | False | False | COALESCE(g.GeographyKey,0); FROM stg.sellers s LEFT JOIN dw.DimGeography g ON g.ZipCodePrefix=s.seller_zip_code_prefix |
| UnmatchedZip | bit | False | False | s.dq_unmatched_zip; FROM stg.sellers s LEFT JOIN dw.DimGeography g ON g.ZipCodePrefix=s.seller_zip_code_prefix |

### dw.FactOrderItems

Grain: one (order_id,order_item_id). History: snapshot / load audit.

| Column | SQL type | Nullable | Identity | Source / meaning |
| --- | --- | --- | --- | --- |
| OrderID | varchar(32) | False | False | s.order_id; FROM stg.order_items s JOIN dw.FactOrders o ON o.OrderID=s.order_id LEFT JOIN dw.DimProduct p ON p.ProductID=s.product_id LEFT JOIN dw.DimSeller v ON v.SellerID=s.seller_id |
| OrderItemID | varchar(10) | False | False | s.order_item_id; FROM stg.order_items s JOIN dw.FactOrders o ON o.OrderID=s.order_id LEFT JOIN dw.DimProduct p ON p.ProductID=s.product_id LEFT JOIN dw.DimSeller v ON v.SellerID=s.seller_id |
| OrderKey | int | False | False | o.OrderKey; FROM stg.order_items s JOIN dw.FactOrders o ON o.OrderID=s.order_id LEFT JOIN dw.DimProduct p ON p.ProductID=s.product_id LEFT JOIN dw.DimSeller v ON v.SellerID=s.seller_id |
| SourceProductID | varchar(32) | False | False | s.product_id; FROM stg.order_items s JOIN dw.FactOrders o ON o.OrderID=s.order_id LEFT JOIN dw.DimProduct p ON p.ProductID=s.product_id LEFT JOIN dw.DimSeller v ON v.SellerID=s.seller_id |
| SourceSellerID | varchar(32) | False | False | s.seller_id; FROM stg.order_items s JOIN dw.FactOrders o ON o.OrderID=s.order_id LEFT JOIN dw.DimProduct p ON p.ProductID=s.product_id LEFT JOIN dw.DimSeller v ON v.SellerID=s.seller_id |
| ProductKey | int | False | False | COALESCE(p.ProductKey,0); FROM stg.order_items s JOIN dw.FactOrders o ON o.OrderID=s.order_id LEFT JOIN dw.DimProduct p ON p.ProductID=s.product_id LEFT JOIN dw.DimSeller v ON v.SellerID=s.seller_id |
| SellerKey | int | False | False | COALESCE(v.SellerKey,0); FROM stg.order_items s JOIN dw.FactOrders o ON o.OrderID=s.order_id LEFT JOIN dw.DimProduct p ON p.ProductID=s.product_id LEFT JOIN dw.DimSeller v ON v.SellerID=s.seller_id |
| CustomerKey | int | False | False | o.CustomerKey; FROM stg.order_items s JOIN dw.FactOrders o ON o.OrderID=s.order_id LEFT JOIN dw.DimProduct p ON p.ProductID=s.product_id LEFT JOIN dw.DimSeller v ON v.SellerID=s.seller_id |
| CustomerGeographyKey | int | False | False | o.CustomerGeographyKey; FROM stg.order_items s JOIN dw.FactOrders o ON o.OrderID=s.order_id LEFT JOIN dw.DimProduct p ON p.ProductID=s.product_id LEFT JOIN dw.DimSeller v ON v.SellerID=s.seller_id |
| SellerGeographyKey | int | False | False | COALESCE(v.GeographyKey,0); FROM stg.order_items s JOIN dw.FactOrders o ON o.OrderID=s.order_id LEFT JOIN dw.DimProduct p ON p.ProductID=s.product_id LEFT JOIN dw.DimSeller v ON v.SellerID=s.seller_id |
| OrderStatusKey | int | False | False | o.OrderStatusKey; FROM stg.order_items s JOIN dw.FactOrders o ON o.OrderID=s.order_id LEFT JOIN dw.DimProduct p ON p.ProductID=s.product_id LEFT JOIN dw.DimSeller v ON v.SellerID=s.seller_id |
| PurchaseDateKey | int | False | False | o.PurchaseDateKey; FROM stg.order_items s JOIN dw.FactOrders o ON o.OrderID=s.order_id LEFT JOIN dw.DimProduct p ON p.ProductID=s.product_id LEFT JOIN dw.DimSeller v ON v.SellerID=s.seller_id |
| ShippingLimitDateKey | int | False | False | COALESCE(CONVERT(int,CONVERT(char(8),s.shipping_limit_date,112)),0); FROM stg.order_items s JOIN dw.FactOrders o ON o.OrderID=s.order_id LEFT JOIN dw.DimProduct p ON p.ProductID=s.product_id LEFT JOIN dw.DimSeller v ON v.SellerID=s.seller_id |
| ShippingLimitTimestamp | datetime2(0) | True | False | s.shipping_limit_date; FROM stg.order_items s JOIN dw.FactOrders o ON o.OrderID=s.order_id LEFT JOIN dw.DimProduct p ON p.ProductID=s.product_id LEFT JOIN dw.DimSeller v ON v.SellerID=s.seller_id |
| ItemPrice | decimal(19,2) | False | False | s.price; FROM stg.order_items s JOIN dw.FactOrders o ON o.OrderID=s.order_id LEFT JOIN dw.DimProduct p ON p.ProductID=s.product_id LEFT JOIN dw.DimSeller v ON v.SellerID=s.seller_id |
| FreightValue | decimal(19,2) | False | False | s.freight_value; FROM stg.order_items s JOIN dw.FactOrders o ON o.OrderID=s.order_id LEFT JOIN dw.DimProduct p ON p.ProductID=s.product_id LEFT JOIN dw.DimSeller v ON v.SellerID=s.seller_id |
| SalesEligible | bit | False | False | o.SalesEligible; FROM stg.order_items s JOIN dw.FactOrders o ON o.OrderID=s.order_id LEFT JOIN dw.DimProduct p ON p.ProductID=s.product_id LEFT JOIN dw.DimSeller v ON v.SellerID=s.seller_id |
| SourceQualityFlagCount | int | False | False | CONVERT(int,s.[dq_invalid_shipping_limit_date])+CONVERT(int,s.[dq_invalid_price])+CONVERT(int,s.[dq_invalid_freight_value])+CONVERT(int,s.[dq_shipping_limit_before_purchase])+CONVERT(int,s.[dq_shipping_limit_after_purchase_year_range])+CONVERT(int,s.[dq_negative_price])+CONVERT(int,s.[dq_zero_price])+CONVERT(int,s.[dq_negative_freight_value])+CONVERT(int,s.[dq_zero_freight_value]); FROM stg.order_items s JOIN dw.FactOrders o ON o.OrderID=s.order_id LEFT JOIN dw.DimProduct p ON p.ProductID=s.product_id LEFT JOIN dw.DimSeller v ON v.SellerID=s.seller_id |
| LoadID | uniqueidentifier | False | False | s.LoadID; FROM stg.order_items s JOIN dw.FactOrders o ON o.OrderID=s.order_id LEFT JOIN dw.DimProduct p ON p.ProductID=s.product_id LEFT JOIN dw.DimSeller v ON v.SellerID=s.seller_id |

### dw.FactOrders

Grain: one order_id. History: snapshot / load audit.

| Column | SQL type | Nullable | Identity | Source / meaning |
| --- | --- | --- | --- | --- |
| OrderKey | int | False | True | sql/08_load_warehouse.sql: FactOrders explicit INSERT/UPDATE mapping |
| OrderID | varchar(32) | False | False | s.order_id; FROM stg.orders s LEFT JOIN (SELECT order_id,COUNT(*) ItemCount,SUM(price) Revenue,SUM(freight_value) Freight FROM stg.order_items GROUP BY order_id) i ON i.order_id=s.order_id LEFT JOIN (SELECT order_id,COUNT(*) PaymentCount FROM stg.payments GROUP BY order_id) p ON p.order_id=s.order_id LEFT JOIN (SELECT order_id,COUNT(*) ReviewCount FROM stg.reviews GROUP BY order_id) r ON r.order_id=s.order_id LEFT JOIN dw.DimCustomer c ON c.CustomerID=s.customer_id LEFT JOIN dw.DimOrderStatus os ON os.OrderStatus=s.order_status CROSS APPLY (SELECT CONVERT(bit,CASE WHEN s.order_approved_at<s.order_purchase_timestamp OR s.order_delivered_carrier_date<s.order_purchase_timestamp OR s.order_delivered_customer_date<s.order_purchase_timestamp OR s.order_delivered_carrier_date<s.order_approved_at OR s.order_delivered_customer_date<s.order_delivered_carrier_date THEN 1 ELSE 0 END) InvalidChronology) q CROSS APPLY (SELECT  CONVERT(bit,CASE WHEN s.order_status='delivered' AND s.order_delivered_customer_date IS NOT NULL AND s.order_estimated_delivery_date IS NOT NULL THEN 1 ELSE 0 END) OnTimeEligible,  CONVERT(bit,CASE WHEN s.order_status='delivered' AND s.order_purchase_timestamp IS NOT NULL AND s.order_delivered_customer_date>=s.order_purchase_timestamp AND q.InvalidChronology=0 THEN 1 ELSE 0 END) DurationEligible) v |
| SourceCustomerID | varchar(32) | False | False | s.customer_id; FROM stg.orders s LEFT JOIN (SELECT order_id,COUNT(*) ItemCount,SUM(price) Revenue,SUM(freight_value) Freight FROM stg.order_items GROUP BY order_id) i ON i.order_id=s.order_id LEFT JOIN (SELECT order_id,COUNT(*) PaymentCount FROM stg.payments GROUP BY order_id) p ON p.order_id=s.order_id LEFT JOIN (SELECT order_id,COUNT(*) ReviewCount FROM stg.reviews GROUP BY order_id) r ON r.order_id=s.order_id LEFT JOIN dw.DimCustomer c ON c.CustomerID=s.customer_id LEFT JOIN dw.DimOrderStatus os ON os.OrderStatus=s.order_status CROSS APPLY (SELECT CONVERT(bit,CASE WHEN s.order_approved_at<s.order_purchase_timestamp OR s.order_delivered_carrier_date<s.order_purchase_timestamp OR s.order_delivered_customer_date<s.order_purchase_timestamp OR s.order_delivered_carrier_date<s.order_approved_at OR s.order_delivered_customer_date<s.order_delivered_carrier_date THEN 1 ELSE 0 END) InvalidChronology) q CROSS APPLY (SELECT  CONVERT(bit,CASE WHEN s.order_status='delivered' AND s.order_delivered_customer_date IS NOT NULL AND s.order_estimated_delivery_date IS NOT NULL THEN 1 ELSE 0 END) OnTimeEligible,  CONVERT(bit,CASE WHEN s.order_status='delivered' AND s.order_purchase_timestamp IS NOT NULL AND s.order_delivered_customer_date>=s.order_purchase_timestamp AND q.InvalidChronology=0 THEN 1 ELSE 0 END) DurationEligible) v |
| CustomerKey | int | False | False | COALESCE(c.CustomerKey,0); FROM stg.orders s LEFT JOIN (SELECT order_id,COUNT(*) ItemCount,SUM(price) Revenue,SUM(freight_value) Freight FROM stg.order_items GROUP BY order_id) i ON i.order_id=s.order_id LEFT JOIN (SELECT order_id,COUNT(*) PaymentCount FROM stg.payments GROUP BY order_id) p ON p.order_id=s.order_id LEFT JOIN (SELECT order_id,COUNT(*) ReviewCount FROM stg.reviews GROUP BY order_id) r ON r.order_id=s.order_id LEFT JOIN dw.DimCustomer c ON c.CustomerID=s.customer_id LEFT JOIN dw.DimOrderStatus os ON os.OrderStatus=s.order_status CROSS APPLY (SELECT CONVERT(bit,CASE WHEN s.order_approved_at<s.order_purchase_timestamp OR s.order_delivered_carrier_date<s.order_purchase_timestamp OR s.order_delivered_customer_date<s.order_purchase_timestamp OR s.order_delivered_carrier_date<s.order_approved_at OR s.order_delivered_customer_date<s.order_delivered_carrier_date THEN 1 ELSE 0 END) InvalidChronology) q CROSS APPLY (SELECT  CONVERT(bit,CASE WHEN s.order_status='delivered' AND s.order_delivered_customer_date IS NOT NULL AND s.order_estimated_delivery_date IS NOT NULL THEN 1 ELSE 0 END) OnTimeEligible,  CONVERT(bit,CASE WHEN s.order_status='delivered' AND s.order_purchase_timestamp IS NOT NULL AND s.order_delivered_customer_date>=s.order_purchase_timestamp AND q.InvalidChronology=0 THEN 1 ELSE 0 END) DurationEligible) v |
| CustomerGeographyKey | int | False | False | COALESCE(c.GeographyKey,0); FROM stg.orders s LEFT JOIN (SELECT order_id,COUNT(*) ItemCount,SUM(price) Revenue,SUM(freight_value) Freight FROM stg.order_items GROUP BY order_id) i ON i.order_id=s.order_id LEFT JOIN (SELECT order_id,COUNT(*) PaymentCount FROM stg.payments GROUP BY order_id) p ON p.order_id=s.order_id LEFT JOIN (SELECT order_id,COUNT(*) ReviewCount FROM stg.reviews GROUP BY order_id) r ON r.order_id=s.order_id LEFT JOIN dw.DimCustomer c ON c.CustomerID=s.customer_id LEFT JOIN dw.DimOrderStatus os ON os.OrderStatus=s.order_status CROSS APPLY (SELECT CONVERT(bit,CASE WHEN s.order_approved_at<s.order_purchase_timestamp OR s.order_delivered_carrier_date<s.order_purchase_timestamp OR s.order_delivered_customer_date<s.order_purchase_timestamp OR s.order_delivered_carrier_date<s.order_approved_at OR s.order_delivered_customer_date<s.order_delivered_carrier_date THEN 1 ELSE 0 END) InvalidChronology) q CROSS APPLY (SELECT  CONVERT(bit,CASE WHEN s.order_status='delivered' AND s.order_delivered_customer_date IS NOT NULL AND s.order_estimated_delivery_date IS NOT NULL THEN 1 ELSE 0 END) OnTimeEligible,  CONVERT(bit,CASE WHEN s.order_status='delivered' AND s.order_purchase_timestamp IS NOT NULL AND s.order_delivered_customer_date>=s.order_purchase_timestamp AND q.InvalidChronology=0 THEN 1 ELSE 0 END) DurationEligible) v |
| OrderStatusKey | int | False | False | COALESCE(os.OrderStatusKey,0); FROM stg.orders s LEFT JOIN (SELECT order_id,COUNT(*) ItemCount,SUM(price) Revenue,SUM(freight_value) Freight FROM stg.order_items GROUP BY order_id) i ON i.order_id=s.order_id LEFT JOIN (SELECT order_id,COUNT(*) PaymentCount FROM stg.payments GROUP BY order_id) p ON p.order_id=s.order_id LEFT JOIN (SELECT order_id,COUNT(*) ReviewCount FROM stg.reviews GROUP BY order_id) r ON r.order_id=s.order_id LEFT JOIN dw.DimCustomer c ON c.CustomerID=s.customer_id LEFT JOIN dw.DimOrderStatus os ON os.OrderStatus=s.order_status CROSS APPLY (SELECT CONVERT(bit,CASE WHEN s.order_approved_at<s.order_purchase_timestamp OR s.order_delivered_carrier_date<s.order_purchase_timestamp OR s.order_delivered_customer_date<s.order_purchase_timestamp OR s.order_delivered_carrier_date<s.order_approved_at OR s.order_delivered_customer_date<s.order_delivered_carrier_date THEN 1 ELSE 0 END) InvalidChronology) q CROSS APPLY (SELECT  CONVERT(bit,CASE WHEN s.order_status='delivered' AND s.order_delivered_customer_date IS NOT NULL AND s.order_estimated_delivery_date IS NOT NULL THEN 1 ELSE 0 END) OnTimeEligible,  CONVERT(bit,CASE WHEN s.order_status='delivered' AND s.order_purchase_timestamp IS NOT NULL AND s.order_delivered_customer_date>=s.order_purchase_timestamp AND q.InvalidChronology=0 THEN 1 ELSE 0 END) DurationEligible) v |
| PurchaseDateKey | int | False | False | COALESCE(CONVERT(int,CONVERT(char(8),s.order_purchase_timestamp,112)),0); FROM stg.orders s LEFT JOIN (SELECT order_id,COUNT(*) ItemCount,SUM(price) Revenue,SUM(freight_value) Freight FROM stg.order_items GROUP BY order_id) i ON i.order_id=s.order_id LEFT JOIN (SELECT order_id,COUNT(*) PaymentCount FROM stg.payments GROUP BY order_id) p ON p.order_id=s.order_id LEFT JOIN (SELECT order_id,COUNT(*) ReviewCount FROM stg.reviews GROUP BY order_id) r ON r.order_id=s.order_id LEFT JOIN dw.DimCustomer c ON c.CustomerID=s.customer_id LEFT JOIN dw.DimOrderStatus os ON os.OrderStatus=s.order_status CROSS APPLY (SELECT CONVERT(bit,CASE WHEN s.order_approved_at<s.order_purchase_timestamp OR s.order_delivered_carrier_date<s.order_purchase_timestamp OR s.order_delivered_customer_date<s.order_purchase_timestamp OR s.order_delivered_carrier_date<s.order_approved_at OR s.order_delivered_customer_date<s.order_delivered_carrier_date THEN 1 ELSE 0 END) InvalidChronology) q CROSS APPLY (SELECT  CONVERT(bit,CASE WHEN s.order_status='delivered' AND s.order_delivered_customer_date IS NOT NULL AND s.order_estimated_delivery_date IS NOT NULL THEN 1 ELSE 0 END) OnTimeEligible,  CONVERT(bit,CASE WHEN s.order_status='delivered' AND s.order_purchase_timestamp IS NOT NULL AND s.order_delivered_customer_date>=s.order_purchase_timestamp AND q.InvalidChronology=0 THEN 1 ELSE 0 END) DurationEligible) v |
| ApprovalDateKey | int | False | False | COALESCE(CONVERT(int,CONVERT(char(8),s.order_approved_at,112)),0); FROM stg.orders s LEFT JOIN (SELECT order_id,COUNT(*) ItemCount,SUM(price) Revenue,SUM(freight_value) Freight FROM stg.order_items GROUP BY order_id) i ON i.order_id=s.order_id LEFT JOIN (SELECT order_id,COUNT(*) PaymentCount FROM stg.payments GROUP BY order_id) p ON p.order_id=s.order_id LEFT JOIN (SELECT order_id,COUNT(*) ReviewCount FROM stg.reviews GROUP BY order_id) r ON r.order_id=s.order_id LEFT JOIN dw.DimCustomer c ON c.CustomerID=s.customer_id LEFT JOIN dw.DimOrderStatus os ON os.OrderStatus=s.order_status CROSS APPLY (SELECT CONVERT(bit,CASE WHEN s.order_approved_at<s.order_purchase_timestamp OR s.order_delivered_carrier_date<s.order_purchase_timestamp OR s.order_delivered_customer_date<s.order_purchase_timestamp OR s.order_delivered_carrier_date<s.order_approved_at OR s.order_delivered_customer_date<s.order_delivered_carrier_date THEN 1 ELSE 0 END) InvalidChronology) q CROSS APPLY (SELECT  CONVERT(bit,CASE WHEN s.order_status='delivered' AND s.order_delivered_customer_date IS NOT NULL AND s.order_estimated_delivery_date IS NOT NULL THEN 1 ELSE 0 END) OnTimeEligible,  CONVERT(bit,CASE WHEN s.order_status='delivered' AND s.order_purchase_timestamp IS NOT NULL AND s.order_delivered_customer_date>=s.order_purchase_timestamp AND q.InvalidChronology=0 THEN 1 ELSE 0 END) DurationEligible) v |
| CarrierDateKey | int | False | False | COALESCE(CONVERT(int,CONVERT(char(8),s.order_delivered_carrier_date,112)),0); FROM stg.orders s LEFT JOIN (SELECT order_id,COUNT(*) ItemCount,SUM(price) Revenue,SUM(freight_value) Freight FROM stg.order_items GROUP BY order_id) i ON i.order_id=s.order_id LEFT JOIN (SELECT order_id,COUNT(*) PaymentCount FROM stg.payments GROUP BY order_id) p ON p.order_id=s.order_id LEFT JOIN (SELECT order_id,COUNT(*) ReviewCount FROM stg.reviews GROUP BY order_id) r ON r.order_id=s.order_id LEFT JOIN dw.DimCustomer c ON c.CustomerID=s.customer_id LEFT JOIN dw.DimOrderStatus os ON os.OrderStatus=s.order_status CROSS APPLY (SELECT CONVERT(bit,CASE WHEN s.order_approved_at<s.order_purchase_timestamp OR s.order_delivered_carrier_date<s.order_purchase_timestamp OR s.order_delivered_customer_date<s.order_purchase_timestamp OR s.order_delivered_carrier_date<s.order_approved_at OR s.order_delivered_customer_date<s.order_delivered_carrier_date THEN 1 ELSE 0 END) InvalidChronology) q CROSS APPLY (SELECT  CONVERT(bit,CASE WHEN s.order_status='delivered' AND s.order_delivered_customer_date IS NOT NULL AND s.order_estimated_delivery_date IS NOT NULL THEN 1 ELSE 0 END) OnTimeEligible,  CONVERT(bit,CASE WHEN s.order_status='delivered' AND s.order_purchase_timestamp IS NOT NULL AND s.order_delivered_customer_date>=s.order_purchase_timestamp AND q.InvalidChronology=0 THEN 1 ELSE 0 END) DurationEligible) v |
| ActualDeliveryDateKey | int | False | False | COALESCE(CONVERT(int,CONVERT(char(8),s.order_delivered_customer_date,112)),0); FROM stg.orders s LEFT JOIN (SELECT order_id,COUNT(*) ItemCount,SUM(price) Revenue,SUM(freight_value) Freight FROM stg.order_items GROUP BY order_id) i ON i.order_id=s.order_id LEFT JOIN (SELECT order_id,COUNT(*) PaymentCount FROM stg.payments GROUP BY order_id) p ON p.order_id=s.order_id LEFT JOIN (SELECT order_id,COUNT(*) ReviewCount FROM stg.reviews GROUP BY order_id) r ON r.order_id=s.order_id LEFT JOIN dw.DimCustomer c ON c.CustomerID=s.customer_id LEFT JOIN dw.DimOrderStatus os ON os.OrderStatus=s.order_status CROSS APPLY (SELECT CONVERT(bit,CASE WHEN s.order_approved_at<s.order_purchase_timestamp OR s.order_delivered_carrier_date<s.order_purchase_timestamp OR s.order_delivered_customer_date<s.order_purchase_timestamp OR s.order_delivered_carrier_date<s.order_approved_at OR s.order_delivered_customer_date<s.order_delivered_carrier_date THEN 1 ELSE 0 END) InvalidChronology) q CROSS APPLY (SELECT  CONVERT(bit,CASE WHEN s.order_status='delivered' AND s.order_delivered_customer_date IS NOT NULL AND s.order_estimated_delivery_date IS NOT NULL THEN 1 ELSE 0 END) OnTimeEligible,  CONVERT(bit,CASE WHEN s.order_status='delivered' AND s.order_purchase_timestamp IS NOT NULL AND s.order_delivered_customer_date>=s.order_purchase_timestamp AND q.InvalidChronology=0 THEN 1 ELSE 0 END) DurationEligible) v |
| EstimatedDeliveryDateKey | int | False | False | COALESCE(CONVERT(int,CONVERT(char(8),s.order_estimated_delivery_date,112)),0); FROM stg.orders s LEFT JOIN (SELECT order_id,COUNT(*) ItemCount,SUM(price) Revenue,SUM(freight_value) Freight FROM stg.order_items GROUP BY order_id) i ON i.order_id=s.order_id LEFT JOIN (SELECT order_id,COUNT(*) PaymentCount FROM stg.payments GROUP BY order_id) p ON p.order_id=s.order_id LEFT JOIN (SELECT order_id,COUNT(*) ReviewCount FROM stg.reviews GROUP BY order_id) r ON r.order_id=s.order_id LEFT JOIN dw.DimCustomer c ON c.CustomerID=s.customer_id LEFT JOIN dw.DimOrderStatus os ON os.OrderStatus=s.order_status CROSS APPLY (SELECT CONVERT(bit,CASE WHEN s.order_approved_at<s.order_purchase_timestamp OR s.order_delivered_carrier_date<s.order_purchase_timestamp OR s.order_delivered_customer_date<s.order_purchase_timestamp OR s.order_delivered_carrier_date<s.order_approved_at OR s.order_delivered_customer_date<s.order_delivered_carrier_date THEN 1 ELSE 0 END) InvalidChronology) q CROSS APPLY (SELECT  CONVERT(bit,CASE WHEN s.order_status='delivered' AND s.order_delivered_customer_date IS NOT NULL AND s.order_estimated_delivery_date IS NOT NULL THEN 1 ELSE 0 END) OnTimeEligible,  CONVERT(bit,CASE WHEN s.order_status='delivered' AND s.order_purchase_timestamp IS NOT NULL AND s.order_delivered_customer_date>=s.order_purchase_timestamp AND q.InvalidChronology=0 THEN 1 ELSE 0 END) DurationEligible) v |
| PurchaseTimestamp | datetime2(0) | True | False | s.order_purchase_timestamp; FROM stg.orders s LEFT JOIN (SELECT order_id,COUNT(*) ItemCount,SUM(price) Revenue,SUM(freight_value) Freight FROM stg.order_items GROUP BY order_id) i ON i.order_id=s.order_id LEFT JOIN (SELECT order_id,COUNT(*) PaymentCount FROM stg.payments GROUP BY order_id) p ON p.order_id=s.order_id LEFT JOIN (SELECT order_id,COUNT(*) ReviewCount FROM stg.reviews GROUP BY order_id) r ON r.order_id=s.order_id LEFT JOIN dw.DimCustomer c ON c.CustomerID=s.customer_id LEFT JOIN dw.DimOrderStatus os ON os.OrderStatus=s.order_status CROSS APPLY (SELECT CONVERT(bit,CASE WHEN s.order_approved_at<s.order_purchase_timestamp OR s.order_delivered_carrier_date<s.order_purchase_timestamp OR s.order_delivered_customer_date<s.order_purchase_timestamp OR s.order_delivered_carrier_date<s.order_approved_at OR s.order_delivered_customer_date<s.order_delivered_carrier_date THEN 1 ELSE 0 END) InvalidChronology) q CROSS APPLY (SELECT  CONVERT(bit,CASE WHEN s.order_status='delivered' AND s.order_delivered_customer_date IS NOT NULL AND s.order_estimated_delivery_date IS NOT NULL THEN 1 ELSE 0 END) OnTimeEligible,  CONVERT(bit,CASE WHEN s.order_status='delivered' AND s.order_purchase_timestamp IS NOT NULL AND s.order_delivered_customer_date>=s.order_purchase_timestamp AND q.InvalidChronology=0 THEN 1 ELSE 0 END) DurationEligible) v |
| ApprovalTimestamp | datetime2(0) | True | False | s.order_approved_at; FROM stg.orders s LEFT JOIN (SELECT order_id,COUNT(*) ItemCount,SUM(price) Revenue,SUM(freight_value) Freight FROM stg.order_items GROUP BY order_id) i ON i.order_id=s.order_id LEFT JOIN (SELECT order_id,COUNT(*) PaymentCount FROM stg.payments GROUP BY order_id) p ON p.order_id=s.order_id LEFT JOIN (SELECT order_id,COUNT(*) ReviewCount FROM stg.reviews GROUP BY order_id) r ON r.order_id=s.order_id LEFT JOIN dw.DimCustomer c ON c.CustomerID=s.customer_id LEFT JOIN dw.DimOrderStatus os ON os.OrderStatus=s.order_status CROSS APPLY (SELECT CONVERT(bit,CASE WHEN s.order_approved_at<s.order_purchase_timestamp OR s.order_delivered_carrier_date<s.order_purchase_timestamp OR s.order_delivered_customer_date<s.order_purchase_timestamp OR s.order_delivered_carrier_date<s.order_approved_at OR s.order_delivered_customer_date<s.order_delivered_carrier_date THEN 1 ELSE 0 END) InvalidChronology) q CROSS APPLY (SELECT  CONVERT(bit,CASE WHEN s.order_status='delivered' AND s.order_delivered_customer_date IS NOT NULL AND s.order_estimated_delivery_date IS NOT NULL THEN 1 ELSE 0 END) OnTimeEligible,  CONVERT(bit,CASE WHEN s.order_status='delivered' AND s.order_purchase_timestamp IS NOT NULL AND s.order_delivered_customer_date>=s.order_purchase_timestamp AND q.InvalidChronology=0 THEN 1 ELSE 0 END) DurationEligible) v |
| CarrierTimestamp | datetime2(0) | True | False | s.order_delivered_carrier_date; FROM stg.orders s LEFT JOIN (SELECT order_id,COUNT(*) ItemCount,SUM(price) Revenue,SUM(freight_value) Freight FROM stg.order_items GROUP BY order_id) i ON i.order_id=s.order_id LEFT JOIN (SELECT order_id,COUNT(*) PaymentCount FROM stg.payments GROUP BY order_id) p ON p.order_id=s.order_id LEFT JOIN (SELECT order_id,COUNT(*) ReviewCount FROM stg.reviews GROUP BY order_id) r ON r.order_id=s.order_id LEFT JOIN dw.DimCustomer c ON c.CustomerID=s.customer_id LEFT JOIN dw.DimOrderStatus os ON os.OrderStatus=s.order_status CROSS APPLY (SELECT CONVERT(bit,CASE WHEN s.order_approved_at<s.order_purchase_timestamp OR s.order_delivered_carrier_date<s.order_purchase_timestamp OR s.order_delivered_customer_date<s.order_purchase_timestamp OR s.order_delivered_carrier_date<s.order_approved_at OR s.order_delivered_customer_date<s.order_delivered_carrier_date THEN 1 ELSE 0 END) InvalidChronology) q CROSS APPLY (SELECT  CONVERT(bit,CASE WHEN s.order_status='delivered' AND s.order_delivered_customer_date IS NOT NULL AND s.order_estimated_delivery_date IS NOT NULL THEN 1 ELSE 0 END) OnTimeEligible,  CONVERT(bit,CASE WHEN s.order_status='delivered' AND s.order_purchase_timestamp IS NOT NULL AND s.order_delivered_customer_date>=s.order_purchase_timestamp AND q.InvalidChronology=0 THEN 1 ELSE 0 END) DurationEligible) v |
| ActualDeliveryTimestamp | datetime2(0) | True | False | s.order_delivered_customer_date; FROM stg.orders s LEFT JOIN (SELECT order_id,COUNT(*) ItemCount,SUM(price) Revenue,SUM(freight_value) Freight FROM stg.order_items GROUP BY order_id) i ON i.order_id=s.order_id LEFT JOIN (SELECT order_id,COUNT(*) PaymentCount FROM stg.payments GROUP BY order_id) p ON p.order_id=s.order_id LEFT JOIN (SELECT order_id,COUNT(*) ReviewCount FROM stg.reviews GROUP BY order_id) r ON r.order_id=s.order_id LEFT JOIN dw.DimCustomer c ON c.CustomerID=s.customer_id LEFT JOIN dw.DimOrderStatus os ON os.OrderStatus=s.order_status CROSS APPLY (SELECT CONVERT(bit,CASE WHEN s.order_approved_at<s.order_purchase_timestamp OR s.order_delivered_carrier_date<s.order_purchase_timestamp OR s.order_delivered_customer_date<s.order_purchase_timestamp OR s.order_delivered_carrier_date<s.order_approved_at OR s.order_delivered_customer_date<s.order_delivered_carrier_date THEN 1 ELSE 0 END) InvalidChronology) q CROSS APPLY (SELECT  CONVERT(bit,CASE WHEN s.order_status='delivered' AND s.order_delivered_customer_date IS NOT NULL AND s.order_estimated_delivery_date IS NOT NULL THEN 1 ELSE 0 END) OnTimeEligible,  CONVERT(bit,CASE WHEN s.order_status='delivered' AND s.order_purchase_timestamp IS NOT NULL AND s.order_delivered_customer_date>=s.order_purchase_timestamp AND q.InvalidChronology=0 THEN 1 ELSE 0 END) DurationEligible) v |
| EstimatedDeliveryTimestamp | datetime2(0) | True | False | s.order_estimated_delivery_date; FROM stg.orders s LEFT JOIN (SELECT order_id,COUNT(*) ItemCount,SUM(price) Revenue,SUM(freight_value) Freight FROM stg.order_items GROUP BY order_id) i ON i.order_id=s.order_id LEFT JOIN (SELECT order_id,COUNT(*) PaymentCount FROM stg.payments GROUP BY order_id) p ON p.order_id=s.order_id LEFT JOIN (SELECT order_id,COUNT(*) ReviewCount FROM stg.reviews GROUP BY order_id) r ON r.order_id=s.order_id LEFT JOIN dw.DimCustomer c ON c.CustomerID=s.customer_id LEFT JOIN dw.DimOrderStatus os ON os.OrderStatus=s.order_status CROSS APPLY (SELECT CONVERT(bit,CASE WHEN s.order_approved_at<s.order_purchase_timestamp OR s.order_delivered_carrier_date<s.order_purchase_timestamp OR s.order_delivered_customer_date<s.order_purchase_timestamp OR s.order_delivered_carrier_date<s.order_approved_at OR s.order_delivered_customer_date<s.order_delivered_carrier_date THEN 1 ELSE 0 END) InvalidChronology) q CROSS APPLY (SELECT  CONVERT(bit,CASE WHEN s.order_status='delivered' AND s.order_delivered_customer_date IS NOT NULL AND s.order_estimated_delivery_date IS NOT NULL THEN 1 ELSE 0 END) OnTimeEligible,  CONVERT(bit,CASE WHEN s.order_status='delivered' AND s.order_purchase_timestamp IS NOT NULL AND s.order_delivered_customer_date>=s.order_purchase_timestamp AND q.InvalidChronology=0 THEN 1 ELSE 0 END) DurationEligible) v |
| MerchandiseRevenue | decimal(19,2) | True | False | i.Revenue; FROM stg.orders s LEFT JOIN (SELECT order_id,COUNT(*) ItemCount,SUM(price) Revenue,SUM(freight_value) Freight FROM stg.order_items GROUP BY order_id) i ON i.order_id=s.order_id LEFT JOIN (SELECT order_id,COUNT(*) PaymentCount FROM stg.payments GROUP BY order_id) p ON p.order_id=s.order_id LEFT JOIN (SELECT order_id,COUNT(*) ReviewCount FROM stg.reviews GROUP BY order_id) r ON r.order_id=s.order_id LEFT JOIN dw.DimCustomer c ON c.CustomerID=s.customer_id LEFT JOIN dw.DimOrderStatus os ON os.OrderStatus=s.order_status CROSS APPLY (SELECT CONVERT(bit,CASE WHEN s.order_approved_at<s.order_purchase_timestamp OR s.order_delivered_carrier_date<s.order_purchase_timestamp OR s.order_delivered_customer_date<s.order_purchase_timestamp OR s.order_delivered_carrier_date<s.order_approved_at OR s.order_delivered_customer_date<s.order_delivered_carrier_date THEN 1 ELSE 0 END) InvalidChronology) q CROSS APPLY (SELECT  CONVERT(bit,CASE WHEN s.order_status='delivered' AND s.order_delivered_customer_date IS NOT NULL AND s.order_estimated_delivery_date IS NOT NULL THEN 1 ELSE 0 END) OnTimeEligible,  CONVERT(bit,CASE WHEN s.order_status='delivered' AND s.order_purchase_timestamp IS NOT NULL AND s.order_delivered_customer_date>=s.order_purchase_timestamp AND q.InvalidChronology=0 THEN 1 ELSE 0 END) DurationEligible) v |
| FreightAmount | decimal(19,2) | True | False | i.Freight; FROM stg.orders s LEFT JOIN (SELECT order_id,COUNT(*) ItemCount,SUM(price) Revenue,SUM(freight_value) Freight FROM stg.order_items GROUP BY order_id) i ON i.order_id=s.order_id LEFT JOIN (SELECT order_id,COUNT(*) PaymentCount FROM stg.payments GROUP BY order_id) p ON p.order_id=s.order_id LEFT JOIN (SELECT order_id,COUNT(*) ReviewCount FROM stg.reviews GROUP BY order_id) r ON r.order_id=s.order_id LEFT JOIN dw.DimCustomer c ON c.CustomerID=s.customer_id LEFT JOIN dw.DimOrderStatus os ON os.OrderStatus=s.order_status CROSS APPLY (SELECT CONVERT(bit,CASE WHEN s.order_approved_at<s.order_purchase_timestamp OR s.order_delivered_carrier_date<s.order_purchase_timestamp OR s.order_delivered_customer_date<s.order_purchase_timestamp OR s.order_delivered_carrier_date<s.order_approved_at OR s.order_delivered_customer_date<s.order_delivered_carrier_date THEN 1 ELSE 0 END) InvalidChronology) q CROSS APPLY (SELECT  CONVERT(bit,CASE WHEN s.order_status='delivered' AND s.order_delivered_customer_date IS NOT NULL AND s.order_estimated_delivery_date IS NOT NULL THEN 1 ELSE 0 END) OnTimeEligible,  CONVERT(bit,CASE WHEN s.order_status='delivered' AND s.order_purchase_timestamp IS NOT NULL AND s.order_delivered_customer_date>=s.order_purchase_timestamp AND q.InvalidChronology=0 THEN 1 ELSE 0 END) DurationEligible) v |
| ItemCount | int | False | False | COALESCE(i.ItemCount,0); FROM stg.orders s LEFT JOIN (SELECT order_id,COUNT(*) ItemCount,SUM(price) Revenue,SUM(freight_value) Freight FROM stg.order_items GROUP BY order_id) i ON i.order_id=s.order_id LEFT JOIN (SELECT order_id,COUNT(*) PaymentCount FROM stg.payments GROUP BY order_id) p ON p.order_id=s.order_id LEFT JOIN (SELECT order_id,COUNT(*) ReviewCount FROM stg.reviews GROUP BY order_id) r ON r.order_id=s.order_id LEFT JOIN dw.DimCustomer c ON c.CustomerID=s.customer_id LEFT JOIN dw.DimOrderStatus os ON os.OrderStatus=s.order_status CROSS APPLY (SELECT CONVERT(bit,CASE WHEN s.order_approved_at<s.order_purchase_timestamp OR s.order_delivered_carrier_date<s.order_purchase_timestamp OR s.order_delivered_customer_date<s.order_purchase_timestamp OR s.order_delivered_carrier_date<s.order_approved_at OR s.order_delivered_customer_date<s.order_delivered_carrier_date THEN 1 ELSE 0 END) InvalidChronology) q CROSS APPLY (SELECT  CONVERT(bit,CASE WHEN s.order_status='delivered' AND s.order_delivered_customer_date IS NOT NULL AND s.order_estimated_delivery_date IS NOT NULL THEN 1 ELSE 0 END) OnTimeEligible,  CONVERT(bit,CASE WHEN s.order_status='delivered' AND s.order_purchase_timestamp IS NOT NULL AND s.order_delivered_customer_date>=s.order_purchase_timestamp AND q.InvalidChronology=0 THEN 1 ELSE 0 END) DurationEligible) v |
| PaymentRecordCount | int | False | False | COALESCE(p.PaymentCount,0); FROM stg.orders s LEFT JOIN (SELECT order_id,COUNT(*) ItemCount,SUM(price) Revenue,SUM(freight_value) Freight FROM stg.order_items GROUP BY order_id) i ON i.order_id=s.order_id LEFT JOIN (SELECT order_id,COUNT(*) PaymentCount FROM stg.payments GROUP BY order_id) p ON p.order_id=s.order_id LEFT JOIN (SELECT order_id,COUNT(*) ReviewCount FROM stg.reviews GROUP BY order_id) r ON r.order_id=s.order_id LEFT JOIN dw.DimCustomer c ON c.CustomerID=s.customer_id LEFT JOIN dw.DimOrderStatus os ON os.OrderStatus=s.order_status CROSS APPLY (SELECT CONVERT(bit,CASE WHEN s.order_approved_at<s.order_purchase_timestamp OR s.order_delivered_carrier_date<s.order_purchase_timestamp OR s.order_delivered_customer_date<s.order_purchase_timestamp OR s.order_delivered_carrier_date<s.order_approved_at OR s.order_delivered_customer_date<s.order_delivered_carrier_date THEN 1 ELSE 0 END) InvalidChronology) q CROSS APPLY (SELECT  CONVERT(bit,CASE WHEN s.order_status='delivered' AND s.order_delivered_customer_date IS NOT NULL AND s.order_estimated_delivery_date IS NOT NULL THEN 1 ELSE 0 END) OnTimeEligible,  CONVERT(bit,CASE WHEN s.order_status='delivered' AND s.order_purchase_timestamp IS NOT NULL AND s.order_delivered_customer_date>=s.order_purchase_timestamp AND q.InvalidChronology=0 THEN 1 ELSE 0 END) DurationEligible) v |
| ReviewRecordCount | int | False | False | COALESCE(r.ReviewCount,0); FROM stg.orders s LEFT JOIN (SELECT order_id,COUNT(*) ItemCount,SUM(price) Revenue,SUM(freight_value) Freight FROM stg.order_items GROUP BY order_id) i ON i.order_id=s.order_id LEFT JOIN (SELECT order_id,COUNT(*) PaymentCount FROM stg.payments GROUP BY order_id) p ON p.order_id=s.order_id LEFT JOIN (SELECT order_id,COUNT(*) ReviewCount FROM stg.reviews GROUP BY order_id) r ON r.order_id=s.order_id LEFT JOIN dw.DimCustomer c ON c.CustomerID=s.customer_id LEFT JOIN dw.DimOrderStatus os ON os.OrderStatus=s.order_status CROSS APPLY (SELECT CONVERT(bit,CASE WHEN s.order_approved_at<s.order_purchase_timestamp OR s.order_delivered_carrier_date<s.order_purchase_timestamp OR s.order_delivered_customer_date<s.order_purchase_timestamp OR s.order_delivered_carrier_date<s.order_approved_at OR s.order_delivered_customer_date<s.order_delivered_carrier_date THEN 1 ELSE 0 END) InvalidChronology) q CROSS APPLY (SELECT  CONVERT(bit,CASE WHEN s.order_status='delivered' AND s.order_delivered_customer_date IS NOT NULL AND s.order_estimated_delivery_date IS NOT NULL THEN 1 ELSE 0 END) OnTimeEligible,  CONVERT(bit,CASE WHEN s.order_status='delivered' AND s.order_purchase_timestamp IS NOT NULL AND s.order_delivered_customer_date>=s.order_purchase_timestamp AND q.InvalidChronology=0 THEN 1 ELSE 0 END) DurationEligible) v |
| SalesEligible | bit | False | False | CONVERT(bit,CASE WHEN s.order_status='delivered' AND i.ItemCount>0 THEN 1 ELSE 0 END); FROM stg.orders s LEFT JOIN (SELECT order_id,COUNT(*) ItemCount,SUM(price) Revenue,SUM(freight_value) Freight FROM stg.order_items GROUP BY order_id) i ON i.order_id=s.order_id LEFT JOIN (SELECT order_id,COUNT(*) PaymentCount FROM stg.payments GROUP BY order_id) p ON p.order_id=s.order_id LEFT JOIN (SELECT order_id,COUNT(*) ReviewCount FROM stg.reviews GROUP BY order_id) r ON r.order_id=s.order_id LEFT JOIN dw.DimCustomer c ON c.CustomerID=s.customer_id LEFT JOIN dw.DimOrderStatus os ON os.OrderStatus=s.order_status CROSS APPLY (SELECT CONVERT(bit,CASE WHEN s.order_approved_at<s.order_purchase_timestamp OR s.order_delivered_carrier_date<s.order_purchase_timestamp OR s.order_delivered_customer_date<s.order_purchase_timestamp OR s.order_delivered_carrier_date<s.order_approved_at OR s.order_delivered_customer_date<s.order_delivered_carrier_date THEN 1 ELSE 0 END) InvalidChronology) q CROSS APPLY (SELECT  CONVERT(bit,CASE WHEN s.order_status='delivered' AND s.order_delivered_customer_date IS NOT NULL AND s.order_estimated_delivery_date IS NOT NULL THEN 1 ELSE 0 END) OnTimeEligible,  CONVERT(bit,CASE WHEN s.order_status='delivered' AND s.order_purchase_timestamp IS NOT NULL AND s.order_delivered_customer_date>=s.order_purchase_timestamp AND q.InvalidChronology=0 THEN 1 ELSE 0 END) DurationEligible) v |
| OnTimeEligible | bit | False | False | v.OnTimeEligible; FROM stg.orders s LEFT JOIN (SELECT order_id,COUNT(*) ItemCount,SUM(price) Revenue,SUM(freight_value) Freight FROM stg.order_items GROUP BY order_id) i ON i.order_id=s.order_id LEFT JOIN (SELECT order_id,COUNT(*) PaymentCount FROM stg.payments GROUP BY order_id) p ON p.order_id=s.order_id LEFT JOIN (SELECT order_id,COUNT(*) ReviewCount FROM stg.reviews GROUP BY order_id) r ON r.order_id=s.order_id LEFT JOIN dw.DimCustomer c ON c.CustomerID=s.customer_id LEFT JOIN dw.DimOrderStatus os ON os.OrderStatus=s.order_status CROSS APPLY (SELECT CONVERT(bit,CASE WHEN s.order_approved_at<s.order_purchase_timestamp OR s.order_delivered_carrier_date<s.order_purchase_timestamp OR s.order_delivered_customer_date<s.order_purchase_timestamp OR s.order_delivered_carrier_date<s.order_approved_at OR s.order_delivered_customer_date<s.order_delivered_carrier_date THEN 1 ELSE 0 END) InvalidChronology) q CROSS APPLY (SELECT  CONVERT(bit,CASE WHEN s.order_status='delivered' AND s.order_delivered_customer_date IS NOT NULL AND s.order_estimated_delivery_date IS NOT NULL THEN 1 ELSE 0 END) OnTimeEligible,  CONVERT(bit,CASE WHEN s.order_status='delivered' AND s.order_purchase_timestamp IS NOT NULL AND s.order_delivered_customer_date>=s.order_purchase_timestamp AND q.InvalidChronology=0 THEN 1 ELSE 0 END) DurationEligible) v |
| IsOnTime | bit | True | False | CASE WHEN v.OnTimeEligible=1 THEN CASE WHEN CAST(s.order_delivered_customer_date AS date)<=CAST(s.order_estimated_delivery_date AS date) THEN 1 ELSE 0 END END; FROM stg.orders s LEFT JOIN (SELECT order_id,COUNT(*) ItemCount,SUM(price) Revenue,SUM(freight_value) Freight FROM stg.order_items GROUP BY order_id) i ON i.order_id=s.order_id LEFT JOIN (SELECT order_id,COUNT(*) PaymentCount FROM stg.payments GROUP BY order_id) p ON p.order_id=s.order_id LEFT JOIN (SELECT order_id,COUNT(*) ReviewCount FROM stg.reviews GROUP BY order_id) r ON r.order_id=s.order_id LEFT JOIN dw.DimCustomer c ON c.CustomerID=s.customer_id LEFT JOIN dw.DimOrderStatus os ON os.OrderStatus=s.order_status CROSS APPLY (SELECT CONVERT(bit,CASE WHEN s.order_approved_at<s.order_purchase_timestamp OR s.order_delivered_carrier_date<s.order_purchase_timestamp OR s.order_delivered_customer_date<s.order_purchase_timestamp OR s.order_delivered_carrier_date<s.order_approved_at OR s.order_delivered_customer_date<s.order_delivered_carrier_date THEN 1 ELSE 0 END) InvalidChronology) q CROSS APPLY (SELECT  CONVERT(bit,CASE WHEN s.order_status='delivered' AND s.order_delivered_customer_date IS NOT NULL AND s.order_estimated_delivery_date IS NOT NULL THEN 1 ELSE 0 END) OnTimeEligible,  CONVERT(bit,CASE WHEN s.order_status='delivered' AND s.order_purchase_timestamp IS NOT NULL AND s.order_delivered_customer_date>=s.order_purchase_timestamp AND q.InvalidChronology=0 THEN 1 ELSE 0 END) DurationEligible) v |
| DurationEligible | bit | False | False | v.DurationEligible; FROM stg.orders s LEFT JOIN (SELECT order_id,COUNT(*) ItemCount,SUM(price) Revenue,SUM(freight_value) Freight FROM stg.order_items GROUP BY order_id) i ON i.order_id=s.order_id LEFT JOIN (SELECT order_id,COUNT(*) PaymentCount FROM stg.payments GROUP BY order_id) p ON p.order_id=s.order_id LEFT JOIN (SELECT order_id,COUNT(*) ReviewCount FROM stg.reviews GROUP BY order_id) r ON r.order_id=s.order_id LEFT JOIN dw.DimCustomer c ON c.CustomerID=s.customer_id LEFT JOIN dw.DimOrderStatus os ON os.OrderStatus=s.order_status CROSS APPLY (SELECT CONVERT(bit,CASE WHEN s.order_approved_at<s.order_purchase_timestamp OR s.order_delivered_carrier_date<s.order_purchase_timestamp OR s.order_delivered_customer_date<s.order_purchase_timestamp OR s.order_delivered_carrier_date<s.order_approved_at OR s.order_delivered_customer_date<s.order_delivered_carrier_date THEN 1 ELSE 0 END) InvalidChronology) q CROSS APPLY (SELECT  CONVERT(bit,CASE WHEN s.order_status='delivered' AND s.order_delivered_customer_date IS NOT NULL AND s.order_estimated_delivery_date IS NOT NULL THEN 1 ELSE 0 END) OnTimeEligible,  CONVERT(bit,CASE WHEN s.order_status='delivered' AND s.order_purchase_timestamp IS NOT NULL AND s.order_delivered_customer_date>=s.order_purchase_timestamp AND q.InvalidChronology=0 THEN 1 ELSE 0 END) DurationEligible) v |
| DeliveryDurationDays | decimal(20,10) | True | False | CASE WHEN v.DurationEligible=1 THEN CONVERT(decimal(20,10),DATEDIFF_BIG(second,s.order_purchase_timestamp,s.order_delivered_customer_date)/86400.0000000000) END; FROM stg.orders s LEFT JOIN (SELECT order_id,COUNT(*) ItemCount,SUM(price) Revenue,SUM(freight_value) Freight FROM stg.order_items GROUP BY order_id) i ON i.order_id=s.order_id LEFT JOIN (SELECT order_id,COUNT(*) PaymentCount FROM stg.payments GROUP BY order_id) p ON p.order_id=s.order_id LEFT JOIN (SELECT order_id,COUNT(*) ReviewCount FROM stg.reviews GROUP BY order_id) r ON r.order_id=s.order_id LEFT JOIN dw.DimCustomer c ON c.CustomerID=s.customer_id LEFT JOIN dw.DimOrderStatus os ON os.OrderStatus=s.order_status CROSS APPLY (SELECT CONVERT(bit,CASE WHEN s.order_approved_at<s.order_purchase_timestamp OR s.order_delivered_carrier_date<s.order_purchase_timestamp OR s.order_delivered_customer_date<s.order_purchase_timestamp OR s.order_delivered_carrier_date<s.order_approved_at OR s.order_delivered_customer_date<s.order_delivered_carrier_date THEN 1 ELSE 0 END) InvalidChronology) q CROSS APPLY (SELECT  CONVERT(bit,CASE WHEN s.order_status='delivered' AND s.order_delivered_customer_date IS NOT NULL AND s.order_estimated_delivery_date IS NOT NULL THEN 1 ELSE 0 END) OnTimeEligible,  CONVERT(bit,CASE WHEN s.order_status='delivered' AND s.order_purchase_timestamp IS NOT NULL AND s.order_delivered_customer_date>=s.order_purchase_timestamp AND q.InvalidChronology=0 THEN 1 ELSE 0 END) DurationEligible) v |
| InvalidChronology | bit | False | False | q.InvalidChronology; FROM stg.orders s LEFT JOIN (SELECT order_id,COUNT(*) ItemCount,SUM(price) Revenue,SUM(freight_value) Freight FROM stg.order_items GROUP BY order_id) i ON i.order_id=s.order_id LEFT JOIN (SELECT order_id,COUNT(*) PaymentCount FROM stg.payments GROUP BY order_id) p ON p.order_id=s.order_id LEFT JOIN (SELECT order_id,COUNT(*) ReviewCount FROM stg.reviews GROUP BY order_id) r ON r.order_id=s.order_id LEFT JOIN dw.DimCustomer c ON c.CustomerID=s.customer_id LEFT JOIN dw.DimOrderStatus os ON os.OrderStatus=s.order_status CROSS APPLY (SELECT CONVERT(bit,CASE WHEN s.order_approved_at<s.order_purchase_timestamp OR s.order_delivered_carrier_date<s.order_purchase_timestamp OR s.order_delivered_customer_date<s.order_purchase_timestamp OR s.order_delivered_carrier_date<s.order_approved_at OR s.order_delivered_customer_date<s.order_delivered_carrier_date THEN 1 ELSE 0 END) InvalidChronology) q CROSS APPLY (SELECT  CONVERT(bit,CASE WHEN s.order_status='delivered' AND s.order_delivered_customer_date IS NOT NULL AND s.order_estimated_delivery_date IS NOT NULL THEN 1 ELSE 0 END) OnTimeEligible,  CONVERT(bit,CASE WHEN s.order_status='delivered' AND s.order_purchase_timestamp IS NOT NULL AND s.order_delivered_customer_date>=s.order_purchase_timestamp AND q.InvalidChronology=0 THEN 1 ELSE 0 END) DurationEligible) v |
| MissingPurchaseTimestamp | bit | False | False | CONVERT(bit,CASE WHEN s.order_purchase_timestamp IS NULL THEN 1 ELSE 0 END); FROM stg.orders s LEFT JOIN (SELECT order_id,COUNT(*) ItemCount,SUM(price) Revenue,SUM(freight_value) Freight FROM stg.order_items GROUP BY order_id) i ON i.order_id=s.order_id LEFT JOIN (SELECT order_id,COUNT(*) PaymentCount FROM stg.payments GROUP BY order_id) p ON p.order_id=s.order_id LEFT JOIN (SELECT order_id,COUNT(*) ReviewCount FROM stg.reviews GROUP BY order_id) r ON r.order_id=s.order_id LEFT JOIN dw.DimCustomer c ON c.CustomerID=s.customer_id LEFT JOIN dw.DimOrderStatus os ON os.OrderStatus=s.order_status CROSS APPLY (SELECT CONVERT(bit,CASE WHEN s.order_approved_at<s.order_purchase_timestamp OR s.order_delivered_carrier_date<s.order_purchase_timestamp OR s.order_delivered_customer_date<s.order_purchase_timestamp OR s.order_delivered_carrier_date<s.order_approved_at OR s.order_delivered_customer_date<s.order_delivered_carrier_date THEN 1 ELSE 0 END) InvalidChronology) q CROSS APPLY (SELECT  CONVERT(bit,CASE WHEN s.order_status='delivered' AND s.order_delivered_customer_date IS NOT NULL AND s.order_estimated_delivery_date IS NOT NULL THEN 1 ELSE 0 END) OnTimeEligible,  CONVERT(bit,CASE WHEN s.order_status='delivered' AND s.order_purchase_timestamp IS NOT NULL AND s.order_delivered_customer_date>=s.order_purchase_timestamp AND q.InvalidChronology=0 THEN 1 ELSE 0 END) DurationEligible) v |
| MissingApprovalTimestamp | bit | False | False | CONVERT(bit,CASE WHEN s.order_approved_at IS NULL THEN 1 ELSE 0 END); FROM stg.orders s LEFT JOIN (SELECT order_id,COUNT(*) ItemCount,SUM(price) Revenue,SUM(freight_value) Freight FROM stg.order_items GROUP BY order_id) i ON i.order_id=s.order_id LEFT JOIN (SELECT order_id,COUNT(*) PaymentCount FROM stg.payments GROUP BY order_id) p ON p.order_id=s.order_id LEFT JOIN (SELECT order_id,COUNT(*) ReviewCount FROM stg.reviews GROUP BY order_id) r ON r.order_id=s.order_id LEFT JOIN dw.DimCustomer c ON c.CustomerID=s.customer_id LEFT JOIN dw.DimOrderStatus os ON os.OrderStatus=s.order_status CROSS APPLY (SELECT CONVERT(bit,CASE WHEN s.order_approved_at<s.order_purchase_timestamp OR s.order_delivered_carrier_date<s.order_purchase_timestamp OR s.order_delivered_customer_date<s.order_purchase_timestamp OR s.order_delivered_carrier_date<s.order_approved_at OR s.order_delivered_customer_date<s.order_delivered_carrier_date THEN 1 ELSE 0 END) InvalidChronology) q CROSS APPLY (SELECT  CONVERT(bit,CASE WHEN s.order_status='delivered' AND s.order_delivered_customer_date IS NOT NULL AND s.order_estimated_delivery_date IS NOT NULL THEN 1 ELSE 0 END) OnTimeEligible,  CONVERT(bit,CASE WHEN s.order_status='delivered' AND s.order_purchase_timestamp IS NOT NULL AND s.order_delivered_customer_date>=s.order_purchase_timestamp AND q.InvalidChronology=0 THEN 1 ELSE 0 END) DurationEligible) v |
| MissingCarrierTimestamp | bit | False | False | CONVERT(bit,CASE WHEN s.order_delivered_carrier_date IS NULL THEN 1 ELSE 0 END); FROM stg.orders s LEFT JOIN (SELECT order_id,COUNT(*) ItemCount,SUM(price) Revenue,SUM(freight_value) Freight FROM stg.order_items GROUP BY order_id) i ON i.order_id=s.order_id LEFT JOIN (SELECT order_id,COUNT(*) PaymentCount FROM stg.payments GROUP BY order_id) p ON p.order_id=s.order_id LEFT JOIN (SELECT order_id,COUNT(*) ReviewCount FROM stg.reviews GROUP BY order_id) r ON r.order_id=s.order_id LEFT JOIN dw.DimCustomer c ON c.CustomerID=s.customer_id LEFT JOIN dw.DimOrderStatus os ON os.OrderStatus=s.order_status CROSS APPLY (SELECT CONVERT(bit,CASE WHEN s.order_approved_at<s.order_purchase_timestamp OR s.order_delivered_carrier_date<s.order_purchase_timestamp OR s.order_delivered_customer_date<s.order_purchase_timestamp OR s.order_delivered_carrier_date<s.order_approved_at OR s.order_delivered_customer_date<s.order_delivered_carrier_date THEN 1 ELSE 0 END) InvalidChronology) q CROSS APPLY (SELECT  CONVERT(bit,CASE WHEN s.order_status='delivered' AND s.order_delivered_customer_date IS NOT NULL AND s.order_estimated_delivery_date IS NOT NULL THEN 1 ELSE 0 END) OnTimeEligible,  CONVERT(bit,CASE WHEN s.order_status='delivered' AND s.order_purchase_timestamp IS NOT NULL AND s.order_delivered_customer_date>=s.order_purchase_timestamp AND q.InvalidChronology=0 THEN 1 ELSE 0 END) DurationEligible) v |
| MissingActualDeliveryTimestamp | bit | False | False | CONVERT(bit,CASE WHEN s.order_delivered_customer_date IS NULL THEN 1 ELSE 0 END); FROM stg.orders s LEFT JOIN (SELECT order_id,COUNT(*) ItemCount,SUM(price) Revenue,SUM(freight_value) Freight FROM stg.order_items GROUP BY order_id) i ON i.order_id=s.order_id LEFT JOIN (SELECT order_id,COUNT(*) PaymentCount FROM stg.payments GROUP BY order_id) p ON p.order_id=s.order_id LEFT JOIN (SELECT order_id,COUNT(*) ReviewCount FROM stg.reviews GROUP BY order_id) r ON r.order_id=s.order_id LEFT JOIN dw.DimCustomer c ON c.CustomerID=s.customer_id LEFT JOIN dw.DimOrderStatus os ON os.OrderStatus=s.order_status CROSS APPLY (SELECT CONVERT(bit,CASE WHEN s.order_approved_at<s.order_purchase_timestamp OR s.order_delivered_carrier_date<s.order_purchase_timestamp OR s.order_delivered_customer_date<s.order_purchase_timestamp OR s.order_delivered_carrier_date<s.order_approved_at OR s.order_delivered_customer_date<s.order_delivered_carrier_date THEN 1 ELSE 0 END) InvalidChronology) q CROSS APPLY (SELECT  CONVERT(bit,CASE WHEN s.order_status='delivered' AND s.order_delivered_customer_date IS NOT NULL AND s.order_estimated_delivery_date IS NOT NULL THEN 1 ELSE 0 END) OnTimeEligible,  CONVERT(bit,CASE WHEN s.order_status='delivered' AND s.order_purchase_timestamp IS NOT NULL AND s.order_delivered_customer_date>=s.order_purchase_timestamp AND q.InvalidChronology=0 THEN 1 ELSE 0 END) DurationEligible) v |
| MissingEstimatedDeliveryTimestamp | bit | False | False | CONVERT(bit,CASE WHEN s.order_estimated_delivery_date IS NULL THEN 1 ELSE 0 END); FROM stg.orders s LEFT JOIN (SELECT order_id,COUNT(*) ItemCount,SUM(price) Revenue,SUM(freight_value) Freight FROM stg.order_items GROUP BY order_id) i ON i.order_id=s.order_id LEFT JOIN (SELECT order_id,COUNT(*) PaymentCount FROM stg.payments GROUP BY order_id) p ON p.order_id=s.order_id LEFT JOIN (SELECT order_id,COUNT(*) ReviewCount FROM stg.reviews GROUP BY order_id) r ON r.order_id=s.order_id LEFT JOIN dw.DimCustomer c ON c.CustomerID=s.customer_id LEFT JOIN dw.DimOrderStatus os ON os.OrderStatus=s.order_status CROSS APPLY (SELECT CONVERT(bit,CASE WHEN s.order_approved_at<s.order_purchase_timestamp OR s.order_delivered_carrier_date<s.order_purchase_timestamp OR s.order_delivered_customer_date<s.order_purchase_timestamp OR s.order_delivered_carrier_date<s.order_approved_at OR s.order_delivered_customer_date<s.order_delivered_carrier_date THEN 1 ELSE 0 END) InvalidChronology) q CROSS APPLY (SELECT  CONVERT(bit,CASE WHEN s.order_status='delivered' AND s.order_delivered_customer_date IS NOT NULL AND s.order_estimated_delivery_date IS NOT NULL THEN 1 ELSE 0 END) OnTimeEligible,  CONVERT(bit,CASE WHEN s.order_status='delivered' AND s.order_purchase_timestamp IS NOT NULL AND s.order_delivered_customer_date>=s.order_purchase_timestamp AND q.InvalidChronology=0 THEN 1 ELSE 0 END) DurationEligible) v |
| SourceQualityFlagCount | int | False | False | CONVERT(int,s.[dq_invalid_order_purchase_timestamp])+CONVERT(int,s.[dq_invalid_order_approved_at])+CONVERT(int,s.[dq_invalid_order_delivered_carrier_date])+CONVERT(int,s.[dq_invalid_order_delivered_customer_date])+CONVERT(int,s.[dq_invalid_order_estimated_delivery_date])+CONVERT(int,s.[dq_no_items])+CONVERT(int,s.[dq_no_payments])+CONVERT(int,s.[dq_no_reviews])+CONVERT(int,s.[dq_missing_order_approved_at])+CONVERT(int,s.[dq_delivered_missing_order_approved_at])+CONVERT(int,s.[dq_missing_order_delivered_carrier_date])+CONVERT(int,s.[dq_delivered_missing_order_delivered_carrier_date])+CONVERT(int,s.[dq_missing_order_delivered_customer_date])+CONVERT(int,s.[dq_delivered_missing_order_delivered_customer_date])+CONVERT(int,s.[dq_approval_before_purchase])+CONVERT(int,s.[dq_carrier_before_purchase])+CONVERT(int,s.[dq_delivery_before_purchase])+CONVERT(int,s.[dq_carrier_before_approval])+CONVERT(int,s.[dq_delivery_before_carrier]); FROM stg.orders s LEFT JOIN (SELECT order_id,COUNT(*) ItemCount,SUM(price) Revenue,SUM(freight_value) Freight FROM stg.order_items GROUP BY order_id) i ON i.order_id=s.order_id LEFT JOIN (SELECT order_id,COUNT(*) PaymentCount FROM stg.payments GROUP BY order_id) p ON p.order_id=s.order_id LEFT JOIN (SELECT order_id,COUNT(*) ReviewCount FROM stg.reviews GROUP BY order_id) r ON r.order_id=s.order_id LEFT JOIN dw.DimCustomer c ON c.CustomerID=s.customer_id LEFT JOIN dw.DimOrderStatus os ON os.OrderStatus=s.order_status CROSS APPLY (SELECT CONVERT(bit,CASE WHEN s.order_approved_at<s.order_purchase_timestamp OR s.order_delivered_carrier_date<s.order_purchase_timestamp OR s.order_delivered_customer_date<s.order_purchase_timestamp OR s.order_delivered_carrier_date<s.order_approved_at OR s.order_delivered_customer_date<s.order_delivered_carrier_date THEN 1 ELSE 0 END) InvalidChronology) q CROSS APPLY (SELECT  CONVERT(bit,CASE WHEN s.order_status='delivered' AND s.order_delivered_customer_date IS NOT NULL AND s.order_estimated_delivery_date IS NOT NULL THEN 1 ELSE 0 END) OnTimeEligible,  CONVERT(bit,CASE WHEN s.order_status='delivered' AND s.order_purchase_timestamp IS NOT NULL AND s.order_delivered_customer_date>=s.order_purchase_timestamp AND q.InvalidChronology=0 THEN 1 ELSE 0 END) DurationEligible) v |
| LoadID | uniqueidentifier | False | False | s.LoadID; FROM stg.orders s LEFT JOIN (SELECT order_id,COUNT(*) ItemCount,SUM(price) Revenue,SUM(freight_value) Freight FROM stg.order_items GROUP BY order_id) i ON i.order_id=s.order_id LEFT JOIN (SELECT order_id,COUNT(*) PaymentCount FROM stg.payments GROUP BY order_id) p ON p.order_id=s.order_id LEFT JOIN (SELECT order_id,COUNT(*) ReviewCount FROM stg.reviews GROUP BY order_id) r ON r.order_id=s.order_id LEFT JOIN dw.DimCustomer c ON c.CustomerID=s.customer_id LEFT JOIN dw.DimOrderStatus os ON os.OrderStatus=s.order_status CROSS APPLY (SELECT CONVERT(bit,CASE WHEN s.order_approved_at<s.order_purchase_timestamp OR s.order_delivered_carrier_date<s.order_purchase_timestamp OR s.order_delivered_customer_date<s.order_purchase_timestamp OR s.order_delivered_carrier_date<s.order_approved_at OR s.order_delivered_customer_date<s.order_delivered_carrier_date THEN 1 ELSE 0 END) InvalidChronology) q CROSS APPLY (SELECT  CONVERT(bit,CASE WHEN s.order_status='delivered' AND s.order_delivered_customer_date IS NOT NULL AND s.order_estimated_delivery_date IS NOT NULL THEN 1 ELSE 0 END) OnTimeEligible,  CONVERT(bit,CASE WHEN s.order_status='delivered' AND s.order_purchase_timestamp IS NOT NULL AND s.order_delivered_customer_date>=s.order_purchase_timestamp AND q.InvalidChronology=0 THEN 1 ELSE 0 END) DurationEligible) v |

### dw.FactPayments

Grain: one (order_id,payment_sequential). History: snapshot / load audit.

| Column | SQL type | Nullable | Identity | Source / meaning |
| --- | --- | --- | --- | --- |
| OrderID | varchar(32) | False | False | s.order_id; FROM stg.payments s JOIN dw.FactOrders o ON o.OrderID=s.order_id LEFT JOIN dw.DimPaymentType p ON p.PaymentType=s.payment_type |
| PaymentSequential | varchar(10) | False | False | s.payment_sequential; FROM stg.payments s JOIN dw.FactOrders o ON o.OrderID=s.order_id LEFT JOIN dw.DimPaymentType p ON p.PaymentType=s.payment_type |
| OrderKey | int | False | False | o.OrderKey; FROM stg.payments s JOIN dw.FactOrders o ON o.OrderID=s.order_id LEFT JOIN dw.DimPaymentType p ON p.PaymentType=s.payment_type |
| PaymentTypeKey | int | False | False | COALESCE(p.PaymentTypeKey,0); FROM stg.payments s JOIN dw.FactOrders o ON o.OrderID=s.order_id LEFT JOIN dw.DimPaymentType p ON p.PaymentType=s.payment_type |
| CustomerKey | int | False | False | o.CustomerKey; FROM stg.payments s JOIN dw.FactOrders o ON o.OrderID=s.order_id LEFT JOIN dw.DimPaymentType p ON p.PaymentType=s.payment_type |
| CustomerGeographyKey | int | False | False | o.CustomerGeographyKey; FROM stg.payments s JOIN dw.FactOrders o ON o.OrderID=s.order_id LEFT JOIN dw.DimPaymentType p ON p.PaymentType=s.payment_type |
| OrderStatusKey | int | False | False | o.OrderStatusKey; FROM stg.payments s JOIN dw.FactOrders o ON o.OrderID=s.order_id LEFT JOIN dw.DimPaymentType p ON p.PaymentType=s.payment_type |
| PurchaseDateKey | int | False | False | o.PurchaseDateKey; FROM stg.payments s JOIN dw.FactOrders o ON o.OrderID=s.order_id LEFT JOIN dw.DimPaymentType p ON p.PaymentType=s.payment_type |
| Installments | int | True | False | s.payment_installments; FROM stg.payments s JOIN dw.FactOrders o ON o.OrderID=s.order_id LEFT JOIN dw.DimPaymentType p ON p.PaymentType=s.payment_type |
| PaymentAmount | decimal(19,2) | False | False | s.payment_value; FROM stg.payments s JOIN dw.FactOrders o ON o.OrderID=s.order_id LEFT JOIN dw.DimPaymentType p ON p.PaymentType=s.payment_type |
| SalesEligible | bit | False | False | o.SalesEligible; FROM stg.payments s JOIN dw.FactOrders o ON o.OrderID=s.order_id LEFT JOIN dw.DimPaymentType p ON p.PaymentType=s.payment_type |
| SourceQualityFlagCount | int | False | False | CONVERT(int,s.[dq_invalid_payment_installments])+CONVERT(int,s.[dq_invalid_payment_value])+CONVERT(int,s.[dq_negative_payment_value])+CONVERT(int,s.[dq_zero_payment_value])+CONVERT(int,s.[dq_nonpositive_installments])+CONVERT(int,s.[dq_noninteger_payment_installments]); FROM stg.payments s JOIN dw.FactOrders o ON o.OrderID=s.order_id LEFT JOIN dw.DimPaymentType p ON p.PaymentType=s.payment_type |
| LoadID | uniqueidentifier | False | False | s.LoadID; FROM stg.payments s JOIN dw.FactOrders o ON o.OrderID=s.order_id LEFT JOIN dw.DimPaymentType p ON p.PaymentType=s.payment_type |

### dw.FactReviews

Grain: one (review_id,order_id). History: snapshot / load audit.

| Column | SQL type | Nullable | Identity | Source / meaning |
| --- | --- | --- | --- | --- |
| ReviewID | varchar(32) | False | False | s.review_id; FROM stg.reviews s JOIN dw.FactOrders o ON o.OrderID=s.order_id |
| OrderID | varchar(32) | False | False | s.order_id; FROM stg.reviews s JOIN dw.FactOrders o ON o.OrderID=s.order_id |
| OrderKey | int | False | False | o.OrderKey; FROM stg.reviews s JOIN dw.FactOrders o ON o.OrderID=s.order_id |
| CustomerKey | int | False | False | o.CustomerKey; FROM stg.reviews s JOIN dw.FactOrders o ON o.OrderID=s.order_id |
| CustomerGeographyKey | int | False | False | o.CustomerGeographyKey; FROM stg.reviews s JOIN dw.FactOrders o ON o.OrderID=s.order_id |
| OrderStatusKey | int | False | False | o.OrderStatusKey; FROM stg.reviews s JOIN dw.FactOrders o ON o.OrderID=s.order_id |
| PurchaseDateKey | int | False | False | o.PurchaseDateKey; FROM stg.reviews s JOIN dw.FactOrders o ON o.OrderID=s.order_id |
| ReviewCreationDateKey | int | False | False | COALESCE(CONVERT(int,CONVERT(char(8),s.review_creation_date,112)),0); FROM stg.reviews s JOIN dw.FactOrders o ON o.OrderID=s.order_id |
| ReviewAnswerDateKey | int | False | False | COALESCE(CONVERT(int,CONVERT(char(8),s.review_answer_timestamp,112)),0); FROM stg.reviews s JOIN dw.FactOrders o ON o.OrderID=s.order_id |
| ReviewCreationTimestamp | datetime2(0) | True | False | s.review_creation_date; FROM stg.reviews s JOIN dw.FactOrders o ON o.OrderID=s.order_id |
| ReviewAnswerTimestamp | datetime2(0) | True | False | s.review_answer_timestamp; FROM stg.reviews s JOIN dw.FactOrders o ON o.OrderID=s.order_id |
| ReviewScore | int | True | False | s.review_score; FROM stg.reviews s JOIN dw.FactOrders o ON o.OrderID=s.order_id |
| ValidScore | bit | False | False | CONVERT(bit,CASE WHEN s.review_score BETWEEN 1 AND 5 THEN 1 ELSE 0 END); FROM stg.reviews s JOIN dw.FactOrders o ON o.OrderID=s.order_id |
| HasTitle | bit | False | False | CONVERT(bit,CASE WHEN s.review_comment_title IS NULL THEN 0 ELSE 1 END); FROM stg.reviews s JOIN dw.FactOrders o ON o.OrderID=s.order_id |
| HasMessage | bit | False | False | CONVERT(bit,CASE WHEN s.review_comment_message IS NULL THEN 0 ELSE 1 END); FROM stg.reviews s JOIN dw.FactOrders o ON o.OrderID=s.order_id |
| SalesEligible | bit | False | False | o.SalesEligible; FROM stg.reviews s JOIN dw.FactOrders o ON o.OrderID=s.order_id |
| SourceQualityFlagCount | int | False | False | CONVERT(int,s.[dq_invalid_review_creation_date])+CONVERT(int,s.[dq_invalid_review_answer_timestamp])+CONVERT(int,s.[dq_invalid_review_score])+CONVERT(int,s.[dq_answer_before_creation])+CONVERT(int,s.[dq_noninteger_review_score])+CONVERT(int,s.[dq_score_out_of_range])+CONVERT(int,s.[dq_repeated_review_id]); FROM stg.reviews s JOIN dw.FactOrders o ON o.OrderID=s.order_id |
| LoadID | uniqueidentifier | False | False | s.LoadID; FROM stg.reviews s JOIN dw.FactOrders o ON o.OrderID=s.order_id |

## Power BI additions and roles

The report adds a shared `DimOrder`, separate customer/seller geography, role-playing dates and helper tables. There are 31 semantic tables, including helpers, rather than 31 warehouse business entities. The model retains 37 single-direction relationships.

`FactOrders[Delivery Timeliness]` displays On time, Late or Not eligible from the existing SLA flags. `FactOrders[Delivery Duration Band]` displays five ordered elapsed-day bins only for duration-eligible orders. These calculated display columns do not modify SQL. Review month labels sort by month number.

All 58 measures and the two display-column expressions are in [DAX reference](dax_reference.md). The [schema diagram](../sql/schema/olist_sales_dw.mmd) describes the physical warehouse; [architecture](architecture.md) explains how its relationships differ from the semantic filter graph.
