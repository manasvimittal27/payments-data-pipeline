"""Land the raw extracts in the warehouse exactly as delivered (every column as text).

Loading as text keeps bad values visible: casting happens in dbt staging, where a value
that fails to parse becomes a data quality finding instead of a failed load.
"""
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
DB = ROOT / "warehouse.duckdb"

con = duckdb.connect(str(DB))
con.execute("CREATE SCHEMA IF NOT EXISTS raw")
for f in sorted(RAW.glob("*.csv")):
    con.execute(f"""CREATE OR REPLACE TABLE raw.{f.stem} AS
                    SELECT *, '{f.name}' AS _source_file, now() AS _loaded_at
                    FROM read_csv('{f}', all_varchar = true, header = true)""")
    n = con.execute(f"SELECT COUNT(*) FROM raw.{f.stem}").fetchone()[0]
    print(f"raw.{f.stem:<22} {n:>9,} rows")
con.close()
