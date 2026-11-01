"""F07 Windows actual-build evidence collection. GitHub Actions only."""
import hashlib
import json
import ntpath
import os
from pathlib import Path
import re
import runpy
import shutil
import subprocess
import sys
import traceback

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
LOCK = json.loads((HERE / "contract.json").read_text(encoding="utf-8"))
OUT = ROOT / "build/f07-windows-provider"
RECORDS = {}
COMMANDS = []
def need(ok, reason):
    if not ok:
        raise RuntimeError(reason)
def digest(data):
    return hashlib.sha256(data).hexdigest()
def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()
def copy(label, source):
    need(not source.is_symlink(), "source_symlink:" + label)
    source = source.resolve(strict=True)
    need(source.is_relative_to(ROOT.resolve()) and source.is_file(), "nonregular_or_external_source:" + label)
    data = source.read_bytes()
    target = OUT / label
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    RECORDS[label] = {"actual_path": str(source), "bytes": len(data), "sha256": digest(data)}
    return RECORDS[label]
def execute(argv, name, timeout=1800, cwd=ROOT):
    argv = list(map(str, argv))
    need(re.fullmatch(r"[a-zA-Z0-9_.-]+", name) is not None, "command_name")
    log = OUT / "logs" / (name + ".log")
    log.parent.mkdir(parents=True, exist_ok=True)
    record = {"name": name, "argv": argv, "cwd": str(cwd.resolve()),
              "environment_delta": {"VERBOSE": "1"}, "timeout_seconds": timeout,
              "returncode": None, "status": "running", "output": str(log.relative_to(OUT))}
    COMMANDS.append(record)
    write_json(OUT / "commands.json", COMMANDS)
    env = dict(os.environ, VERBOSE="1")
    print("F07_COMMAND " + json.dumps(record), flush=True)
    try:
        with log.open("wb") as output:
            done = subprocess.run(argv, cwd=cwd, env=env, stdout=output,
                                  stderr=subprocess.STDOUT, timeout=timeout)
        record.update(returncode=done.returncode, status="completed")
    except subprocess.TimeoutExpired:
        record.update(status="timed_out")
        raise
    finally:
        write_json(OUT / "commands.json", COMMANDS)
        if log.exists():
            print(log.read_text(encoding="utf-8", errors="replace"), flush=True)
    need(done.returncode == 0, name + "_failed")
