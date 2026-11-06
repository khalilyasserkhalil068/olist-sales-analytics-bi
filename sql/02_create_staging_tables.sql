-- All cleaned columns are preserved. SourceRow is a parsed CSV record ordinal.
SET XACT_ABORT ON;
GO

IF OBJECT_ID(N'stg.customers',N'U') IS NULL
CREATE TABLE stg.[customers] (
    [customer_id] varchar(32) NOT NULL,
    [customer_unique_id] varchar(32) NOT NULL,
    [customer_zip_code_prefix] varchar(5) NOT NULL,
    [customer_city] nvarchar(128) NOT NULL,
    [customer_state] varchar(2) NOT NULL,
    [dq_unmatched_zip] bit NOT NULL,
    [dq_invalid_zip_format] bit NOT NULL,
    [LoadID] uniqueidentifier NOT NULL,
    [SourceRow] bigint NOT NULL,
    [LoadedAtUTC] datetime2(3) NOT NULL CONSTRAINT DF_stg_customers_LoadedAt DEFAULT SYSUTCDATETIME(),
    CONSTRAINT [PK_stg_customers] PRIMARY KEY ([customer_id])
);
GO

IF OBJECT_ID(N'stg.orders',N'U') IS NULL
CREATE TABLE stg.[orders] (
    [order_id] varchar(32) NOT NULL,
    [customer_id] varchar(32) NOT NULL,
    [order_status] varchar(32) NOT NULL,
    [order_purchase_timestamp] datetime2(0) NULL,
    [order_approved_at] datetime2(0) NULL,
    [order_delivered_carrier_date] datetime2(0) NULL,
    [order_delivered_customer_date] datetime2(0) NULL,
    [order_estimated_delivery_date] datetime2(0) NULL,
    [dq_invalid_order_purchase_timestamp] bit NOT NULL,
    [dq_invalid_order_approved_at] bit NOT NULL,
    [dq_invalid_order_delivered_carrier_date] bit NOT NULL,
    [dq_invalid_order_delivered_customer_date] bit NOT NULL,
    [dq_invalid_order_estimated_delivery_date] bit NOT NULL,
    [dq_no_items] bit NOT NULL,
    [dq_no_payments] bit NOT NULL,
    [dq_no_reviews] bit NOT NULL,
    [dq_missing_order_approved_at] bit NOT NULL,
    [dq_delivered_missing_order_approved_at] bit NOT NULL,
    [dq_missing_order_delivered_carrier_date] bit NOT NULL,
    [dq_delivered_missing_order_delivered_carrier_date] bit NOT NULL,
    [dq_missing_order_delivered_customer_date] bit NOT NULL,
    [dq_delivered_missing_order_delivered_customer_date] bit NOT NULL,
    [dq_approval_before_purchase] bit NOT NULL,
    [dq_carrier_before_purchase] bit NOT NULL,
    [dq_delivery_before_purchase] bit NOT NULL,
    [dq_carrier_before_approval] bit NOT NULL,
    [dq_delivery_before_carrier] bit NOT NULL,
    [LoadID] uniqueidentifier NOT NULL,
    [SourceRow] bigint NOT NULL,
    [LoadedAtUTC] datetime2(3) NOT NULL CONSTRAINT DF_stg_orders_LoadedAt DEFAULT SYSUTCDATETIME(),
    CONSTRAINT [PK_stg_orders] PRIMARY KEY ([order_id])
);
GO

IF OBJECT_ID(N'stg.order_items',N'U') IS NULL
CREATE TABLE stg.[order_items] (
    [order_id] varchar(32) NOT NULL,
    [order_item_id] varchar(10) NOT NULL,
    [product_id] varchar(32) NOT NULL,
    [seller_id] varchar(32) NOT NULL,
    [shipping_limit_date] datetime2(0) NULL,
    [price] decimal(19,2) NOT NULL,
    [freight_value] decimal(19,2) NOT NULL,
    [dq_invalid_shipping_limit_date] bit NOT NULL,
    [dq_invalid_price] bit NOT NULL,
    [dq_invalid_freight_value] bit NOT NULL,
    [dq_shipping_limit_before_purchase] bit NOT NULL,
    [dq_shipping_limit_after_purchase_year_range] bit NOT NULL,
    [dq_negative_price] bit NOT NULL,
    [dq_zero_price] bit NOT NULL,
    [dq_negative_freight_value] bit NOT NULL,
    [dq_zero_freight_value] bit NOT NULL,
    [LoadID] uniqueidentifier NOT NULL,
    [SourceRow] bigint NOT NULL,
    [LoadedAtUTC] datetime2(3) NOT NULL CONSTRAINT DF_stg_order_items_LoadedAt DEFAULT SYSUTCDATETIME(),
    CONSTRAINT [PK_stg_order_items] PRIMARY KEY ([order_id], [order_item_id])
);
GO

