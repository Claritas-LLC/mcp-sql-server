import json
from decimal import Decimal
from mcp_sqlserver.server import db_sql2019_analyze_table_health

if __name__ == "__main__":
    result = db_sql2019_analyze_table_health(
        instance=1,
        database_name="USGISPRO_800",
        schema="dbo",
        table_name="Account",
        view="standard"
    )

    def default(o):
        if isinstance(o, Decimal):
            return float(o)
        raise TypeError(f"Object of type {type(o).__name__} is not JSON serializable")

    with open("db_sql2019_analyze_table_health_output.json", "w") as f:
        json.dump(result, f, indent=2, default=default)
    print("Output written to db_sql2019_analyze_table_health_output.json")
