"""Actions-only fault check for the original-export publication receipt."""
import json
import os
from pathlib import Path
import subprocess

assert os.environ.get("GITHUB_ACTIONS") == "true"
out = Path("build/s15-evidence/publish-io").resolve()
out.mkdir()
env = os.environ.copy()
env["LD_PRELOAD"] = str(Path("build/publish-io.so").resolve())
marker = Path("build/s15-evidence/publish-io-hit").resolve()
assert not marker.exists()
env["ROE_FAULT_MARKER"] = str(marker)
proc = subprocess.run(
    [str(Path("build/s15-consumer/original-export-probe").resolve()),
     "export", str(Path("build/s15-evidence/library.db").resolve()),
     str(out), "normal", "1"],
    capture_output=True, text=True, env=env, timeout=180, check=True,
)
receipt = json.loads(proc.stdout)
assert marker.read_bytes() == b"x", "publication fault did not fire exactly once"
assert receipt["status"] == 6 and len(receipt["items"]) == 1, receipt
item = receipt["items"][0]
assert item["status"] == 6 and not item["committed"] and not item["created"], receipt
assert not item["cleanup_pending"] and not list(out.iterdir()), receipt
Path("build/s15-evidence/publish-io.json").write_text(
    json.dumps({"source": os.environ["GITHUB_SHA"], "run": os.environ["GITHUB_RUN_ID"],
                "attempt": os.environ["GITHUB_RUN_ATTEMPT"], "receipt": receipt},
               indent=2) + "\n", encoding="utf-8")
