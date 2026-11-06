-- Execute inside the Python-managed snapshot transaction. No COMMIT in this file.
SET NOCOUNT ON;
SET XACT_ABORT ON;
-- This file never starts/ends a transaction; the Python loader owns it.
-- Refuse standalone/autocommit execution before any persistent write.
IF DB_NAME()<>N'OlistSalesDW'
    THROW 51000, 'Snapshot load requires OlistSalesDW.', 1;
IF XACT_STATE()<>1 OR @@TRANCOUNT=0
    THROW 51000, 'Snapshot load requires an active committable transaction.', 1;
IF OBJECT_ID(N'audit.WarehouseMetadata',N'U') IS NULL
    THROW 51000, 'Warehouse ownership marker is missing.', 1;
IF (SELECT COUNT(*) FROM audit.WarehouseMetadata)<>1
   OR NOT EXISTS(SELECT 1 FROM audit.WarehouseMetadata WHERE ProjectName=N'OlistSalesDW' AND SchemaVersion=1)
    THROW 51000, 'Unsupported warehouse ownership marker.', 1;

IF NOT EXISTS(SELECT 1 FROM dw.DimGeography WHERE GeographyKey=0)
BEGIN
 SET IDENTITY_INSERT dw.DimGeography ON;
 INSERT dw.DimGeography(GeographyKey,ZipCodePrefix,LookupMatched,ConflictingCities,ConflictingStates) VALUES(0,'~',0,0,0);
 SET IDENTITY_INSERT dw.DimGeography OFF;
END;

IF NOT EXISTS(SELECT 1 FROM dw.DimCustomer WHERE CustomerKey=0)
BEGIN
 SET IDENTITY_INSERT dw.DimCustomer ON;
 INSERT dw.DimCustomer(CustomerKey,CustomerID,GeographyKey,UnmatchedZip) VALUES(0,'~UNKNOWN',0,0);
 SET IDENTITY_INSERT dw.DimCustomer OFF;
END;

IF NOT EXISTS(SELECT 1 FROM dw.DimProduct WHERE ProductKey=0)
BEGIN
 SET IDENTITY_INSERT dw.DimProduct ON;
 INSERT dw.DimProduct(ProductKey,ProductID,CategoryLabel,CategoryMissing,CategoryUntranslated) VALUES(0,'~UNKNOWN',N'Unknown dimension member',0,0);
 SET IDENTITY_INSERT dw.DimProduct OFF;
END;

IF NOT EXISTS(SELECT 1 FROM dw.DimSeller WHERE SellerKey=0)
BEGIN
 SET IDENTITY_INSERT dw.DimSeller ON;
 INSERT dw.DimSeller(SellerKey,SellerID,GeographyKey,UnmatchedZip) VALUES(0,'~UNKNOWN',0,0);
 SET IDENTITY_INSERT dw.DimSeller OFF;
END;

IF NOT EXISTS(SELECT 1 FROM dw.DimPaymentType WHERE PaymentTypeKey=0)
BEGIN
 SET IDENTITY_INSERT dw.DimPaymentType ON;
 INSERT dw.DimPaymentType(PaymentTypeKey,PaymentType) VALUES(0,'~UNKNOWN');
 SET IDENTITY_INSERT dw.DimPaymentType OFF;
END;

IF NOT EXISTS(SELECT 1 FROM dw.DimOrderStatus WHERE OrderStatusKey=0)
BEGIN
 SET IDENTITY_INSERT dw.DimOrderStatus ON;
 INSERT dw.DimOrderStatus(OrderStatusKey,OrderStatus) VALUES(0,'~UNKNOWN');
 SET IDENTITY_INSERT dw.DimOrderStatus OFF;
END;

