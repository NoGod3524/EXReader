#!/usr/bin/env python3
"""F03 SDK 3.42 production admission and explicit original-driver adapter. Actions only."""
import hashlib
import json
import os
from pathlib import Path
import re
import importlib.util
import shlex
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
BASE = "94fb236a4a2da87dfbaf4f1dd2a47885d615a230"
CANONICAL = "ec11cf862ca3b44483d7e8c4726ae748ab438337"
INTAKE = "48bd5a35d99c3a21a8159288dd08ac8dbb41c677"
REVIEWED_ACCEPTANCE = "61dc8d6190e65dc12886d2d0f0e97b501c52be56"
PREVIOUS_CORRECTION = "b4d97d6d62c1366972d321174b728980e287b2cd"
TEST_CLOSURE_BASE = "9d493b2235d81c216767295948f417c1bd12bf2d"
OWNER_CONSUMER_BASE = "d9b36c36349a320e64f0bdf00d612c134c4eeeea"
IMPORT_STATUS_BASE = "0b5c77592a264f5cdb6f12f03dbe7b78bb698b7d"
SDK = "8357eafa28423a7ab93ba08b823af80f01ad1505"
FIXTURE_SOURCE = "39600d0d3a3a5e4bc2599a92e94e494a542f06f1"
BRANCH = "dot/f03-production-acceptance-v342-20261102"
MARKER = "[F03-PRODUCTION-ACCEPTANCE-V342-20261102]"

def require(value, message):
    if not value:
        raise ValueError(message)

def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()

def blob(source, path):
    return subprocess.check_output(["git", "show", source + ":" + path], cwd=ROOT)

def digest(data):
    return hashlib.sha256(data).hexdigest()

def configuration():
    c = json.loads((HERE / "contract.json").read_text())
    require((c["review_base"], c["canonical_source"], c["product_intake_head"], c["sdk_source"],
             c["sdk_version"], c["fixture_source"], c["branch"]) ==
            (BASE, CANONICAL, INTAKE, SDK, "3.42.0", FIXTURE_SOURCE, BRANCH), "fixed admission identity")
    require(c.get("commit_marker") == MARKER, "fixed authorized commit marker")
    require(c["reviewed_acceptance_base"] == REVIEWED_ACCEPTANCE, "fixed R1 acceptance parent")
    require(c["previous_correction_base"] == PREVIOUS_CORRECTION, "fixed preserved R2 parent")
    require(c["test_closure_base"] == TEST_CLOSURE_BASE, "fixed preserved R3 parent")
    require(c["owner_consumer_base"] == OWNER_CONSUMER_BASE, "fixed preserved R4 parent")
    require(c["import_status_base"] == IMPORT_STATUS_BASE, "fixed preserved R5 parent")
    return c

def host_import_status_contract():
    """Only the reviewed status literal changes; all twenty cases retain their bytes."""
    expected = json.loads(r'''{
  "version": "host-import-reading-limit-status-v1",
  "source": "tests/reader_android_host_import/java/org/exreader/host/HostImportUiTest.java",
  "source_blob": "c0a48388a7b5b2c6e21ff029c8bffc33041e7c93",
  "overlay": "tests/dot_f03_production_acceptance_20261102/androidTest/org/exreader/host/HostImportUiTest.java",
  "staged_path": "org/exreader/host/HostImportUiTest.java",
  "old_literal": "status(\"Current reader has a 32 MiB reading limit\");",
  "new_literal": "status(\"Selected book exceeds 32 MiB reading limit. The 128 MiB staging ceiling does not make larger books readable\");",
  "reading_limit_bytes": 33554432,
  "staging_limit_bytes": 134217728,
  "cases": 20,
  "phases": 9,
  "runtime_accepted": false
}''')
    c = configuration()
    require(c["host_import_status_contract"] == expected, "fixed single-literal status contract")
    source = expected["source"]
    require(c["test_dependency_sources"][expected["staged_path"]] == source and
            c["test_dependency_blobs"][source] == expected["source_blob"],
            "original UI runner provenance remains pinned")
    require(git("rev-parse", IMPORT_STATUS_BASE + ":" + source) == expected["source_blob"],
            "fixed original UI runner blob")
    original = blob(IMPORT_STATUS_BASE, source)
    require((ROOT / source).read_bytes() == original, "original UI test must remain unchanged")
    before, after = expected["old_literal"].encode(), expected["new_literal"].encode()
    require(original.count(before) == 1 and original.count(after) == 0, "unique original status assertion")
    reviewed = (ROOT / expected["overlay"]).read_bytes()
    require(reviewed == original.replace(before, after, 1),
            "only the approved status literal may change; all safety assertions retained")
    require(reviewed == blob("HEAD", expected["overlay"]), "dirty status overlay")
    return {"policy": expected, "source_sha256": digest(original),
            "overlay_sha256": digest(reviewed), "runtime_accepted": False}

def catalog_schema_contract():
    c = configuration()
    expected = {
    "asset_schema_version": 1,
    "runtime_schema_version": 3,
    "runtime_tables": [
        "reader_book_series",
        "reader_book_shelves",
        "reader_book_tags",
        "reader_books",
        "reader_local_books",
        "reader_original_pending",
        "reader_originals",
        "reader_outbox",
        "reader_revisions",
        "reader_series",
        "reader_shelves",
        "reader_tags"
    ],
    "catalog_cases": 8,
    "mapping_cases": 14,
    "mapping_phases": [
        "seed-before",
        "recover-before",
        "seed-during",
        "recover-during"
    ],
    "interrupted_migration_scope": "001_catalog.sql: SQLITE_CREATE_TABLE reader_book_shelves only",
    "all_migration_interruptions_accepted": False,
    "old_apk_upgrade_accepted": False
}
    require(c["catalog_schema_policy"] == expected, "asset v1 and runtime v3 are separate fixed contracts")
    expected_blobs = {
        "tests/dot_f03_production_acceptance_20261102/androidTest/org/exreader/host/CatalogStoreTest.java": "dc20e2ec8851b00c761e7332d32f885df946f209",
        "tests/dot_f03_production_acceptance_20261102/androidTest/org/exreader/host/ImportMappingTest.java": "12f758e93e1c74589d0d624415973ba05e6d02fe"}
    require(c["catalog_overlay_blobs"] == expected_blobs, "exact previously exercised catalog/mapping sources")
    sources = {}
    for relative, expected_blob in expected_blobs.items():
        original = c["overlay_sources"][relative]
        require(git("rev-parse", FIXTURE_SOURCE + ":" + original) == expected_blob and
                (ROOT / relative).read_bytes() == blob(FIXTURE_SOURCE, original),
                "catalog/mapping overlay is not byte-identical to reviewed source")
        sources[relative] = {"source": FIXTURE_SOURCE, "path": original, "blob": expected_blob,
                             "sha256": digest((ROOT / relative).read_bytes())}
    protected = {
        "apps/reader/store/001_catalog.sql", "apps/reader/store/002_originals.sql",
        "apps/reader/store/003_original_staging.sql", "apps/reader/store/native/catalog.c",
        "examples/android/app/src/main/java/org/exreader/host/CatalogStore.java",
        "examples/android/app/src/main/java/org/exreader/host/BookStore.java",
        "examples/android/app/src/debug/cpp/catalog_fixture.inc"}
    require(set(c["catalog_runtime_blobs"]) == protected, "complete runtime catalog and fault-injection provenance")
    for path, expected_blob in c["catalog_runtime_blobs"].items():
        require(git("rev-parse", INTAKE + ":" + path) == expected_blob and
                (ROOT / path).read_bytes() == blob(INTAKE, path), "unchanged product migration/fault source")
    return {"policy": expected, "overlay_sources": sources,
            "runtime_source_blobs": c["catalog_runtime_blobs"], "runtime_accepted": False}



