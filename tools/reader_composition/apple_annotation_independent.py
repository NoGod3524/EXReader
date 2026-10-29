#!/usr/bin/env python3
"""Actions-only independent review of each original native annotation host."""
import argparse, hashlib, io, json, os, plistlib, subprocess, tempfile, zipfile
from pathlib import Path, PurePosixPath
assert os.environ.get("GITHUB_ACTIONS") == "true"
REPO = "NoGod3524/EXReader"
SOURCES = {
    "macos": (40923468266, "622b9558f79eda07211e15c51bffcd728da6c553", 123625260629),
    "iphone": (40923468266, "622b9558f79eda07211e15c51bffcd728da6c553", 123625260345),
    "ipad": (40923468266, "622b9558f79eda07211e15c51bffcd728da6c553", 123625260444),
}
FEATURE_CASES = {
    "testBorrowedFontRollbackOriginalExportAndReadOnlySnapshot()",
    "testNativeAnnotationPreviewConfirmCancelAndDuplicate()",
    "testNativeHistoryAfterFoundAndLargeRotationExit()",
    "testTypedNullAndConcurrentHeadsRequirePreviewConfirmation()",
    "testDirectoryPickerCancellationPreservesReader()",
}
SCREEN_CASES = {
    "testNativeAnnotationPreviewConfirmCancelAndDuplicate": [
        "native-jsonl-folder-save", "native-markdown-folder-save",
        "native-preview-no-revisions-write", "invalid-annotation-rejected",
        "native-picker-invalid-rejected", "invalid-import-revision-identity-unchanged",
        "native-picker-valid-preview", "jsonl-markdown-content-verified",
        "preview-cancel", "confirmed-exact-duplicate"],
    "testTypedNullAndConcurrentHeadsRequirePreviewConfirmation": [
        "typed-null-preview-preserved", "concurrent-heads-await-confirmation",
        "concurrent-heads-retained"],
    "testDirectoryPickerCancellationPreservesReader": ["native-directory-picker-cancel"],
}
def api(path, binary=False):
    raw = subprocess.check_output(["gh", "api", "repos/"+REPO+"/"+path])
    return raw if binary else json.loads(raw)
def digest(data): return hashlib.sha256(data).hexdigest()
def safe_zip(raw):
    z = zipfile.ZipFile(io.BytesIO(raw))
    names = z.namelist()
    assert len(names) == len(set(names)), "duplicate ZIP member"
    assert all(not PurePosixPath(n).is_absolute() and ".." not in PurePosixPath(n).parts and "\\" not in n for n in names)
    return z
def cases(bundle):
    raw = subprocess.check_output(["xcrun", "xcresulttool", "get", "test-results", "tests", "--path", str(bundle), "--format", "json"])
    rows = []
    def walk(node):
        if node.get("nodeType") == "Test Case": rows.append((node["name"], node["result"]))
        for child in node.get("children", []): walk(child)
    for node in json.loads(raw)["testNodes"]: walk(node)
    assert len(rows) == len(dict(rows)), "duplicate test case"
    return dict(rows)
