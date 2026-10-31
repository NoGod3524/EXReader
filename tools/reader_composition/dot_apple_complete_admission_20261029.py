"""Exact c44-based tap-decision measurement admission; Actions only."""
import os, subprocess
from pathlib import Path
BASE="c44a9cf211fffa4ed6f2720ffa49a186c3b4d196"
BRANCHES={"codex/dot-apple-tap-decision-measure-20261031","codex/dot-apple-tap-decision-full-20261031"}
FEATURES="tests/reader_team24_apple/ui/FeaturesUITests.swift"
FONT="tests/reader_apple_font/ui/FontReaderUITests.swift"
FULL=".github/workflows/dot-apple-complete-20261029.yml"
FOCUS=".github/workflows/dot-apple-query-focused-20261030.yml"
SELF="tools/reader_composition/dot_apple_complete_admission_20261029.py"
DOC="docs/reader-total-progress/dot-apple-query-observation-20261030.md"
OLD_FEATURES_BLOB="fa974c4079e3a4d41322160249619bfb5b66d299"
NEW_FEATURES_BLOB="7b1b9d6b3d8093cf34744f3776a5f3b7ce3a1738"
CLOCK="ProcessInfo.processInfo.systemUptime"
def replace_once(text,old,new):
 assert text.count(old)==1,old
 return text.replace(old,new,1)
# Measurement only: clock reads and prints on iOS; no new accessibility query,
# no change to tap/drag count or order, original short-circuit order retained.
FEATURE_REPLACEMENTS=[
("    private func tap(_ id: String) {\n#if os(iOS)\n        let scroll = app.scrollViews.matching(identifier: \"features.scroll\").firstMatch\n",
 "#if os(iOS)\n    private var tapCallSeq = 0\n    private func decision(_ message: String) { print(\"EXR-DECISION \\(message)\") }\n#endif\n    private func tap(_ id: String) {\n#if os(iOS)\n        tapCallSeq += 1\n        let callID = tapCallSeq\n        var querySeq = 0\n        let callStart = "+CLOCK+"\n        let scroll = app.scrollViews.matching(identifier: \"features.scroll\").firstMatch\n"),
("            guard let snapshot = try? target.snapshot() else { return false }\n            targetFrame = snapshot.frame\n#if os(macOS)\n",
 "#if os(iOS)\n            querySeq += 1\n            let snapshotStart = "+CLOCK+"\n#endif\n            guard let snapshot = try? target.snapshot() else {\n#if os(iOS)\n                decision(\"tap call=\\(callID) id=\\(id) query=\\(querySeq) t=\\("+CLOCK+" - callStart) snapshot=nil\")\n#endif\n                return false\n            }\n#if os(iOS)\n            let snapshotSeconds = "+CLOCK+" - snapshotStart\n#endif\n            targetFrame = snapshot.frame\n#if os(macOS)\n"),
("            guard !visible.isNull, visible.width >= 12, visible.height >= 12,\n                  snapshot.isEnabled, target.isHittable else { return false }\n",
 "            let sizeOK = !visible.isNull && visible.width >= 12 && visible.height >= 12\n            var hittable: Bool?\n            var hittableSeconds: Double?\n            if sizeOK && snapshot.isEnabled {\n                let hittableStart = "+CLOCK+"\n                hittable = target.isHittable\n                hittableSeconds = "+CLOCK+" - hittableStart\n            }\n            decision(\"tap call=\\(callID) id=\\(id) query=\\(querySeq) t=\\("+CLOCK+" - callStart) viewport=\\(String(describing: viewport)) frame=\\(snapshot.frame) snapshotSeconds=\\(snapshotSeconds) enabled=\\(snapshot.isEnabled) visible=\\(visible) hittable=\\(String(describing: hittable)) hittableSeconds=\\(String(describing: hittableSeconds))\")\n            guard hittable == true else { return false }\n"),
("                if let previousAbove, previousAbove != above { controlledCorrection = true }\n",
 "                let priorAbove = previousAbove\n                if let previousAbove, previousAbove != above { controlledCorrection = true }\n"),
("                // A distant section needs a real native flick rather than\n",
 "                let startFraction = above ? (distant ? 0.1 : 0.2) : (distant ? 0.9 : 0.8)\n                let startY = viewport.minY + viewport.height * startFraction\n                decision(\"scroll call=\\(callID) id=\\(id) query=\\(querySeq) t=\\("+CLOCK+" - callStart) above=\\(above) previousAbove=\\(String(describing: priorAbove)) controlledCorrection=\\(controlledCorrection) distant=\\(distant) distance=\\(distance) startX=\\(viewport.midX) startY=\\(startY) endY=\\(startY + (above ? distance : -distance)) velocity=\\(distant ? \"1600\" : \"slow\") hold=\\(distant ? 0 : 0.05)\")\n                // A distant section needs a real native flick rather than\n"),
("        XCTAssertTrue(ready, \"Unavailable \\(id) \\(app.debugDescription)\")\n",
 "#if os(iOS)\n        decision(\"tap-final call=\\(callID) id=\\(id) ready=\\(ready) queries=\\(querySeq) totalSeconds=\\("+CLOCK+" - callStart) targetFrame=\\(targetFrame)\")\n#endif\n        XCTAssertTrue(ready, \"Unavailable \\(id) \\(app.debugDescription)\")\n"),
]
def features_expected(base):
 for old,new in FEATURE_REPLACEMENTS:base=replace_once(base,old,new)
 return base