def owner_consumer_contract():
    """Exact source transformations and complete seven-plus-two call routing."""
    c = configuration()
    expected = json.loads(r'''{
  "version": "native-owner18-organization-v1",
  "paths": {
    "owner": "tests/dot_f03_production_acceptance_20261102/check_reader_owner_android_v342.py",
    "ownerGate": "tests/dot_f03_production_acceptance_20261102/check_owner_evidence_gate_v342.py",
    "org": "tests/dot_f03_production_acceptance_20261102/check_reader_organization_android_v342.py",
    "orgGate": "tests/dot_f03_production_acceptance_20261102/check_organization_evidence_gate_v342.py"
  },
  "owner_reference_source": "39600d0d3a3a5e4bc2599a92e94e494a542f06f1",
  "owner_reference_blob": "b5a03e0657db93b413fdcc98671c92575c4437cb",
  "product_owner_runner_blob": "fa504a46e3a545428037290efb4a2758a72d0e07",
  "owner_cases": 18,
  "typed_kill_cases": 2,
  "organization_native_cases": 8,
  "organization_ui_cases": 8,
  "organization_process_retry_cases": 1,
  "original_functional_checks": 112,
  "original_gate_checks": 87,
  "owner_gate_checks": 19,
  "organization_gate_checks": 15,
  "direct_call_counts": {
    "owner": 3,
    "organization": 2,
    "owner_gate": 1,
    "organization_gate": 1
  },
  "gate_subprocess_calls": 2,
  "old_tools_modified": false,
  "old_tests_modified": false
}''')
    require(c["owner_consumer_contract"] == expected, "fixed complete owner18 consumer contract")
    paths = expected["paths"]
    def replace_once(raw, before, after):
        require(raw.count(before) == 1, "unique versioned source transformation")
        return raw.replace(before, after, 1)
    original_owner_path = "tools/check_reader_owner_android.py"
    original_org_path = "tools/check_reader_organization_android.py"
    owner_gate_path = "tests/android_host/check_owner_evidence_gate.py"
    org_gate_path = "tests/android_host/check_organization_evidence_gate.py"
    old_owner = blob(OWNER_CONSUMER_BASE, original_owner_path)
    reviewed_owner = replace_once(old_owner,
        b"'sdkDatabaseRefusedWithoutModification','opensClosedLegacySystemCatalog'}",
        b"'sdkDatabaseRefusedWithoutModification','opensClosedLegacySystemCatalog','finalizeImportAutomaticallyBootstrapsOnce'}")
    reviewed_owner = replace_once(reviewed_owner, b"'OK (17 tests)'", b"'OK (18 tests)'")
    require(git("rev-parse", FIXTURE_SOURCE + ":" + original_owner_path) == expected["owner_reference_blob"] and
            reviewed_owner == blob(FIXTURE_SOURCE, original_owner_path),
            "exact previously reviewed owner18 implementation, not changed assertions")
    new_owner = replace_once(reviewed_owner, b"import subprocess\n", b"import subprocess\nimport sys\n")
    new_owner = replace_once(new_owner, b"import zipfile\n",
        b'import zipfile\n\n# Only resolve the unchanged native_record helper from its original tools directory.\n'
        b'sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))\n')
    new_org = replace_once(blob(OWNER_CONSUMER_BASE, original_org_path),
                           b"owner['owner_checks']==17", b"owner['owner_checks']==18")
    new_org = replace_once(new_org, b"original_owner_checks=17", b"original_owner_checks=18")
    expected_files = {
        paths["owner"]: new_owner,
        paths["org"]: new_org,
        paths["ownerGate"]: replace_once(blob(OWNER_CONSUMER_BASE, owner_gate_path),
            b"'tools/check_reader_owner_android.py'", ("'" + paths["owner"] + "'").encode()),
        paths["orgGate"]: replace_once(blob(OWNER_CONSUMER_BASE, org_gate_path),
            b"'tools/check_reader_organization_android.py'", ("'" + paths["org"] + "'").encode())}
    for path, raw in expected_files.items():
        require((ROOT / path).read_bytes() == raw, "exact versioned runtime/gate body: " + path)
    runner = "examples/android/app/src/androidTest/java/org/exreader/host/ProductOwnerTest.java"
    require(git("rev-parse", OWNER_CONSUMER_BASE + ":" + runner) == expected["product_owner_runner_blob"] and
            (ROOT / runner).read_bytes() == blob(OWNER_CONSUMER_BASE, runner),
            "unchanged actual eighteen-case owner runner")
    protected = [original_owner_path, original_org_path, owner_gate_path, org_gate_path,
                 "tools/android_host_evidence.py", runner]
    for path in protected:
        require((ROOT / path).read_bytes() == blob(OWNER_CONSUMER_BASE, path),
                "original consumer/helper/test must remain unchanged: " + path)
    workflow = ".github/workflows/reader-f03-production-acceptance-v342.yml"
    desired = blob(OWNER_CONSUMER_BASE, workflow).decode()
    routes = [(original_owner_path, paths["owner"], 3),
              (original_org_path, paths["org"], 2),
              (owner_gate_path, paths["ownerGate"], 1),
              (org_gate_path, paths["orgGate"], 1)]
    for old, new, count in routes:
        require(desired.count(old) == count, "complete original workflow call inventory: " + old)
        desired = desired.replace(old, new)
    compile_line = ("python3 -m py_compile tests/dot_f03_production_acceptance_20261102/admission.py "
        "tests/dot_f03_production_acceptance_20261102/android_host_evidence_v342.py "
        "tests/dot_f03_production_acceptance_20261102/check_android_host_v342.py "
        "tests/dot_f03_production_acceptance_20261102/check_evidence_gate_v342.py "
        "tests/dot_f03_production_acceptance_20261102/check_bounded_evidence_gate_v342.py")
    desired = replace_once(desired, compile_line, compile_line + " " +
                           " ".join(paths[key] for key in ("owner", "ownerGate", "org", "orgGate")))
    require((ROOT / workflow).read_text() == desired, "exact seven call routes and four precompiled entries only")
    require(all(old not in desired for old, _, _ in routes), "unversioned workflow consumer remains")
    return {"policy": expected, "versioned_sha256": {path: digest(raw) for path, raw in expected_files.items()},
            "original_source": OWNER_CONSUMER_BASE, "reviewed_owner_source": FIXTURE_SOURCE,
            "workflow_sha256": digest(desired.encode()), "runtime_accepted": False}


