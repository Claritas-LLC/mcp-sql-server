-- Add mcp_readonly login and user for MCP tool tests
IF NOT EXISTS (SELECT * FROM sys.sql_logins WHERE name = 'mcp_readonly')
BEGIN
    CREATE LOGIN mcp_readonly WITH PASSWORD = '***REMOVED***';
END;
GO
USE TEST_DB;
GO
IF NOT EXISTS (SELECT * FROM sys.database_principals WHERE name = 'mcp_readonly')
BEGIN
    CREATE USER mcp_readonly FOR LOGIN mcp_readonly;
    ALTER ROLE db_datareader ADD MEMBER mcp_readonly;
END;
GO
-- setup_test_simple.sql
-- Sample data setup for dual SQL Server test containers

-- Create a test database
IF DB_ID('TEST_DB') IS NULL
BEGIN
    CREATE DATABASE TEST_DB;
END;
GO

USE TEST_DB;
GO

-- Create a sample table
IF OBJECT_ID('dbo.sample_table', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.sample_table (
        id INT IDENTITY(1,1) PRIMARY KEY,
        name NVARCHAR(100) NOT NULL,
        value INT NOT NULL,
        created_at DATETIME DEFAULT GETDATE()
    );
END;
GO

-- Insert sample data
INSERT INTO dbo.sample_table (name, value) VALUES
    (N'Alice', 10),
    (N'Bob', 20),
    (N'Charlie', 30),
    (N'Diana', 40),
    (N'Eve', 50);
GO

-- Create a second table for join/query tests
IF OBJECT_ID('dbo.related_table', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.related_table (
        rel_id INT IDENTITY(1,1) PRIMARY KEY,
        sample_id INT NOT NULL,
        description NVARCHAR(200),
        FOREIGN KEY (sample_id) REFERENCES dbo.sample_table(id)
    );
END;
GO

-- Insert related data
INSERT INTO dbo.related_table (sample_id, description) VALUES
    (1, N'Related to Alice'),
    (2, N'Related to Bob'),
    (3, N'Related to Charlie');
GO

-- Add a view for testing
IF OBJECT_ID('dbo.vw_sample_summary', 'V') IS NULL
BEGIN
    EXEC('CREATE VIEW dbo.vw_sample_summary AS SELECT s.id, s.name, s.value, r.description FROM dbo.sample_table s LEFT JOIN dbo.related_table r ON s.id = r.sample_id');
END;
GO

-- Add a stored procedure for testing
IF OBJECT_ID('dbo.usp_get_sample_by_value', 'P') IS NULL
BEGIN
    EXEC('CREATE PROCEDURE dbo.usp_get_sample_by_value @min_value INT AS SELECT * FROM dbo.sample_table WHERE value >= @min_value');
END;
GO

-- Add a user for admin tool tests
IF NOT EXISTS (SELECT * FROM sys.sql_logins WHERE name = 'test_user')
BEGIN
    CREATE LOGIN test_user WITH PASSWORD = 'TestUserPassword123!';
END;
GO
USE TEST_DB;
GO
IF NOT EXISTS (SELECT * FROM sys.database_principals WHERE name = 'test_user')
BEGIN
    CREATE USER test_user FOR LOGIN test_user;
    ALTER ROLE db_datareader ADD MEMBER test_user;
    ALTER ROLE db_datawriter ADD MEMBER test_user;
END;
GO