IF NOT EXISTS(SELECT 1 FROM dw.DimDate WHERE DateKey=0)
INSERT dw.DimDate(DateKey,MonthName,DayName) VALUES(0,'Unknown','Unknown');
DECLARE @FirstDate date, @LastDate date;
SELECT @FirstDate=MIN(d), @LastDate=MAX(d) FROM (
 SELECT CAST(order_purchase_timestamp AS date) d FROM stg.orders
 UNION ALL SELECT CAST(order_approved_at AS date) FROM stg.orders
 UNION ALL SELECT CAST(order_delivered_carrier_date AS date) FROM stg.orders
 UNION ALL SELECT CAST(order_delivered_customer_date AS date) FROM stg.orders
 UNION ALL SELECT CAST(order_estimated_delivery_date AS date) FROM stg.orders
 UNION ALL SELECT CAST(shipping_limit_date AS date) FROM stg.order_items
 UNION ALL SELECT CAST(review_creation_date AS date) FROM stg.reviews
 UNION ALL SELECT CAST(review_answer_timestamp AS date) FROM stg.reviews
) dates;
;WITH Calendar AS (
 SELECT @FirstDate AS FullDate
 UNION ALL SELECT DATEADD(day,1,FullDate) FROM Calendar WHERE FullDate<@LastDate
)
INSERT dw.DimDate(DateKey,FullDate,[Day],[Month],MonthName,[Quarter],[Year],YearMonth,DayOfWeek,DayName,IsWeekend)
SELECT CONVERT(int,CONVERT(char(8),FullDate,112)),FullDate,DAY(FullDate),MONTH(FullDate),
 CHOOSE(MONTH(FullDate),'January','February','March','April','May','June','July','August','September','October','November','December'),
 DATEPART(quarter,FullDate),YEAR(FullDate),CONVERT(char(7),FullDate,126),
 (DATEDIFF(day,CONVERT(date,'19000101',112),FullDate)%7)+1,
 CHOOSE((DATEDIFF(day,CONVERT(date,'19000101',112),FullDate)%7)+1,'Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday'),
 CASE WHEN DATEDIFF(day,CONVERT(date,'19000101',112),FullDate)%7 IN (5,6) THEN 1 ELSE 0 END
FROM Calendar c WHERE NOT EXISTS(SELECT 1 FROM dw.DimDate d WHERE d.FullDate=c.FullDate)
OPTION(MAXRECURSION 0);

SELECT z.zip AS [ZipCodePrefix],
 g.geolocation_city AS [ApproximateCity],
 g.geolocation_state AS [ApproximateState],
 g.geolocation_lat AS [Latitude],
 g.geolocation_lng AS [Longitude],
 CAST(CASE WHEN g.zip_code_prefix IS NULL THEN 0 ELSE 1 END AS bit) AS [LookupMatched],
 COALESCE(g.dq_conflicting_city_labels,0) AS [ConflictingCities],
 COALESCE(g.dq_conflicting_states,0) AS [ConflictingStates],
 g.distinct_city_labels AS [DistinctCityLabels],
 g.distinct_states AS [DistinctStateLabels]
INTO #DimGeography
FROM (SELECT zip_code_prefix zip FROM stg.geolocation_zip_lookup UNION SELECT customer_zip_code_prefix FROM stg.customers UNION SELECT seller_zip_code_prefix FROM stg.sellers) z LEFT JOIN stg.geolocation_zip_lookup g ON g.zip_code_prefix=z.zip;
UPDATE d SET d.[ApproximateCity]=s.[ApproximateCity], d.[ApproximateState]=s.[ApproximateState], d.[Latitude]=s.[Latitude], d.[Longitude]=s.[Longitude], d.[LookupMatched]=s.[LookupMatched], d.[ConflictingCities]=s.[ConflictingCities], d.[ConflictingStates]=s.[ConflictingStates], d.[DistinctCityLabels]=s.[DistinctCityLabels], d.[DistinctStateLabels]=s.[DistinctStateLabels]
FROM dw.DimGeography d JOIN #DimGeography s ON d.[ZipCodePrefix]=s.[ZipCodePrefix];
INSERT dw.DimGeography([ZipCodePrefix],[ApproximateCity],[ApproximateState],[Latitude],[Longitude],[LookupMatched],[ConflictingCities],[ConflictingStates],[DistinctCityLabels],[DistinctStateLabels])
SELECT s.[ZipCodePrefix],s.[ApproximateCity],s.[ApproximateState],s.[Latitude],s.[Longitude],s.[LookupMatched],s.[ConflictingCities],s.[ConflictingStates],s.[DistinctCityLabels],s.[DistinctStateLabels] FROM #DimGeography s
WHERE NOT EXISTS(SELECT 1 FROM dw.DimGeography d WHERE d.[ZipCodePrefix]=s.[ZipCodePrefix]) ORDER BY s.[ZipCodePrefix];
DROP TABLE #DimGeography;

