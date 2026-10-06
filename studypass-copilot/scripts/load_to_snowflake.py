"""
Alternative loader: pushes data/*.csv into STUDYPASS.CORE tables with write_pandas
and loads policy chunks. Uses your default connection in ~/.snowflake/connections.toml
(the same one CoCo CLI uses), or set SNOWFLAKE_CONNECTION_NAME.

    pip install "snowflake-connector-python[pandas]"
    python scripts/load_to_snowflake.py
"""
import os
import pandas as pd
import snowflake.connector
from snowflake.connector.pandas_tools import write_pandas

ROOT = os.path.join(os.path.dirname(__file__), "..")
conn = snowflake.connector.connect(connection_name=os.getenv("SNOWFLAKE_CONNECTION_NAME", "default"))
cur = conn.cursor()
for stmt in ["USE WAREHOUSE STUDYPASS_WH", "USE SCHEMA STUDYPASS.CORE"]:
    cur.execute(stmt)

for table in ["customers", "students", "remittances", "card_txns", "documents"]:
    df = pd.read_csv(os.path.join(ROOT, "data", f"{table}.csv"))
    for c in df.columns:
        if c in ("ONBOARDED_ON", "INTAKE_DATE", "TXN_DATE", "UPLOADED_ON"):
            df[c] = pd.to_datetime(df[c]).dt.date
        if c == "TXN_TS":
            df[c] = pd.to_datetime(df[c])
    cur.execute(f"TRUNCATE TABLE {table.upper()}")
    ok, _, n, _ = write_pandas(conn, df, table.upper(), use_logical_type=True)
    print(f"{table}: {n} rows loaded ({'ok' if ok else 'FAILED'})")

conn.close()
