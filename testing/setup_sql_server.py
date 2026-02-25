import os
import time
import subprocess
import pyodbc
import pandas as pd
import numpy as np

# Configuration
CONTAINER_NAME = "mcp_sqlserver_test"
DB_PASSWORD = "McpTestPassword123!"
DB_PORT = 1433
DB_USER = "sa"
DRIVER = "{ODBC Driver 17 for SQL Server}"

def get_connection_string(database="master"):
    return f"DRIVER={DRIVER};SERVER=127.0.0.1,{DB_PORT};DATABASE={database};UID={DB_USER};PWD={DB_PASSWORD};TrustServerCertificate=yes;"

def run_command(command):
    print(f"Running: {command}")
    subprocess.run(command, shell=True, check=True)

def provision_container():
    print("Provisioning SQL Server container...")
    # Check if container exists
    try:
        subprocess.run(f"docker inspect {CONTAINER_NAME}", shell=True, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print("Container exists. Removing...")
        run_command(f"docker rm -f {CONTAINER_NAME}")
    except subprocess.CalledProcessError:
        pass

    # Run container
    # Windows/PowerShell requires double quotes or no quotes for simple values
    run_command(
        f'docker run -e "ACCEPT_EULA=Y" -e "MSSQL_SA_PASSWORD={DB_PASSWORD}" '
        f"-p {DB_PORT}:1433 --name {CONTAINER_NAME} -d mcr.microsoft.com/mssql/server:2019-latest"
    )
    
    print("Waiting for SQL Server to start...")
    for i in range(60):
        try:
            conn_str = get_connection_string()
            with pyodbc.connect(conn_str, timeout=1):
                pass
            print("SQL Server is ready!")
            return
        except Exception as e:
            time.sleep(2)
            if i % 5 == 0:
                print(f"Waiting... ({e})")
            else:
                print(".", end="", flush=True)
    
    raise Exception("SQL Server failed to start in time.")

def populate_data():
    print("\nPopulating sample data...")
    conn = pyodbc.connect(get_connection_string(), autocommit=True)
    cursor = conn.cursor()
    
    # Create Test Database
    try:
        cursor.execute("DROP DATABASE IF EXISTS testdb")
    except:
        pass
    cursor.execute("CREATE DATABASE testdb")
    conn.close()
    
    # Connect to testdb
    conn = pyodbc.connect(get_connection_string("testdb"), autocommit=True)
    cursor = conn.cursor()
    
    # Create Tables
    print("Creating tables...")
    cursor.execute("""
        CREATE TABLE products (
            id INT IDENTITY(1,1) PRIMARY KEY,
            name NVARCHAR(100),
            price DECIMAL(10, 2),
            stock INT,
            created_at DATETIME DEFAULT GETDATE()
        )
    """)
    
    cursor.execute("""
        CREATE TABLE customers (
            id INT IDENTITY(1,1) PRIMARY KEY,
            name NVARCHAR(100),
            email NVARCHAR(100) UNIQUE,
            signup_date DATE
        )
    """)
    
    cursor.execute("""
        CREATE TABLE orders (
            id INT IDENTITY(1,1) PRIMARY KEY,
            customer_id INT FOREIGN KEY REFERENCES customers(id),
            order_date DATETIME DEFAULT GETDATE(),
            total_amount DECIMAL(10, 2),
            status NVARCHAR(20)
        )
    """)
    
    cursor.execute("""
        CREATE TABLE order_items (
            id INT IDENTITY(1,1) PRIMARY KEY,
            order_id INT FOREIGN KEY REFERENCES orders(id),
            product_id INT FOREIGN KEY REFERENCES products(id),
            quantity INT,
            price_per_unit DECIMAL(10, 2)
        )
    """)

    # Generate Data using Pandas/Numpy
    print("Generating data...")
    products = [
        ("Laptop", 1200.00, 50),
        ("Mouse", 25.50, 200),
        ("Keyboard", 80.00, 150),
        ("Monitor", 300.00, 75),
        ("Headphones", 150.00, 100)
    ]
    cursor.executemany("INSERT INTO products (name, price, stock) VALUES (?, ?, ?)", products)
    
    customers = [
        ("Alice Smith", "alice@example.com", "2023-01-01"),
        ("Bob Jones", "bob@example.com", "2023-02-15"),
        ("Charlie Brown", "charlie@example.com", "2023-03-20")
    ]
    cursor.executemany("INSERT INTO customers (name, email, signup_date) VALUES (?, ?, ?)", customers)
    
    # Create some orders
    cursor.execute("INSERT INTO orders (customer_id, total_amount, status) VALUES (1, 1225.50, 'Completed')")
    order_id = cursor.execute("SELECT SCOPE_IDENTITY()").fetchone()[0]
    cursor.execute("INSERT INTO order_items (order_id, product_id, quantity, price_per_unit) VALUES (?, 1, 1, 1200.00)", order_id)
    cursor.execute("INSERT INTO order_items (order_id, product_id, quantity, price_per_unit) VALUES (?, 2, 1, 25.50)", order_id)

    print("Data population complete.")
    conn.close()

if __name__ == "__main__":
    provision_container()
    populate_data()