SELECT s.customer_id AS [CustomerID],
 s.customer_unique_id AS [CustomerUniqueID],
 s.customer_zip_code_prefix AS [SourceZipCodePrefix],
 s.customer_city AS [SourceCity],
 s.customer_state AS [SourceState],
 COALESCE(g.GeographyKey,0) AS [GeographyKey],
 s.dq_unmatched_zip AS [UnmatchedZip]
INTO #DimCustomer
FROM stg.customers s LEFT JOIN dw.DimGeography g ON g.ZipCodePrefix=s.customer_zip_code_prefix;
UPDATE d SET d.[CustomerUniqueID]=s.[CustomerUniqueID], d.[SourceZipCodePrefix]=s.[SourceZipCodePrefix], d.[SourceCity]=s.[SourceCity], d.[SourceState]=s.[SourceState], d.[GeographyKey]=s.[GeographyKey], d.[UnmatchedZip]=s.[UnmatchedZip]
FROM dw.DimCustomer d JOIN #DimCustomer s ON d.[CustomerID]=s.[CustomerID];
INSERT dw.DimCustomer([CustomerID],[CustomerUniqueID],[SourceZipCodePrefix],[SourceCity],[SourceState],[GeographyKey],[UnmatchedZip])
SELECT s.[CustomerID],s.[CustomerUniqueID],s.[SourceZipCodePrefix],s.[SourceCity],s.[SourceState],s.[GeographyKey],s.[UnmatchedZip] FROM #DimCustomer s
WHERE NOT EXISTS(SELECT 1 FROM dw.DimCustomer d WHERE d.[CustomerID]=s.[CustomerID]) ORDER BY s.[CustomerID];
DROP TABLE #DimCustomer;

SELECT s.seller_id AS [SellerID],
 s.seller_zip_code_prefix AS [SourceZipCodePrefix],
 s.seller_city AS [SourceCity],
 s.seller_state AS [SourceState],
 COALESCE(g.GeographyKey,0) AS [GeographyKey],
 s.dq_unmatched_zip AS [UnmatchedZip]
INTO #DimSeller
FROM stg.sellers s LEFT JOIN dw.DimGeography g ON g.ZipCodePrefix=s.seller_zip_code_prefix;
UPDATE d SET d.[SourceZipCodePrefix]=s.[SourceZipCodePrefix], d.[SourceCity]=s.[SourceCity], d.[SourceState]=s.[SourceState], d.[GeographyKey]=s.[GeographyKey], d.[UnmatchedZip]=s.[UnmatchedZip]
FROM dw.DimSeller d JOIN #DimSeller s ON d.[SellerID]=s.[SellerID];
INSERT dw.DimSeller([SellerID],[SourceZipCodePrefix],[SourceCity],[SourceState],[GeographyKey],[UnmatchedZip])
SELECT s.[SellerID],s.[SourceZipCodePrefix],s.[SourceCity],s.[SourceState],s.[GeographyKey],s.[UnmatchedZip] FROM #DimSeller s
WHERE NOT EXISTS(SELECT 1 FROM dw.DimSeller d WHERE d.[SellerID]=s.[SellerID]) ORDER BY s.[SellerID];
DROP TABLE #DimSeller;

