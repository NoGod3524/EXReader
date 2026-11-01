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
    require(SCOPE.get("allowed_path_count") == 26 and len(SCOPE["allowed_paths"]) == 26 and
            len(set(SCOPE["allowed_paths"])) == 26, "authorized twenty-six-path contract malformed")
    extra = {}
    import_case = os.environ.get("F03_IMPORT_CONTRACT_CASE", "")
    if import_case:
        require(import_case == "f03/two-host-import-contract" and
                os.environ.get("GITHUB_REF") == "refs/heads/dot/f03-import-contract-20261101",
                "import contract route mismatch")
        extra = {'tools/check_android_host.py': 'b03096584d45c8f415440c0f75699f5a8faf0ff1', 'docs/READER-ANDROID-HOST-IMPORT.md': 'f6d681aec8c7bd968c30f29a73fc78eca8f2c78b', 'tests/reader_android_import_contract_20261101/check.py': '5419fb4dac40f79c4238f1639d81ec37a0f92d0a', '.github/workflows/reader-android-import-contract-20261101.yml': '147de484f60332d50ca8a786b76541226fdaec46'}
        require(SCOPE.get("import_contract_blob_exceptions") == extra,
                "import contract exact reviewed exception map mismatch")
    catalog_case = os.environ.get("F03_CATALOG_CONTRACT_CASE", "")
    if catalog_case:
        require(not import_case and catalog_case == "f03/android-catalog-retained" and
                os.environ.get("GITHUB_REF") == "refs/heads/dot/f03-android-catalog-20261101",
                "catalog contract route mismatch")
        extra = {'tools/check_android_host.py': 'b03096584d45c8f415440c0f75699f5a8faf0ff1', 'docs/READER-ANDROID-HOST-IMPORT.md': 'f6d681aec8c7bd968c30f29a73fc78eca8f2c78b', 'tests/reader_android_import_contract_20261101/check.py': '5419fb4dac40f79c4238f1639d81ec37a0f92d0a', '.github/workflows/reader-android-import-contract-20261101.yml': '147de484f60332d50ca8a786b76541226fdaec46', 'examples/android/app/src/androidTest/java/org/exreader/host/CatalogStoreTest.java': 'dc20e2ec8851b00c761e7332d32f885df946f209'}
        require(SCOPE.get("catalog_contract_blob_exceptions") == extra,
                "catalog contract exact reviewed exception map mismatch")
    mapping_case = os.environ.get("F03_IMPORTMAPPING_CONTRACT_CASE", "")
    if mapping_case:
        require(not import_case and not catalog_case and mapping_case == "f03/android-importmapping-retained" and
                os.environ.get("GITHUB_REF") == "refs/heads/dot/f03-android-importmapping-20261101",
                "import mapping contract route mismatch")
        extra = {'tools/check_android_host.py': 'b03096584d45c8f415440c0f75699f5a8faf0ff1', 'docs/READER-ANDROID-HOST-IMPORT.md': 'f6d681aec8c7bd968c30f29a73fc78eca8f2c78b', 'tests/reader_android_import_contract_20261101/check.py': '5419fb4dac40f79c4238f1639d81ec37a0f92d0a', '.github/workflows/reader-android-import-contract-20261101.yml': '147de484f60332d50ca8a786b76541226fdaec46', 'examples/android/app/src/androidTest/java/org/exreader/host/CatalogStoreTest.java': 'dc20e2ec8851b00c761e7332d32f885df946f209', 'examples/android/app/src/androidTest/java/org/exreader/host/ImportMappingTest.java': '12f758e93e1c74589d0d624415973ba05e6d02fe'}
        require(SCOPE.get("import_mapping_contract_blob_exceptions") == extra,
                "import mapping contract exact reviewed exception map mismatch")
    owner_case = os.environ.get("F03_OWNER_CONTRACT_CASE", "")
    if owner_case:
        require(not import_case and not catalog_case and not mapping_case and
                owner_case == "f03/android-owner-retained" and
                os.environ.get("GITHUB_REF") == "refs/heads/dot/f03-android-owner-20261101",
                "owner contract route mismatch")
        extra = {'tools/check_android_host.py': 'b03096584d45c8f415440c0f75699f5a8faf0ff1', 'docs/READER-ANDROID-HOST-IMPORT.md': 'f6d681aec8c7bd968c30f29a73fc78eca8f2c78b', 'tests/reader_android_import_contract_20261101/check.py': '5419fb4dac40f79c4238f1639d81ec37a0f92d0a', '.github/workflows/reader-android-import-contract-20261101.yml': '147de484f60332d50ca8a786b76541226fdaec46', 'examples/android/app/src/androidTest/java/org/exreader/host/CatalogStoreTest.java': 'dc20e2ec8851b00c761e7332d32f885df946f209', 'examples/android/app/src/androidTest/java/org/exreader/host/ImportMappingTest.java': '12f758e93e1c74589d0d624415973ba05e6d02fe', 'tools/check_reader_owner_android.py': 'b5a03e0657db93b413fdcc98671c92575c4437cb'}
        require(SCOPE.get("owner_contract_blob_exceptions") == extra,
                "owner contract exact reviewed exception map mismatch")
    require(set(changed).issubset(set(SCOPE["allowed_paths"]) | set(extra)),
            "outside authorized twenty-six paths and reviewed import contract exception")
    for path, expected_blob in extra.items():
        actual_blob = subprocess.check_output(["git", "rev-parse", "HEAD:" + path],
                                             cwd=ROOT, text=True).strip()
        require(actual_blob == expected_blob, "reviewed import contract blob mismatch: " + path)
    production = SCOPE["authorized_production_blob_sha"]
    expected_production = {
        "apps/reader/desktop/windows_records_owner.cpp",
        "examples/apple/HostReadingRecords.swift",
        "examples/android/app/src/main/java/org/exreader/host/ReadingParserPolicy.java",
    }
    require(set(production) == expected_production and
            set(SCOPE["authorized_production_paths"]) == expected_production,
            "authorized parser production paths mismatch")
    require(not any(p.startswith(("examples/","apps/","tools/")) and p not in production and p not in extra
                    for p in changed), "production or original owner source changed")
    for path, expected_blob in production.items():
        actual_blob = subprocess.check_output(["git", "rev-parse", "HEAD:" + path],
                                             cwd=ROOT, text=True).strip()
        require(actual_blob == expected_blob, "reviewed parser production blob mismatch: " + path)

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
