"""Authenticate same-run Windows account evidence on Actions."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import zipfile

assert os.environ.get("GITHUB_ACTIONS") == "true"
repo = "repos/NoGod3524/EXReader/"
run_id = 40642072411
artifact_id = 12795934576
source = "42445abd6dfeb312c8803d0a000a32f2a0459a15"
expected = "bf48afd9828d90777b10e7efcc9411038aee7d5f689c445edfabc79cb2c09659"

def api(path):
    return subprocess.check_output(["gh", "api", repo + path])

run = json.loads(api(f"actions/runs/{run_id}"))
assert run["head_sha"] == source and run["run_attempt"] == 1
items = json.loads(api(f"actions/runs/{run_id}/artifacts?per_page=100"))["artifacts"]
item, = [x for x in items if x["id"] == artifact_id]
assert item["workflow_run"]["head_sha"] == source and item["workflow_run"]["id"] == run_id
assert item["name"] == f"windows-sync-account-early-{run_id}-1"
assert item["digest"] == "sha256:" + expected and not item["expired"]
data = api(f"actions/artifacts/{artifact_id}/zip")
assert len(data) == item["size_in_bytes"] and hashlib.sha256(data).hexdigest() == expected
import io
with zipfile.ZipFile(io.BytesIO(data)) as z:
    names = z.namelist()
    report_name, = [n for n in names if n.endswith("sync-account-ui/account-ui.json")]
    report = json.loads(z.read(report_name))
    logfile, = [n for n in names if n.endswith("sync-account.log")]
    assert z.getinfo(logfile).file_size > 0
    assert report["source_sha"] == source and report["run_id"] == str(run_id) and report["attempt"] == "1"
    assert report["accepted"] is True and report["count"] == 32 and len(report["checks"]) == 32
    assert len(set(report["checks"])) == 32
    required = {"planted_concurrent_pending_and_tombstone_heads_stay_explicit_without_projection",
                "conflicted_local_original_still_reads_offline_with_unchanged_heads_and_no_page_jump",
                "no_plaintext_credential_survives_any_product_shutdown"}
    assert required <= set(report["checks"]), required - set(report["checks"])
    result = {"source_sha": source, "run_id": run_id, "attempt": 1, "checks": 32,
              "artifact_id": artifact_id, "artifact_sha256": expected,
              "report_sha256": hashlib.sha256(z.read(report_name)).hexdigest(),
              "program_sha256": report["program_sha256"],
              "diagnostic_source": os.environ["GITHUB_SHA"],
              "diagnostic_run": os.environ["GITHUB_RUN_ID"]}
    out = Path("evidence"); out.mkdir()
    (out/"account-summary.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result), flush=True)