SELECT s.product_id AS [ProductID],
 s.product_category_name AS [SourceCategory],
 s.product_category_name_english AS [EnglishCategory],
 CASE WHEN s.dq_category_missing=1 THEN N'Unknown (missing category)' WHEN s.dq_category_untranslated=1 THEN N'Untranslated: '+s.product_category_name ELSE s.product_category_name_english END AS [CategoryLabel],
 s.dq_category_missing AS [CategoryMissing],
 s.dq_category_untranslated AS [CategoryUntranslated],
 s.product_name_lenght AS [NameLength],
 s.product_description_lenght AS [DescriptionLength],
 s.product_photos_qty AS [PhotosQuantity],
 s.product_weight_g AS [WeightGrams],
 s.product_length_cm AS [LengthCM],
 s.product_height_cm AS [HeightCM],
 s.product_width_cm AS [WidthCM]
INTO #DimProduct
FROM stg.products s;
UPDATE d SET d.[SourceCategory]=s.[SourceCategory], d.[EnglishCategory]=s.[EnglishCategory], d.[CategoryLabel]=s.[CategoryLabel], d.[CategoryMissing]=s.[CategoryMissing], d.[CategoryUntranslated]=s.[CategoryUntranslated], d.[NameLength]=s.[NameLength], d.[DescriptionLength]=s.[DescriptionLength], d.[PhotosQuantity]=s.[PhotosQuantity], d.[WeightGrams]=s.[WeightGrams], d.[LengthCM]=s.[LengthCM], d.[HeightCM]=s.[HeightCM], d.[WidthCM]=s.[WidthCM]
FROM dw.DimProduct d JOIN #DimProduct s ON d.[ProductID]=s.[ProductID];
INSERT dw.DimProduct([ProductID],[SourceCategory],[EnglishCategory],[CategoryLabel],[CategoryMissing],[CategoryUntranslated],[NameLength],[DescriptionLength],[PhotosQuantity],[WeightGrams],[LengthCM],[HeightCM],[WidthCM])
SELECT s.[ProductID],s.[SourceCategory],s.[EnglishCategory],s.[CategoryLabel],s.[CategoryMissing],s.[CategoryUntranslated],s.[NameLength],s.[DescriptionLength],s.[PhotosQuantity],s.[WeightGrams],s.[LengthCM],s.[HeightCM],s.[WidthCM] FROM #DimProduct s
WHERE NOT EXISTS(SELECT 1 FROM dw.DimProduct d WHERE d.[ProductID]=s.[ProductID]) ORDER BY s.[ProductID];
DROP TABLE #DimProduct;

SELECT payment_type AS [PaymentType]
INTO #DimPaymentType
FROM (SELECT DISTINCT payment_type FROM stg.payments) s;
INSERT dw.DimPaymentType([PaymentType])
SELECT s.[PaymentType] FROM #DimPaymentType s
WHERE NOT EXISTS(SELECT 1 FROM dw.DimPaymentType d WHERE d.[PaymentType]=s.[PaymentType]) ORDER BY s.[PaymentType];
DROP TABLE #DimPaymentType;

SELECT order_status AS [OrderStatus]
INTO #DimOrderStatus
FROM (SELECT DISTINCT order_status FROM stg.orders) s;
INSERT dw.DimOrderStatus([OrderStatus])
SELECT s.[OrderStatus] FROM #DimOrderStatus s
WHERE NOT EXISTS(SELECT 1 FROM dw.DimOrderStatus d WHERE d.[OrderStatus]=s.[OrderStatus]) ORDER BY s.[OrderStatus];
DROP TABLE #DimOrderStatus;

DELETE FROM dw.FactReviews;
DELETE FROM dw.FactPayments;
DELETE FROM dw.FactOrderItems;

