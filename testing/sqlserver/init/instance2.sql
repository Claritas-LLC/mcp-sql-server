IF DB_ID('CITYGIS_810') IS NULL
BEGIN
    CREATE DATABASE [CITYGIS_810];
END;
GO
USE [CITYGIS_810];
GO
IF OBJECT_ID('dbo.Zoning','U') IS NULL
BEGIN
    CREATE TABLE dbo.Zoning (
        ZoneID INT IDENTITY(1,1) PRIMARY KEY,
        ZoneName NVARCHAR(64) NOT NULL,
        ZoneType NVARCHAR(32) NOT NULL,
        UpdatedUtc DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME()
    );
END;
GO
IF NOT EXISTS (SELECT 1 FROM dbo.Zoning)
BEGIN
    INSERT INTO dbo.Zoning (ZoneName, ZoneType)
    VALUES ('Downtown Core', 'Commercial'), ('Riverside', 'Residential'), ('Industrial West', 'Industrial');
END;
GO