FOCUS_REPLACEMENTS=[
("branches: [codex/dot-apple-observe-focused-20261031]","branches: [codex/dot-apple-tap-decision-measure-20261031]"),
(OLD_FEATURES_BLOB,NEW_FEATURES_BLOB),
("for label in ('Test Case',","for label in ('EXR-DECISION','Test Case',"),
("                          if 'snapshot-tap-frame' in line:row['frame_numbers']","                          if 'EXR-DECISION' in line:row['decision']=line.split('EXR-DECISION',1)[1].strip()[:600]\n                          if 'snapshot-tap-frame' in line:row['frame_numbers']"),
]
FULL_REPLACEMENTS=[
("branches: [codex/dot-apple-observe-full-20261031]","branches: [codex/dot-apple-tap-decision-full-20261031]"),
(OLD_FEATURES_BLOB,NEW_FEATURES_BLOB),
]
def apply(text,pairs):
 for old,new in pairs:text=replace_once(text,old,new)
 return text
def git(*args):return subprocess.check_output(["git",*args],text=True).strip()
def source(path):return subprocess.check_output(["git","show",BASE+":"+path]).decode()
if __name__=="__main__":
 assert os.environ.get("GITHUB_ACTIONS")=="true"
 assert git("rev-parse","HEAD")==os.environ["GITHUB_SHA"]
 assert os.environ["GITHUB_REF_NAME"] in BRANCHES
 subprocess.run(["git","merge-base","--is-ancestor",BASE,"HEAD"],check=True)
 assert set(git("diff","--name-only",BASE,"HEAD").splitlines())=={FEATURES,FULL,FOCUS,SELF,DOC}
 assert git("rev-parse",BASE+":"+FEATURES)==OLD_FEATURES_BLOB
 actual=Path(FEATURES).read_text()
 assert actual==features_expected(source(FEATURES))
 assert git("rev-parse","HEAD:"+FEATURES)==NEW_FEATURES_BLOB
 marker="    func testBorrowedFontRollbackOriginalExportAndReadOnlySnapshot()"
 base_features=source(FEATURES)
 assert actual[actual.index(marker):]==base_features[base_features.index(marker):]
 assert actual.count("addingTimeInterval(90)")==1 and actual.count("for _ in 0..<24")==1
 assert git("rev-parse","HEAD:"+FONT)=="4fa83609db34c48456be9a393d3d7745560a4cbb"
 assert git("rev-parse","HEAD:tests/apple_features_repair_20261029/focused_runner.py")=="8e95f34dd0375fd437a45ecc9d2efcf6d0bf2682"
 assert git("rev-parse","HEAD:tools/check_apple_product.py")=="ed7f62597e01d4e045f679369805d27abc20b7bc"
 assert Path(FOCUS).read_text()==apply(source(FOCUS),FOCUS_REPLACEMENTS)
 assert Path(FULL).read_text()==apply(source(FULL),FULL_REPLACEMENTS)
 doc=Path(DOC).read_text();assert doc.startswith(source(DOC)) and "tap-decision measurement" in doc[len(source(DOC)):]
 print("Exact c44 tap-decision measurement: iOS clock reads and prints only; no added accessibility query, tap/drag count/order, body, setup/teardown, 90s/24/240/360, SDK, Font, runner or checker change.",flush=True)