SELECT s.order_id AS [OrderID],
 s.customer_id AS [SourceCustomerID],
 COALESCE(c.CustomerKey,0) AS [CustomerKey],
 COALESCE(c.GeographyKey,0) AS [CustomerGeographyKey],
 COALESCE(os.OrderStatusKey,0) AS [OrderStatusKey],
 COALESCE(CONVERT(int,CONVERT(char(8),s.order_purchase_timestamp,112)),0) AS [PurchaseDateKey],
 COALESCE(CONVERT(int,CONVERT(char(8),s.order_approved_at,112)),0) AS [ApprovalDateKey],
 COALESCE(CONVERT(int,CONVERT(char(8),s.order_delivered_carrier_date,112)),0) AS [CarrierDateKey],
 COALESCE(CONVERT(int,CONVERT(char(8),s.order_delivered_customer_date,112)),0) AS [ActualDeliveryDateKey],
 COALESCE(CONVERT(int,CONVERT(char(8),s.order_estimated_delivery_date,112)),0) AS [EstimatedDeliveryDateKey],
 s.order_purchase_timestamp AS [PurchaseTimestamp],
 s.order_approved_at AS [ApprovalTimestamp],
 s.order_delivered_carrier_date AS [CarrierTimestamp],
 s.order_delivered_customer_date AS [ActualDeliveryTimestamp],
 s.order_estimated_delivery_date AS [EstimatedDeliveryTimestamp],
 i.Revenue AS [MerchandiseRevenue],
 i.Freight AS [FreightAmount],
 COALESCE(i.ItemCount,0) AS [ItemCount],
 COALESCE(p.PaymentCount,0) AS [PaymentRecordCount],
 COALESCE(r.ReviewCount,0) AS [ReviewRecordCount],
 CONVERT(bit,CASE WHEN s.order_status='delivered' AND i.ItemCount>0 THEN 1 ELSE 0 END) AS [SalesEligible],
 v.OnTimeEligible AS [OnTimeEligible],
 CASE WHEN v.OnTimeEligible=1 THEN CASE WHEN CAST(s.order_delivered_customer_date AS date)<=CAST(s.order_estimated_delivery_date AS date) THEN 1 ELSE 0 END END AS [IsOnTime],
 v.DurationEligible AS [DurationEligible],
 CASE WHEN v.DurationEligible=1 THEN CONVERT(decimal(20,10),CONVERT(decimal(28,10),DATEDIFF_BIG(second,s.order_purchase_timestamp,s.order_delivered_customer_date))/CONVERT(decimal(5,0),86400)) END AS [DeliveryDurationDays],
 q.InvalidChronology AS [InvalidChronology],
 CONVERT(bit,CASE WHEN s.order_purchase_timestamp IS NULL THEN 1 ELSE 0 END) AS [MissingPurchaseTimestamp],
 CONVERT(bit,CASE WHEN s.order_approved_at IS NULL THEN 1 ELSE 0 END) AS [MissingApprovalTimestamp],
 CONVERT(bit,CASE WHEN s.order_delivered_carrier_date IS NULL THEN 1 ELSE 0 END) AS [MissingCarrierTimestamp],
 CONVERT(bit,CASE WHEN s.order_delivered_customer_date IS NULL THEN 1 ELSE 0 END) AS [MissingActualDeliveryTimestamp],
 CONVERT(bit,CASE WHEN s.order_estimated_delivery_date IS NULL THEN 1 ELSE 0 END) AS [MissingEstimatedDeliveryTimestamp],
 CONVERT(int,s.[dq_invalid_order_purchase_timestamp])+CONVERT(int,s.[dq_invalid_order_approved_at])+CONVERT(int,s.[dq_invalid_order_delivered_carrier_date])+CONVERT(int,s.[dq_invalid_order_delivered_customer_date])+CONVERT(int,s.[dq_invalid_order_estimated_delivery_date])+CONVERT(int,s.[dq_no_items])+CONVERT(int,s.[dq_no_payments])+CONVERT(int,s.[dq_no_reviews])+CONVERT(int,s.[dq_missing_order_approved_at])+CONVERT(int,s.[dq_delivered_missing_order_approved_at])+CONVERT(int,s.[dq_missing_order_delivered_carrier_date])+CONVERT(int,s.[dq_delivered_missing_order_delivered_carrier_date])+CONVERT(int,s.[dq_missing_order_delivered_customer_date])+CONVERT(int,s.[dq_delivered_missing_order_delivered_customer_date])+CONVERT(int,s.[dq_approval_before_purchase])+CONVERT(int,s.[dq_carrier_before_purchase])+CONVERT(int,s.[dq_delivery_before_purchase])+CONVERT(int,s.[dq_carrier_before_approval])+CONVERT(int,s.[dq_delivery_before_carrier]) AS [SourceQualityFlagCount],
 s.LoadID AS [LoadID]
