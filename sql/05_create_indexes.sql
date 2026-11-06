-- Compact rowstore indexes for this snapshot. Do not index every low-cardinality flag.
IF NOT EXISTS(SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID(N'dw.DimDate') AND name=N'IX_DimDate_FullDate')
CREATE UNIQUE INDEX IX_DimDate_FullDate ON dw.DimDate(FullDate) WHERE FullDate IS NOT NULL;
GO
IF NOT EXISTS(SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID(N'dw.DimCustomer') AND name=N'IX_DimCustomer_UniqueIdentity')
CREATE  INDEX IX_DimCustomer_UniqueIdentity ON dw.DimCustomer(CustomerUniqueID) INCLUDE(SourceState);
GO
IF NOT EXISTS(SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID(N'dw.DimCustomer') AND name=N'IX_DimCustomer_Geography')
CREATE  INDEX IX_DimCustomer_Geography ON dw.DimCustomer(GeographyKey) ;
GO
IF NOT EXISTS(SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID(N'dw.DimSeller') AND name=N'IX_DimSeller_Geography')
CREATE  INDEX IX_DimSeller_Geography ON dw.DimSeller(GeographyKey) ;
GO
IF NOT EXISTS(SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID(N'dw.FactOrders') AND name=N'IX_FactOrders_SalesDate')
CREATE  INDEX IX_FactOrders_SalesDate ON dw.FactOrders(SalesEligible,PurchaseDateKey) INCLUDE(MerchandiseRevenue,FreightAmount,ItemCount,CustomerKey);
GO
IF NOT EXISTS(SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID(N'dw.FactOrders') AND name=N'IX_FactOrders_Customer')
CREATE  INDEX IX_FactOrders_Customer ON dw.FactOrders(CustomerKey) INCLUDE(SalesEligible,MerchandiseRevenue);
GO
IF NOT EXISTS(SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID(N'dw.FactOrders') AND name=N'IX_FactOrders_Status')
CREATE  INDEX IX_FactOrders_Status ON dw.FactOrders(OrderStatusKey) ;
GO
IF NOT EXISTS(SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID(N'dw.FactOrders') AND name=N'IX_FactOrders_Geography')
CREATE  INDEX IX_FactOrders_Geography ON dw.FactOrders(CustomerGeographyKey) ;
GO
IF NOT EXISTS(SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID(N'dw.FactOrders') AND name=N'IX_FactOrders_ActualDelivery')
CREATE  INDEX IX_FactOrders_ActualDelivery ON dw.FactOrders(ActualDeliveryDateKey) INCLUDE(OnTimeEligible,IsOnTime,DurationEligible,DeliveryDurationDays);
GO
IF NOT EXISTS(SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID(N'dw.FactOrderItems') AND name=N'IX_FactOrderItems_OrderKey')
CREATE  INDEX IX_FactOrderItems_OrderKey ON dw.FactOrderItems(OrderKey) ;
GO
IF NOT EXISTS(SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID(N'dw.FactOrderItems') AND name=N'IX_FactOrderItems_Product')
CREATE  INDEX IX_FactOrderItems_Product ON dw.FactOrderItems(ProductKey) INCLUDE(ItemPrice,SalesEligible,OrderKey);
GO
IF NOT EXISTS(SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID(N'dw.FactOrderItems') AND name=N'IX_FactOrderItems_Seller')
CREATE  INDEX IX_FactOrderItems_Seller ON dw.FactOrderItems(SellerKey) ;
GO
IF NOT EXISTS(SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID(N'dw.FactOrderItems') AND name=N'IX_FactOrderItems_PurchaseDate')
CREATE  INDEX IX_FactOrderItems_PurchaseDate ON dw.FactOrderItems(PurchaseDateKey) ;
GO
IF NOT EXISTS(SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID(N'dw.FactPayments') AND name=N'IX_FactPayments_OrderKey')
CREATE  INDEX IX_FactPayments_OrderKey ON dw.FactPayments(OrderKey) ;
GO
IF NOT EXISTS(SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID(N'dw.FactPayments') AND name=N'IX_FactPayments_TypeDate')
CREATE  INDEX IX_FactPayments_TypeDate ON dw.FactPayments(PaymentTypeKey,PurchaseDateKey) INCLUDE(PaymentAmount,SalesEligible);
GO
IF NOT EXISTS(SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID(N'dw.FactReviews') AND name=N'IX_FactReviews_OrderKey')
CREATE  INDEX IX_FactReviews_OrderKey ON dw.FactReviews(OrderKey) INCLUDE(ReviewScore,ValidScore,SalesEligible);
GO
IF NOT EXISTS(SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID(N'dw.FactReviews') AND name=N'IX_FactReviews_CreationDate')
CREATE  INDEX IX_FactReviews_CreationDate ON dw.FactReviews(ReviewCreationDateKey) ;
GO
