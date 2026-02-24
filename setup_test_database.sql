-- SQL Server 2019 Test Database Setup Script
-- This script creates a comprehensive test database with various scenarios for testing MCP tools

-- Create test database
IF NOT EXISTS (SELECT * FROM sys.databases WHERE name = 'TEST_DB')
BEGIN
    CREATE DATABASE TEST_DB;
END
GO

USE TEST_DB;
GO

-- Enable Query Store for testing db_sql2019_show_top_queries
ALTER DATABASE TEST_DB SET QUERY_STORE = ON;
ALTER DATABASE TEST_DB SET QUERY_STORE (OPERATION_MODE = READ_WRITE, CLEANUP_POLICY = (STALE_QUERY_THRESHOLD_DAYS = 30));
GO

-- Create schemas
CREATE SCHEMA IF NOT EXISTS sales;
CREATE SCHEMA IF NOT EXISTS hr;
CREATE SCHEMA IF NOT EXISTS inventory;
GO

-- Create tables with various characteristics for comprehensive testing

-- 1. Sales tables (OLTP scenario)
CREATE TABLE sales.Customers (
    CustomerID INT IDENTITY(1,1) PRIMARY KEY,
    FirstName NVARCHAR(50) NOT NULL,
    LastName NVARCHAR(50) NOT NULL,
    Email NVARCHAR(100) UNIQUE,
    Phone NVARCHAR(20),
    Address NVARCHAR(200),
    City NVARCHAR(50),
    State NVARCHAR(2),
    ZipCode NVARCHAR(10),
    CreatedDate DATETIME2 DEFAULT GETDATE(),
    ModifiedDate DATETIME2 DEFAULT GETDATE()
);

CREATE TABLE sales.Products (
    ProductID INT IDENTITY(1,1) PRIMARY KEY,
    ProductName NVARCHAR(100) NOT NULL,
    ProductCode NVARCHAR(20) UNIQUE,
    Category NVARCHAR(50),
    Price DECIMAL(10,2) NOT NULL,
    Cost DECIMAL(10,2),
    StockQuantity INT DEFAULT 0,
    ReorderLevel INT DEFAULT 10,
    Discontinued BIT DEFAULT 0,
    CreatedDate DATETIME2 DEFAULT GETDATE()
);

CREATE TABLE sales.Orders (
    OrderID INT IDENTITY(1,1) PRIMARY KEY,
    CustomerID INT NOT NULL,
    OrderDate DATETIME2 DEFAULT GETDATE(),
    ShipDate DATETIME2,
    TotalAmount DECIMAL(12,2) NOT NULL,
    OrderStatus NVARCHAR(20) DEFAULT 'Pending',
    ShippingAddress NVARCHAR(200),
    FOREIGN KEY (CustomerID) REFERENCES sales.Customers(CustomerID)
);

CREATE TABLE sales.OrderDetails (
    OrderDetailID INT IDENTITY(1,1) PRIMARY KEY,
    OrderID INT NOT NULL,
    ProductID INT NOT NULL,
    Quantity INT NOT NULL,
    UnitPrice DECIMAL(10,2) NOT NULL,
    Discount DECIMAL(5,2) DEFAULT 0,
    FOREIGN KEY (OrderID) REFERENCES sales.Orders(OrderID),
    FOREIGN KEY (ProductID) REFERENCES sales.Products(ProductID)
);

-- 2. HR tables (Analytics scenario)
CREATE TABLE hr.Employees (
    EmployeeID INT IDENTITY(1,1) PRIMARY KEY,
    FirstName NVARCHAR(50) NOT NULL,
    LastName NVARCHAR(50) NOT NULL,
    Email NVARCHAR(100) UNIQUE,
    Department NVARCHAR(50),
    Position NVARCHAR(100),
    Salary DECIMAL(10,2),
    HireDate DATE,
    BirthDate DATE,
    ManagerID INT,
    IsActive BIT DEFAULT 1,
    CreatedDate DATETIME2 DEFAULT GETDATE(),
    FOREIGN KEY (ManagerID) REFERENCES hr.Employees(EmployeeID)
);