def verify_source():
    c = configuration()
    require(os.environ.get("GITHUB_ACTIONS") == "true", "Actions only")
    require(os.environ.get("GITHUB_REF") == "refs/heads/" + BRANCH, "exclusive acceptance branch")
    require(os.environ.get("GITHUB_RUN_ATTEMPT") == "1", "one authorized run; no retry")
    require(not any(value for key, value in os.environ.items() if key.startswith("ANDROID_CANDIDATE_")),
            "candidate evidence cannot enter production admission")
    require(os.environ.get("ANDROID_OWNERSHIP_HEAD") == CANONICAL, "reviewed ownership boundary")
    require(MARKER in git("log", "-1", "--format=%B"), "authorized acceptance commit marker")
    source = git("rev-parse", "HEAD")
    require(source == os.environ["GITHUB_SHA"], "tested source differs from run")
    require(git("rev-list", "--parents", "-n", "1", source).split() == [source, IMPORT_STATUS_BASE],
            "exact single R6 status correction on preserved R5")
    for parent, child in ((BASE, CANONICAL), (CANONICAL, INTAKE), (INTAKE, REVIEWED_ACCEPTANCE), (REVIEWED_ACCEPTANCE, PREVIOUS_CORRECTION), (PREVIOUS_CORRECTION, TEST_CLOSURE_BASE), (TEST_CLOSURE_BASE, OWNER_CONSUMER_BASE), (OWNER_CONSUMER_BASE, IMPORT_STATUS_BASE), (IMPORT_STATUS_BASE, source)):
        require(git("merge-base", parent, child) == parent, "source ancestry mismatch")
    for start, end, key in ((BASE, CANONICAL, "canonical_delta"),
                            (CANONICAL, INTAKE, "intake_delta")):
        records = c[key]
        changed = git("diff", "--name-only", start, end).splitlines()
        require(set(changed) == set(records), "exact reviewed delta paths: " + key)
        for path, expected in records.items():
            require(git("rev-parse", end + ":" + path) == expected, "fixed delta blob: " + path)
    require(set(git("diff", "--name-only", INTAKE, REVIEWED_ACCEPTANCE).splitlines()) == set(c["new_paths"]),
            "preserved R1 exact ten-file package")
    require(all(line.startswith("A\t") for line in git("diff", "--name-status", INTAKE, REVIEWED_ACCEPTANCE).splitlines()),
            "preserved R1 additions only")
    for path, expected in c["r1_package_blobs"].items():
        require(git("rev-parse", REVIEWED_ACCEPTANCE + ":" + path) == expected, "preserved R1 package blob")
    require(set(c["r1_package_blobs"]) == set(c["new_paths"]), "complete R1 package pin")
    require(set(git("diff", "--name-only", REVIEWED_ACCEPTANCE, PREVIOUS_CORRECTION).splitlines()) ==
            set(c["previous_correction_blobs"]), "preserved exact R2 five-file correction")
    require(len(c["previous_correction_blobs"]) == 5 and
            all(line.startswith("M\t") for line in git("diff", "--name-status", REVIEWED_ACCEPTANCE, PREVIOUS_CORRECTION).splitlines()),
            "preserved R2 modifications only")
    for path, expected in c["previous_correction_blobs"].items():
        require(git("rev-parse", PREVIOUS_CORRECTION + ":" + path) == expected, "preserved R2 package blob")
    require(set(git("diff", "--name-only", PREVIOUS_CORRECTION, TEST_CLOSURE_BASE).splitlines()) ==
            set(c["r3_package_blobs"]), "preserved exact R3 three-file correction")
    require(len(c["r3_package_blobs"]) == 3 and
            all(line.startswith("M\t") for line in git("diff", "--name-status", PREVIOUS_CORRECTION, TEST_CLOSURE_BASE).splitlines()),
            "preserved R3 modifications only")
    for path, expected in c["r3_package_blobs"].items():
        require(git("rev-parse", TEST_CLOSURE_BASE + ":" + path) == expected, "preserved R3 package blob")
    r4_delta = {**{p: "M" for p in c["r3_package_blobs"]},
                **{p: "A" for p in c["catalog_overlay_blobs"]}}
    require(set(c["r4_package_blobs"]) == set(r4_delta) and len(r4_delta) == 5,
            "preserved R4 exact two additions and three modifications")
    require({row.split("\t", 1)[1]: row.split("\t", 1)[0]
             for row in git("diff", "--name-status", TEST_CLOSURE_BASE, OWNER_CONSUMER_BASE).splitlines()} == r4_delta,
            "preserved R4 exact authorized delta")
    for path, expected_blob in c["r4_package_blobs"].items():
        require(git("rev-parse", OWNER_CONSUMER_BASE + ":" + path) == expected_blob, "preserved R4 package blob")
    r5_delta = {**{p: "M" for p in c["r3_package_blobs"]},
                **{p: "A" for p in c["owner_consumer_contract"]["paths"].values()}}
    require(set(c["r5_package_blobs"]) == set(r5_delta) and len(r5_delta) == 7,
            "preserved R5 exact four additions and three modifications")
    require({row.split("\t", 1)[1]: row.split("\t", 1)[0]
             for row in git("diff", "--name-status", OWNER_CONSUMER_BASE, IMPORT_STATUS_BASE).splitlines()} == r5_delta,
            "preserved R5 exact delta")
    for path, expected in c["r5_package_blobs"].items():
        require(git("rev-parse", IMPORT_STATUS_BASE + ":" + path) == expected, "preserved R5 package blob")
    expected_delta = {
        "tests/dot_f03_production_acceptance_20261102/admission.py": "M",
        "tests/dot_f03_production_acceptance_20261102/contract.json": "M",
        "tests/dot_f03_production_acceptance_20261102/androidTest/org/exreader/host/HostImportUiTest.java": "A"}
    require(set(c["approved_delta"]) == set(expected_delta), "R6 exact one addition and two modifications")
    require({row.split("\t", 1)[1]: row.split("\t", 1)[0]
             for row in git("diff", "--name-status", IMPORT_STATUS_BASE, source).splitlines()} == expected_delta,
            "R6 exact authorized delta status and paths")
    for path in set(c["new_paths"]) | set(c["approved_delta"]):
        require(git("cat-file", "-t", source + ":" + path) == "blob", "acceptance path must be a file")
        require((ROOT / path).read_bytes() == blob(source, path), "modified acceptance file: " + path)
    require(not git("diff", "--name-only", SDK, source, "--", *c["sdk_frozen_paths"]),
            "SDK and original fixture/workflow freeze")
    for path, expected in c["jni_blobs"].items():
        require(git("rev-parse", source + ":" + path) == expected, "reviewed JNI identity: " + path)
        require(digest((ROOT / path).read_bytes()) == digest(blob(CANONICAL, path)), "dirty JNI: " + path)
    require(not git("diff", "--name-only", "f32bb8aa18ed3de286900f19ce4230fd93435dd0",
                    source, "--", "apps/reader/store/001_catalog.sql"), "original catalog freeze")
    for path in c["intake_delta"]:
        require((ROOT / path).read_bytes() == blob(INTAKE, path), "intake bytes changed: " + path)
    require(not git("diff", "--name-only", "HEAD", "--", *c["immutable_worktree_paths"]),
            "tracked SDK, production, old checks or old tests modified")
    original_contract = json.loads(blob(CANONICAL, "tests/dot_f04_reading_sync_20261031/contract.json"))
    require(set(c["canonical_delta"]) == set(original_contract["canonical"]["union_paths"]),
            "reuse the exact previously reviewed source union")
    for path in c["original_f04_protected_paths"]:
        require(not git("diff", "--name-only", BASE, CANONICAL, "--", path), "old F04 protected source: " + path)
    parser_delta = {
        "examples/android/app/src/main/java/org/exreader/host/ReadingParserPolicy.java": (
            '        if (recorded.equals("exreader-sdk-" + actual)) return true;',
            '        if (actual.equals("3.42.0") && recorded.equals("3.42.0")) return true;'),
        "apps/reader/desktop/windows_records_owner.cpp": (
            ' if(!std::strcmp(recorded,exr_version()))return true;',
            ' if(!std::strcmp(exr_version(),"3.42.0")&&!std::strcmp(recorded,"exreader-sdk-3.42.0"))return true;'),
        "examples/apple/HostReadingRecords.swift": (
            '        if recorded == actual { return true }',
            '        if actual == "3.42.0" && recorded == "exreader-sdk-3.42.0" { return true }')}
    require(set(git("diff", "--name-only", BASE, CANONICAL, "--", "apps", "examples").splitlines()) ==
            set(parser_delta), "only the three reviewed parser changes")
    for path, (anchor, added) in parser_delta.items():
        old = blob(BASE, path)
        require(old.count(anchor.encode()) == 1, "unique parser anchor")
        require(blob(CANONICAL, path) == old.replace(anchor.encode(), (anchor + "\n" + added).encode(), 1),
                "exact reviewed parser delta")
    require(b'#define EXR_VERSION "3.42.0"' in (ROOT / "include/exr/base.h").read_bytes(),
            "actual frozen SDK version, not a Gradle label")
    for relative, original in c["overlay_sources"].items():
        require((ROOT / relative).read_bytes() == blob(FIXTURE_SOURCE, original), "reviewed overlay bytes")
    for path, expected in c["additional_source_trees"].items():
        require(git("rev-parse", "HEAD:" + path) == expected, "frozen dependency/test source: " + path)
        require(not git("diff", "--name-only", "HEAD", "--", path), "dirty dependency/test source: " + path)
    for path, expected in c["test_dependency_blobs"].items():
        require(git("rev-parse", "HEAD:" + path) == expected and
                (ROOT / path).read_bytes() == blob("HEAD", path), "unchanged complete test dependency: " + path)
    require(set(c["test_dependency_sources"].values()) == set(c["test_dependency_blobs"]),
            "complete test dependency manifest")
    capability = private_copy_contract()
    schema_contract = catalog_schema_contract()
    consumers = owner_consumer_contract()
    status_contract = host_import_status_contract()
    return {"host_import_status_contract": status_contract, "owner_consumer_contract": consumers, "catalog_schema_contract": schema_contract, "test_dependency_blobs": c["test_dependency_blobs"], "private_copy_capability": capability, "source_sha": source, "review_base": BASE, "ownership_head": CANONICAL,
            "product_intake_head": INTAKE, "sdk_source": SDK, "sdk_version": "3.42.0",
            "contract_sha256": digest((HERE / "contract.json").read_bytes()),
            "run_id": os.environ["GITHUB_RUN_ID"], "attempt": os.environ["GITHUB_RUN_ATTEMPT"],
            "source_admitted": True, "runtime_accepted": False}