IF OBJECT_ID(N'stg.payments',N'U') IS NULL
CREATE TABLE stg.[payments] (
    [order_id] varchar(32) NOT NULL,
    [payment_sequential] varchar(10) NOT NULL,
    [payment_type] varchar(32) NOT NULL,
    [payment_installments] int NULL,
    [payment_value] decimal(19,2) NOT NULL,
    [dq_invalid_payment_installments] bit NOT NULL,
    [dq_invalid_payment_value] bit NOT NULL,
    [dq_negative_payment_value] bit NOT NULL,
    [dq_zero_payment_value] bit NOT NULL,
    [dq_nonpositive_installments] bit NOT NULL,
    [dq_noninteger_payment_installments] bit NOT NULL,
    [LoadID] uniqueidentifier NOT NULL,
    [SourceRow] bigint NOT NULL,
    [LoadedAtUTC] datetime2(3) NOT NULL CONSTRAINT DF_stg_payments_LoadedAt DEFAULT SYSUTCDATETIME(),
    CONSTRAINT [PK_stg_payments] PRIMARY KEY ([order_id], [payment_sequential])
);
GO

IF OBJECT_ID(N'stg.reviews',N'U') IS NULL
CREATE TABLE stg.[reviews] (
    [review_id] varchar(32) NOT NULL,
    [order_id] varchar(32) NOT NULL,
    [review_score] int NULL,
    [review_comment_title] nvarchar(200) NULL,
    [review_comment_message] nvarchar(2000) NULL,
    [review_creation_date] datetime2(0) NULL,
    [review_answer_timestamp] datetime2(0) NULL,
    [dq_invalid_review_creation_date] bit NOT NULL,
    [dq_invalid_review_answer_timestamp] bit NOT NULL,
    [dq_invalid_review_score] bit NOT NULL,
    [dq_answer_before_creation] bit NOT NULL,
    [dq_noninteger_review_score] bit NOT NULL,
    [dq_score_out_of_range] bit NOT NULL,
    [dq_repeated_review_id] bit NOT NULL,
    [LoadID] uniqueidentifier NOT NULL,
    [SourceRow] bigint NOT NULL,
    [LoadedAtUTC] datetime2(3) NOT NULL CONSTRAINT DF_stg_reviews_LoadedAt DEFAULT SYSUTCDATETIME(),
    CONSTRAINT [PK_stg_reviews] PRIMARY KEY ([review_id], [order_id])
);
GO

IF OBJECT_ID(N'stg.products',N'U') IS NULL
CREATE TABLE stg.[products] (
    [product_id] varchar(32) NOT NULL,
    [product_category_name] nvarchar(128) NOT NULL,
    [product_name_lenght] int NULL,
    [product_description_lenght] int NULL,
    [product_photos_qty] int NULL,
    [product_weight_g] int NULL,
    [product_length_cm] int NULL,
    [product_height_cm] int NULL,
    [product_width_cm] int NULL,
    [dq_invalid_product_name_lenght] bit NOT NULL,
    [dq_invalid_product_description_lenght] bit NOT NULL,
    [dq_invalid_product_photos_qty] bit NOT NULL,
    [dq_invalid_product_weight_g] bit NOT NULL,
    [dq_invalid_product_length_cm] bit NOT NULL,
    [dq_invalid_product_height_cm] bit NOT NULL,
    [dq_invalid_product_width_cm] bit NOT NULL,
    [dq_category_missing] bit NOT NULL,
    [dq_category_untranslated] bit NOT NULL,
    [product_category_name_english] nvarchar(128) NOT NULL,
    [dq_missing_attributes] bit NOT NULL,
    [dq_nonpositive_product_weight_g] bit NOT NULL,
    [dq_nonpositive_product_length_cm] bit NOT NULL,
    [dq_nonpositive_product_height_cm] bit NOT NULL,
    [dq_nonpositive_product_width_cm] bit NOT NULL,
    [LoadID] uniqueidentifier NOT NULL,
    [SourceRow] bigint NOT NULL,
    [LoadedAtUTC] datetime2(3) NOT NULL CONSTRAINT DF_stg_products_LoadedAt DEFAULT SYSUTCDATETIME(),
    CONSTRAINT [PK_stg_products] PRIMARY KEY ([product_id])
);
GO