CREATE TABLE hr.Departments (
    DepartmentID INT IDENTITY(1,1) PRIMARY KEY,
    DepartmentName NVARCHAR(50) NOT NULL,
    Budget DECIMAL(15,2),
    ManagerID INT,
    Location NVARCHAR(100),
    FOREIGN KEY (ManagerID) REFERENCES hr.Employees(EmployeeID)
);

-- 3. Inventory tables (Mixed workload)
CREATE TABLE inventory.Warehouses (
    WarehouseID INT IDENTITY(1,1) PRIMARY KEY,
    WarehouseName NVARCHAR(100) NOT NULL,
    Location NVARCHAR(200),
    Capacity INT,
    ManagerID INT,
    CreatedDate DATETIME2 DEFAULT GETDATE()
);

CREATE TABLE inventory.StockMovements (
    MovementID BIGINT IDENTITY(1,1) PRIMARY KEY,
    ProductID INT NOT NULL,
    WarehouseID INT NOT NULL,
    MovementType NVARCHAR(20) NOT NULL, -- 'IN', 'OUT', 'TRANSFER'
    Quantity INT NOT NULL,
    MovementDate DATETIME2 DEFAULT GETDATE(),
    ReferenceID NVARCHAR(50),
    Notes NVARCHAR(500),
    FOREIGN KEY (ProductID) REFERENCES sales.Products(ProductID),
    FOREIGN KEY (WarehouseID) REFERENCES inventory.Warehouses(WarehouseID)
);

-- Create indexes (some with fragmentation for testing db_sql2019_check_fragmentation)
CREATE INDEX IX_Customers_Email ON sales.Customers(Email);
CREATE INDEX IX_Customers_City_State ON sales.Customers(City, State);
CREATE INDEX IX_Products_Category ON sales.Products(Category);
CREATE INDEX IX_Products_Price ON sales.Products(Price);
CREATE INDEX IX_Orders_CustomerID ON sales.Orders(CustomerID);
CREATE INDEX IX_Orders_OrderDate ON sales.Orders(OrderDate);
CREATE INDEX IX_OrderDetails_OrderID ON sales.OrderDetails(OrderID);
CREATE INDEX IX_OrderDetails_ProductID ON sales.OrderDetails(ProductID);
CREATE INDEX IX_Employees_Department ON hr.Employees(Department);
CREATE INDEX IX_Employees_HireDate ON hr.Employees(HireDate);
CREATE INDEX IX_StockMovements_ProductID ON inventory.StockMovements(ProductID);
CREATE INDEX IX_StockMovements_MovementDate ON inventory.StockMovements(MovementDate);

-- Create some composite indexes
CREATE INDEX IX_Orders_CustomerDate ON sales.Orders(CustomerID, OrderDate);
CREATE INDEX IX_StockMovements_ProductWarehouse ON inventory.StockMovements(ProductID, WarehouseID);

-- Insert sample data

-- Customers
INSERT INTO sales.Customers (FirstName, LastName, Email, Phone, Address, City, State, ZipCode) VALUES
('John', 'Doe', 'john.doe@email.com', '555-0101', '123 Main St', 'New York', 'NY', '10001'),
('Jane', 'Smith', 'jane.smith@email.com', '555-0102', '456 Oak Ave', 'Los Angeles', 'CA', '90001'),
('Bob', 'Johnson', 'bob.johnson@email.com', '555-0103', '789 Pine Rd', 'Chicago', 'IL', '60601'),
('Alice', 'Williams', 'alice.williams@email.com', '555-0104', '321 Elm St', 'Houston', 'TX', '77001'),
('Charlie', 'Brown', 'charlie.brown@email.com', '555-0105', '654 Maple Dr', 'Phoenix', 'AZ', '85001'),
('Diana', 'Davis', 'diana.davis@email.com', '555-0106', '987 Cedar Ln', 'Philadelphia', 'PA', '19101'),
('Edward', 'Miller', 'edward.miller@email.com', '555-0107', '147 Birch Ct', 'San Antonio', 'TX', '78201'),
('Fiona', 'Wilson', 'fiona.wilson@email.com', '555-0108', '258 Spruce Way', 'San Diego', 'CA', '92101'),
('George', 'Moore', 'george.moore@email.com', '555-0109', '369 Willow Ave', 'Dallas', 'TX', '75201'),
('Helen', 'Taylor', 'helen.taylor@email.com', '555-0110', '741 Aspen Blvd', 'San Jose', 'CA', '95101');