INTO #FactOrders
FROM stg.orders s
LEFT JOIN (SELECT order_id,COUNT(*) ItemCount,SUM(price) Revenue,SUM(freight_value) Freight FROM stg.order_items GROUP BY order_id) i ON i.order_id=s.order_id
LEFT JOIN (SELECT order_id,COUNT(*) PaymentCount FROM stg.payments GROUP BY order_id) p ON p.order_id=s.order_id
LEFT JOIN (SELECT order_id,COUNT(*) ReviewCount FROM stg.reviews GROUP BY order_id) r ON r.order_id=s.order_id
LEFT JOIN dw.DimCustomer c ON c.CustomerID=s.customer_id
LEFT JOIN dw.DimOrderStatus os ON os.OrderStatus=s.order_status
CROSS APPLY (SELECT CONVERT(bit,CASE WHEN s.order_approved_at<s.order_purchase_timestamp OR s.order_delivered_carrier_date<s.order_purchase_timestamp OR s.order_delivered_customer_date<s.order_purchase_timestamp OR s.order_delivered_carrier_date<s.order_approved_at OR s.order_delivered_customer_date<s.order_delivered_carrier_date THEN 1 ELSE 0 END) InvalidChronology) q
CROSS APPLY (SELECT
 CONVERT(bit,CASE WHEN s.order_status='delivered' AND s.order_delivered_customer_date IS NOT NULL AND s.order_estimated_delivery_date IS NOT NULL THEN 1 ELSE 0 END) OnTimeEligible,
 CONVERT(bit,CASE WHEN s.order_status='delivered' AND s.order_purchase_timestamp IS NOT NULL AND s.order_delivered_customer_date>=s.order_purchase_timestamp AND q.InvalidChronology=0 THEN 1 ELSE 0 END) DurationEligible) v;