def admission():
    need(os.environ.get("GITHUB_ACTIONS") == "true" and sys.platform == "win32",
         "windows_actions_only")
    need(os.environ.get("GITHUB_RUN_ATTEMPT") == "1", "one_attempt_only")
    need(os.environ.get("GITHUB_REF") == "refs/heads/" + LOCK["branch"], "exclusive_branch")
    source = git("rev-parse", "HEAD")
    need(source == os.environ["GITHUB_SHA"], "source_identity")
    need(LOCK["trigger"] in git("show", "-s", "--format=%B", "HEAD"), "explicit_trigger")
    changed = set(git("diff", "--name-only", LOCK["base"], source).splitlines())
    need(changed == set(LOCK["paths"]), "exclusive_four_file_scope")
    for path in LOCK["paths"]:
        result = subprocess.run(["git", "cat-file", "-e", LOCK["base"] + ":" + path],
                                cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        need(result.returncode != 0, "new_paths_only:" + path)
    guard = {}
    for path in ("src", "include", "cmake", "CMakeLists.txt", "tests/fixtures"):
        actual = git("rev-parse", source + ":" + path)
        frozen = git("rev-parse", LOCK["sdk_freeze"] + ":" + path)
        guard[path] = {"actual": actual, "frozen": frozen}
        need(actual == frozen, "sdk_object_changed:" + path)
    need(git("hash-object", LOCK["recipe"]) == LOCK["recipe_blob"], "original_recipe_changed")
    write_json(OUT / "admission.json", {"source": source, "base": LOCK["base"],
               "sdk_freeze": LOCK["sdk_freeze"], "sdk_guard": guard, "paths": sorted(changed),
               "recipe": LOCK["recipe"], "recipe_blob": LOCK["recipe_blob"]})
    return source
def actual_build():
    sys.path.insert(0, str(ROOT / "tests/reader_windows_raw3"))
    import host_build as H
    def instrumented_run(argv, name, timeout=1800):
        argv = list(map(str, argv))
        if name == "host-configure":
            argv.append("-DCMAKE_EXE_LINKER_FLAGS=/VERBOSE:LIB")
        if name == "host-build":
            argv.extend(["--", "-d", "keeprsp"])
        execute(argv, name, timeout)
        # Preserve the original helper's normal log location as well.
        original = H.OUT / "logs" / (name + ".log")
        original.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(OUT / "logs" / (name + ".log"), original)
    H.run = instrumented_run
    prefix = (ROOT / "build/f07-public-hash/prefix").resolve()
    previous = os.environ.get("EXREADER_ORIGINAL_HASH_PREFIX")
    need(previous in (None, "", prefix.as_posix()), "foreign_hash_prefix")
    execute(["cmake", "-S", ROOT / "extras/opds", "-B", ROOT / "build/f07-public-hash/build",
             "-G", "Ninja", "-DCMAKE_BUILD_TYPE=Release", "-DEXREADER_OPDS_HASH_ONLY=ON",
             "-DCMAKE_POSITION_INDEPENDENT_CODE=ON", "-DCMAKE_INSTALL_PREFIX=" + prefix.as_posix()],
            "hash-configure")
    execute(["cmake", "--build", ROOT / "build/f07-public-hash/build", "--parallel", "4"], "hash-build")
    execute(["cmake", "--install", ROOT / "build/f07-public-hash/build"], "hash-install")
    need((prefix / "lib/cmake/EXReaderOPDSHash/EXReaderOPDSHashConfig.cmake").is_file(),
         "public_hash_install_missing")
    os.environ["EXREADER_ORIGINAL_HASH_PREFIX"] = prefix.as_posix()
    runpy.run_path(str(ROOT / LOCK["recipe"]), run_name="__f07_original_recipe__")
    return prefix
def linkage_observation(log, sdk, product):
    # Observe all original rows. Do not turn collection into provider certification.
    searches = list(re.finditer(r"(?mi)^\s*Searching\s+(.+?\.lib):\s*$", log))
    blocks, sqlite, findings = [], [], []
    targets = {"sdk": str(sdk.resolve(strict=True)), "product": str(product.resolve(strict=True))}
    canon = lambda p: ntpath.normcase(ntpath.normpath(p))
    for index, match in enumerate(searches):
        end = searches[index + 1].start() if index + 1 < len(searches) else len(log)
        full = match.group(1).strip()
        text = log[match.start():end]
        rows = []
        for loaded in re.finditer(r"(?mi)^\s*Loaded\s+(.+?\.lib)\(\s*([^)]+)\s*\)\s*$", text):
            archive, member = loaded.group(1).strip(), loaded.group(2).strip()
            row = {"searching_path": full, "loaded_archive_text": archive, "member": member,
                   "line": log.count("\n", 0, match.start() + loaded.start()) + 1}
            rows.append(row)
            if member.lower() in ("sqlite3.c.obj", "sqlite3.c.o"):
                observation = dict(row, identity_verified=False)
                roles = [key for key, value in targets.items() if canon(full) == canon(value)]
                checks = {"searching_absolute": ntpath.isabs(full),
                          "basename_match": canon(ntpath.basename(archive)) == canon(ntpath.basename(full)),
                          "loaded_absolute_match": not ntpath.isabs(archive) or canon(archive) == canon(full),
                          "known_installed_path": len(roles) == 1}
                observation["checks"] = checks
                if all(checks.values()):
                    # Only follow the two known build outputs, never an arbitrary log path.
                    path = Path(targets[roles[0]])
                    need(not path.is_symlink(), "loaded_archive_symlink")
                    path = path.resolve(strict=True)
                    need(path.is_relative_to(ROOT.resolve()) and path.is_file(), "loaded_archive_external")
                    body = path.read_bytes()
                    observation.update(role=roles[0], actual_path=str(path), bytes=len(body),
                                       sha256=digest(body), identity_verified=True)
                else:
                    findings.append({"line": row["line"], "kind": "unverified_loaded_identity", "checks": checks})
                sqlite.append(observation)
        blocks.append({"start_line": log.count("\n", 0, match.start()) + 1,
                       "searching": full, "text": text, "loaded": rows})
    identities = sorted({(row["role"], row["member"].lower()) for row in sqlite if row["identity_verified"]})
    classification = ("missing_sqlite_loaded_rows" if not sqlite else
                      "unverified_loaded_identity" if any(not row["identity_verified"] for row in sqlite) else
                      "multiple_observed_provider_members" if len(identities) > 1 else
                      "single_observed_provider_member")
    observation = {"classification": classification, "findings": findings,
                   "searching_blocks": blocks,
                   "all_loaded_lines": [{"line": i, "text": line}
                                       for i, line in enumerate(log.splitlines(), 1)
                                       if re.match(r"\s*Loaded\s+", line)],
                   "sqlite_loaded": sqlite, "provider_certified": False}
    write_json(OUT / "linker-contexts.json", observation)
    return observation
def collect():
    build = ROOT / "build/windows-sdk342"
    sdk = build / "sdk/lib/exreader/exr_vendor_exr_sqlite.lib"
    candidates = sorted((build / "sdk-build").rglob("exr_sqlite.lib"))
    need(len(candidates) == 1, "sdk_build_archive_not_unique")
    sdk_build = candidates[0]
    product = build / "product/lib/reader_catalog_sqlite.lib"
    a = copy("archives/sdk-build.lib", sdk_build)
    b = copy("archives/sdk-installed.lib", sdk)
    c = copy("archives/product-installed.lib", product)
    sdk_identical = sdk_build.read_bytes() == sdk.read_bytes()
    copy("host/EXReaderWave3.exe", build / "host/EXReaderWave3.exe")
    copy("host/EXReader.exe", build / "package/EXReader/EXReader.exe")
    package_identical = ((build / "host/EXReaderWave3.exe").read_bytes() ==
                         (build / "package/EXReader/EXReader.exe").read_bytes())
    copy("host/windows-host.map", build / "host/windows-host.map")
    for relative in ("CMakeCache.txt", "build.ninja", "CMakeFiles/rules.ninja"):
        copy("host-build/" + relative, build / "host" / relative)
    responses = sorted((build / "host").rglob("*.rsp"))
    rules = (build / "host/CMakeFiles/rules.ninja").read_text(encoding="utf-8", errors="replace")
    response_status = {"declared_in_rules": "rspfile" in rules, "present": len(responses),
                       "files": [str(p.relative_to(build / "host")) for p in responses]}
    for path in responses:
        copy("host-build/" + path.relative_to(build / "host").as_posix(), path)
    for path in sorted((build / "package").rglob("*.json")):
        copy("package-metadata/" + path.relative_to(build / "package").as_posix(), path)
    copy("sdk/EXReaderDependencies.cmake", build / "sdk/lib/cmake/EXReader/EXReaderDependencies.cmake")
    execute(["cmake", "--version"], "cmake-version", 120)
    execute(["ninja", "--version"], "ninja-version", 120)
    execute(["dumpbin", "/IMPORTS", build / "package/EXReader/EXReader.exe"], "host-imports", 120)
    for role, archive in (("sdk-build", sdk_build), ("sdk-installed", sdk), ("product-installed", product)):
        execute(["dumpbin", "/SYMBOLS", archive], role + "-symbols", 120)
        execute(["dumpbin", "/LINKERMEMBER:1", archive], role + "-members", 120)
    imports = (OUT / "logs/host-imports.log").read_text(encoding="utf-8", errors="replace")
    raw_log = (OUT / "logs/host-build.log").read_bytes()
    try:
        log = raw_log.decode("utf-8", errors="strict")
        decoding = "utf8_strict"
    except UnicodeDecodeError:
        log = raw_log.decode("utf-8", errors="replace")
        decoding = "utf8_replacement_for_observation_raw_bytes_retained"
    configured = [entry for entry in COMMANDS if entry["name"] == "host-configure"]
    need(len(configured) == 1 and "-DCMAKE_EXE_LINKER_FLAGS=/VERBOSE:LIB" in configured[0]["argv"],
         "verbose_configure_command_missing")
    observed = linkage_observation(log, sdk, product)
    return {"sdk_build": a, "sdk_installed": b, "product_installed": c,
            "sdk_build_install_identical": sdk_identical, "package_host_identical": package_identical,
            "system_sqlite_import_observed": bool(re.search(r"(?i)(?:lib)?sqlite3[^\s/]*\.dll", imports)),
            "linker_observation": observed, "log_decoding": decoding,
            "raw_log_sha256": digest(raw_log), "response_status": response_status}
def seal(summary):
    write_json(OUT / "summary.json", summary)
    inventory = {}
    for path in sorted(OUT.rglob("*")):
        if path.is_file() and path != OUT / "manifest.json":
            need(not path.is_symlink(), "evidence_symlink")
            relative = path.relative_to(OUT).as_posix()
            data = path.read_bytes()
            inventory[relative] = dict(RECORDS.get(relative, {}), bytes=len(data), sha256=digest(data))
    write_json(OUT / "manifest.json", {"schema": 1, "source": os.environ.get("GITHUB_SHA"),
               "run": os.environ.get("GITHUB_RUN_ID"), "attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
               "sdk_freeze": LOCK["sdk_freeze"], "files": inventory,
               "manifest_excluded_from_own_inventory": True, "diagnostic_only": True,
               "F07_accepted": False, "formal_count_changed": False})
def main():
    need(os.environ.get("GITHUB_ACTIONS") == "true" and sys.platform == "win32",
         "windows_actions_only")
    OUT.mkdir(parents=True, exist_ok=False)
    result = {"diagnostic_completed": False, "errors": [], "diagnostic_only": True,
              "F07_accepted": False, "formal_count_changed": False,
              "host_runtime_provider_observed": False, "old_tests_changed": False,
              "source": os.environ.get("GITHUB_SHA"), "run": os.environ.get("GITHUB_RUN_ID"),
              "attempt": os.environ.get("GITHUB_RUN_ATTEMPT"), "python": sys.version}
    try:
        admission()
        result["public_hash_prefix"] = str(actual_build())
        result["evidence"] = collect()
        result["diagnostic_completed"] = True
    except Exception as error:
        result["errors"].append(type(error).__name__ + ":" + str(error))
        (OUT / "failure.txt").write_text(traceback.format_exc(), encoding="utf-8")
        traceback.print_exc()
    finally:
        seal(result)
        print("F07_WINDOWS_PROVIDER " + json.dumps(result), flush=True)
    if not result["diagnostic_completed"]:
        raise SystemExit(1)
if __name__ == "__main__":
    main()
