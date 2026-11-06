-- FactOrders retains all statuses. Missing item totals are NULL, never fabricated zero baskets.
IF OBJECT_ID(N'dw.FactOrders',N'U') IS NULL
CREATE TABLE dw.FactOrders (
    OrderKey int IDENTITY(1,1) NOT NULL PRIMARY KEY,
    OrderID varchar(32) NOT NULL UNIQUE,
    SourceCustomerID varchar(32) NOT NULL,
    CustomerKey int NOT NULL REFERENCES dw.DimCustomer(CustomerKey),
    CustomerGeographyKey int NOT NULL REFERENCES dw.DimGeography(GeographyKey),
    OrderStatusKey int NOT NULL REFERENCES dw.DimOrderStatus(OrderStatusKey),
    PurchaseDateKey int NOT NULL REFERENCES dw.DimDate(DateKey),
    ApprovalDateKey int NOT NULL REFERENCES dw.DimDate(DateKey),
    CarrierDateKey int NOT NULL REFERENCES dw.DimDate(DateKey),
    ActualDeliveryDateKey int NOT NULL REFERENCES dw.DimDate(DateKey),
    EstimatedDeliveryDateKey int NOT NULL REFERENCES dw.DimDate(DateKey),
    PurchaseTimestamp datetime2(0) NULL, ApprovalTimestamp datetime2(0) NULL,
    CarrierTimestamp datetime2(0) NULL, ActualDeliveryTimestamp datetime2(0) NULL,
    EstimatedDeliveryTimestamp datetime2(0) NULL,
    MerchandiseRevenue decimal(19,2) NULL, FreightAmount decimal(19,2) NULL,
    ItemCount int NOT NULL, PaymentRecordCount int NOT NULL, ReviewRecordCount int NOT NULL,
    SalesEligible bit NOT NULL, OnTimeEligible bit NOT NULL, IsOnTime bit NULL,
    DurationEligible bit NOT NULL, DeliveryDurationDays decimal(20,10) NULL,
    InvalidChronology bit NOT NULL, MissingPurchaseTimestamp bit NOT NULL,
    MissingApprovalTimestamp bit NOT NULL, MissingCarrierTimestamp bit NOT NULL,
    MissingActualDeliveryTimestamp bit NOT NULL, MissingEstimatedDeliveryTimestamp bit NOT NULL,
    SourceQualityFlagCount int NOT NULL,
    LoadID uniqueidentifier NOT NULL REFERENCES audit.LoadRun(LoadID),
    CONSTRAINT UQ_FactOrders_Key_ID UNIQUE(OrderKey,OrderID),
    CONSTRAINT CK_FactOrders_OnTime CHECK((OnTimeEligible=0 AND IsOnTime IS NULL) OR (OnTimeEligible=1 AND IsOnTime IS NOT NULL)),
    CONSTRAINT CK_FactOrders_Duration CHECK((DurationEligible=0 AND DeliveryDurationDays IS NULL) OR (DurationEligible=1 AND DeliveryDurationDays IS NOT NULL AND DeliveryDurationDays>=0))
);
IF OBJECT_ID(N'dw.FactOrderItems',N'U') IS NULL
CREATE TABLE dw.FactOrderItems (
    OrderID varchar(32) NOT NULL, OrderItemID varchar(10) NOT NULL,
    OrderKey int NOT NULL, SourceProductID varchar(32) NOT NULL, SourceSellerID varchar(32) NOT NULL,
    ProductKey int NOT NULL REFERENCES dw.DimProduct(ProductKey),
    SellerKey int NOT NULL REFERENCES dw.DimSeller(SellerKey),
    CustomerKey int NOT NULL REFERENCES dw.DimCustomer(CustomerKey),
    CustomerGeographyKey int NOT NULL REFERENCES dw.DimGeography(GeographyKey),
    SellerGeographyKey int NOT NULL REFERENCES dw.DimGeography(GeographyKey),
    OrderStatusKey int NOT NULL REFERENCES dw.DimOrderStatus(OrderStatusKey),
    PurchaseDateKey int NOT NULL REFERENCES dw.DimDate(DateKey),
    ShippingLimitDateKey int NOT NULL REFERENCES dw.DimDate(DateKey),
    ShippingLimitTimestamp datetime2(0) NULL,
    ItemPrice decimal(19,2) NOT NULL, FreightValue decimal(19,2) NOT NULL,
    SalesEligible bit NOT NULL, SourceQualityFlagCount int NOT NULL,
    LoadID uniqueidentifier NOT NULL REFERENCES audit.LoadRun(LoadID),
    PRIMARY KEY(OrderID,OrderItemID),
    FOREIGN KEY(OrderKey,OrderID) REFERENCES dw.FactOrders(OrderKey,OrderID)
);
IF OBJECT_ID(N'dw.FactPayments',N'U') IS NULL
CREATE TABLE dw.FactPayments (
    OrderID varchar(32) NOT NULL, PaymentSequential varchar(10) NOT NULL,
    OrderKey int NOT NULL, PaymentTypeKey int NOT NULL REFERENCES dw.DimPaymentType(PaymentTypeKey),
    CustomerKey int NOT NULL REFERENCES dw.DimCustomer(CustomerKey),
    CustomerGeographyKey int NOT NULL REFERENCES dw.DimGeography(GeographyKey),
    OrderStatusKey int NOT NULL REFERENCES dw.DimOrderStatus(OrderStatusKey),
    PurchaseDateKey int NOT NULL REFERENCES dw.DimDate(DateKey),
    Installments int NULL, PaymentAmount decimal(19,2) NOT NULL,
    SalesEligible bit NOT NULL, SourceQualityFlagCount int NOT NULL,
    LoadID uniqueidentifier NOT NULL REFERENCES audit.LoadRun(LoadID),
    PRIMARY KEY(OrderID,PaymentSequential),
    FOREIGN KEY(OrderKey,OrderID) REFERENCES dw.FactOrders(OrderKey,OrderID)
);
IF OBJECT_ID(N'dw.FactReviews',N'U') IS NULL
CREATE TABLE dw.FactReviews (
    ReviewID varchar(32) NOT NULL, OrderID varchar(32) NOT NULL, OrderKey int NOT NULL,
    CustomerKey int NOT NULL REFERENCES dw.DimCustomer(CustomerKey),
    CustomerGeographyKey int NOT NULL REFERENCES dw.DimGeography(GeographyKey),
    OrderStatusKey int NOT NULL REFERENCES dw.DimOrderStatus(OrderStatusKey),
    PurchaseDateKey int NOT NULL REFERENCES dw.DimDate(DateKey),
    ReviewCreationDateKey int NOT NULL REFERENCES dw.DimDate(DateKey),
    ReviewAnswerDateKey int NOT NULL REFERENCES dw.DimDate(DateKey),
    ReviewCreationTimestamp datetime2(0) NULL, ReviewAnswerTimestamp datetime2(0) NULL,
    ReviewScore int NULL, ValidScore bit NOT NULL, HasTitle bit NOT NULL, HasMessage bit NOT NULL,
    SalesEligible bit NOT NULL, SourceQualityFlagCount int NOT NULL,
    LoadID uniqueidentifier NOT NULL REFERENCES audit.LoadRun(LoadID),
    PRIMARY KEY(ReviewID,OrderID),
    FOREIGN KEY(OrderKey,OrderID) REFERENCES dw.FactOrders(OrderKey,OrderID)
);
GO
