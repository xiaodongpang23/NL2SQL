#!/usr/bin/env python3
"""
setup_db.py — idempotent setup of the nl2sql PostgreSQL database.
Run with: python setup_db.py  (conda env nl2sql active)
"""
from pathlib import Path
import pandas as pd
from sqlalchemy import create_engine, text

DB_URL      = "postgresql+psycopg2://xpang@/nl2sql?host=/tmp&port=5432"
PROJECT_DIR = Path(__file__).parent
DDL_FILE    = PROJECT_DIR / "DDL-create-financial-tables.sql"
DATA_DIR    = PROJECT_DIR / "financial-data-set"

# FK-safe load order; transactions last (depends on accounts)
TABLE_ORDER = ["customer", "accounts", "investments", "loans", "orders", "transactions"]


def read_csv(table_name: str) -> pd.DataFrame:
    """Read CSV, promoting the unnamed pandas index column back to 'id'."""
    df = pd.read_csv(DATA_DIR / f"{table_name}.csv", index_col=0)
    df.index.name = "id"
    return df.reset_index()


def main():
    engine = create_engine(DB_URL)
    ddl = DDL_FILE.read_text()

    print("[1/3] Dropping existing tables...")
    with engine.begin() as conn:
        for table in reversed(TABLE_ORDER):
            conn.execute(text(f"DROP TABLE IF EXISTS {table} CASCADE"))
            print(f"  dropped: {table}")

    print("[2/3] Creating tables from DDL...")
    with engine.begin() as conn:
        for stmt in [s.strip() for s in ddl.split(";") if s.strip()]:
            conn.execute(text(stmt))
    print("  tables created.")

    print("[3/3] Loading CSV data...")
    for table in TABLE_ORDER:
        df = read_csv(table)
        df.to_sql(table, con=engine, if_exists="append", index=False, method="multi", chunksize=500)
        print(f"  {table}: {len(df)} rows loaded")

    print("\nRow counts:")
    with engine.connect() as conn:
        for table in TABLE_ORDER:
            n = conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()
            print(f"  {table}: {n}")

    print("\nDone.")


if __name__ == "__main__":
    main()
