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
    return c

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
    require(git("rev-list", "--parents", "-n", "1", source).split() == [source, REVIEWED_ACCEPTANCE],
            "exact single corrective acceptance commit on preserved R1")
    for parent, child in ((BASE, CANONICAL), (CANONICAL, INTAKE), (INTAKE, REVIEWED_ACCEPTANCE), (REVIEWED_ACCEPTANCE, source)):
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
    require(set(git("diff", "--name-only", REVIEWED_ACCEPTANCE, source).splitlines()) == set(c["approved_delta"]),
            "R2 must modify exactly the five authorized acceptance files")
    for path in c["new_paths"]:
        require(git("cat-file", "-t", source + ":" + path) == "blob", "new path must be a file")
        require((ROOT / path).read_bytes() == blob(source, path), "modified acceptance file: " + path)
    require(all(line.startswith("M\t") for line in git("diff", "--name-status", REVIEWED_ACCEPTANCE, source).splitlines()),
            "R2 only modifies existing acceptance files")
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
    capability = private_copy_contract()
    return {"private_copy_capability": capability, "source_sha": source, "review_base": BASE, "ownership_head": CANONICAL,
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
    # Compare every staged original except the two explicitly reviewed overlay classes.
    old_root = ROOT / "examples/android/app/src/androidTest/java"
    overlay_names = {Path(p).relative_to("examples/android/app/src/androidTest/java").as_posix()
                     for p in c["overlay_sources"].values()}
    for path in old_root.rglob("*"):
        if path.is_file() and path.relative_to(old_root).as_posix() not in overlay_names:
            require((java / path.relative_to(old_root)).read_bytes() == path.read_bytes(),
                    "overlay changed another original test")
    require(len(list(java.rglob("OrganizationTest.java"))) == 1 and
            len(list(java.rglob("OrganizationBootstrapRecoveryTest.java"))) == 1, "unique overlay classes")
    host_test = ROOT / "tests/reader_android_host_import/java/org/exreader/host/HostImportUiTest.java"
    target = java / "org/exreader/host/HostImportUiTest.java"
    require(not target.exists(), "host import runner class collision")
    shutil.copyfile(host_test, target)
    require(len(list(java.rglob("HostImportUiTest.java"))) == 1 and target.read_bytes() == host_test.read_bytes(),
            "one unchanged existing host import runner")
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
        required = {"admission", "prepare", "hash_owner", "build", "emulator", "catalog", "preflight", "gate48",
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
        for name, count in (("gate48", 48), ("gate20", 20), ("shelf_gate", 19), ("owner_gate", 19)):
            value = json.loads((ROOT / records[name]).read_text())
            require(len(value["checks"]) == count, "original gate count: " + name)
        hash_owner = hash_owner_proof()
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


def main():
    require(len(sys.argv) > 1, "explicit action required")
    action = sys.argv[1]
    if action == "admit":
        print(json.dumps(verify_source()))
    elif action == "prepare":
        prepare()
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
