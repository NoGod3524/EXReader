"""Admit a reviewed integration tree without the component branches' stale guards."""
import hashlib
import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
CONTRACT = HERE / "contract.json"

def need(value, message):
    if not value:
        raise ValueError(message)

def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def contract():
    value = json.loads(CONTRACT.read_text())
    need(value["schema"] == 1, "contract schema")
    need(value["linux_budgets"] == {"p95_ms": 16.67, "p99_ms": 33.34,
         "first_interactive_ms": 2000, "peak_rss_bytes": 536870912}, "frozen Linux budgets")
    need(value["linux_frame_groups"] == [
        "ui_all_frames", "ui_reader_frames", "ui_shelf_frames", "ui_body_frames",
        "ui_page_turn_frames", "ui_font_frames", "ui_locate_jump_frames"], "all seven frame groups")
    return value

def admission():
    need(os.environ.get("GITHUB_ACTIONS") == "true", "Actions only")
    need(os.environ.get("GITHUB_REPOSITORY") == "NoGod3524/EXReader", "repository")
    ident = {"source_sha": os.environ["GITHUB_SHA"], "run_id": os.environ["GITHUB_RUN_ID"],
             "attempt": os.environ["GITHUB_RUN_ATTEMPT"]}
    need(all(ident[k].isdigit() and int(ident[k]) > 0 for k in ("run_id", "attempt")), "run/attempt")
    need(git("rev-parse", "HEAD") == ident["source_sha"], "checked-out source")
    need(not git("status", "--porcelain", "--untracked-files=no"), "tracked source changed")
    c = contract()
    base = c["reviewed_source"]
    git("merge-base", "--is-ancestor", base, "HEAD")
    changed = git("diff", "--no-renames", "--name-only", base, "HEAD").splitlines()
    need(all(p.startswith(c["allowed_test_prefix"]) or p == c["allowed_workflow"]
             for p in changed), "unreviewed integration changes: " + repr(changed))
    # The diff guard includes build recipes, fixtures, all production paths and
    # the original test bodies. Only this final adapter and its workflow may differ.
    return {**ident, "reviewed_source": base, "contract_sha256": sha(CONTRACT),
            "changed": changed, "adapter_files": {
                p: sha(ROOT / p) for p in git("ls-files", c["allowed_test_prefix"], c["allowed_workflow"]).splitlines()}}
