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


DIAGNOSTIC_PRODUCT_PATHS = frozenset(
    "examples/android/app/src/main/java/org/exreader/host/" + name
    for name in ("ReaderView.java", "ReaderFrameObserver.java", "ShelfWindowMetrics.java"))

def diagnostic_binding_keys(contract):
    bindings = contract.get("diagnostic_product_bindings")
    if "diagnostic_product_bindings" not in contract:
        bindings = {}
    else:
        need(type(bindings) is dict and set(bindings) == DIAGNOSTIC_PRODUCT_PATHS,
             "exact three diagnostic product bindings")
        for path, digest in bindings.items():
            need(type(digest) is str and len(digest) == 64 and
                 all(c in "0123456789abcdef" for c in digest), "diagnostic hash syntax")
    return bindings

def validate_diagnostic_bindings(contract, changed, actual_hashes):
    bindings = diagnostic_binding_keys(contract)
    need(type(changed) is list and all(type(p) is str for p in changed), "changed path list")
    if bindings:
        need(set(changed) & DIAGNOSTIC_PRODUCT_PATHS == DIAGNOSTIC_PRODUCT_PATHS,
             "all three diagnostic changes declared")
        for path,digest in bindings.items():
            need(actual_hashes.get(path) == digest, "diagnostic product hash: " + path)
    need(type(changed) is list and all(type(p) is str and
         (p.startswith(contract["allowed_test_prefix"]) or p == contract["allowed_workflow"] or p in bindings)
         for p in changed), "unreviewed diagnostic source")
    return bindings

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
    bindings = validate_diagnostic_bindings(c, changed, {
        p: sha(ROOT / p) for p in diagnostic_binding_keys(c)})
    # Only the three explicitly reviewed diagnostic Java contents may additionally differ.
    # Build recipes, SDK and original test bodies remain forbidden; reviewed_source is unchanged.
    return {**ident, "reviewed_source": base, "contract_sha256": sha(CONTRACT),
            "changed": changed, "adapter_files": {
                p: sha(ROOT / p) for p in sorted(set(git("ls-files", c["allowed_test_prefix"], c["allowed_workflow"]).splitlines()) | set(bindings))}}