UPDATE d SET d.[SourceCustomerID]=s.[SourceCustomerID], d.[CustomerKey]=s.[CustomerKey], d.[CustomerGeographyKey]=s.[CustomerGeographyKey], d.[OrderStatusKey]=s.[OrderStatusKey], d.[PurchaseDateKey]=s.[PurchaseDateKey], d.[ApprovalDateKey]=s.[ApprovalDateKey], d.[CarrierDateKey]=s.[CarrierDateKey], d.[ActualDeliveryDateKey]=s.[ActualDeliveryDateKey], d.[EstimatedDeliveryDateKey]=s.[EstimatedDeliveryDateKey], d.[PurchaseTimestamp]=s.[PurchaseTimestamp], d.[ApprovalTimestamp]=s.[ApprovalTimestamp], d.[CarrierTimestamp]=s.[CarrierTimestamp], d.[ActualDeliveryTimestamp]=s.[ActualDeliveryTimestamp], d.[EstimatedDeliveryTimestamp]=s.[EstimatedDeliveryTimestamp], d.[MerchandiseRevenue]=s.[MerchandiseRevenue], d.[FreightAmount]=s.[FreightAmount], d.[ItemCount]=s.[ItemCount], d.[PaymentRecordCount]=s.[PaymentRecordCount], d.[ReviewRecordCount]=s.[ReviewRecordCount], d.[SalesEligible]=s.[SalesEligible], d.[OnTimeEligible]=s.[OnTimeEligible], d.[IsOnTime]=s.[IsOnTime], d.[DurationEligible]=s.[DurationEligible], d.[DeliveryDurationDays]=s.[DeliveryDurationDays], d.[InvalidChronology]=s.[InvalidChronology], d.[MissingPurchaseTimestamp]=s.[MissingPurchaseTimestamp], d.[MissingApprovalTimestamp]=s.[MissingApprovalTimestamp], d.[MissingCarrierTimestamp]=s.[MissingCarrierTimestamp], d.[MissingActualDeliveryTimestamp]=s.[MissingActualDeliveryTimestamp], d.[MissingEstimatedDeliveryTimestamp]=s.[MissingEstimatedDeliveryTimestamp], d.[SourceQualityFlagCount]=s.[SourceQualityFlagCount], d.[LoadID]=s.[LoadID]
FROM dw.FactOrders d JOIN #FactOrders s ON d.[OrderID]=s.[OrderID];
INSERT dw.FactOrders([OrderID],[SourceCustomerID],[CustomerKey],[CustomerGeographyKey],[OrderStatusKey],[PurchaseDateKey],[ApprovalDateKey],[CarrierDateKey],[ActualDeliveryDateKey],[EstimatedDeliveryDateKey],[PurchaseTimestamp],[ApprovalTimestamp],[CarrierTimestamp],[ActualDeliveryTimestamp],[EstimatedDeliveryTimestamp],[MerchandiseRevenue],[FreightAmount],[ItemCount],[PaymentRecordCount],[ReviewRecordCount],[SalesEligible],[OnTimeEligible],[IsOnTime],[DurationEligible],[DeliveryDurationDays],[InvalidChronology],[MissingPurchaseTimestamp],[MissingApprovalTimestamp],[MissingCarrierTimestamp],[MissingActualDeliveryTimestamp],[MissingEstimatedDeliveryTimestamp],[SourceQualityFlagCount],[LoadID])
SELECT s.[OrderID],s.[SourceCustomerID],s.[CustomerKey],s.[CustomerGeographyKey],s.[OrderStatusKey],s.[PurchaseDateKey],s.[ApprovalDateKey],s.[CarrierDateKey],s.[ActualDeliveryDateKey],s.[EstimatedDeliveryDateKey],s.[PurchaseTimestamp],s.[ApprovalTimestamp],s.[CarrierTimestamp],s.[ActualDeliveryTimestamp],s.[EstimatedDeliveryTimestamp],s.[MerchandiseRevenue],s.[FreightAmount],s.[ItemCount],s.[PaymentRecordCount],s.[ReviewRecordCount],s.[SalesEligible],s.[OnTimeEligible],s.[IsOnTime],s.[DurationEligible],s.[DeliveryDurationDays],s.[InvalidChronology],s.[MissingPurchaseTimestamp],s.[MissingApprovalTimestamp],s.[MissingCarrierTimestamp],s.[MissingActualDeliveryTimestamp],s.[MissingEstimatedDeliveryTimestamp],s.[SourceQualityFlagCount],s.[LoadID] FROM #FactOrders s
WHERE NOT EXISTS(SELECT 1 FROM dw.FactOrders d WHERE d.[OrderID]=s.[OrderID]) ORDER BY s.[OrderID];
DROP TABLE #FactOrders;

DELETE d FROM dw.FactOrders d WHERE NOT EXISTS(SELECT 1 FROM stg.orders s WHERE s.order_id=d.OrderID);

INSERT dw.FactOrderItems([OrderID],[OrderKey],[CustomerKey],[CustomerGeographyKey],[OrderStatusKey],[PurchaseDateKey],[SalesEligible],[LoadID],[OrderItemID],[SourceProductID],[SourceSellerID],[ProductKey],[SellerKey],[SellerGeographyKey],[ShippingLimitDateKey],[ShippingLimitTimestamp],[ItemPrice],[FreightValue],[SourceQualityFlagCount])
SELECT s.order_id,
 o.OrderKey,
 o.CustomerKey,
 o.CustomerGeographyKey,
 o.OrderStatusKey,
 o.PurchaseDateKey,
 o.SalesEligible,
 s.LoadID,
 s.order_item_id,
 s.product_id,
 s.seller_id,
 COALESCE(p.ProductKey,0),
 COALESCE(v.SellerKey,0),
 COALESCE(v.GeographyKey,0),
 COALESCE(CONVERT(int,CONVERT(char(8),s.shipping_limit_date,112)),0),
 s.shipping_limit_date,
 s.price,
 s.freight_value,
 CONVERT(int,s.[dq_invalid_shipping_limit_date])+CONVERT(int,s.[dq_invalid_price])+CONVERT(int,s.[dq_invalid_freight_value])+CONVERT(int,s.[dq_shipping_limit_before_purchase])+CONVERT(int,s.[dq_shipping_limit_after_purchase_year_range])+CONVERT(int,s.[dq_negative_price])+CONVERT(int,s.[dq_zero_price])+CONVERT(int,s.[dq_negative_freight_value])+CONVERT(int,s.[dq_zero_freight_value])
