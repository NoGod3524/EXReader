"""Actions-only full Apple source admission; no focused guard is reused."""
import os, subprocess
from pathlib import Path
assert os.environ.get("GITHUB_ACTIONS") == "true"
BASE = "a6e2e506f70a86afc56fe7da5db9fa8186caf1f8"
PASSED = "c66b5590e42adcf708365ba4fa315a811e475aaa"
BRANCH = "codex/dot-apple-complete-20261029"
WORKFLOW = ".github/workflows/dot-apple-complete-20261029.yml"
SELF = "tools/reader_composition/dot_apple_complete_admission_20261029.py"
FEATURES = "tests/reader_team24_apple/ui/FeaturesUITests.swift"
ORIGINAL = "tests/apple_native_original/ui/OriginalSaveUITests.swift"
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
assert set(git("diff", "--name-only", PASSED, "HEAD").splitlines()) == {WORKFLOW, SELF, FEATURES, ORIGINAL}
assert set(git("diff", "--name-only", BASE, "HEAD").splitlines()) == INHERITED | {WORKFLOW, SELF, ORIGINAL}
for path in INHERITED - {FEATURES}:
 assert source("HEAD", path) == source(PASSED, path), path
for path, blob in {
 "tests/reader_team24_apple/ui/FeaturesUITests.swift":"a46f223bf0a96e52b5a5904f66eb270c74c95c91",
 ORIGINAL:"808c63adf60136f8f14d4893a282fb02ba7697f6",
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

# Exact platform-only repair: retain all c66 iOS helper text and every test body.
qualified = source(PASSED, FEATURES).decode()
mac_before = """            targetFrame = snapshot.frame
            let visible"""
mac_after = """            targetFrame = snapshot.frame
#if os(macOS)
            let inViewport = viewport.map { $0.contains(CGPoint(x: targetFrame.midX, y: targetFrame.midY)) } ?? true
            return inViewport && snapshot.isEnabled && target.isHittable
#else
            let visible"""
assert qualified.count(mac_before) == 1
qualified = qualified.replace(mac_before, mac_after, 1)
close_before = """            targetFrame = visible
            return true
        }"""
close_after = """            targetFrame = visible
            return true
#endif
        }"""
assert qualified.count(close_before) == 1
assert source("HEAD", FEATURES).decode() == qualified.replace(close_before, close_after, 1)
# User-authorized 2026-10-30 04:49:18 UTC exception: one existing 90s wait
# selects a genuinely ready native Files control; every other byte is frozen.
original_before = "        if !newFolder.exists {\n            let overflow = app.buttons[\"OverflowBarButtonItem\"].firstMatch\n            XCTAssertTrue(wait { overflow.exists && overflow.isHittable }, app.debugDescription)\n            overflow.tap()\n        }\n"
original_after = "        if !newFolder.exists {\n            let overflow = app.buttons[\"OverflowBarButtonItem\"].firstMatch\n            XCTAssertTrue(wait {\n                (newFolder.exists && newFolder.isHittable) || (overflow.exists && overflow.isHittable)\n            }, app.debugDescription)\n            if !(newFolder.exists && newFolder.isHittable) { overflow.tap() }\n        }\n"
original_frozen = source("4a68d80fbaa524fc28f899d209d795248627080b", ORIGINAL).decode()
assert original_frozen.count(original_before) == 1
assert source("HEAD", ORIGINAL).decode() == original_frozen.replace(original_before, original_after, 1)

original = source(PASSED, ".github/workflows/apple-sdk342-full-handoff-20261029.yml").decode()
expected = original.replace(
 "branches: [codex/apple-sdk342-full-handoff-20261029, codex/apple-opdshash-resume-20261029, codex/public-product-resume-20261029]",
 "branches: [" + BRANCH + "]", 1)
expected = expected.replace("f7a3ddefc25d7a901dc0ef810dc66d850b9cb20f", "a46f223bf0a96e52b5a5904f66eb270c74c95c91", 1)
expected = expected.replace("      - name: Original checker and retained runner unchanged",
 "      - name: Exact qualified Apple source and independent full wrapper\n        run: python3 " + SELF + "\n      - name: Original checker and retained runner unchanged", 1)
expected = expected.replace("tests/reader_apple_font/ui tests/apple_native_original/ui", "tests/reader_apple_font/ui tests/apple_native_original/ui \u0027:(exclude)tests/apple_native_original/ui/OriginalSaveUITests.swift\u0027", 1)
assert Path(WORKFLOW).read_text() == expected
print("Full source exact 10-path closure: Mac-only geometry correction and explicitly authorized original-export readiness exception; all other original39 and supplemental assertions, runners, checker, owner guard and budgets retained.", flush=True)
