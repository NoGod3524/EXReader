# SPDX-License-Identifier: MIT
"""Run every capture in order; each stage resumes from its saved raw JSON."""
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ARMS = sys.argv[1]
STAGES = [["probe", "--rounds", "12"], ["primary", "--rounds", "16"], ["four-arm", "--rounds", "12"],
          ["parity"], ["validate", "--resume", "--rounds", "12"]]
for stage in STAGES:
    print("STAGE", *stage, flush=True)
    subprocess.run([sys.executable, "-B", "-u", str(HERE / "measure.py"), ARMS, *stage], check=True)
print("ALL DONE", flush=True)
