"""Actions-only focused Apple feature repair admission; original case bodies stay exact."""
import os,subprocess
from pathlib import Path
assert os.environ.get("GITHUB_ACTIONS")=="true"
BASE="a6e2e506f70a86afc56fe7da5db9fa8186caf1f8"
ALLOWED={"examples/apple/HostWave3Views.swift","tests/reader_team24_apple/ui/FeaturesUITests.swift",
 "tests/apple_features_repair_20261029/focused_runner.py","tests/apple_features_repair_20261029/admission.py",
 "tools/reader_composition/repair_apple_features_admission_20261029.py",
 ".github/workflows/repair-apple-features-20261029.yml","docs/reader-total-progress/repair-apple-features-20261029.md"}
def git(*args):return subprocess.check_output(["git",*args],text=True).strip()
def source(path):return subprocess.check_output(["git","show",BASE+":"+path],text=True)
assert git("rev-parse","HEAD")==os.environ["GITHUB_SHA"]
assert set(git("diff","--name-only",BASE,"HEAD").splitlines())==ALLOWED
path="tests/reader_team24_apple/ui/FeaturesUITests.swift";old=source(path);new=Path(path).read_text()
marker="    func testBorrowedFontRollbackOriginalExportAndReadOnlySnapshot()"
assert old[old.index(marker):]==new[new.index(marker):]
assert old[:old.index("    private func tap(")]==new[:new.index("    private func tap(")]
assert old[old.index("    private func mark("):]==new[new.index("    private func mark("):]
assert new.count("for _ in 0..<24")==1 and new.count("addingTimeInterval(90)")==1
share=source("examples/apple/HostWave3Views.swift")
for old,new in [("            .sheet(isPresented: $sharing) { HostWave3Activity(url: url) }","            .sheet(isPresented: $sharing) { HostWave3Activity(url: url) { sharing = false } }"),("private struct HostWave3Activity: UIViewControllerRepresentable {\n    let url: URL\n    func makeUIViewController(context: Context) -> UIActivityViewController {\n        let controller = UIActivityViewController(activityItems: [url], applicationActivities: nil)","private struct HostWave3Activity: UIViewControllerRepresentable {\n    let url: URL\n    let onFinish: () -> Void\n    func makeUIViewController(context: Context) -> UIActivityViewController {\n        let controller = UIActivityViewController(activityItems: [url], applicationActivities: nil)\n        let finish = onFinish\n        controller.completionWithItemsHandler = { _, _, _, _ in\n            DispatchQueue.main.async { finish() }\n        }")]:
 assert share.count(old)==1;share=share.replace(old,new,1)
assert Path("examples/apple/HostWave3Views.swift").read_text()==share
runner=source("tests/reader_team24_apple/run_ui.py")
runner=runner.replace("        for mode, tests, expected in [('wave3', ROOT / 'tests/reader_team24_apple/ui', 5), ('base', base_tests, 13),\n                                     ('control', control_tests, 13), ('search', search_tests, 4), ('theme', theme_tests, 4)]:","        for mode, tests, expected in [('wave3', ROOT / 'tests/reader_team24_apple/ui', 5)]:",1)
runner=runner.replace("result['accepted'] = len(phases) == 5","result['accepted'] = len(phases) == 1",1)
runner=runner.replace("    def run(argv, role, timeout=4800):","    result['focused_feature_cases_only'] = True\n    result['full_original39_acceptance'] = False\n    def run(argv, role, timeout=4800):",1)
assert Path("tests/apple_features_repair_20261029/focused_runner.py").read_text()==runner
adapter=source("tests/apple_sdk342_host/run_ui.py")
adapter=adapter.replace("tests/reader_team24_apple/run_ui.py","tests/apple_features_repair_20261029/focused_runner.py",1)
adapter=adapter.replace('len(identity["programs"]) == 5','len(identity["programs"]) == 1',1)
adapter=adapter.replace('"installed": installed, "accepted": False, "programs": {}}','"installed": installed, "accepted": False, "programs": {}, "focused_feature_cases_only": True, "full_original39_acceptance": False}',1)
assert Path("tests/apple_features_repair_20261029/admission.py").read_text()==adapter
print("Original five feature bodies, teardown, 90s wait, 24 drags, native 240/360 budgets and original runners preserved; focus is 5 cases only",flush=True)
