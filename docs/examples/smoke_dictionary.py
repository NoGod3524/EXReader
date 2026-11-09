# SPDX-License-Identifier: MIT
"""Run the documented dictionary example against the existing test fixture builder."""
from pathlib import Path
import subprocess
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tests"))
from check_dictionary import fixture

with tempfile.TemporaryDirectory(prefix="exreader-doc-dictionary-") as directory:
    path, _ = fixture(Path(directory), compressed=False)
    result = subprocess.run([sys.argv[1], str(path), "word01"], check=True,
                            capture_output=True, text=True, encoding="utf-8")
    print(result.stdout, end="")
    if "word01: n. definition 1" not in result.stdout:
        raise SystemExit("dictionary example did not return the fixture definition")
