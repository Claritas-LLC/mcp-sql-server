-- SQL Server 2019 Simple Test Database Setup
-- Stripped-down version focusing on core tables and data

-- Create test database
IF NOT EXISTS (SELECT * FROM sys.databases WHERE name = 'TEST_DB')
BEGIN
    CREATE DATABASE TEST_DB;
END
GO

USE TEST_DB;
GO

-- Enable Query Store
ALTER DATABASE TEST_DB SET QUERY_STORE = ON;
ALTER DATABASE TEST_DB SET QUERY_STORE (OPERATION_MODE = READ_WRITE, CLEANUP_POLICY = (STALE_QUERY_THRESHOLD_DAYS = 30));
GO

-- Create schemas first
CREATE SCHEMA sales;
GO

CREATE SCHEMA hr;
GO

CREATE SCHEMA inventory;
GO

-- Sales tables
CREATE TABLE sales.Customers (
    CustomerID INT IDENTITY(1,1) PRIMARY KEY,
    FirstName NVARCHAR(50) NOT NULL,
    LastName NVARCHAR(50) NOT NULL,
    Email NVARCHAR(100) UNIQUE,
    City NVARCHAR(50),
    State NVARCHAR(2),
    CreatedDate DATETIME2 DEFAULT GETDATE()
);
GO

CREATE TABLE sales.Products (
    ProductID INT IDENTITY(1,1) PRIMARY KEY,
    ProductName NVARCHAR(100) NOT NULL,
    Category NVARCHAR(50),
    Price DECIMAL(10,2) NOT NULL,
    StockQuantity INT DEFAULT 0,
    CreatedDate DATETIME2 DEFAULT GETDATE()
);
GO

CREATE TABLE sales.Orders (
    OrderID INT IDENTITY(1,1) PRIMARY KEY,
    CustomerID INT NOT NULL,
    OrderDate DATETIME2 DEFAULT GETDATE(),
    TotalAmount DECIMAL(12,2) NOT NULL,
    OrderStatus NVARCHAR(20) DEFAULT 'Pending',
    FOREIGN KEY (CustomerID) REFERENCES sales.Customers(CustomerID)
);
GO

CREATE TABLE sales.OrderDetails (
    OrderDetailID INT IDENTITY(1,1) PRIMARY KEY,
    OrderID INT NOT NULL,
    ProductID INT NOT NULL,
    Quantity INT NOT NULL,
    UnitPrice DECIMAL(10,2) NOT NULL,
    FOREIGN KEY (OrderID) REFERENCES sales.Orders(OrderID),
    FOREIGN KEY (ProductID) REFERENCES sales.Products(ProductID)
);
GO

-- HR tables
CREATE TABLE hr.Employees (
    EmployeeID INT IDENTITY(1,1) PRIMARY KEY,
    FirstName NVARCHAR(50) NOT NULL,
    LastName NVARCHAR(50) NOT NULL,
    Department NVARCHAR(50),
    Position NVARCHAR(100),
    Salary DECIMAL(10,2),
    HireDate DATE,
    ManagerID INT,
    IsActive BIT DEFAULT 1,
    FOREIGN KEY (ManagerID) REFERENCES hr.Employees(EmployeeID)
);
GO

-- Inventory tables
CREATE TABLE inventory.Warehouses (
    WarehouseID INT IDENTITY(1,1) PRIMARY KEY,
    WarehouseName NVARCHAR(100) NOT NULL,
    Location NVARCHAR(200),
    Capacity INT
);
GO

CREATE TABLE inventory.StockMovements (
    MovementID BIGINT IDENTITY(1,1) PRIMARY KEY,
    ProductID INT NOT NULL,
    WarehouseID INT NOT NULL,
    MovementType NVARCHAR(20) NOT NULL,
    Quantity INT NOT NULL,
    MovementDate DATETIME2 DEFAULT GETDATE(),
    FOREIGN KEY (ProductID) REFERENCES sales.Products(ProductID),
    FOREIGN KEY (WarehouseID) REFERENCES inventory.Warehouses(WarehouseID)
);
GO

-- Indexes
CREATE INDEX IX_Customers_Email ON sales.Customers(Email);
CREATE INDEX IX_Orders_CustomerID ON sales.Orders(CustomerID);
CREATE INDEX IX_Orders_OrderDate ON sales.Orders(OrderDate);
CREATE INDEX IX_OrderDetails_OrderID ON sales.OrderDetails(OrderID);
CREATE INDEX IX_OrderDetails_ProductID ON sales.OrderDetails(ProductID);
CREATE INDEX IX_Employees_Department ON hr.Employees(Department);
CREATE INDEX IX_StockMovements_ProductID ON inventory.StockMovements(ProductID);
GO