def write_report(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")

def prepare():
    report = verify_source()
    c = configuration()
    temporary = Path(os.environ["RUNNER_TEMP"]) / "f03-production-v342"
    temporary.mkdir(exist_ok=False)
    java = temporary / "androidTest-java"
    shutil.copytree(ROOT / "examples/android/app/src/androidTest/java", java)
    for relative, original in c["overlay_sources"].items():
        target = java / Path(original).relative_to("examples/android/app/src/androidTest/java")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, target)
    # Compare every staged original except the four explicitly reviewed overlay classes.
    old_root = ROOT / "examples/android/app/src/androidTest/java"
    overlay_names = {Path(p).relative_to("examples/android/app/src/androidTest/java").as_posix()
                     for p in c["overlay_sources"].values()}
    for path in old_root.rglob("*"):
        if path.is_file() and path.relative_to(old_root).as_posix() not in overlay_names:
            require((java / path.relative_to(old_root)).read_bytes() == path.read_bytes(),
                    "overlay changed another original test")
    require(all(len(list(java.rglob(Path(name).name))) == 1 for name in overlay_names),
            "every reviewed overlay class has exactly one staged definition")
    for relative, original in c["test_dependency_sources"].items():
        target = java / relative
        require(not target.exists(), "test dependency class collision: " + relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / original, target)
        require(target.read_bytes() == blob("HEAD", original) and len(list(java.rglob(target.name))) == 1,
                "one unchanged original test helper/runner: " + relative)
    status = host_import_status_contract()["policy"]
    target = java / status["staged_path"]
    require(target.read_bytes() == blob(IMPORT_STATUS_BASE, status["source"]),
            "status override starts from the validated original runner")
    shutil.copyfile(ROOT / status["overlay"], target)
    require(target.read_bytes() == (ROOT / status["overlay"]).read_bytes() and
            len(list(java.rglob(target.name))) == 1, "one exact reviewed status runner definition")
    expected = {p.relative_to(old_root).as_posix() for p in old_root.rglob("*") if p.is_file()}
    expected.update(overlay_names)
    expected.update(c["test_dependency_sources"])
    require({p.relative_to(java).as_posix() for p in java.rglob("*") if p.is_file()} == expected,
            "complete test staging without extra or missing files")
    real_gradle = shutil.which("gradle")
    require(real_gradle and Path(real_gradle).is_file(), "installed Gradle 8.9 launcher")
    wrapper = temporary / "gradle"
    init = HERE / "android-test-overlay.init.gradle"
    wrapper.write_text("#!/usr/bin/env bash\nset -euo pipefail\n" +
                       'test "${EXREADER_ORIGINAL_HASH_PREFIX:?missing installed hash owner}" = ' +
                       shlex.quote(str(installed_hash_prefix())) + "\n" +
                       "python3 " + shlex.quote(str(HERE / "admission.py")) + " hash-proof >/dev/null\n" +
                       "exec " + shlex.quote(real_gradle) +
                       " --init-script " + shlex.quote(str(init)) + ' -PexrSdkVersion=3.42.0 -PexrHostImport=true "$@"\n')
    wrapper.chmod(0o755)
    with open(os.environ["GITHUB_ENV"], "a") as stream:
        stream.write("F03_GRADLE=" + str(wrapper) + "\nF03_ANDROID_TEST_JAVA=" + str(java) + "\n")
    report["overlay_files_sha256"] = {p.relative_to(java).as_posix(): digest(p.read_bytes())
                                     for p in sorted(java.rglob("*")) if p.is_file()}
    report["gradle_wrapper_sha256"] = digest(wrapper.read_bytes())
    report["gradle_real_launcher"] = real_gradle
    write_report(ROOT / "build/f03-production/source-admission.json", report)

