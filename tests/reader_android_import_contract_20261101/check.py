"""Actions-only fixed static import-contract regression; no APK or emulator."""
import hashlib
from unittest.mock import patch
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
BASE = "f12da3b05c95bb14c4b7193850ba50e8a1f99e74"
sys.path.insert(0, str(ROOT / "tools"))
spec = importlib.util.spec_from_file_location("import_contract_checker", ROOT / "tools/check_android_host.py")
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)

MUTATIONS = [
    ("activity-owner", "activity", "imports = ImportController.get(this)", "imports = MissingController.get(this)"),
    ("activity-result", "activity", "imports.submit(data);", "imports.ignore(data);"),
    ("private-controller-factory", "controller", "ImportEntry.createWithDisplayFilename(", "ImportEntry.missingFactory("),
    ("controller-submit", "controller", "entry.submit(intent)", "entry.ignore(intent)"),
    ("gradle-dependency", "gradle", "implementation project(':importentry')", "implementation project(':missing')"),
    ("gradle-location", "settings", "../../extras/android-import-entry/android/importentry", "../../missing"),
    ("intent-dispatch", "entry", "submit(uri, intent.getType())", "ignore(uri, intent.getType())"),
    ("uri-worker", "entry", "worker.execute(() -> run(ticket, mimeHint))", "worker.execute(() -> ignore(ticket, mimeHint))"),
    ("worker-copy", "entry", "copied = copy(ticket, mimeHint);", "copied = ignore(ticket, mimeHint);"),
    ("copy-open", "entry", "afd = open(uri);", "afd = ignore(uri);"),
    ("provider-open", "entry", "resolver.openAssetFileDescriptor(uri,", "resolver.ignoreDescriptor(uri,"),
    ("provider-write", "entry", 'resolver.openAssetFileDescriptor(uri, "r")', 'resolver.openAssetFileDescriptor(uri, "w")'),
    ("permission-refusal", "entry", "new Failure(ImportError.Code.PERMISSION,", "new Failure(ImportError.Code.IO,"),
    ("atomic-publication", "entry", "Files.move(part.toPath(), target.toPath(),", "Files.copy(part.toPath(), target.toPath(),"),
    ("constructor-recovery", "entry", "cleanStaging();", "ignoreStaging();"),
    ("private-ready-reconstruction", "entry", "new ReadyRequest(name, f,", "new MissingRequest(name, f,"),
    ("host-private-file", "activity", "copyUri(Uri.fromFile(ready.file()),", "copyUri(Uri.fromFile(missing.file()),"),
    ("controller-native-handoff", "controller", "owner.importReady(next)", "owner.ignoreReady(next)"),
    ("factory-return", "entry", "return create(context, stagingParent, ownerExecutor, owner, DEFAULT_STALL_TIMEOUT_MILLIS, true);", "return missing(context, stagingParent, ownerExecutor, owner, DEFAULT_STALL_TIMEOUT_MILLIS, true);"),
    ("factory-constructor", "entry", "return new ImportEntry(context.getApplicationContext().getContentResolver(),", "return new MissingEntry(context.getApplicationContext().getContentResolver(),"),
    ("ready-callback", "controller", "pending.add(request);", "pending.ignore(request);"),
    ("copy-finish", "entry", "finish(ticket, copied, null);", "ignore(ticket, copied, null);"),
    ("gradle-include", "settings", "include ':importentry'", "include ':missing'"),
    ("finish-deliver", "entry", "deliver(ticket, request, error);", "ignore(ticket, request, error);"),
    ("deliver-ready", "entry", "owner.onReady(ticket, request)", "owner.ignoreReady(ticket, request)"),
]
EXPECTED = ["current-private-copy", "private-copy-formatting", "legacy-real-call"] + [item[0] for item in MUTATIONS] + [
    "comments-only", "strings-only", "isolated-call", "other-checker-bytes-unchanged", "other-static-negative", "original-static-checker"]

