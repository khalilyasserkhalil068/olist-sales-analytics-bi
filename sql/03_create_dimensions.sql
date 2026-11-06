-- Type 1 source snapshots: stable surrogate keys; no invented attribute history.
IF OBJECT_ID(N'dw.DimDate',N'U') IS NULL
CREATE TABLE dw.DimDate (
    DateKey int NOT NULL PRIMARY KEY,
    FullDate date NULL,
    [Day] tinyint NULL, [Month] tinyint NULL, MonthName varchar(12) NOT NULL,
    [Quarter] tinyint NULL, [Year] smallint NULL, YearMonth char(7) NULL,
    DayOfWeek tinyint NULL, DayName varchar(12) NOT NULL, IsWeekend bit NULL
);
IF OBJECT_ID(N'dw.DimGeography',N'U') IS NULL
CREATE TABLE dw.DimGeography (
    GeographyKey int IDENTITY(1,1) NOT NULL PRIMARY KEY,
    ZipCodePrefix varchar(5) NOT NULL UNIQUE,
    ApproximateCity nvarchar(128) NULL, ApproximateState varchar(2) NULL,
    Latitude decimal(28,20) NULL, Longitude decimal(28,20) NULL,
    LookupMatched bit NOT NULL, ConflictingCities bit NOT NULL, ConflictingStates bit NOT NULL,
    DistinctCityLabels int NULL, DistinctStateLabels int NULL
);
IF OBJECT_ID(N'dw.DimCustomer',N'U') IS NULL
CREATE TABLE dw.DimCustomer (
    CustomerKey int IDENTITY(1,1) NOT NULL PRIMARY KEY,
    CustomerID varchar(32) NOT NULL UNIQUE,
    CustomerUniqueID varchar(32) NULL,
    SourceZipCodePrefix varchar(5) NULL, SourceCity nvarchar(128) NULL, SourceState varchar(2) NULL,
    GeographyKey int NOT NULL REFERENCES dw.DimGeography(GeographyKey),
    UnmatchedZip bit NOT NULL
);
IF OBJECT_ID(N'dw.DimProduct',N'U') IS NULL
CREATE TABLE dw.DimProduct (
    ProductKey int IDENTITY(1,1) NOT NULL PRIMARY KEY,
    ProductID varchar(32) NOT NULL UNIQUE,
    SourceCategory nvarchar(128) NULL, EnglishCategory nvarchar(128) NULL,
    CategoryLabel nvarchar(160) NOT NULL,
    CategoryMissing bit NOT NULL, CategoryUntranslated bit NOT NULL,
    NameLength int NULL, DescriptionLength int NULL, PhotosQuantity int NULL,
    WeightGrams int NULL, LengthCM int NULL, HeightCM int NULL, WidthCM int NULL
);
IF OBJECT_ID(N'dw.DimSeller',N'U') IS NULL
CREATE TABLE dw.DimSeller (
    SellerKey int IDENTITY(1,1) NOT NULL PRIMARY KEY,
    SellerID varchar(32) NOT NULL UNIQUE,
    SourceZipCodePrefix varchar(5) NULL, SourceCity nvarchar(128) NULL, SourceState varchar(2) NULL,
    GeographyKey int NOT NULL REFERENCES dw.DimGeography(GeographyKey),
    UnmatchedZip bit NOT NULL
);
IF OBJECT_ID(N'dw.DimPaymentType',N'U') IS NULL
CREATE TABLE dw.DimPaymentType (
    PaymentTypeKey int IDENTITY(1,1) NOT NULL PRIMARY KEY,
    PaymentType varchar(32) NOT NULL UNIQUE
);
IF OBJECT_ID(N'dw.DimOrderStatus',N'U') IS NULL
CREATE TABLE dw.DimOrderStatus (
    OrderStatusKey int IDENTITY(1,1) NOT NULL PRIMARY KEY,
    OrderStatus varchar(32) NOT NULL UNIQUE
);
GO