-- Insert sample data
INSERT INTO sales.Customers VALUES
('John', 'Doe', 'john@test.com', 'New York', 'NY', GETDATE()),
('Jane', 'Smith', 'jane@test.com', 'Los Angeles', 'CA', GETDATE()),
('Bob', 'Johnson', 'bob@test.com', 'Chicago', 'IL', GETDATE()),
('Alice', 'Williams', 'alice@test.com', 'Houston', 'TX', GETDATE()),
('Charlie', 'Brown', 'charlie@test.com', 'Phoenix', 'AZ', GETDATE());
GO

INSERT INTO sales.Products VALUES
('Laptop Pro', 'Electronics', 1299.99, 50, GETDATE()),
('Wireless Mouse', 'Electronics', 29.99, 200, GETDATE()),
('USB-C Hub', 'Electronics', 49.99, 150, GETDATE()),
('Office Chair', 'Furniture', 199.99, 25, GETDATE()),
('Standing Desk', 'Furniture', 399.99, 15, GETDATE());
GO

INSERT INTO inventory.Warehouses VALUES
('Main Warehouse', 'New York', 10000),
('West Coast Hub', 'Los Angeles', 8000),
('Central Distribution', 'Chicago', 12000);
GO

INSERT INTO hr.Employees (FirstName, LastName, Department, Position, Salary, HireDate, IsActive) VALUES
('Michael', 'Scott', 'Management', 'Regional Manager', 75000, '2020-01-15', 1),
('Jim', 'Halpert', 'Sales', 'Sales Representative', 45000, '2020-02-01', 1),
('Pam', 'Beesly', 'Administration', 'Receptionist', 35000, '2020-02-15', 1),
('Dwight', 'Schrute', 'Sales', 'Assistant Manager', 50000, '2020-01-20', 1),
('Angela', 'Martin', 'Accounting', 'Accountant', 48000, '2020-03-01', 1);
GO

-- Insert orders
INSERT INTO sales.Orders (CustomerID, OrderDate, TotalAmount, OrderStatus) VALUES
(1, DATEADD(day, -10, GETDATE()), 1500.00, 'Completed'),
(2, DATEADD(day, -5, GETDATE()), 299.99, 'Completed'),
(3, DATEADD(day, -3, GETDATE()), 2000.00, 'Pending'),
(4, GETDATE(), 500.00, 'Pending'),
(1, DATEADD(day, -15, GETDATE()), 800.00, 'Completed');
GO

-- Insert order details
INSERT INTO sales.OrderDetails (OrderID, ProductID, Quantity, UnitPrice) VALUES
(1, 1, 1, 1299.99),
(2, 2, 1, 29.99),
(3, 4, 2, 199.99),
(4, 5, 1, 399.99),
(5, 3, 3, 49.99);
GO

-- Insert stock movements
INSERT INTO inventory.StockMovements (ProductID, WarehouseID, MovementType, Quantity, MovementDate) VALUES
(1, 1, 'IN', 50, DATEADD(day, -30, GETDATE())),
(2, 1, 'IN', 200, DATEADD(day, -25, GETDATE())),
(3, 2, 'IN', 150, DATEADD(day, -20, GETDATE())),
(4, 3, 'IN', 30, DATEADD(day, -15, GETDATE())),
(5, 3, 'IN', 20, DATEADD(day, -10, GETDATE())),
(1, 1, 'OUT', 2, DATEADD(day, -5, GETDATE()));
GO

-- Create a view
CREATE VIEW sales.CustomerOrderSummary AS
SELECT 
    c.CustomerID,
    c.FirstName + ' ' + c.LastName AS CustomerName,
    COUNT(o.OrderID) AS TotalOrders,
    SUM(o.TotalAmount) AS TotalSpent
FROM sales.Customers c
LEFT JOIN sales.Orders o ON c.CustomerID = o.CustomerID
GROUP BY c.CustomerID, c.FirstName, c.LastName;
GO

-- Create a stored procedure
CREATE PROCEDURE sales.GetCustomerOrders
    @CustomerID INT
AS
BEGIN
    SELECT 
        o.OrderID,
        o.OrderDate,
        o.TotalAmount,
        od.ProductID,
        p.ProductName,
        od.Quantity
    FROM sales.Orders o
    JOIN sales.OrderDetails od ON o.OrderID = od.OrderID
    JOIN sales.Products p ON od.ProductID = p.ProductID
    WHERE o.CustomerID = @CustomerID
    ORDER BY o.OrderDate DESC;
END;
GO

-- Create test users
CREATE LOGIN test_user1 WITH PASSWORD = 'TestPass123!@';
CREATE USER test_user1 FOR LOGIN test_user1;
GRANT SELECT ON SCHEMA::sales TO test_user1;
GO

PRINT 'Test database setup completed successfully!';
