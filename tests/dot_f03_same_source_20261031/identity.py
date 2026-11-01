"""Actions-only identities and read-only organization snapshots. Never writes product DBs."""
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
SCOPE = json.loads((HERE / "scope.json").read_text(encoding="utf-8"))
TABLES = {
    "reader_shelves": ("shelf_id", "parent_id", "name", "ordinal", "deleted"),
    "reader_tags": ("tag_id", "name", "deleted"),
    "reader_series": ("series_id", "name", "deleted"),
    "reader_book_shelves": ("shelf_id", "book_key", "ordinal"),
    "reader_book_tags": ("tag_id", "book_key"),
    "reader_book_series": ("series_id", "book_key", "ordinal"),
}
def require(value, message):
    if not value:
        raise AssertionError(message)
def digest(path):
    with Path(path).open("rb") as stream:
        h = hashlib.sha256()
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()
def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
def check_candidate_fields(product_baseline, sdk_freeze, changed, historical_owner_guard_reexecuted=False):
    require(product_baseline == SCOPE["baseline"] and product_baseline != SCOPE["sdk_source"],
            "candidate product baseline mismatch")
    require(sdk_freeze == SCOPE["sdk_source"], "candidate SDK freeze mismatch")
    require(historical_owner_guard_reexecuted is False, "historical owner guard falsely claimed")
    require(SCOPE.get("allowed_path_count") == 23 and len(SCOPE["allowed_paths"]) == 23 and
            len(set(SCOPE["allowed_paths"])) == 23, "authorized twenty-three-path contract malformed")
    require(set(changed).issubset(set(SCOPE["allowed_paths"])), "outside authorized twenty-three paths")
    require(not any(p.startswith(("examples/","apps/","tools/")) for p in changed),
            "production or original owner source changed")

def identity():
    require(os.environ.get("GITHUB_ACTIONS") == "true", "Actions only")
    result = {key: os.environ[env] for key, env in
              (("source_sha", "GITHUB_SHA"), ("run_id", "GITHUB_RUN_ID"), ("attempt", "GITHUB_RUN_ATTEMPT"))}
    require(subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip() ==
            result["source_sha"], "checkout/source mismatch")
    subprocess.run(["git", "merge-base", "--is-ancestor", SCOPE["baseline"], result["source_sha"]],
                   cwd=ROOT, check=True)
    subprocess.run(["git", "diff", "--exit-code", SCOPE["sdk_source"], result["source_sha"],
                    "--", *SCOPE["sdk_paths"]], cwd=ROOT, check=True)
    changed = subprocess.check_output(["git","diff","--name-only",SCOPE["baseline"],
        result["source_sha"]],cwd=ROOT,text=True).splitlines()
    check_candidate_fields(SCOPE["baseline"],SCOPE["sdk_source"],changed)
    result.update(candidate_admission=True, product_baseline=SCOPE["baseline"],
        sdk_freeze=SCOPE["sdk_source"], historical_owner_guard_reexecuted=False,
        historical_owner_evidence_ref=SCOPE["historical_owner_evidence_ref"])
    return result
def same_identity(value, expected):
    for field in SCOPE["identity_fields"]:
        require(value.get(field) == expected[field], "identity mismatch: " + field)
def evidence(path, root):
    path, root = Path(path).resolve(strict=True), Path(root).resolve(strict=True)
    require(path.is_relative_to(root) and path.is_file(), "evidence escapes receipt root")
    return {"path": str(path.relative_to(root)).replace("\\", "/"),
            "bytes": path.stat().st_size, "sha256": digest(path)}
def read_snapshot(database):
    """Open live product database read-only. A transaction pins a consistent WAL-aware view."""
    database = Path(database).resolve(strict=True)
    connection = sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)
    connection.execute("PRAGMA query_only=ON")
    try:
        connection.execute("BEGIN")
        value = {}
        for table, columns in TABLES.items():
            query = "SELECT " + ",".join(columns) + " FROM " + table + " ORDER BY " + ",".join(columns)
            value[table] = [dict(zip(columns, row)) for row in connection.execute(query)]
        rows = connection.execute(
            "SELECT revision_id,entity_kind,entity_key,operation,body_json FROM reader_revisions "
            "WHERE entity_kind IN ('shelf','tag','series','membership') ORDER BY revision_id"
        ).fetchall()
        value["revisions"] = [{"id": row[0], "kind": row[1], "key": row[2], "operation": row[3],
                               "body": json.loads(row[4]),
                               "body_sha256": hashlib.sha256(row[4].encode("utf-8")).hexdigest()}
                              for row in rows]
        connection.rollback()
        return value
    finally:
        connection.close()
def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    require(not path.exists(), "refuse overwrite: " + str(path))
    path.write_bytes(canonical(value) + b"\n")
def snapshot_receipt(host, database, program, output, kind):
    require(host in SCOPE["hosts"], "unknown host")
    value = {**identity(), "host": host, "kind": kind, "sdk_version": SCOPE["sdk_version"],
             "program_sha256": digest(program), "snapshot": read_snapshot(database),
             "complete_product_accepted": False}
    value["snapshot_sha256"] = hashlib.sha256(canonical(value["snapshot"])).hexdigest()
    write_json(output, value)
    return value
