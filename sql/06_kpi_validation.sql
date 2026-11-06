-- Independent SQL calculations: derive eligibility from source status and actual child counts.
-- No joins between detail fact tables; aggregate each grain independently.
SET NOCOUNT ON;
;WITH Eligible AS (
 SELECT o.* FROM dw.FactOrders o JOIN dw.DimOrderStatus s ON s.OrderStatusKey=o.OrderStatusKey
 WHERE s.OrderStatus='delivered' AND EXISTS(SELECT 1 FROM dw.FactOrderItems i WHERE i.OrderKey=o.OrderKey)
), Items AS (
 SELECT i.* FROM dw.FactOrderItems i JOIN Eligible e ON e.OrderKey=i.OrderKey
), Customers AS (
 SELECT c.CustomerUniqueID,COUNT_BIG(*) OrderCount FROM Eligible e
 JOIN dw.DimCustomer c ON c.CustomerKey=e.CustomerKey GROUP BY c.CustomerUniqueID
), Delivery AS (
 SELECT o.*,
 CASE WHEN ApprovalTimestamp<PurchaseTimestamp OR CarrierTimestamp<PurchaseTimestamp
 OR ActualDeliveryTimestamp<PurchaseTimestamp OR CarrierTimestamp<ApprovalTimestamp
 OR ActualDeliveryTimestamp<CarrierTimestamp THEN 1 ELSE 0 END BadChronology
 FROM dw.FactOrders o JOIN dw.DimOrderStatus s ON s.OrderStatusKey=o.OrderStatusKey WHERE s.OrderStatus='delivered'
), OnTime AS (
 SELECT * FROM Delivery WHERE ActualDeliveryTimestamp IS NOT NULL AND EstimatedDeliveryTimestamp IS NOT NULL
), Duration AS (
 SELECT * FROM Delivery WHERE PurchaseTimestamp IS NOT NULL AND ActualDeliveryTimestamp>=PurchaseTimestamp AND BadChronology=0
), Reviews AS (
 SELECT r.* FROM dw.FactReviews r JOIN Eligible e ON e.OrderKey=r.OrderKey WHERE r.ReviewScore BETWEEN 1 AND 5
), Monthly AS (
 SELECT d.YearMonth,SUM(i.ItemPrice) Revenue FROM Items i JOIN dw.DimDate d ON d.DateKey=i.PurchaseDateKey GROUP BY d.YearMonth
), Categories AS (
 SELECT p.CategoryLabel,SUM(i.ItemPrice) Revenue FROM Items i JOIN dw.DimProduct p ON p.ProductKey=i.ProductKey GROUP BY p.CategoryLabel
), States AS (
 SELECT c.SourceState,SUM(i.ItemPrice) Revenue FROM Items i JOIN dw.DimCustomer c ON c.CustomerKey=i.CustomerKey GROUP BY c.SourceState
)
-- Normalize EVERY arm before UNION ALL. SUM(decimal(19,2)) returns decimal(38,2);
-- mixing it with decimal(38,10) otherwise forces the union to scale 2.
-- An outer cast cannot recover fractional digits already rounded by the union.
SELECT Metric,ActualValue FROM (
 SELECT 'Merchandise Revenue' Metric,CONVERT(decimal(38,10),SUM(ItemPrice)) ActualValue FROM Items
 UNION ALL SELECT 'Eligible Orders',CONVERT(decimal(38,10),COUNT_BIG(*)) FROM Eligible
 UNION ALL SELECT 'Excluded Orders',CONVERT(decimal(38,10),(SELECT COUNT_BIG(*) FROM dw.FactOrders)-COUNT_BIG(*)) FROM Eligible
 UNION ALL SELECT 'Unique Customers',CONVERT(decimal(38,10),COUNT_BIG(*)) FROM Customers
 UNION ALL SELECT 'Items Sold',CONVERT(decimal(38,10),COUNT_BIG(*)) FROM Items
 UNION ALL SELECT 'Freight Total',CONVERT(decimal(38,10),SUM(FreightValue)) FROM Items
 UNION ALL SELECT 'Average Freight / Order',CONVERT(decimal(38,10),CONVERT(decimal(28,10),SUM(FreightValue))/CONVERT(decimal(19,0),(SELECT COUNT_BIG(*) FROM Eligible))) FROM Items
 UNION ALL SELECT 'AOV',CONVERT(decimal(38,10),CONVERT(decimal(28,10),SUM(ItemPrice))/CONVERT(decimal(19,0),(SELECT COUNT_BIG(*) FROM Eligible))) FROM Items
 UNION ALL SELECT 'On-Time Eligible Orders',CONVERT(decimal(38,10),COUNT_BIG(*)) FROM OnTime
 UNION ALL SELECT 'On-Time Orders',CONVERT(decimal(38,10),COUNT_BIG(*)) FROM OnTime WHERE CAST(ActualDeliveryTimestamp AS date)<=CAST(EstimatedDeliveryTimestamp AS date)
 UNION ALL SELECT 'Late Orders',CONVERT(decimal(38,10),COUNT_BIG(*)) FROM OnTime WHERE CAST(ActualDeliveryTimestamp AS date)>CAST(EstimatedDeliveryTimestamp AS date)
 UNION ALL SELECT 'On-Time Rate',CONVERT(decimal(38,10),100.0*CONVERT(decimal(28,10),SUM(CASE WHEN CAST(ActualDeliveryTimestamp AS date)<=CAST(EstimatedDeliveryTimestamp AS date) THEN CONVERT(bigint,1) ELSE CONVERT(bigint,0) END))/CONVERT(decimal(19,0),COUNT_BIG(*))) FROM OnTime
 UNION ALL SELECT 'Duration-Eligible Orders',CONVERT(decimal(38,10),COUNT_BIG(*)) FROM Duration
 UNION ALL SELECT 'Average Duration',CONVERT(decimal(38,10),CONVERT(decimal(28,10),SUM(DATEDIFF_BIG(second,PurchaseTimestamp,ActualDeliveryTimestamp)))/CONVERT(decimal(19,0),COUNT_BIG(*))/CONVERT(decimal(5,0),86400)) FROM Duration
 UNION ALL SELECT 'Valid Review Records',CONVERT(decimal(38,10),COUNT_BIG(*)) FROM Reviews
 UNION ALL SELECT 'Average Review Score',CONVERT(decimal(38,10),AVG(CONVERT(decimal(20,10),ReviewScore))) FROM Reviews
 UNION ALL SELECT 'Repeat Customers',CONVERT(decimal(38,10),COUNT_BIG(*)) FROM Customers WHERE OrderCount>=2
 UNION ALL SELECT 'Repeat Customer Rate',CONVERT(decimal(38,10),100.0*CONVERT(decimal(28,10),SUM(CASE WHEN OrderCount>=2 THEN CONVERT(bigint,1) ELSE CONVERT(bigint,0) END))/CONVERT(decimal(19,0),COUNT_BIG(*))) FROM Customers
 UNION ALL SELECT 'Revenue - order totals',CONVERT(decimal(38,10),SUM(MerchandiseRevenue)) FROM Eligible
 UNION ALL SELECT 'Revenue - monthly totals',CONVERT(decimal(38,10),SUM(Revenue)) FROM Monthly
 UNION ALL SELECT 'Revenue - categories',CONVERT(decimal(38,10),SUM(Revenue)) FROM Categories
 UNION ALL SELECT 'Revenue - customer states',CONVERT(decimal(38,10),SUM(Revenue)) FROM States
 UNION ALL SELECT 'All Item Price',CONVERT(decimal(38,10),SUM(ItemPrice)) FROM dw.FactOrderItems
 UNION ALL SELECT 'All Freight',CONVERT(decimal(38,10),SUM(FreightValue)) FROM dw.FactOrderItems
 UNION ALL SELECT 'All Payments',CONVERT(decimal(38,10),SUM(PaymentAmount)) FROM dw.FactPayments
) metrics ORDER BY Metric;