p = argparse.ArgumentParser(); p.add_argument("--platform", choices=SOURCES, required=True)
platform = p.parse_args().platform
run_id, source, job_id = SOURCES[platform]
out = Path("build/apple-annotation-independent")/platform
out.mkdir(parents=True, exist_ok=True)
result = {"platform":platform, "run":run_id, "source":source, "job":job_id, "accepted":False, "catalog_changed":False}
try:
    run = api("actions/runs/%d/attempts/1"%run_id)
    assert run["head_sha"] == source and run["run_attempt"] == 1
    assert run["status"] in ("in_progress", "completed")
    assert run["conclusion"] in (None, "success", "failure"), "retain original run state; this is one completed host only"
    job = api("actions/jobs/%d"%job_id)
    assert job["run_id"] == run_id and job["head_sha"] == source and job["status"] == "completed" and job["conclusion"] == "success"
    name = "team24-apple-native-%s-%d-1"%(platform, run_id)
    matches = [a for a in api("actions/runs/%d/artifacts?per_page=100"%run_id)["artifacts"] if a["name"] == name]
    assert len(matches) == 1
    meta = matches[0]
    assert not meta["expired"] and meta["workflow_run"]["id"] == run_id and meta["workflow_run"]["head_sha"] == source
    raw = api("actions/artifacts/%d/zip"%meta["id"], True)
    assert len(raw) == meta["size_in_bytes"] and "sha256:"+digest(raw) == meta["digest"]
    if platform == "macos":
        assert meta["id"] == 12920073975 and len(raw) == 316382076 and digest(raw) == "11792b2252650bf055fe035b92a4f7e83b0d7bf248fb404a432d4a651d16e4ac"
    result.update(artifact=meta["id"], archive_bytes=len(raw), archive_sha256=digest(raw), original_run_status=run["status"], original_run_conclusion=run["conclusion"], whole_run_accepted=False)
    with tempfile.TemporaryDirectory() as work, safe_zip(raw) as z:
        root = Path(work)
        z.extractall(root)
        report = json.loads((root/"result.json").read_text())
        assert (report["source_sha"], str(report["run_id"]), str(report["attempt"]), report["platform"]) == (source, str(run_id), "1", platform)
        assert report["accepted"] is True and report["physical_device"] is False and report["complete_product"] is False
        expected_old_tests = {
            "tests/apple_host/reading/ui/ReadingUITests.swift": "79efae4675091b6fb59edd99a4c864ad5dac04e1b5dd23726dadc6e0aba2ec91",
            "tests/apple_host/navigation/ui/NavigationUITests.swift": "13793f3afde654e19aac0413b708a9add9066dd828bd9f71ded229a31eb6f357",
            "tests/apple_host/search/ui/SearchUITests.swift": "423e5d9898ac21506612f1f5ac38917844259d40baa8e24484785b21c4b82e1a",
            "tests/apple_host/page_theme/ui/ThemeUITests.swift": "1bca59d26dbfb82cf2ac09154ea2bc7e2f278a2349d22be1a8cb494c64f28a4b",
            "tests/apple_host/EXReaderHostUITests.swift": "081d841c6a4158e779fd375bd8a0854f05a87c22c4ae7c00e449a97458b27058",
        }
        assert report["unchanged_old_tests"] == expected_old_tests
        phases = report["phases"]
        assert [q["mode"] for q in phases] == ["wave3", "base", "control", "search", "theme"]
        native_cases, programs = {}, {}
        for phase, expected in zip(phases, (5, 13, 13, 4, 4)):
            mode = phase["mode"]
            assert phase["accepted"] is True and phase["expected_cases"] == expected
            native = cases(root/("theme-os/theme.xcresult" if mode == "theme" else mode+".xcresult"))
            assert len(native) == expected and set(native.values()) == {"Passed"}
            assert native == {r["name"]:r["result"] for r in phase["cases"]}
            if mode == "wave3": assert set(native) == FEATURE_CASES
            native_cases[mode] = list(native)
            checker = phase["original_checker"]
            assert checker["accepted"] is True and checker["system_sqlite_fallback"] is False and checker["static_sdk_linked"] is False
            program = phase["program"]
            assert program["bundle_source_sha"] == source and program["bundle_id"] == "org.exreader.host" and program["physical_device"] is False
            package = PurePosixPath(program["packaged_app"])
            assert not package.is_absolute() and ".." not in package.parts
            with safe_zip((root/str(package)).read_bytes()) as app:
                executable = "EXReaderHost.app/Contents/MacOS/EXReaderHost" if platform == "macos" else "EXReaderHost.app/EXReaderHost"
                info_path = "EXReaderHost.app/Contents/Info.plist" if platform == "macos" else "EXReaderHost.app/Info.plist"
                binary = app.read(executable)
                info = plistlib.loads(app.read(info_path))
                assert len(binary) == program["bytes"] and digest(binary) == program["sha256"]
                assert info["EXRSourceSHA"] == source and info["CFBundleIdentifier"] == "org.exreader.host"
                programs[mode] = digest(binary)
        system = json.loads((root/"theme-os/system-commands.json").read_text())
        assert system["source_sha"] == source and str(system["run_id"]) == str(run_id) and str(system["attempt"]) == "1"
        assert system["served"] == ["dark", "light"]
        if platform == "macos":
            appearance_commands = [c for c in system["commands"] if c["argv"][0] == "osascript" and "set dark mode to " in c["argv"][-1] and c["exit_code"] == 0]
            assert any(c["argv"][-1].endswith("set dark mode to true") for c in appearance_commands)
            assert any(c["argv"][-1].endswith("set dark mode to false") for c in appearance_commands)
        else:
            appearance_commands = [c for c in system["commands"] if "appearance" in c["argv"] and c["exit_code"] == 0]
            assert any(c["argv"][-1] == "dark" for c in appearance_commands)
            assert any(c["argv"][-1] == "light" for c in appearance_commands)
        assert all(c["completed_at_unix"] >= c["started_at_unix"] for c in appearance_commands)
        attachments = root/"independent-attachments"
        subprocess.run(["xcrun", "xcresulttool", "export", "attachments", "--path", str(root/"wave3.xcresult"), "--output-path", str(attachments)], check=True)
        manifest = json.loads((attachments/"manifest.json").read_text())
        found = set()
        for group in manifest:
            owner = group.get("testIdentifier") or group.get("testName") or ""
            owners = [c for c in SCREEN_CASES if c in owner]
            if not owners: continue
            assert len(owners) == 1
            case = owners[0]
            for a in group["attachments"]:
                title = a["suggestedHumanReadableName"]
                marks = [m for m in SCREEN_CASES[case] if title.startswith(m)]
                if not marks: continue
                assert len(marks) == 1
                filename = a["exportedFileName"]
                assert PurePosixPath(filename).name == filename and "\\" not in filename
                data = (attachments/filename).read_bytes()
                assert data.startswith(b"\x89PNG\r\n\x1a\n")
                found.add((case, marks[0]))
        expected = {(case, mark) for case, marks in SCREEN_CASES.items() for mark in marks}
        assert found == expected, ("missing native evidence screenshots", sorted(expected-found))
        result.update(accepted=True, native_cases=native_cases, program_sha256=programs,
                      screenshot_checks=len(found), physical_device=False, sdk_version="3.41.0",
                      exported_content_basis="native XCTest checks actual selected-folder JSONL and Markdown; exported payloads not separately retained")
except Exception as error:
    result["error"] = repr(error)
finally:
    (out/"result.json").write_text(json.dumps(result, indent=2)+"\n")
    print(json.dumps(result), flush=True)
assert result["accepted"], result.get("error", "annotation evidence incomplete")
