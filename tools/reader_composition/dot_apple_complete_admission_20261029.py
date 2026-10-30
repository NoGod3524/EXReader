"""Exact b2f-based query-helper candidate admission; Actions only."""
import os, subprocess
from pathlib import Path
assert os.environ.get("GITHUB_ACTIONS") == "true"
BASE="b2f4e6e1363d0ee20fcb87a6acef548e0624318a"
BRANCHES={"codex/dot-apple-input-focused-20261030","codex/dot-apple-input-full-20261030"}
FEATURES="tests/reader_team24_apple/ui/FeaturesUITests.swift"
FONT="tests/reader_apple_font/ui/FontReaderUITests.swift"
FULL=".github/workflows/dot-apple-complete-20261029.yml"
FOCUS=".github/workflows/dot-apple-query-focused-20261030.yml"
SELF="tools/reader_composition/dot_apple_complete_admission_20261029.py"
DOC="docs/reader-total-progress/dot-apple-query-observation-20261030.md"
def git(*args):return subprocess.check_output(["git",*args],text=True).strip()
def source(path):return subprocess.check_output(["git","show",BASE+":"+path]).decode()
def replace_once(text,old,new):
 assert text.count(old)==1,old
 return text.replace(old,new,1)
assert git("rev-parse","HEAD")==os.environ["GITHUB_SHA"]
assert os.environ["GITHUB_REF_NAME"] in BRANCHES
subprocess.run(["git","merge-base","--is-ancestor",BASE,"HEAD"],check=True)
assert set(git("diff","--name-only",BASE,"HEAD").splitlines())=={FEATURES,FONT,FULL,FOCUS,SELF,DOC}
assert set(git("diff","--name-only","8ec841fe5127b810ad37f14662de51650c0b51c2","HEAD").splitlines())=={FEATURES,FULL,FOCUS,SELF,DOC}
feature_replacements=[["        func inDirectory() -> Bool {\n            (currentDirectoryMenu.exists && localRoot.exists) || directory.exists\n        }","        func observeDirectory(knownRoot: Bool? = nil) -> (directory: Bool, root: Bool?) {\n            var root = knownRoot\n            if currentDirectoryMenu.exists {\n                if root == nil { root = localRoot.exists }\n                if root == true { return (true, root) }\n            }\n            return (directory.exists, root)\n        }\n        func inDirectory() -> Bool { observeDirectory().directory }"],["        XCTAssertTrue(wait {\n            localRoot.exists || inDirectory() || (local.exists && local.isHittable) ||\n            (browse.exists && browse.isHittable)\n        }, app.debugDescription)","        XCTAssertTrue(wait {\n            let root = localRoot.exists\n            return root || observeDirectory(knownRoot: root).directory || (local.exists && local.isHittable) ||\n            (browse.exists && browse.isHittable)\n        }, app.debugDescription)"],["        if !inDirectory() && !localRoot.exists {","        let entry = observeDirectory()\n        if !entry.directory && !(entry.root ?? localRoot.exists) {"],["        XCTAssertTrue(wait { inDirectory() || localRoot.exists }, app.debugDescription)","        XCTAssertTrue(wait {\n            let position = observeDirectory()\n            return position.directory || (position.root ?? localRoot.exists)\n        }, app.debugDescription)"]]
feature_replacements.append(['            inline.typeText(String(repeating: XCUIKeyboardKey.delete.rawValue, count: old.count))\n            inline.typeText("EXReaderAnnotations\\n")', '            inline.typeText(String(repeating: XCUIKeyboardKey.delete.rawValue, count: old.count) + "EXReaderAnnotations\\n")'])
expected=source(FEATURES)
for old,new in feature_replacements:expected=replace_once(expected,old,new)
actual=Path(FEATURES).read_text()
assert actual==expected
marker="    func testBorrowedFontRollbackOriginalExportAndReadOnlySnapshot()"
assert actual[actual.index(marker):]==source(FEATURES)[source(FEATURES).index(marker):]
prefix="    private var nativeShareObserved"
assert actual[:actual.index(prefix)]==source(FEATURES)[:source(FEATURES).index(prefix)]
assert actual.count("addingTimeInterval(90)")==1 and actual.count("for _ in 0..<24")==1
font_before,font_after=["    private func element(_ id: String) -> XCUIElement {\n        app.descendants(matching: .any).matching(identifier: id).firstMatch\n    }","    private func element(_ id: String) -> XCUIElement {\n#if os(iOS)\n        if id == \"features.scroll\" { return app.scrollViews.matching(identifier: id).firstMatch }\n        let labels: Set<String> = [\n            \"features.status\", \"features.font.observation\", \"library.title\",\n            \"library.busy\", \"library.font.observation\", \"reader.location\"\n        ]\n        if labels.contains(id) { return app.staticTexts.matching(identifier: id).firstMatch }\n        let buttons: Set<String> = [\n            \"features.close\", \"features.cancel\", \"library.import.epub\", \"reader.next\", \"reader.back\"\n        ]\n        if buttons.contains(id) || id.hasPrefix(\"library.book.\") || id.hasPrefix(\"features.font.\") {\n            return app.buttons.matching(identifier: id).firstMatch\n        }\n#endif\n        return app.descendants(matching: .any).matching(identifier: id).firstMatch\n    }"]
assert Path(FONT).read_text()==replace_once(source(FONT),font_before,font_after)
assert git("rev-parse","HEAD:"+FEATURES)=="91bf54e9347d4a8bff73e70722d51a42116866fc"
assert git("rev-parse","HEAD:"+FONT)=="4fa83609db34c48456be9a393d3d7745560a4cbb"
full=replace_once(source(FULL),"branches: [codex/dot-apple-complete-20261029]","branches: [codex/dot-apple-input-full-20261030]")
full=replace_once(full,"  workflow_dispatch:\n","")
full=replace_once(full,"824647af22c2e57a9df01e94064b20a44c2df03b","91bf54e9347d4a8bff73e70722d51a42116866fc")
full=replace_once(full,"':(exclude)tests/apple_native_original/ui/OriginalSaveUITests.swift'","':(exclude)tests/apple_native_original/ui/OriginalSaveUITests.swift' ':(exclude)tests/reader_apple_font/ui/FontReaderUITests.swift'")
assert Path(FULL).read_text()==full
focus=full.split("  native:\n")[0]
focus=replace_once(focus,"name: Apple SDK 3.42 full same-source host gates","name: Apple query helper focused validation")
focus=replace_once(focus,"branches: [codex/dot-apple-input-full-20261030]","branches: [codex/dot-apple-input-focused-20261030]")
native="  native:\n"+full.split("  native:\n",1)[1].split("  authenticate:\n",1)[0]
native=replace_once(native,"  native:\n","  focused:\n")
native=replace_once(native,"Team24 Apple native","Focused original five")
native=replace_once(native,"platform: [macos, iphone, ipad]","platform: [iphone, ipad]")
native=replace_once(native,"Original 39 cases and real 3.42 program identity","Original five cases and real 3.42 program identity")
native=replace_once(native,"tests/apple_sdk342_host/run_ui.py","tests/apple_features_repair_20261029/focused_runner.py")
native=replace_once(native,"name: team24-apple-native-","name: focused-original-five-")
font="  supplemental:\n"+full.split("  supplemental:\n",1)[1].split("  full-host-summary:\n",1)[0]
font=replace_once(font,"  supplemental:\n","  focused-font:\n")
font=replace_once(font,"Apple 3.42","Focused Apple 3.42")
font=replace_once(font,"platform: [macos, iphone, ipad]","platform: [iphone, ipad]")
font=replace_once(font,"suite: [font, original, organization, sync]","suite: [font]")
assert Path(FOCUS).read_text()==focus+native+font
print("Exact candidate: previous qualified helpers plus one identical native input stream in a single typeText call; font bytes unchanged. All other source, SDK, runners, checker, five bodies, font body, teardown, 90s/24/240/360 unchanged. Focused six; full nineteen on identical SHA.",flush=True)