-- Products
INSERT INTO sales.Products (ProductName, ProductCode, Category, Price, Cost, StockQuantity, ReorderLevel) VALUES
('Laptop Pro', 'LAP-001', 'Electronics', 1299.99, 800.00, 50, 10),
('Wireless Mouse', 'MOU-001', 'Electronics', 29.99, 15.00, 200, 30),
('USB-C Hub', 'HUB-001', 'Electronics', 49.99, 25.00, 150, 20),
('Office Chair', 'CHA-001', 'Furniture', 199.99, 120.00, 25, 5),
('Standing Desk', 'DES-001', 'Furniture', 399.99, 250.00, 15, 3),
('Monitor 27"', 'MON-001', 'Electronics', 299.99, 180.00, 40, 8),
('Keyboard Mechanical', 'KEY-001', 'Electronics', 89.99, 45.00, 75, 15),
('Desk Lamp', 'LAM-001', 'Furniture', 39.99, 20.00, 60, 12),
('Filing Cabinet', 'CAB-001', 'Furniture', 149.99, 90.00, 20, 4),
('Webcam HD', 'CAM-001', 'Electronics', 79.99, 40.00, 100, 18);

-- Warehouses
INSERT INTO inventory.Warehouses (WarehouseName, Location, Capacity, ManagerID) VALUES
('Main Warehouse', 'New York', 10000, 1),
('West Coast Hub', 'Los Angeles', 8000, 2),
('Central Distribution', 'Chicago', 12000, 3);

-- Employees
INSERT INTO hr.Employees (FirstName, LastName, Email, Department, Position, Salary, HireDate, BirthDate, ManagerID) VALUES
('Michael', 'Scott', 'michael.scott@company.com', 'Management', 'Regional Manager', 75000, '2020-01-15', '1980-03-15', NULL),
('Jim', 'Halpert', 'jim.halpert@company.com', 'Sales', 'Sales Representative', 45000, '2020-02-01', '1985-07-20', 1),
('Pam', 'Beesly', 'pam.beesly@company.com', 'Administration', 'Receptionist', 35000, '2020-02-15', '1987-11-25', 1),
('Dwight', 'Schrute', 'dwight.schrute@company.com', 'Sales', 'Assistant Regional Manager', 50000, '2020-01-20', '1983-01-24', 1),
('Angela', 'Martin', 'angela.martin@company.com', 'Accounting', 'Accountant', 48000, '2020-03-01', '1982-06-11', 1),
('Kevin', 'Malone', 'kevin.malone@company.com', 'Accounting', 'Accountant', 46000, '2020-03-15', '1981-06-01', 5),
('Oscar', 'Martinez', 'oscar.martinez@company.com', 'Accounting', 'Accountant', 47000, '2020-03-10', '1980-04-12', 5),
('Stanley', 'Hudson', 'stanley.hudson@company.com', 'Sales', 'Sales Representative', 44000, '2020-01-25', '1975-02-19', 1),
('Phyllis', 'Vance', 'phyllis.vance@company.com', 'Sales', 'Sales Representative', 43000, '2020-02-10', '1978-07-10', 1),
('Andy', 'Bernard', 'andy.bernard@company.com', 'Sales', 'Sales Representative', 42000, '2020-04-01', '1984-02-23', 1);

-- Create some orders and order details to generate data for analysis
DECLARE @i INT = 1;
DECLARE @orderID INT;
DECLARE @customerID INT;
DECLARE @productID INT;
DECLARE @quantity INT;