FROM stg.order_items s JOIN dw.FactOrders o ON o.OrderID=s.order_id LEFT JOIN dw.DimProduct p ON p.ProductID=s.product_id LEFT JOIN dw.DimSeller v ON v.SellerID=s.seller_id;

INSERT dw.FactPayments([OrderID],[OrderKey],[CustomerKey],[CustomerGeographyKey],[OrderStatusKey],[PurchaseDateKey],[SalesEligible],[LoadID],[PaymentSequential],[PaymentTypeKey],[Installments],[PaymentAmount],[SourceQualityFlagCount])
SELECT s.order_id,
 o.OrderKey,
 o.CustomerKey,
 o.CustomerGeographyKey,
 o.OrderStatusKey,
 o.PurchaseDateKey,
 o.SalesEligible,
 s.LoadID,
 s.payment_sequential,
 COALESCE(p.PaymentTypeKey,0),
 s.payment_installments,
 s.payment_value,
 CONVERT(int,s.[dq_invalid_payment_installments])+CONVERT(int,s.[dq_invalid_payment_value])+CONVERT(int,s.[dq_negative_payment_value])+CONVERT(int,s.[dq_zero_payment_value])+CONVERT(int,s.[dq_nonpositive_installments])+CONVERT(int,s.[dq_noninteger_payment_installments])
FROM stg.payments s JOIN dw.FactOrders o ON o.OrderID=s.order_id LEFT JOIN dw.DimPaymentType p ON p.PaymentType=s.payment_type;

INSERT dw.FactReviews([OrderID],[OrderKey],[CustomerKey],[CustomerGeographyKey],[OrderStatusKey],[PurchaseDateKey],[SalesEligible],[LoadID],[ReviewID],[ReviewCreationDateKey],[ReviewAnswerDateKey],[ReviewCreationTimestamp],[ReviewAnswerTimestamp],[ReviewScore],[ValidScore],[HasTitle],[HasMessage],[SourceQualityFlagCount])
SELECT s.order_id,
 o.OrderKey,
 o.CustomerKey,
 o.CustomerGeographyKey,
 o.OrderStatusKey,
 o.PurchaseDateKey,
 o.SalesEligible,
 s.LoadID,
 s.review_id,
 COALESCE(CONVERT(int,CONVERT(char(8),s.review_creation_date,112)),0),
 COALESCE(CONVERT(int,CONVERT(char(8),s.review_answer_timestamp,112)),0),
 s.review_creation_date,
 s.review_answer_timestamp,
 s.review_score,
 CONVERT(bit,CASE WHEN s.review_score BETWEEN 1 AND 5 THEN 1 ELSE 0 END),
 CONVERT(bit,CASE WHEN s.review_comment_title IS NULL THEN 0 ELSE 1 END),
 CONVERT(bit,CASE WHEN s.review_comment_message IS NULL THEN 0 ELSE 1 END),
 CONVERT(int,s.[dq_invalid_review_creation_date])+CONVERT(int,s.[dq_invalid_review_answer_timestamp])+CONVERT(int,s.[dq_invalid_review_score])+CONVERT(int,s.[dq_answer_before_creation])+CONVERT(int,s.[dq_noninteger_review_score])+CONVERT(int,s.[dq_score_out_of_range])+CONVERT(int,s.[dq_repeated_review_id])
FROM stg.reviews s JOIN dw.FactOrders o ON o.OrderID=s.order_id;