IF OBJECT_ID(N'stg.sellers',N'U') IS NULL
CREATE TABLE stg.[sellers] (
    [seller_id] varchar(32) NOT NULL,
    [seller_zip_code_prefix] varchar(5) NOT NULL,
    [seller_city] nvarchar(128) NOT NULL,
    [seller_state] varchar(2) NOT NULL,
    [dq_unmatched_zip] bit NOT NULL,
    [dq_invalid_zip_format] bit NOT NULL,
    [LoadID] uniqueidentifier NOT NULL,
    [SourceRow] bigint NOT NULL,
    [LoadedAtUTC] datetime2(3) NOT NULL CONSTRAINT DF_stg_sellers_LoadedAt DEFAULT SYSUTCDATETIME(),
    CONSTRAINT [PK_stg_sellers] PRIMARY KEY ([seller_id])
);
GO

IF OBJECT_ID(N'stg.category_translations',N'U') IS NULL
CREATE TABLE stg.[category_translations] (
    [product_category_name] nvarchar(128) NOT NULL,
    [product_category_name_english] nvarchar(128) NOT NULL,
    [LoadID] uniqueidentifier NOT NULL,
    [SourceRow] bigint NOT NULL,
    [LoadedAtUTC] datetime2(3) NOT NULL CONSTRAINT DF_stg_category_translations_LoadedAt DEFAULT SYSUTCDATETIME(),
    CONSTRAINT [PK_stg_category_translations] PRIMARY KEY ([product_category_name])
);
GO

IF OBJECT_ID(N'stg.geolocation',N'U') IS NULL
CREATE TABLE stg.[geolocation] (
    [geolocation_zip_code_prefix] varchar(5) NOT NULL,
    [geolocation_lat] decimal(28,20) NOT NULL,
    [geolocation_lng] decimal(28,20) NOT NULL,
    [geolocation_city] nvarchar(128) NOT NULL,
    [geolocation_state] varchar(2) NOT NULL,
    [dq_invalid_geolocation_lat] bit NOT NULL,
    [dq_invalid_geolocation_lng] bit NOT NULL,
    [dq_invalid_zip_format] bit NOT NULL,
    [dq_invalid_coordinate] bit NOT NULL,
    [LoadID] uniqueidentifier NOT NULL,
    [SourceRow] bigint NOT NULL,
    [LoadedAtUTC] datetime2(3) NOT NULL CONSTRAINT DF_stg_geolocation_LoadedAt DEFAULT SYSUTCDATETIME(),
    CONSTRAINT [PK_stg_geolocation] PRIMARY KEY ([SourceRow])
);
GO

IF OBJECT_ID(N'stg.geolocation_zip_lookup',N'U') IS NULL
CREATE TABLE stg.[geolocation_zip_lookup] (
    [zip_code_prefix] varchar(5) NOT NULL,
    [geolocation_state] varchar(2) NOT NULL,
    [geolocation_city] nvarchar(128) NOT NULL,
    [geolocation_lat] decimal(28,20) NOT NULL,
    [geolocation_lng] decimal(28,20) NOT NULL,
    [distinct_observations] int NOT NULL,
    [distinct_city_labels] int NOT NULL,
    [distinct_states] int NOT NULL,
    [distinct_coordinate_pairs] int NOT NULL,
    [coordinate_repetitions_excess] int NOT NULL,
    [source_rows] int NOT NULL,
    [dq_conflicting_city_labels] bit NOT NULL,
    [dq_conflicting_states] bit NOT NULL,
    [dq_missing_coordinate] bit NOT NULL,
    [LoadID] uniqueidentifier NOT NULL,
    [SourceRow] bigint NOT NULL,
    [LoadedAtUTC] datetime2(3) NOT NULL CONSTRAINT DF_stg_geolocation_zip_lookup_LoadedAt DEFAULT SYSUTCDATETIME(),
    CONSTRAINT [PK_stg_geolocation_zip_lookup] PRIMARY KEY ([zip_code_prefix])
);
GO