WHILE @i <= 50
BEGIN
    -- Random customer (1-10)
    SET @customerID = ABS(CHECKSUM(NEWID())) % 10 + 1;
    
    -- Insert order
    INSERT INTO sales.Orders (CustomerID, OrderDate, ShipDate, TotalAmount, OrderStatus, ShippingAddress)
    VALUES (@customerID, DATEADD(day, -ABS(CHECKSUM(NEWID())) % 365, GETDATE()), 
            DATEADD(day, 2, DATEADD(day, -ABS(CHECKSUM(NEWID())) % 365, GETDATE())),
            0, 'Completed', 'Customer Address ' + CAST(@customerID AS NVARCHAR));
    
    SET @orderID = SCOPE_IDENTITY();
    
    -- Add 1-5 products to order
    DECLARE @j INT = 1;
    DECLARE @orderTotal DECIMAL(12,2) = 0;
    
    WHILE @j <= ABS(CHECKSUM(NEWID())) % 5 + 1
    BEGIN
        SET @productID = ABS(CHECKSUM(NEWID())) % 10 + 1;
        SET @quantity = ABS(CHECKSUM(NEWID())) % 5 + 1;
        
        DECLARE @unitPrice DECIMAL(10,2);
        SELECT @unitPrice = Price FROM sales.Products WHERE ProductID = @productID;
        
        INSERT INTO sales.OrderDetails (OrderID, ProductID, Quantity, UnitPrice, Discount)
        VALUES (@orderID, @productID, @quantity, @unitPrice, 0);
        
        SET @orderTotal = @orderTotal + (@unitPrice * @quantity);
        SET @j = @j + 1;
    END
    
    -- Update order total
    UPDATE sales.Orders SET TotalAmount = @orderTotal WHERE OrderID = @orderID;
    
    SET @i = @i + 1;
END

-- Create some stock movements
INSERT INTO inventory.StockMovements (ProductID, WarehouseID, MovementType, Quantity, ReferenceID, Notes)
SELECT 
    ProductID,
    ABS(CHECKSUM(NEWID())) % 3 + 1,
    CASE WHEN ABS(CHECKSUM(NEWID())) % 2 = 0 THEN 'IN' ELSE 'OUT' END,
    ABS(CHECKSUM(NEWID())) % 100 + 1,
    'REF-' + CAST(ABS(CHECKSUM(NEWID())) % 1000 AS NVARCHAR),
    'Stock movement for ' + ProductName
FROM sales.Products
CROSS APPLY (SELECT TOP 3 * FROM inventory.Warehouses) w
WHERE ABS(CHECKSUM(NEWID())) % 3 = 0;

-- Create some fragmented indexes by doing heavy updates/inserts
UPDATE sales.Customers SET City = UPPER(City) WHERE CustomerID % 3 = 0;
UPDATE sales.Products SET Price = Price * 1.1 WHERE ProductID % 4 = 0;
DELETE FROM sales.OrderDetails WHERE OrderDetailID % 7 = 0;

-- Insert more data to create fragmentation
INSERT INTO sales.Customers (FirstName, LastName, Email, Phone, Address, City, State, ZipCode)
SELECT 
    'Test' + CAST(ROW_NUMBER() OVER(ORDER BY (SELECT NULL)) AS NVARCHAR),
    'Customer' + CAST(ROW_NUMBER() OVER(ORDER BY (SELECT NULL)) AS NVARCHAR),
    'test' + CAST(ROW_NUMBER() OVER(ORDER BY (SELECT NULL)) AS NVARCHAR) + '@email.com',
    '555-' + RIGHT('0000' + CAST(ROW_NUMBER() OVER(ORDER BY (SELECT NULL)) AS NVARCHAR), 4),
    'Test Address ' + CAST(ROW_NUMBER() OVER(ORDER BY (SELECT NULL)) AS NVARCHAR),
    'TestCity',
    'TS',
    '00000'
FROM sys.objects CROSS JOIN sys.objects s2
WHERE ROW_NUMBER() OVER(ORDER BY (SELECT NULL)) <= 100;

-- Create a table without primary key for testing
CREATE TABLE sales.TempOrders (
    OrderData NVARCHAR(MAX),
    CreatedDate DATETIME2 DEFAULT GETDATE()
);

-- Insert some data into temp table
INSERT INTO sales.TempOrders (OrderData)
SELECT 'Order data ' + CAST(ABS(CHECKSUM(NEWID())) AS NVARCHAR)
FROM sys.objects;

