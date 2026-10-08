"""Run the whole pipeline: generate raw extracts -> land in warehouse -> dbt build -> report."""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
run = lambda cmd, cwd=ROOT: subprocess.run(cmd, cwd=cwd, check=True)

run([sys.executable, "src/generate_raw.py"])
run([sys.executable, "src/load_raw.py"])
run(["dbt", "build", "--profiles-dir", "."], cwd=ROOT / "dbt")   # models + all data tests
run(["dbt", "docs", "generate", "--profiles-dir", "."], cwd=ROOT / "dbt")
run([sys.executable, "src/report.py"])
