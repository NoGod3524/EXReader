"""Compare the actual baseline/candidate catalog repair on one Actions runner."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

ROOT = Path(__file__).resolve().parents[2]
BASE = "19ac07d8b241d394f07e877ca5cc957a03714642"
OUT = ROOT / "build/f08-catalog-wal"
EVIDENCE = OUT / "evidence"

def run(name, args, env=None):
    path = EVIDENCE / (name + ".log")
    with path.open("wb") as stream:
        process = subprocess.run([str(v) for v in args], cwd=ROOT, env=env, stdout=stream, stderr=subprocess.STDOUT)
    if process.returncode:
        print(path.read_text(errors="replace")[-14000:], flush=True)
        raise RuntimeError(name + " failed: " + str(process.returncode))
    return path.read_text()

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    assert os.environ.get("GITHUB_ACTIONS") == "true"
    production = ["apps/reader/desktop/catalog_sdk.c", "apps/reader/store/native/catalog.c",
                  "apps/reader/store/native/catalog.h"]
    owned = production + ["tests/reader_startup_profile/CMakeLists.txt", "tests/reader_startup_profile/profile.c",
                          "tests/reader_startup_profile/wal_crash.c", "tests/reader_f08_catalog_wal_20261031/run.py",
                          "tests/reader_f08_catalog_wal_20261031/filesystem.c",
                          ".github/workflows/f08-linux-catalog-wal-20261031.yml"]
    changed = subprocess.check_output(["git", "diff", "--name-only", BASE, "HEAD"], cwd=ROOT, text=True).splitlines()
    assert set(changed) == set(owned)
    subprocess.run(["git", "diff", "--exit-code", BASE, "HEAD", "--",
                    "src", "include", "cmake", "CMakeLists.txt", "examples", "tools",
                    "tests/reader_perf_gtk", "tests/reader_product_performance_handoff"], cwd=ROOT, check=True)
    EVIDENCE.mkdir(parents=True, exist_ok=False)
    run("filesystem", ["stat", "-f", "-c", "%T %t", OUT])
    baseline = OUT / "baseline"
    baseline.mkdir()
    with (OUT / "baseline.tar").open("wb") as stream:
        subprocess.run(["git", "archive", BASE, "apps/reader/store", "apps/reader/desktop",
                        "apps/reader/original-import", "licenses"], cwd=ROOT, stdout=stream, check=True)
    run("baseline-source", ["tar", "-xf", OUT / "baseline.tar", "-C", baseline])
    hashed = OUT / "hash-stage"
    run("hash-configure", ["cmake", "-S", "extras/opds", "-B", OUT / "hash-build", "-G", "Ninja",
                          "-DCMAKE_BUILD_TYPE=Release", "-DEXREADER_OPDS_HASH_ONLY=ON",
                          "-DCMAKE_INSTALL_PREFIX=" + str(hashed)])
    run("hash-build", ["cmake", "--build", OUT / "hash-build", "--parallel", "4"])
    run("hash-install", ["cmake", "--install", OUT / "hash-build"])
    os.environ["EXREADER_ORIGINAL_HASH_PREFIX"] = str(hashed.resolve())
    run("sdk-configure", ["cmake", "--preset", "reading-library"])
    run("sdk-build", ["cmake", "--build", "--preset", "reading-library", "--parallel", "4"])
    run("sdk-install", ["cmake", "--install", "build/reading-library"])
    sdk = ROOT / "build/reading-library/stage"
    binaries = {}
    for name, source in (("baseline", baseline), ("candidate", ROOT)):
        binary = OUT / (name + "-build")
        run(name + "-configure", ["cmake", "-S", "tests/reader_startup_profile", "-B", binary, "-G", "Ninja",
                                 "-DCMAKE_BUILD_TYPE=Release", "-DEXR_SDK=" + str(sdk), "-DEXR_SDK_VERSION=3.42.0",
                                 "-DREADER_SOURCE_ROOT=" + str(source), "-DREADER_ORIGINAL_HASH_PREFIX=" + str(hashed)])
        run(name + "-build", ["cmake", "--build", binary, "--parallel", "4"])
        binaries[name] = binary
    template = OUT / "sdk-template.sqlite"
    run("seed", [binaries["candidate"] / "seed_shelf", template])
    rows = []
    for repeat in range(3):
        order = ("baseline", "candidate") if repeat % 2 == 0 else ("candidate", "baseline")
        for name in order:
            folder = OUT / (name + "-" + str(repeat))
            folder.mkdir()
            shutil.copyfile(template, folder / "sdk.sqlite")
            for phase in ("first", "repeat"):
                if phase == "first":
                    run(name + "-drop-cache-" + str(repeat), ["sudo", "sh", "-c", "sync; echo 3 > /proc/sys/vm/drop_caches"])
                env = dict(os.environ, EXR_EXPECT_MODE="delete" if name == "baseline" else "wal")
                text = run(name + "-" + str(repeat) + "-" + phase,
                           [binaries[name] / "startup_profile", folder / "sdk.sqlite", folder / "product-main.sqlite", phase], env)
                result = json.loads(text.strip().splitlines()[-1])
                row = {"variant": name, "repetition": repeat, "phase": phase, **result}
                rows.append(row)
                print("F08_CATALOG_PROFILE", json.dumps(row), flush=True)
    binary = binaries["candidate"]
    for name, exe, args in (
        ("sdk-contracts", "reader-desktop-catalog-check", [ROOT / "tests/fixtures"]),
        ("native-contracts", "reader-native-catalog-check", [ROOT / "apps/reader/store/001_catalog.sql"]),
    ):
        folder = EVIDENCE / name
        folder.mkdir()
        run(name, [binary / exe, folder, *args])
    fakefs = OUT / "filesystem.so"
    run("filesystem-control-build", ["cc", "-shared", "-fPIC", "-Wall", "-Wextra", "-Werror",
                                     "tests/reader_f08_catalog_wal_20261031/filesystem.c", "-ldl", "-o", fakefs])
    for kind in ("nfs", "unknown", "error", "persist"):
        folder = OUT / ("policy-" + kind)
        folder.mkdir()
        shutil.copyfile(template, folder / "sdk.sqlite")
        env = dict(os.environ, EXR_EXPECT_MODE="persist" if kind == "persist" else "delete")
        if kind == "persist":
            env["EXR_PROFILE_PERSIST"] = "1"
        else:
            env.update(LD_PRELOAD=str(fakefs), F08_FILESYSTEM=kind)
        run("policy-" + kind, [binary / "startup_profile", folder / "sdk.sqlite", folder / "product-main.sqlite", "first"], env)
    crash = OUT / "crash"
    crash.mkdir()
    log = EVIDENCE / "crash-seed.log"
    with log.open("wb") as stream:
        process = subprocess.Popen([str(binary / "reader-wal-crash-check"), str(crash), "seed"],
                                   stdout=stream, stderr=subprocess.STDOUT, cwd=ROOT)
        try:
            deadline = time.monotonic() + 30
            while "READY_TO_KILL_COMMITTED_WAL" not in log.read_text():
                if process.poll() is not None or time.monotonic() >= deadline:
                    raise RuntimeError("committed WAL witness missing: " + log.read_text())
                time.sleep(.05)
        finally:
            process.kill()
            process.wait(timeout=10)
    assert process.returncode == -9
    run("crash-recovery", [binary / "reader-wal-crash-check", crash, "recover"])
    report = {"source_sha": os.environ["GITHUB_SHA"], "run_id": os.environ["GITHUB_RUN_ID"],
              "attempt": os.environ["GITHUB_RUN_ATTEMPT"], "baseline_source": BASE, "profiles": rows,
              "regression_and_policy_checks_passed": True, "committed_wal_recovered_after_sigkill": True,
              "production_files": {p: sha(ROOT / p) for p in production},
              "profile_programs": {name: sha(path / "startup_profile") for name, path in binaries.items()},
              "scope": "Product catalog repair only; UI budget acceptance requires the full original product cohorts.",
              "f08_accepted": False}
    (EVIDENCE / "result.json").write_text(json.dumps(report, indent=2) + "\n")
    print("F08_CATALOG_WAL", json.dumps(report), flush=True)

if __name__ == "__main__":
    main()
