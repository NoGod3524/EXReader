"""Actions-only full Apple source admission; no focused guard is reused."""
import os, subprocess
from pathlib import Path
assert os.environ.get("GITHUB_ACTIONS") == "true"
BASE = "a6e2e506f70a86afc56fe7da5db9fa8186caf1f8"
PASSED = "c66b5590e42adcf708365ba4fa315a811e475aaa"
BRANCH = "codex/dot-apple-complete-20261029"
WORKFLOW = ".github/workflows/dot-apple-complete-20261029.yml"
SELF = "tools/reader_composition/dot_apple_complete_admission_20261029.py"
INHERITED = {
 "examples/apple/HostWave3Views.swift", "tests/reader_team24_apple/ui/FeaturesUITests.swift",
 "tests/apple_features_repair_20261029/focused_runner.py", "tests/apple_features_repair_20261029/admission.py",
 "tools/reader_composition/repair_apple_features_admission_20261029.py",
 ".github/workflows/repair-apple-features-20261029.yml",
 "docs/reader-total-progress/repair-apple-features-20261029.md",
}
def git(*args):
 return subprocess.check_output(["git", *args], text=True).strip()
def source(ref, path):
 return subprocess.check_output(["git", "show", ref + ":" + path])
assert git("rev-parse", "HEAD") == os.environ["GITHUB_SHA"]
assert os.environ["GITHUB_REF_NAME"] == BRANCH
subprocess.run(["git", "merge-base", "--is-ancestor", PASSED, "HEAD"], check=True)
subprocess.run(["git", "merge-base", "--is-ancestor", BASE, "HEAD"], check=True)
assert set(git("diff", "--name-only", PASSED, "HEAD").splitlines()) == {WORKFLOW, SELF}
assert set(git("diff", "--name-only", BASE, "HEAD").splitlines()) == INHERITED | {WORKFLOW, SELF}
for path in INHERITED:
 assert source("HEAD", path) == source(PASSED, path), path
for path, blob in {
 "tests/reader_team24_apple/ui/FeaturesUITests.swift":"44b701a3f28d61d91b3588bc0fccc69e5c70e9f1",
 "examples/apple/HostWave3Views.swift":"5573a621e6748e86054952b62a1a5ba561e43e5c",
 "examples/apple/HostViews.swift":"3132f72e98f4d574b5ade0381226e7b7dfeb1f62",
}.items():
 assert git("rev-parse", "HEAD:" + path) == blob, path
path = "tests/reader_team24_apple/ui/FeaturesUITests.swift"
old, new = source(BASE, path), source("HEAD", path)
marker = b"    func testBorrowedFontRollbackOriginalExportAndReadOnlySnapshot()"
assert old[old.index(marker):] == new[new.index(marker):]
assert old[:old.index(b"    private func e(")] == new[:new.index(b"    private var nativeShareObserved")]
assert new.count(b"addingTimeInterval(90)") == 1 and new.count(b"for _ in 0..<24") == 1
original = source(PASSED, ".github/workflows/apple-sdk342-full-handoff-20261029.yml").decode()
expected = original.replace(
 "branches: [codex/apple-sdk342-full-handoff-20261029, codex/apple-opdshash-resume-20261029, codex/public-product-resume-20261029]",
 "branches: [" + BRANCH + "]", 1)
expected = expected.replace("f7a3ddefc25d7a901dc0ef810dc66d850b9cb20f", "44b701a3f28d61d91b3588bc0fccc69e5c70e9f1", 1)
expected = expected.replace("      - name: Original checker and retained runner unchanged",
 "      - name: Exact qualified Apple source and independent full wrapper\n        run: python3 " + SELF + "\n      - name: Original checker and retained runner unchanged", 1)
assert Path(WORKFLOW).read_text() == expected
print("Full source exact 9-path closure: qualified c66 runtime/helpers unchanged; original39 and 12 supplemental run body, checker, owner guard and budgets retained.", flush=True)