def main():
    assert os.environ.get("GITHUB_ACTIONS") == "true", "Actions only"
    assert os.environ.get("GITHUB_REPOSITORY") == "NoGod3524/EXReader"
    assert subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip() == os.environ["GITHUB_SHA"]
    sources = {name: (ROOT / path).read_text() for name, path in checker.IMPORT_CONTRACT_PATHS.items()}
    results = []
    def sha(value):
        return hashlib.sha256(value.encode()).hexdigest()
    def record(name, passed, expected, actual, inputs):
        results.append({"name": name, "passed": bool(passed), "expected": expected, "actual": actual, "input_sha256": inputs})
    def contract_case(name, values, accept):
        problems = checker.import_contract_sources(values)
        record(name, (not problems) == accept, "accept" if accept else "reject", problems,
               {key: sha(value) for key, value in values.items()})
    contract_case("current-private-copy", sources, True)
    formatted = dict(sources)
    formatted["activity"] = formatted["activity"].replace("imports.submit(data);", "imports /* bridge */ . submit ( data ) ;")
    formatted["entry"] = formatted["entry"].replace("Files.move(", "Files /* bridge */ . move (\n")
    formatted["gradle"] = formatted["gradle"].replace("implementation project", "implementation /* bridge */ project")
    contract_case("private-copy-formatting", formatted, True)
    legacy = {key: "" for key in sources}
    legacy["activity"] = 'class MainActivity { protected void onActivityResult(int requestCode, int resultCode, Intent data) { getContentResolver().takePersistableUriPermission(uri, flags); } }'
    contract_case("legacy-real-call", legacy, True)
    for name, key, old, new in MUTATIONS:
        assert old in sources[key], "mutation anchor absent: " + name
        changed = dict(sources); changed[key] = sources[key].replace(old, new)
        contract_case(name, changed, False)
    changed = dict(sources); changed["activity"] = "/*" + sources["activity"].replace("*/", "* /") + "*/"
    contract_case("comments-only", changed, False)
    changed = dict(sources); changed["activity"] = "class MainActivity { String fake = " + json.dumps(sources["activity"]) + "; }"
    contract_case("strings-only", changed, False)
    changed = dict(sources); changed["activity"] = sources["activity"].replace("imports.submit(data);", "imports.ignore(data);") + "\nclass Isolated { void unused() { imports.submit(data); } }"
    contract_case("isolated-call", changed, False)
    current = (ROOT / "tools/check_android_host.py").read_text()
    start = current.index("\n# Narrow source-contract migration;")
    end = current.index("\ndef static_checks():", start)
    restored = current[:start] + current[end:]
    restored = restored.replace("    problems.extend(import_contract_checks(ROOT))\n", "", 1)
    restored = restored.replace("'onSaveInstanceState',", "'onSaveInstanceState', 'takePersistableUriPermission',", 1)
    original = subprocess.check_output(["git", "show", BASE + ":tools/check_android_host.py"], cwd=ROOT, text=True)
    record("other-checker-bytes-unchanged", restored == original, "byte-identical", restored == original,
           {"restored": sha(restored), "baseline": sha(original)})
    view_path = ROOT / "examples/android/app/src/main/java/org/exreader/host/ReaderView.java"
    original_read = Path.read_text
    view_text = original_read(view_path)
    def changed_read(path, *args, **kwargs):
        value = original_read(path, *args, **kwargs)
        return value.replace("onTouchEvent", "missingTouchEvent") if path == view_path else value
    with patch.object(Path, "read_text", changed_read):
        other_problems, _ = checker.static_checks()
    record("other-static-negative", other_problems == ["ReaderView lacks onTouchEvent"],
           ["ReaderView lacks onTouchEvent"], other_problems,
           {"ReaderView.java": sha(view_text.replace("onTouchEvent", "missingTouchEvent"))})
    output = ROOT / "build/android-import-contract/original-static.json"
    process = subprocess.run([sys.executable, "tools/check_android_host.py", "--repo", str(ROOT), "--output", str(output)], cwd=ROOT)
    report = json.loads(output.read_text()) if output.exists() else {}
    record("original-static-checker", process.returncode == 0 and report.get("candidate_validated") is True and report.get("accepted") is False and not report.get("problems"),
           "candidate validated; product not accepted", {"returncode": process.returncode, "report": report}, {"checker": sha(current)})
    assert [item["name"] for item in results] == EXPECTED and len(results) == 34
    result = {"source_sha": os.environ["GITHUB_SHA"], "run_id": os.environ["GITHUB_RUN_ID"], "attempt": os.environ["GITHUB_RUN_ATTEMPT"],
        "checks": results, "count": 34, "positive_contract_cases": 3, "negative_contract_cases": 28, "preservation_and_original_checker_cases": 2, "other_static_negative_cases": 1,
        "source_files_sha256": {checker.IMPORT_CONTRACT_PATHS[key]: sha(value) for key, value in sources.items()},
        "runtime_executed": False, "current_sdk_runtime_accepted": False,
        "accepted": all(item["passed"] for item in results), "static_only": True, "product_accepted": False, "formal_count_credit": 0}
    output.with_name("result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, sort_keys=True))
    assert result["accepted"], "static import-contract regression failed"

if __name__ == "__main__":
    main()
