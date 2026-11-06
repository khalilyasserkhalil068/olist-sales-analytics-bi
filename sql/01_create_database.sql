-- Run against master with autocommit. Never drops an existing database.
-- A direct execution must not silently adopt an unrelated existing database.
IF DB_ID(N'OlistSalesDW') IS NOT NULL
    EXEC(N'USE [OlistSalesDW];
        IF OBJECT_ID(N''audit.WarehouseMetadata'',N''U'') IS NULL
            THROW 51000, ''Existing OlistSalesDW is not owned by this project.'', 1;
        IF (SELECT COUNT(*) FROM audit.WarehouseMetadata)<>1
           OR NOT EXISTS(SELECT 1 FROM audit.WarehouseMetadata WHERE ProjectName=N''OlistSalesDW'' AND SchemaVersion=1)
            THROW 51000, ''Unsupported warehouse ownership marker.'', 1;');
IF DB_ID(N'OlistSalesDW') IS NULL
    EXEC(N'CREATE DATABASE [OlistSalesDW] COLLATE Latin1_General_100_BIN2');
GO
USE [OlistSalesDW];
GO
IF SCHEMA_ID(N'stg') IS NULL EXEC(N'CREATE SCHEMA stg AUTHORIZATION dbo');
IF SCHEMA_ID(N'dw') IS NULL EXEC(N'CREATE SCHEMA dw AUTHORIZATION dbo');
IF SCHEMA_ID(N'audit') IS NULL EXEC(N'CREATE SCHEMA audit AUTHORIZATION dbo');
GO
IF OBJECT_ID(N'audit.WarehouseMetadata',N'U') IS NULL
BEGIN
    CREATE TABLE audit.WarehouseMetadata (
        ProjectName nvarchar(128) NOT NULL PRIMARY KEY,
        SchemaVersion int NOT NULL,
        CreatedAtUTC datetime2(3) NOT NULL DEFAULT SYSUTCDATETIME()
    );
    INSERT audit.WarehouseMetadata(ProjectName,SchemaVersion) VALUES(N'OlistSalesDW',1);
END;
IF OBJECT_ID(N'audit.LoadRun',N'U') IS NULL
CREATE TABLE audit.LoadRun (
    LoadID uniqueidentifier NOT NULL PRIMARY KEY,
    StartedAtUTC datetime2(3) NOT NULL DEFAULT SYSUTCDATETIME(),
    FinishedAtUTC datetime2(3) NULL,
    Status varchar(20) NOT NULL CHECK(Status IN ('RUNNING','PASS','FAIL')),
    SourceFingerprint char(64) NOT NULL,
    ErrorMessage nvarchar(4000) NULL
);
IF OBJECT_ID(N'audit.LoadFile',N'U') IS NULL
CREATE TABLE audit.LoadFile (
    LoadID uniqueidentifier NOT NULL REFERENCES audit.LoadRun(LoadID),
    FileName nvarchar(128) NOT NULL,
    SHA256 char(64) NOT NULL,
    SourceRows bigint NOT NULL,
    StagedRows bigint NOT NULL,
    PRIMARY KEY(LoadID,FileName)
);
IF OBJECT_ID(N'audit.ValidationResult',N'U') IS NULL
CREATE TABLE audit.ValidationResult (
    ValidationID bigint IDENTITY PRIMARY KEY,
    LoadID uniqueidentifier NOT NULL REFERENCES audit.LoadRun(LoadID),
    CheckName nvarchar(200) NOT NULL,
    Status varchar(20) NOT NULL CHECK(Status IN ('PASS','FAIL','WARN','NOT EXECUTED')),
    ActualValue nvarchar(200) NULL,
    ExpectedValue nvarchar(200) NULL,
    Details nvarchar(2000) NULL,
    CheckedAtUTC datetime2(3) NOT NULL DEFAULT SYSUTCDATETIME()
);
GO
