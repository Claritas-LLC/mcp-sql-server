import pytest
import sqlite3

@pytest.fixture(scope="function")
def sqlite_conn():
    conn = sqlite3.connect(":memory:")
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE table1 (id INT PRIMARY KEY, name TEXT)")
    cursor.execute("CREATE TABLE table2 (id INT PRIMARY KEY, table1_id INT, FOREIGN KEY(table1_id) REFERENCES table1(id))")
    conn.commit()
    yield conn
    conn.close()