def original_build(arguments):
    verify_source()
    hash_owner_proof()
    import android_host_evidence_v342 as versioned
    previous = sys.modules.get("android_host_evidence")
    old_argv = sys.argv[:]
    extensions = []
    module = None
    original_product = None
    try:
        # Only this process gets the versioned ownership adapter. Original disk files remain unchanged.
        sys.modules["android_host_evidence"] = versioned
        spec = importlib.util.spec_from_file_location("f03_retained_build", ROOT / "tools/build_android_host.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        original_product = module.build_product
        def product_with_complete_install(product_stage, build):
            original_run = module.run
            def complete_catalog_install_targets(argv, *args, **kwargs):
                values = list(map(str, argv))
                if (len(values) == 8 and values[0] == shutil.which("cmake") and
                        values[1] == "--build" and
                        Path(values[2]).resolve() == (build / "catalog").resolve() and
                        values[3:] == ["--parallel", "4", "--target", "reader_catalog", "--verbose"]):
                    extended = list(argv[:-1]) + ["reader_original_import", argv[-1]]
                    extensions.append({"original": values, "extended": list(map(str, extended))})
                    return original_run(extended, *args, **kwargs)
                return original_run(argv, *args, **kwargs)
            module.run = complete_catalog_install_targets
            try:
                original_product(product_stage, build)
            finally:
                module.run = original_run
            require(len(extensions) == 1, "exact original catalog build target observed once")
        module.build_product = product_with_complete_install
        sys.argv = [str(ROOT / "tools/build_android_host.py"), *arguments]
        module.main()
        hash_owner_proof()
    finally:
        write_report(ROOT / "build/f03-production/build-adapter.json",
                     {"catalog_install_target_extensions": extensions, "original_driver_modified": False})
        if module is not None and original_product is not None:
            module.build_product = original_product
        sys.argv = old_argv
        if previous is None:
            sys.modules.pop("android_host_evidence", None)
        else:
            sys.modules["android_host_evidence"] = previous


def recovery():
    c = configuration()
    root = ROOT / "build/f03-recovery"
    report = json.loads((root / "device-report.json").read_text())
    for key, env in (("source_sha", "GITHUB_SHA"), ("run_id", "GITHUB_RUN_ID"), ("attempt", "GITHUB_RUN_ATTEMPT")):
        require(report.get(key) == os.environ[env], "recovery actual run identity: " + key)
    require(report.get("api") == 34 and report.get("abi") == "x86_64", "recovery device identity")
    checks = report.get("checks", [])
    require(report.get("count") == 12 and report.get("failed") == 0 and
            [item.get("id") for item in checks] == c["recovery_cases"] and
            all(item.get("passed") is True and item.get("source_preserved") is True for item in checks),
            "all twelve original recovery cases must pass in order")
    log = (root / "instrumentation.txt").read_text()
    require(re.findall(r"^INSTRUMENTATION_STATUS_CODE: (-?\d+)\s*$", log, re.M) == ["1", "0"] * 12,
            "recovery case completion status")
    require(re.findall(r"^INSTRUMENTATION_CODE: (-?\d+)\s*$", log, re.M) == ["-1"] and
            re.search(r"^OK \(12 tests\)\s*$", log, re.M), "recovery terminal result")
    require(not any(x in log for x in ("FAILURES!!!", "INSTRUMENTATION_FAILED", "INSTRUMENTATION_ABORTED")),
            "recovery instrumentation failure")
    require(set(re.findall(r"^INSTRUMENTATION_STATUS: class=(.+)\s*$", log, re.M)) ==
            {"org.exreader.host.OrganizationBootstrapRecoveryTest"}, "recovery class identity")
    names = re.findall(r"^INSTRUMENTATION_STATUS: test=(.+)\s*$", log, re.M)
    require(names == [name for name in c["recovery_cases"] for _ in (0, 1)], "recovery case log identity")
    result = {key: report[key] for key in ("source_sha", "run_id", "attempt")}
    result.update({"recovery_accepted": True, "runtime_accepted": False,
                   "device_report_sha256": digest((root / "device-report.json").read_bytes()),
                   "instrumentation_sha256": digest((root / "instrumentation.txt").read_bytes())})
    write_report(root / "result.json", result)
    print(json.dumps(result))

def final_result():
    destination = ROOT / "build/f03-production/result.json"
    result = {"accepted": False, "problems": [], "source_sha": os.environ.get("GITHUB_SHA"),
              "run_id": os.environ.get("GITHUB_RUN_ID"), "attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
              "scope": "F03 intake historical-state recovery and complete retained Android acceptance",
              "old_apk_upgrade_accepted": False, "complete_product": False}
    try:
        admitted = verify_source()
        outcomes = json.loads(os.environ["F03_UPSTREAM"])
        required = {"admission", "prepare", "hash_owner", "test_compile", "build", "emulator", "catalog", "preflight", "gate48",
                    "gate20", "host", "shelf", "shelf_gate", "owner", "owner_gate", "organization", "organization_gate"}
        require(set(outcomes) == required and all(v == "success" for v in outcomes.values()),
                "a required original or new stage failed, skipped or was cancelled")
        identity = {k: result[k] for k in ("source_sha", "run_id", "attempt")}
        records = {
            "host": "build/shelf-android/original-result.json",
            "gate48": "build/android-host/gate-review.json",
            "gate20": "build/android-host/bounded-gate-review.json",
            "shelf": "build/shelf-android/shelf-result.json",
            "shelf_gate": "build/shelf-android/shelf-gate-review.json",
            "owner": "build/owner-android/result.json",
            "owner_gate": "build/owner-android/gate-review.json",
            "organization": "build/organization-android/result.json",
            "organization_gate": "build/organization-android/gate-review.json"}
        proofs = {}
        for name, relative in records.items():
            path = ROOT / relative
            value = json.loads(path.read_text())
            require(value.get("accepted") is True and not value.get("problems") and not value.get("problem"),
                    "actual acceptance missing: " + name)
            if name == "host":
                summary = value["summary"]
                require(value.get("candidate_only") is False and value.get("candidate_validated") is False and
                        summary["source_sha"] == identity["source_sha"] and
                        summary["run"]["id"] == identity["run_id"] and
                        summary["run"]["attempt"] == identity["attempt"], "formal host identity")
            else:
                require(all(value.get(k) == v for k, v in identity.items()), "same-run final identity: " + name)
            if "checks" in value:
                require(value["checks"] and all(item.get("passed") is True for item in value["checks"]),
                        "gate checks incomplete: " + name)
            proofs[name] = {"path": relative, "sha256": digest(path.read_bytes())}
        for name, count in (("gate48", 48), ("gate20", 20), ("shelf_gate", 19), ("owner_gate", 19), ("organization_gate", 15)):
            value = json.loads((ROOT / records[name]).read_text())
            require(len(value["checks"]) == count, "original gate count: " + name)
        owner = json.loads((ROOT / records["owner"]).read_text())
        organization = json.loads((ROOT / records["organization"]).read_text())
        require(owner.get("owner_checks") == 18 and owner.get("typed_kill_checks") == 2 and
                owner.get("original_functional_checks") == 112 and owner.get("original_gate_checks") == 87,
                "full actual eighteen-case owner/provider and two real kills required")
        require(organization.get("native_checks") == 8 and organization.get("real_ui_checks") == 8 and
                organization.get("real_process_retry_checks") == 1 and
                organization.get("original_owner_checks") == 18 and organization.get("original_typed_kill_checks") == 2 and
                organization.get("original_functional_checks") == 112 and organization.get("original_gate_checks") == 87 and
                organization.get("original_owner_altered_evidence_checks") == 19,
                "organization consumes the complete actual owner18 chain")
        for name, path_key in (("owner_gate", "ownerGate"), ("organization_gate", "orgGate")):
            gate = json.loads((ROOT / records[name]).read_text())
            gate_path = configuration()["owner_consumer_contract"]["paths"][path_key]
            require(gate.get("script_sha256") == digest((ROOT / gate_path).read_bytes()),
                    "actual versioned gate provenance: " + name)
        hash_owner = hash_owner_proof()
        test_compilation_proof()
        proofs["test_compilation"] = {"path": "build/f03-production/test-compilation.json",
            "sha256": digest((ROOT / "build/f03-production/test-compilation.json").read_bytes())}
        imported = import20()
        require(imported["accepted"] is True, "actual private-copy import suite required")
        recovery()
        recovered = json.loads((ROOT / "build/f03-recovery/result.json").read_text())
        require(recovered["recovery_accepted"] is True and all(recovered.get(k) == v for k, v in identity.items()),
                "twelve same-run recovery cases")
        proofs["recovery"] = {"path": "build/f03-recovery/result.json",
                              "sha256": digest((ROOT / "build/f03-recovery/result.json").read_bytes())}
        result.update(accepted=True, source_admission=admitted, evidence=proofs,
                      original_host_checks=66, original_gate_checks=[48, 20],
                      original_organization_cases=8, recovery_cases=12, import_cases=20,
                      original_catalog_cases=8, original_mapping_cases=14,
                       original_owner_cases=18, original_owner_kill_cases=2,
                       original_organization_ui_cases=8, original_owner_gate_cases=19, original_organization_gate_cases=15,
                      installed_hash_owner=hash_owner, private_copy_runtime=imported, upstream=outcomes)
    except Exception as error:
        result["problems"].append(type(error).__name__ + ": " + str(error))
    write_report(destination, result)
    print(json.dumps(result))
    return 0 if result["accepted"] else 1



def private_copy_contract():
    c = configuration()
    for path, expected in c["private_copy_blobs"].items():
        require(git("rev-parse", "HEAD:" + path) == expected and
                (ROOT / path).read_bytes() == blob("HEAD", path), "private-copy source identity: " + path)
    activity = (ROOT / "examples/android/app/src/main/java/org/exreader/host/MainActivity.java").read_text()
    controller = (ROOT / "examples/android/app/src/main/java/org/exreader/host/ImportController.java").read_text()
    entry = (ROOT / "extras/android-import-entry/android/importentry/src/main/java/org/exreader/importentry/ImportEntry.java").read_text()
    required = [
        (activity, ["ImportEntry.pickerIntent(true)", "imports.submit(data)", "imports.submit(intent)",
                    "ready.size()>MAX_INPUT_BYTES", "32L * 1024 * 1024",
                    "copyUri(Uri.fromFile(ready.file()), ready.id(), task)",
                    'ready.id().startsWith(copied.sha256+".")', "store.finalizeImport(verified)"]),
        (controller, ["context.getApplicationContext()", "ImportEntry.createWithDisplayFilename",
                      'new File(context.getFilesDir(),"incoming")', "opened.pendingReady()", "owner.importReady(next)",
                      "entry.release(request)", "files.execute"]),
        (entry, ["ContentResolver.SCHEME_CONTENT", 'resolver.openAssetFileDescriptor(uri, "r")',
                 "COPY_BUFFER_BYTES = 64 * 1024", "catch (SecurityException e)",
                 "ImportError.Code.PERMISSION", "digest.update(buffer, 0, got)", "out.getFD().sync()",
                 "StandardCopyOption.ATOMIC_MOVE", "public List<ReadyRequest> pendingReady()", "cleanStaging()"])]
    for text, needles in required:
        require(all(value in text for value in needles), "reviewed private-copy capability chain missing")
    require(c["private_copy_policy"] == "temporary-grant-verified-private-copy-v1",
            "explicit private-copy policy approval required")
    return {"policy": c["private_copy_policy"], "source_blobs": c["private_copy_blobs"],
            "persistent_uri_grant_required": False, "runtime_accepted": False}

def installed_hash_prefix():
    prefix = ROOT / "build/f03-production/hash/android/stage"
    require(prefix == prefix.resolve() and not any(p.is_symlink() for p in [prefix, *prefix.parents]),
            "hash prefix and ancestors must be real canonical directories")
    return prefix

def hash_inventory(prefix):
    require(prefix.is_dir() and prefix == prefix.resolve(), "canonical installed hash prefix")
    result = {}
    for path in sorted(prefix.rglob("*")):
        require(not path.is_symlink() and path.resolve().is_relative_to(prefix), "hash owner alias or escape")
        if path.is_file():
            result[path.relative_to(prefix).as_posix()] = {"bytes": path.stat().st_size,
                                                         "sha256": digest(path.read_bytes())}
    required = {"lib/libopds_sha256_stream.a", "include/exreader-opds-hash/opds_sha256_stream.h",
                "lib/cmake/EXReaderOPDSHash/EXReaderOPDSHashConfig.cmake",
                "lib/cmake/EXReaderOPDSHash/EXReaderOPDSHashConfigVersion.cmake",
                "lib/cmake/EXReaderOPDSHash/EXReaderOPDSHashTargets.cmake"}
    require(required <= set(result), "installed hash owner incomplete")
    data = (prefix / "lib/libopds_sha256_stream.a").read_bytes()
    require(data.startswith(b"!<arch>\n"), "hash archive format")
    offset, members = 8, 0
    while offset < len(data):
        header = data[offset:offset + 60]
        require(len(header) == 60 and header[58:60] == b"\x60\n", "hash archive header")
        size = int(header[48:58].strip())
        body = data[offset + 60:offset + 60 + size]
        require(len(body) == size, "hash archive truncation")
        name = header[:16].decode("ascii").strip()
        if name not in ("/", "//", "/SYM64/"):
            require(body[:6] == b"\x7fELF\x02\x01" and len(body) >= 20 and
                    int.from_bytes(body[16:18], "little") == 1 and
                    int.from_bytes(body[18:20], "little") == 62, "hash owner must be x86_64 ELF64 relocatable objects")
            members += 1
        offset += 60 + size + size % 2
    require(offset == len(data) and members > 0, "hash archive members missing")
    return result

def prepare_hash_owner():
    source = verify_source()
    prefix = installed_hash_prefix()
    require(os.environ.get("EXREADER_ORIGINAL_HASH_PREFIX") in (None, "", str(prefix)), "foreign hash environment")
    require(not os.environ.get("READER_ORIGINAL_HASH_PREFIX"), "conflicting hash selector")
    require(not prefix.exists(), "hash installation must be fresh in this run")
    prefix.mkdir(parents=True)
    home = Path(os.environ["ANDROID_HOME"])
    ndk = home / "ndk/27.0.12077973"
    toolchain = ndk / "build/cmake/android.toolchain.cmake"
    require(toolchain.is_file() and "Pkg.Revision = 27.0.12077973" in (ndk / "source.properties").read_text(),
            "exact approved NDK hash-owner compiler")
    build = prefix.parent / "build"
    arguments = ["cmake", "-S", str(ROOT / "extras/opds"), "-B", str(build), "-G", "Ninja",
                 "-DCMAKE_BUILD_TYPE=Release", "-DEXREADER_OPDS_HASH_ONLY=ON",
                 "-DCMAKE_POSITION_INDEPENDENT_CODE=ON", "-DCMAKE_INSTALL_PREFIX=" + str(prefix),
                 "-DCMAKE_TOOLCHAIN_FILE=" + str(toolchain), "-DANDROID_ABI=x86_64",
                 "-DANDROID_PLATFORM=android-26", "-DANDROID_STL=c++_static"]
    for command in (arguments, ["cmake", "--build", str(build), "--parallel", "4", "--target", "install"]):
        subprocess.run(command, cwd=ROOT, check=True)
    cache = build / "CMakeCache.txt"
    require("EXREADER_OPDS_HASH_ONLY:BOOL=ON" in cache.read_text(), "hash-only build identity")
    report = {k: source[k] for k in ("source_sha", "run_id", "attempt")}
    report.update(prefix=str(prefix), package="EXReaderOPDSHash", version="0.1.0",
                  owner_source_tree=git("rev-parse", "HEAD:extras/opds"),
                  configure=arguments, ndk="27.0.12077973", abi="x86_64", platform="android-26",
                  toolchain_sha256=digest(toolchain.read_bytes()), cache_sha256=digest(cache.read_bytes()),
                  files=hash_inventory(prefix))
    write_report(ROOT / "build/f03-production/hash-owner.json", report)
    os.environ["EXREADER_ORIGINAL_HASH_PREFIX"] = str(prefix)
    with open(os.environ["GITHUB_ENV"], "a") as stream:
        stream.write("EXREADER_ORIGINAL_HASH_PREFIX=" + str(prefix) + "\n")
    print(json.dumps({"hash_owner_installed": True, "prefix": str(prefix), "files": report["files"]}))

def hash_owner_proof():
    c = configuration()
    prefix = installed_hash_prefix()
    require(os.environ.get("EXREADER_ORIGINAL_HASH_PREFIX") == str(prefix), "hash prefix lost or replaced in child process")
    require(git("rev-parse", "HEAD:extras/opds") == c["hash_source_tree"], "hash owner source changed")
    report = json.loads((ROOT / "build/f03-production/hash-owner.json").read_text())
    require(all(report.get(k) == os.environ[e] for k, e in
                (("source_sha", "GITHUB_SHA"), ("run_id", "GITHUB_RUN_ID"), ("attempt", "GITHUB_RUN_ATTEMPT"))),
            "hash owner belongs to another run")
    require(report.get("prefix") == str(prefix) and report.get("owner_source_tree") == c["hash_source_tree"] and
            report.get("version") == "0.1.0" and report.get("ndk") == "27.0.12077973" and
            report.get("abi") == "x86_64" and report.get("platform") == "android-26",
            "hash owner target identity")
    require(report.get("files") == hash_inventory(prefix), "installed hash owner bytes changed")
    cache = prefix.parent / "build/CMakeCache.txt"
    require(report["cache_sha256"] == digest(cache.read_bytes()), "hash owner configuration changed")
    toolchain = Path(os.environ["ANDROID_HOME"]) / "ndk/27.0.12077973/build/cmake/android.toolchain.cmake"
    require(report["toolchain_sha256"] == digest(toolchain.read_bytes()), "hash compiler toolchain changed")
    require(not os.environ.get("READER_ORIGINAL_HASH_PREFIX"), "conflicting hash selector")
    return report

def import20():
    c = configuration()
    root = ROOT / "build/android-host-import/ui"
    report = json.loads((root / "result.json").read_text())
    identity = {k: os.environ[e] for k, e in
                (("source_sha", "GITHUB_SHA"), ("run_id", "GITHUB_RUN_ID"), ("attempt", "GITHUB_RUN_ATTEMPT"))}
    require(all(report.get(k) == v for k, v in identity.items()), "host import same-run identity")
    require(report.get("accepted") is True and report.get("checks") == 20 and report.get("api") == 34 and
            report.get("abi") == "x86_64" and report.get("physical_device") is False and
            report.get("reading_limit_bytes") == 32 * 1024 * 1024, "host import 20 actual checks")
    phases = report["phases"]
    expected = c["import20_cases"]
    require([p["phase"] for p in phases] == c["import20_phase_order"] and len(phases) == 9 and
            len({p["pid"] for p in phases}) == 9, "host import original nine process phases")
    for phase in phases:
        names = expected[phase["phase"]]
        raw = json.loads((root / (phase["phase"] + "-raw-report.json")).read_text())
        require(raw == phase and all(raw.get(k) == v for k, v in identity.items()) and
                phase["passed"] is True and phase["count"] == len(names) and
                [row["name"] for row in phase["checks"]] == names and
                all(row["pass"] is True for row in phase["checks"]), "host import original phase assertions")
    require(sum(p["count"] for p in phases) == 20, "host import complete case count")
    protocol = report["marker_protocol"]
    require(protocol["present_exit_code"] == 0 and protocol["absent_exit_code"] != 0, "real boundary marker probe")
    stops = report["process_stops"]
    require(len(stops) == 9 and all(s["force_stop"] is True and not s["pid_after_stop"] for s in stops),
            "actual process stops")
    held = [s for s in stops if s.get("held_boundary")]
    require(len(held) == 4 and {s["phase"] for s in held} == {"kill-copy", "kill-stable", "kill-ready", "kill-published"},
            "four original kill boundaries")
    for stop in held:
        raw = (root / (stop["phase"] + "-boundary-marker.json")).read_bytes()
        marker = json.loads(raw)
        phase_raw = (root / (stop["phase"] + "-raw-report.json")).read_bytes()
        require(marker == stop["boundary_marker"] and digest(raw) == stop["marker_sha256"] and
                all(marker.get(k) == v for k, v in identity.items()) and marker["phase"] == stop["phase"] and
                marker["pid"] == stop["instrumentation_pid"] and
                str(stop["instrumentation_pid"]) in stop["pid_before_stop"].split() and
                len(phase_raw) == marker["report_bytes"] and digest(phase_raw) == marker["report_sha256"],
                "held process/marker/raw report binding")
    artifacts = {
        "org.exreader.host": "examples/android/app/build/outputs/apk/debug/app-debug.apk",
        "org.exreader.host.test": "build/android-host-import/test-apks/host-import-ui.apk",
        "org.exreader.hostimportsource": "tests/reader_android_host_import/source/build/outputs/apk/debug/hostimportsource-debug.apk"}
    require(len(report["apk_identities"]) == 3 and {a["package"] for a in report["apk_identities"]} == set(artifacts),
            "three actually installed host import packages")
    for apk in report["apk_identities"]:
        path = artifacts[apk["package"]]
        require(apk["artifact_path"] == path and apk["sha256"] == apk["installed_sha256"] ==
                digest((ROOT / path).read_bytes()), "actual host import APK identity")
    build = json.loads((ROOT / "build/android-host/build.json").read_text())
    require(digest((ROOT / artifacts["org.exreader.host"]).read_bytes()) ==
            build["artifacts"]["app-debug.apk"]["sha256"], "import suite replaced the original host APK")
    require(any(v["name"] == "system-documentsui" and v["package"] == "com.android.documentsui"
                for v in report["captures"]), "actual system picker evidence")
    for capture in report["captures"]:
        require(Path(capture["name"]).name == capture["name"], "capture path")
        raw = (root / "captures" / (capture["name"] + ".png")).read_bytes()
        require(raw.startswith(b"\x89PNG\r\n\x1a\n") and len(raw) == capture["bytes"] and
                digest(raw) == capture["sha256"], "host import capture bytes")
    result = {**identity, "accepted": True, "checks": 20, "phases": 9,
              "policy": c["private_copy_policy"], "result_sha256": digest((root / "result.json").read_bytes())}
    write_report(ROOT / "build/f03-production/import20-verification.json", result)
    return result



def apk_classes(path):
    """Read actual DEX class definitions, not source-name strings."""
    import struct
    import zipfile
    result = set()
    with zipfile.ZipFile(path) as archive:
        names = [n for n in archive.namelist() if re.fullmatch(r"classes(?:[0-9]+)?\.dex", n)]
        require(names and len(names) == len(set(names)), "APK DEX inventory")
        for name in names:
            data = archive.read(name)
            require(len(data) >= 112 and data[:4] == b"dex\n", "actual DEX header")
            def u32(offset):
                require(0 <= offset <= len(data) - 4, "DEX offset bounds")
                return struct.unpack_from("<I", data, offset)[0]
            require(u32(40) == 0x12345678 and u32(32) == len(data), "DEX endian and file size")
            strings, string_offset = u32(56), u32(60)
            types, type_offset = u32(64), u32(68)
            count, class_offset = u32(96), u32(100)
            require(string_offset + 4 * strings <= len(data) and
                    type_offset + 4 * types <= len(data) and
                    class_offset + 32 * count <= len(data), "DEX table bounds")
            for index in range(count):
                type_index = u32(class_offset + 32 * index)
                require(type_index < types, "DEX class type")
                string_index = u32(type_offset + 4 * type_index)
                require(string_index < strings, "DEX type string")
                offset = u32(string_offset + 4 * string_index)
                for _ in range(5):
                    require(offset < len(data), "DEX string length bounds")
                    byte = data[offset]
                    offset += 1
                    if byte < 128:
                        break
                else:
                    raise ValueError("DEX string length encoding")
                end = data.find(b"\0", offset, min(len(data), offset + 4096))
                require(end >= offset, "DEX descriptor termination")
                descriptor = data[offset:end].decode("utf-8")
                require(descriptor not in result, "duplicate APK class definition")
                result.add(descriptor)
    return sorted(result)

def test_compile_paths():
    return {
        "test": ROOT / "examples/android/app/build/outputs/apk/androidTest/debug/app-debug-androidTest.apk",
        "provider": ROOT / "tests/reader_android_host_import/source/build/outputs/apk/debug/hostimportsource-debug.apk",
        "app": ROOT / "examples/android/app/build/outputs/apk/debug/app-debug.apk",
        "uitest": ROOT / "build/android-host/artifacts/uitest-debug-androidTest.apk"}

def precompile_tests():
    admitted = verify_source()
    hash_owner_proof()
    paths = test_compile_paths()
    build = json.loads((ROOT / "build/android-host/build.json").read_text())
    original_app = build["artifacts"]["app-debug.apk"]["sha256"]
    require(digest(paths["app"].read_bytes()) == original_app, "main APK before test compilation")
    java = Path(os.environ["F03_ANDROID_TEST_JAVA"])
    staged = {p.relative_to(java).as_posix(): digest(p.read_bytes())
              for p in sorted(java.rglob("*")) if p.is_file()}
    admission = json.loads((ROOT / "build/f03-production/source-admission.json").read_text())
    require(staged == admission["overlay_files_sha256"], "staged complete test sources changed")
    for key in ("source_sha", "run_id", "attempt"):
        require(admission[key] == admitted[key], "test stage source/run identity")
    require(admission["host_import_status_contract"] == admitted["host_import_status_contract"],
            "prepared status contract matches admitted source")
    status = admitted["host_import_status_contract"]
    require(digest((java / status["policy"]["staged_path"]).read_bytes()) == status["overlay_sha256"],
            "precompile must use the exact reviewed status overlay")
    wrapper = Path(os.environ["F03_GRADLE"])
    require(digest(wrapper.read_bytes()) == admission["gradle_wrapper_sha256"], "test Gradle wrapper changed")
    command = [str(wrapper), "-p", str(ROOT / "examples/android"), "--no-daemon", "--stacktrace",
               "-PexrSdk=" + str(ROOT / "stage/android-x86_64"),
               "-PexrTestRunner=org.exreader.host.HostImportUiTest",
               ":app:assembleDebugAndroidTest", ":hostimportsource:assembleDebug"]
    subprocess.run(command, cwd=ROOT, check=True)
    require(digest(paths["app"].read_bytes()) == original_app, "test preparation must not alter main APK")
    configs = list((ROOT / "examples/android/app/build/generated/source/buildConfig/debug").rglob("BuildConfig.java"))
    require(len(configs) == 1, "unique actual debug BuildConfig")
    flags = ["READER_SYNC", "READER_SEARCH", "READER_NAVIGATION", "READER_READING",
             "READER_PREFERENCES", "READER_PAGE_THEME", "READER_SELECTOR_BYTES_CANDIDATE", "READER_WAVE3"]
    config = configs[0].read_text()
    require(all(re.search(r"\bboolean\s+" + flag + r"\s*=\s*false\s*;", config) for flag in flags),
            "no additional product capabilities may be enabled to acquire a test helper")
    test_classes = apk_classes(paths["test"])
    expected_classes = sorted("L" + p[:-5] + ";" for p in staged if p.endswith(".java"))
    require(set(expected_classes) <= set(test_classes), "every complete staged Java class must be in test APK")
    required = {"Lorg/exreader/host/" + name + ";" for name in
                ("CatalogStoreTest", "ShelfCatalogTest", "ImportMappingTest", "ProductOwnerTest",
                 "OrganizationTest", "OrganizationBootstrapRecoveryTest", "HostImportUiTest", "ReadingReview")}
    require(required <= set(test_classes), "all retained runners plus actual import runner/helper compiled")
    require("Lorg/exreader/host/ReadingReview;" not in apk_classes(paths["app"]),
            "test helper must not enter the production APK")
    ui_root = ROOT / "examples/android/uitest/src/androidTest/java"
    ui_expected = {"L" + p.relative_to(ui_root).as_posix()[:-5] + ";" for p in ui_root.rglob("*.java")}
    ui_classes = apk_classes(paths["uitest"])
    require(ui_expected and ui_expected <= set(ui_classes), "all retained UI test classes compiled")
    require(digest(paths["uitest"].read_bytes()) == build["artifacts"]["uitest-debug-androidTest.apk"]["sha256"],
            "original UI runner APK unchanged")
    provider_expected = set(configuration()["provider_java_classes"])
    provider_classes = apk_classes(paths["provider"])
    require(provider_expected and provider_expected <= set(provider_classes), "complete original provider compiled")
    import zipfile
    with zipfile.ZipFile(paths["provider"]) as archive:
        for name in ("cover-import.epub", "pdf-public.pdf"):
            require(archive.read("assets/" + name) == (ROOT / "tests/fixtures" / name).read_bytes(),
                    "provider includes unchanged original source fixture: " + name)
    destination = ROOT / "build/f03-production/precompiled-test-apks"
    destination.mkdir(exist_ok=False)
    records = {}
    for name in ("test", "provider"):
        target = destination / (name + ".apk")
        shutil.copyfile(paths[name], target)
        records[name] = {"path": target.relative_to(ROOT).as_posix(), "sha256": digest(target.read_bytes())}
    report = {k: admitted[k] for k in ("source_sha", "run_id", "attempt")}
    report.update(accepted=True, command=command, staged_files_sha256=staged,
                  test_dependency_blobs=configuration()["test_dependency_blobs"], apks=records,
                  host_import_status_contract=admitted["host_import_status_contract"],
                  catalog_schema_contract=admitted["catalog_schema_contract"],
                  main_apk_sha256=original_app, uitest_apk_sha256=digest(paths["uitest"].read_bytes()),
                  build_config_sha256=digest(configs[0].read_bytes()), product_flags={f: False for f in flags},
                  test_classes=test_classes, expected_test_classes=expected_classes,
                  provider_classes=provider_classes, retained_ui_classes=ui_classes,
                  runtime_accepted=False)
    write_report(ROOT / "build/f03-production/test-compilation.json", report)
    print(json.dumps({"test_compilation_accepted": True, "runtime_accepted": False,
                      "main_apk_sha256": original_app, "staged_classes": len(expected_classes)}))

def test_compilation_proof():
    report = json.loads((ROOT / "build/f03-production/test-compilation.json").read_text())
    require(report.get("accepted") is True and report.get("runtime_accepted") is False,
            "complete pre-device test compilation required")
    require(all(report.get(k) == os.environ[e] for k, e in
                (("source_sha", "GITHUB_SHA"), ("run_id", "GITHUB_RUN_ID"), ("attempt", "GITHUB_RUN_ATTEMPT"))),
            "test compilation same source/run")
    require(report["test_dependency_blobs"] == configuration()["test_dependency_blobs"],
            "compiled helper source identity")
    require(report["catalog_schema_contract"] == catalog_schema_contract(),
            "compiled catalog/mapping test contract unchanged")
    status = host_import_status_contract()
    require(report["host_import_status_contract"] == status, "compiled status contract unchanged")
    java = Path(os.environ["F03_ANDROID_TEST_JAVA"])
    require(digest((java / status["policy"]["staged_path"]).read_bytes()) == status["overlay_sha256"],
            "compiled status overlay identity")
    require(report["staged_files_sha256"] ==
            {p.relative_to(java).as_posix(): digest(p.read_bytes()) for p in sorted(java.rglob("*")) if p.is_file()},
            "compiled staged test sources unchanged")
    for record in report["apks"].values():
        require(digest((ROOT / record["path"]).read_bytes()) == record["sha256"], "precompiled APK evidence changed")
    paths = test_compile_paths()
    require(digest(paths["app"].read_bytes()) == report["main_apk_sha256"], "main APK changed after test compilation")
    require(digest(paths["provider"].read_bytes()) == report["apks"]["provider"]["sha256"], "provider APK changed")
    require(digest(paths["uitest"].read_bytes()) == report["uitest_apk_sha256"], "retained UI runner APK changed")
    return report


def main():
    require(len(sys.argv) > 1, "explicit action required")
    action = sys.argv[1]
    if action == "admit":
        print(json.dumps(verify_source()))
    elif action == "prepare":
        prepare()
    elif action == "precompile-tests":
        precompile_tests()
    elif action == "prepare-hash":
        prepare_hash_owner()
    elif action == "hash-proof":
        print(json.dumps(hash_owner_proof()))
    elif action == "import20":
        print(json.dumps(import20()))
    elif action == "build":
        original_build(sys.argv[2:])
    elif action == "recovery":
        recovery()
    elif action == "final":
        return final_result()
    else:
        raise ValueError("unknown action")

if __name__ == "__main__":
    raise SystemExit(main())
