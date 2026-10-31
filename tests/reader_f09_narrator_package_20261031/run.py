# SPDX-License-Identifier: MIT
"""Actions-only clean Windows candidate package for a real Narrator check.

Builds the candidate product source (examples/reader.c with the a835 Escape routing, provider
unchanged) without the test-only diagnostic overlay or EXR_F09_DIAGNOSTICS, packages it with the
existing packager, keeps its preserved 26-check self-test, and records per-file SHA256 so the
downloaded copy can be matched. Not F09 acceptance; the Narrator check itself is manual.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
ROOT = Path(__file__).resolve().parents[2]
PARENT = "6c5f68e62c0ea95d8e3b4818ad4fadf7424b9e5d"
ROUTING = "a8352f3623078e4d64b222c5af4dc7a2f2bfa379"
OUT = ROOT / "build/f09-narrator-package"
NEW_PATHS = {"tests/reader_f09_narrator_package_20261031/run.py",
             ".github/workflows/dot-f09-narrator-package-20261031.yml",
             "docs/reader-total-progress/DOT_F09_NARRATOR_PACKAGE_20261031.md"}
def git(*argv):
    return subprocess.check_output(["git", *argv], cwd=ROOT, text=True).strip()
def run(*argv, cwd=ROOT):
    print("+", *map(str, argv), flush=True)
    subprocess.run(list(map(str, argv)), cwd=cwd, check=True)
def guard():
    assert os.environ.get("GITHUB_ACTIONS") == "true", "Actions only"
    actual = git("rev-parse", "HEAD")
    assert actual == os.environ["GITHUB_SHA"]
    delta = set(git("diff", "--name-only", PARENT, "HEAD").splitlines())
    assert delta == NEW_PATHS, delta
    # Product files must be exactly the pushed a835 routing candidate; the overlay file is not used.
    for frozen in ("examples/reader.c", "apps/reader/desktop/windows_accessibility.inc"):
        assert git("hash-object", "--path=" + frozen, frozen) == git("rev-parse", ROUTING + ":" + frozen), frozen
    return actual
def main():
    source = guard()
    sdk = OUT / "sdk"
    run("cmake", "--preset", "reading-library", "-B", OUT / "sdk-build", "-DCMAKE_INSTALL_PREFIX=" + str(sdk))
    run("cmake", "--build", OUT / "sdk-build", "--parallel", "4")
    run("cmake", "--install", OUT / "sdk-build")
    build = OUT / "candidate-build"
    run("cmake", "-S", ROOT / "apps/reader/desktop", "-B", build, "-G", "Ninja",
        "-DCMAKE_BUILD_TYPE=Release", "-DEXR_SDK=" + str(sdk), "-DEXR_SDK_VERSION=3.42.0")
    run("cmake", "--build", build, "--target", "EXReaderProduct", "--parallel", "4")
    package = OUT / "candidate-package"
    run(sys.executable, ROOT / "tools/build_windows_host.py", "--sdk", sdk,
        "--binary", build / "EXReaderProduct.exe", "--output", package, "--static-reading")
    report = json.loads((package / "report.json").read_text())
    assert report["passed"] is True and report["checks"] >= 26, report
    payload = package / "EXReader"
    files = {p.relative_to(payload).as_posix(): dict(bytes=p.stat().st_size,
             sha256=hashlib.sha256(p.read_bytes()).hexdigest())
             for p in sorted(payload.rglob("*")) if p.is_file()}
    manifest = dict(source=source, product_source=ROUTING, parent=PARENT,
        run=os.environ["GITHUB_RUN_ID"], attempt=os.environ["GITHUB_RUN_ATTEMPT"],
        diagnostic_overlay=False, diagnostics_macro=False, selftest_checks=report["checks"], files=files,
        narrator_verified=False, formal_f09_accepted=False)
    (OUT / "package-manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print("F09-PACKAGE", json.dumps(dict(source=source, files=len(files),
        exe_sha256=files["EXReader.exe"]["sha256"], selftest_checks=report["checks"])), flush=True)
if __name__ == "__main__":
    main()
