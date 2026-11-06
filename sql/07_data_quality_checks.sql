-- Report retained source conditions; they are warnings, not automatic deletion rules.
SET NOCOUNT ON;
SELECT CheckName,AffectedRows FROM (
 SELECT 'Orders without items' CheckName,COUNT_BIG(*) AffectedRows FROM dw.FactOrders WHERE ItemCount=0
 UNION ALL SELECT 'Orders without payments',COUNT_BIG(*) FROM dw.FactOrders WHERE PaymentRecordCount=0
 UNION ALL SELECT 'Orders without reviews',COUNT_BIG(*) FROM dw.FactOrders WHERE ReviewRecordCount=0
 UNION ALL SELECT 'Missing actual delivery timestamp',COUNT_BIG(*) FROM dw.FactOrders WHERE MissingActualDeliveryTimestamp=1
 UNION ALL SELECT 'Invalid chronology',COUNT_BIG(*) FROM dw.FactOrders WHERE InvalidChronology=1
 UNION ALL SELECT 'Customers with unmatched ZIP',COUNT_BIG(*) FROM dw.DimCustomer WHERE UnmatchedZip=1
 UNION ALL SELECT 'Sellers with unmatched ZIP',COUNT_BIG(*) FROM dw.DimSeller WHERE UnmatchedZip=1
 UNION ALL SELECT 'ZIP prefixes with conflicting cities',COUNT_BIG(*) FROM dw.DimGeography WHERE ConflictingCities=1
 UNION ALL SELECT 'ZIP prefixes with conflicting states',COUNT_BIG(*) FROM dw.DimGeography WHERE ConflictingStates=1
 UNION ALL SELECT 'Missing product category',COUNT_BIG(*) FROM dw.DimProduct WHERE CategoryMissing=1
 UNION ALL SELECT 'Untranslated product category',COUNT_BIG(*) FROM dw.DimProduct WHERE CategoryUntranslated=1
 UNION ALL SELECT 'Repeated review ID excess',COUNT_BIG(*)-COUNT_BIG(DISTINCT ReviewID) FROM dw.FactReviews
 UNION ALL SELECT 'Zero payment amounts',COUNT_BIG(*) FROM dw.FactPayments WHERE PaymentAmount=0
 UNION ALL SELECT 'Nonpositive installments',COUNT_BIG(*) FROM dw.FactPayments WHERE Installments<=0
 UNION ALL SELECT 'Delivered payment amount differs from merchandise plus freight',COUNT_BIG(*)
 FROM dw.FactOrders o JOIN (SELECT OrderKey,SUM(PaymentAmount) Amount FROM dw.FactPayments GROUP BY OrderKey) p ON p.OrderKey=o.OrderKey
 WHERE o.SalesEligible=1 AND o.ItemCount>0 AND p.Amount<>o.MerchandiseRevenue+o.FreightAmount
) warnings ORDER BY CheckName;