-- Create a view for testing
CREATE VIEW sales.CustomerOrderSummary AS
SELECT 
    c.CustomerID,
    c.FirstName + ' ' + c.LastName AS CustomerName,
    COUNT(o.OrderID) AS TotalOrders,
    SUM(o.TotalAmount) AS TotalSpent,
    MAX(o.OrderDate) AS LastOrderDate
FROM sales.Customers c
LEFT JOIN sales.Orders o ON c.CustomerID = o.CustomerID
GROUP BY c.CustomerID, c.FirstName, c.LastName;
GO

-- Create a stored procedure for testing
CREATE PROCEDURE sales.GetCustomerOrders
    @CustomerID INT
AS
BEGIN
    SELECT 
        o.OrderID,
        o.OrderDate,
        o.TotalAmount,
        o.OrderStatus,
        od.ProductID,
        p.ProductName,
        od.Quantity,
        od.UnitPrice
    FROM sales.Orders o
    JOIN sales.OrderDetails od ON o.OrderID = od.OrderID
    JOIN sales.Products p ON od.ProductID = p.ProductID
    WHERE o.CustomerID = @CustomerID
    ORDER BY o.OrderDate DESC;
END;
GO

-- Enable some security features for testing db_sql2019_db_sec_perf_metrics
-- Enable TDE (if Enterprise edition)
IF EXISTS (SELECT 1 FROM sys.dm_db_persisted_sku_features WHERE feature_name = 'TransparentDatabaseEncryption')
BEGIN
    CREATE DATABASE ENCRYPTION KEY
    WITH ALGORITHM = AES_256
    ENCRYPTION BY SERVER CERTIFICATE TDECert;
    
    ALTER DATABASE TEST_DB SET ENCRYPTION ON;
END
GO

-- Create some users for testing user management tools
CREATE LOGIN test_user1 WITH PASSWORD = 'TestPass123!';
CREATE LOGIN test_user2 WITH PASSWORD = 'TestPass456!';
CREATE USER test_user1 FOR LOGIN test_user1;
CREATE USER test_user2 FOR LOGIN test_user2;
GRANT SELECT ON SCHEMA::sales TO test_user1;
GRANT SELECT, INSERT ON SCHEMA::hr TO test_user2;
GO

-- Create some statistics for testing
UPDATE STATISTICS sales.Customers WITH FULLSCAN;
UPDATE STATISTICS sales.Products WITH FULLSCAN;
UPDATE STATISTICS sales.Orders WITH FULLSCAN;
GO

-- Force some index fragmentation
-- This will help test the fragmentation tool
UPDATE sales.Customers SET City = 'FRAGMENTED_' + City WHERE CustomerID % 5 = 0;
UPDATE sales.Products SET ProductName = 'FRAGMENTED_' + ProductName WHERE ProductID % 3 = 0;
DELETE FROM sales.Customers WHERE CustomerID > 50 AND CustomerID % 7 = 0;
GO

-- Insert more data to create additional fragmentation
INSERT INTO sales.Customers (FirstName, LastName, Email, Phone, Address, City, State, ZipCode)
SELECT 
    'Frag' + CAST(ROW_NUMBER() OVER(ORDER BY (SELECT NULL)) AS NVARCHAR),
    'Test' + CAST(ROW_NUMBER() OVER(ORDER BY (SELECT NULL)) AS NVARCHAR),
    'frag' + CAST(ROW_NUMBER() OVER(ORDER BY (SELECT NULL)) AS NVARCHAR) + '@test.com',
    '555-' + RIGHT('0000' + CAST(ROW_NUMBER() OVER(ORDER BY (SELECT NULL)) AS NVARCHAR), 4),
    'Frag Address ' + CAST(ROW_NUMBER() OVER(ORDER BY (SELECT NULL)) AS NVARCHAR),
    'FragCity',
    'FG',
    '11111'
FROM sys.objects CROSS JOIN sys.objects
WHERE ROW_NUMBER() OVER(ORDER BY (SELECT NULL)) <= 50;
GO

PRINT 'Test database setup completed successfully!';