"""Run the unchanged full Apple cohorts from the final admitted source."""
import argparse
import importlib.util
import json
import os
import sys

from source import ROOT, admission, need

LEGACY = ROOT / "tests/reader_f08_apple_20261031"


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


R = load("final_apple_run", LEGACY / "run.py")
R.guard = admission


def sdk(target):
    admitted = admission()
    builder = load("final_apple_sdk", ROOT / "tests/apple_sdk342_host/build.py")
    # Admission has already frozen production and build recipes. The original
    # builder now compiles this HEAD and records it as its SDK content source.
    builder.SDK_SOURCE = admitted["source_sha"]
    previous = sys.argv
    try:
        sys.argv = [str(builder.__file__), "--target", target]
        builder.main()
    finally:
        sys.argv = previous


def audit():
    import time,traceback
    started=time.monotonic()
    admission()
    _,n=mac_modules()
    deadline=started+1050
    previous_command=R.command;previous_deadline=n.DEADLINE
    R.command=n.command;n.DEADLINE=deadline
    previous=sys.modules.get("run")
    sys.modules["run"]=R
    out=ROOT/"build/f08-apple-audit";error=None
    try:
        replay=load("final_apple_audit",LEGACY/"audit.py")
        need(replay.guard is admission,"final Apple audit admission binding")
        replay.main(mac_validator=lambda raw,root:audit_mac_full(raw,root,deadline))
    except BaseException as failure:
        error=repr(failure)
        if not (out/"audit.json").exists():
            R.save(out/"audit.json",{**R.identity(),"authenticated":False,"errors":[error],
                   "traceback":traceback.format_exc(),"f08_accepted":False})
        raise
    finally:
        if previous is None:sys.modules.pop("run",None)
        else:sys.modules["run"]=previous
        R.command=previous_command;n.DEADLINE=previous_deadline
        R.save(out/"full-audit-controller.json",{**R.identity(),"elapsed_s":time.monotonic()-started,
               "hard_budget_s":1050,"error":error,"f08_accepted":False})


MAC_HERE = ROOT / "tests/reader_f08_mac_reader_animation_20261101"
ORIGINAL_SEVEN = [
    "test01RealShelfAndBoundedInteractiveRows()",
    "test02ForwardTraversalOfAllOriginals()",
    "test03StableEqualTitles()",
    "test04TitleAuthorAndLiteralSearch()",
    "test05RapidSearchRefreshAndNativeViewport()",
    "test06RotationBackgroundAndProcessRestore()",
    "test07StoredOriginalReadingAndFilteredReturn()",
]
FULL_SOFT_SECONDS, FULL_HARD_SECONDS = 5100, 5250
_MAC_MODULES = None


def mac_modules():
    global _MAC_MODULES
    if _MAC_MODULES is None:
        _MAC_MODULES = (load("full_mac_helpers", MAC_HERE / "helpers.py"),
                        load("full_mac_utilities", MAC_HERE / "run.py"))
    return _MAC_MODULES


def validate_mac_full(folder, expected_identity, expected_program_sha):
    """Pure consumer; expected identity/SHA come from admitted, authenticated archive bytes."""
    import re
    from pathlib import Path
    folder = Path(folder)
    problems, details = [], []
    def check(value, code, at=""):
        if not value:
            if code not in problems: problems.append(code)
            details.append({"code": code, "at": at})
    numeric = {}
    original_peak = None
    original_summary_peak = None
    memory_limit = None
    try:
        h, n = mac_modules()
        inputs = json.loads((folder / "full-mac-input.json").read_text())
        program = json.loads((folder / "program-identity.json").read_text())
        original = json.loads((folder / "original/shelf-ui.json").read_text())
        execution = json.loads((folder / "full-mac-execution.json").read_text())
        checks = json.loads((folder / "full-program-checks.json").read_text())
        source = expected_identity["source_sha"]
        check(isinstance(source, str) and bool(re.fullmatch("[0-9a-f]{40}", source)) and
              isinstance(expected_program_sha, str) and bool(re.fullmatch("[0-9a-f]{64}", expected_program_sha)),
              "full.expected_identity")
        for name, value in (("inputs", inputs), ("original", original), ("execution", execution)):
            check(all(value.get(k) == v for k, v in expected_identity.items()), "full.source_identity", name)
        check(inputs.get("channel") == "existing-apple-full90", "full.channel")
        check(program.get("program_source_sha") == source and
              program.get("sdk_input_source_sha") == program.get("resource_input_source_sha") == source and
              program.get("program_sha256") == expected_program_sha and
              program.get("input_run_id") == expected_identity["run_id"] and
              program.get("input_attempt") == expected_identity["attempt"], "full.program_identity")
        for target in ("macos", "iphonesimulator"):
            item = inputs["sdk_inputs"][target]
            installed, sdk_record = item["installed_identity"], item["sdk_identity"]
            check(all(installed.get(k) == sdk_record.get(k) == v for k, v in expected_identity.items()) and
                  installed.get("sdk_content_candidate") == source and installed.get("target") == target and
                  installed.get("sdk_version") == sdk_record.get("sdk_version") == "3.42.0" and
                  sdk_record.get("platform") == target and sdk_record.get("abi") == 1 and
                  sdk_record.get("job") == "sdk", "full.sdk_identity", target)
        resources = inputs["resources"]
        fixed = h.PROFILE["numeric_scope_authorization"]["sample"]
        check(all(resources.get(k) == v for k, v in expected_identity.items()) and
              resources.get("books") == 2202 and resources.get("sample") ==
              {"bytes": fixed["bytes"], "sha256": fixed["sha256"]}, "full.resource_identity")
        original_summary_peak = original.get("measurements", {}).get("process_peak_rss_bytes")
        original_peak = original_summary_peak
        memory_limit = h.PROFILE["limits_unchanged"]["peak_rss_bytes"]
        check(type(original_peak) is int and original_peak > 0, "full.original_rss_missing")
        raw_peaks, shelf_peaks = [], []
        def collect_original_rss(value):
            if isinstance(value, dict):
                if "cached_rows" in value:
                    rss = value.get("process_peak_rss_bytes")
                    if type(rss) is int and rss > 0: shelf_peaks.append(rss)
                for key, item in value.items():
                    if key == "process_peak_rss_bytes":
                        check(type(item) is int and item > 0, "full.original_rss_missing")
                        if type(item) is int and item > 0: raw_peaks.append(item)
                    elif isinstance(item, (dict, list)): collect_original_rss(item)
            elif isinstance(value, list):
                for item in value: collect_original_rss(item)
        collect_original_rss(original.get("observations", {}))
        check(bool(shelf_peaks) and max(shelf_peaks) == original_summary_peak, "full.original_rss_summary")
        original_peak = max(raw_peaks) if raw_peaks else None
        cases = original.get("cases", [])
        check(original.get("accepted") is True and original.get("originals") == 2202 and
              original.get("ui_cases") == 7 and len(cases) == 7 and
              sorted(v.get("name", "") for v in cases) == sorted(ORIGINAL_SEVEN) and
              all(v.get("result") == "Passed" for v in cases), "full.original_cases")
        check(original.get("program_files", {}).get("EXReaderHost.app/Contents/MacOS/EXReaderHost") ==
              expected_program_sha, "full.original_program_identity")
        names = ["original-seven"] + [v["group"] for v in h.PROFILE["numeric_groups"]]
        check(len(checks) == 8 and [v.get("group") for v in checks] == names and
              all(all(v.get(k) == expected for k, expected in expected_identity.items()) and
                  v.get("before_sha256") == v.get("after_sha256") == expected_program_sha and
                  v.get("files_unchanged") is True for v in checks), "full.program_checks")
        check(execution.get("owned_application_cleanup", {}).get("verified") is True and
              execution.get("problems") == [] and bool(execution.get("commands")) and
              all(v.get("owned_group_terminal_verified") is True and type(v.get("returncode")) is int and
                  v["returncode"] == 0 and v.get("timed_out") is False
                  for v in execution["commands"]), "full.terminal_state")
        check(execution.get("bridge_failure_log_lines") == [], "full.bridge_failure")
        for group, mode in (("reader-capture", "capture"), ("reader-action-only", "action_only")):
            n.verify_final_sidecars(folder / "numeric" / group,
                                   {"final_sidecars": execution["final_sidecars"][group]}, mode)
        numeric = h.assess_numeric(folder / "numeric", program, expected_identity,
                                   expected_producer_source=source)
        check(numeric["numeric_complete"], "full.numeric_incomplete")
    except (KeyError, TypeError, ValueError, AttributeError, OSError, IndexError) as error:
        check(False, "full.malformed", repr(error))
    complete = not problems
    numeric_peak = numeric.get("rss", {}).get("peak_bytes")
    full_peak = max(original_peak, numeric_peak) if all(type(v) is int and v > 0 for v in (original_peak, numeric_peak)) else None
    full_memory_passed = complete and full_peak is not None and full_peak <= memory_limit
    return {"complete": complete, "problems": problems, "details": details,
            "original_seven_passed": complete, "numeric": numeric,
            "numeric_complete": numeric.get("numeric_complete", False),
            "numeric_budgets_passed": numeric.get("numeric_budgets_passed", False),
            "original_shelf_summary_peak_rss_bytes": original_summary_peak,
            "original_peak_rss_bytes": original_peak, "full_peak_rss_bytes": full_peak,
            "full_memory_budget_passed": full_memory_passed,
            "full_budgets_passed": complete and numeric.get("numeric_budgets_passed") is True and full_memory_passed,
            "mac_full_gate_passed": complete and numeric.get("numeric_budgets_passed") is True and full_memory_passed,
            "f08_accepted": False}

def native_mac_full():
    """Use the existing full90 job, with one entry clock and one built Mac application."""
    import hashlib, shutil, signal, subprocess, time, traceback
    from pathlib import Path
    started = time.monotonic()
    ident = R.identity()
    control = ROOT / "build/f08-apple/macos/control"
    control.mkdir(parents=True, exist_ok=True)
    budget = {**ident, "started_uptime_s": started,
              "soft_deadline_uptime_s": started + FULL_SOFT_SECONDS,
              "hard_deadline_uptime_s": started + FULL_HARD_SECONDS,
              "channel": "existing-apple-full90"}
    need(not (control / "budget.json").exists(), "full90 native cannot restart/reset its budget")
    R.save(control / "budget.json", budget)
    admitted = admission()
    h, n = mac_modules()
    n.DEADLINE = budget["soft_deadline_uptime_s"]
    state = {"app": None, "expected": None, "report": None, "program": None}
    def remaining(cleanup=False):
        end = budget["hard_deadline_uptime_s"] if cleanup else budget["soft_deadline_uptime_s"]
        return n.remaining(end)
    def terminal(process, role):
        signals = []
        def snapshot():
            return n.process_group_snapshot(process.pid, min(5, remaining(True)))
        before = snapshot()
        def observed(v): return v.get("probe_returncode") == 0 and "probe_error" not in v
        current = before
        for sig, grace in ((signal.SIGTERM, 2), (signal.SIGKILL, 1)):
            if observed(current) and not n.group_has_live_members(current): break
            try: os.killpg(process.pid, sig); signals.append(int(sig))
            except ProcessLookupError: pass
            limit = min(budget["hard_deadline_uptime_s"], time.monotonic() + grace)
            while time.monotonic() < limit:
                current = snapshot()
                if not observed(current) or not n.group_has_live_members(current): break
                time.sleep(min(.05, max(0, limit-time.monotonic())))
        if process.poll() is None:
            try: process.wait(timeout=min(5, remaining(True)))
            except subprocess.TimeoutExpired: pass
        after = snapshot()
        return {"owned_group_before_cleanup": before, "owned_group_after_cleanup": after,
                "owned_group_signals": signals,
                "owned_group_terminal_verified": observed(before) and observed(after) and
                not n.group_has_live_members(after) and process.poll() is not None}
    def prepare(out, evidence, resources, tests, derived, installed):
        n.prepare_png_tools(out / "full-validation-tools", evidence / "validation-tools")
        R.save(evidence / "full-native-budget.json", budget)
        R.save(evidence / "source-admission.json", admitted)
        sdk_inputs = {}
        for target, folder in installed.items():
            sdk_inputs[target] = {
                "installed_identity": json.loads((folder / "sdk342-installed-identity.json").read_text()),
                "sdk_identity": json.loads((folder / "sdk-identity.json").read_text())}
        sample = resources / "Sample.epub"
        fixed = h.PROFILE["numeric_scope_authorization"]["sample"]
        need(sample.stat().st_size == fixed["bytes"] and R.sha(sample) == fixed["sha256"], "fixed additional Apple Sample")
        seed = json.loads((resources / "shelf-seed.json").read_text())
        inputs = {**ident, "channel": "existing-apple-full90", "sdk_inputs": sdk_inputs,
                  "resources": {**ident, "books": seed["books"], "seed": seed,
                                "sample": {"bytes": sample.stat().st_size, "sha256": R.sha(sample)},
                                "files": n.files_under(resources)},
                  "numeric_profile_source_sha256": R.sha(MAC_HERE / "profile.json")}
        R.save(evidence / "full-mac-input.json", inputs)
        app = derived / "Build/Products/Release/EXReaderHost.app"
        sources = h.driver_sources(ident["source_sha"], str(n.binary(app).resolve()))
        for name, text in sources.items():
            (tests / name).write_text(text); shutil.copyfile(tests/name, evidence/name)
        generated = out / "full-ReaderApp.swift"
        generated.write_text(h.injected_reader_app((ROOT/"examples/apple/ReaderApp.swift").read_text()))
        shutil.copyfile(generated, evidence/"ReaderApp.swift")
        shutil.copyfile(MAC_HERE/"Bridge.swift", evidence/"Bridge.swift")
        R.save(evidence/"driver.json", {"full_mac_extension": True,
            "generated_files": {name: R.sha(tests/name) for name in sources},
            "original_sha256": R.sha(ROOT/"tests/apple_host/shelf/ui/ShelfUITests.swift"),
            "insertion_sha256": R.sha(LEGACY/"Metrics.swift"),
            "candidate_sha256": R.sha(tests/"ShelfUITests.swift"),
            "original_cases_unchanged": True})
    def patch(project, run):
        generated = project.parent / "full-ReaderApp.swift"
        script = 'p=Xcodeproj::Project.open(ARGV[0]);t=p.targets.find{|v|v.name=="EXReaderHost-macOS"};raise "Mac target" unless t;f=t.source_build_phase.files.select{|v|v.file_ref && File.expand_path(v.file_ref.path.to_s,File.dirname(ARGV[0]))==File.expand_path(ARGV[1])};raise "unique App" unless f.length==1;f.first.remove_from_project;[ARGV[2],ARGV[3]].each{|path|t.source_build_phase.add_file_reference(p.main_group.new_file(File.expand_path(path)))};p.save'
        run(["ruby", "-rxcodeproj", "-e", script, project/"EXReaderHost.xcodeproj",
             ROOT/"examples/apple/ReaderApp.swift", generated, MAC_HERE/"Bridge.swift"], "full-app-source")
    def execute(out, evidence, resources, seed, installed, derived, common, test_target, destination, report, run):
        app = derived/"Build/Products/Release/EXReaderHost.app"
        state.update(app=app, report=report)
        report.update(full_mac_extension=True, original_ui_accepted=False, numeric_complete=False,
                      numeric_budgets_passed=False, full_mac_gate_passed=False)
        checks, group_receipts, final_sidecars = [], [], {}
        numeric = evidence/"numeric"; numeric.mkdir()
        R.save(numeric/"numeric-groups.json", group_receipts)
        try:
            run(["xcodebuild", "build-for-testing", *common], "full-build", timeout=600)
            expected = n.verify_program(app); before = R.sha(n.binary(app)); state["expected"] = expected
            program = {"program_source_sha": ident["source_sha"], "program_sha256": before,
                       "program_files": expected, "built_executable_url": str(n.binary(app).resolve()),
                       "sdk_input_source_sha": ident["source_sha"], "resource_input_source_sha": ident["source_sha"],
                       "input_run_id": ident["run_id"], "input_attempt": ident["attempt"], "destination": "platform=macOS"}
            state["program"] = program; R.save(evidence/"program-identity.json", program)
            report.update(program_sha256=before,
                          program_architecture=R.command(["lipo", "-archs", n.binary(app)], text=True).split())
            need(report["program_architecture"] == R.command(["uname", "-m"], text=True).split(), "native runner architecture")
            (evidence/"program-dependencies.txt").write_text(R.command(["otool", "-L", n.binary(app)], text=True))
            (evidence/"xctestrun").mkdir()
            for path in sorted((derived/"Build/Products").glob("*.xctestrun")):
                raw = path.read_bytes()
                need(not any(os.environ.get(k) and os.environ[k].encode() in raw for k in n.CREDENTIAL_NAMES), "credential in xctestrun")
                shutil.copyfile(path, evidence/"xctestrun"/path.name)
            need(list((evidence/"xctestrun").glob("*.xctestrun")), "actual xctestrun")
            def checkpoint(group, call):
                n.verify_program(app, expected); first = R.sha(n.binary(app))
                row = {**ident, "group": group, "before_sha256": first}; checks.append(row)
                R.save(evidence/"full-program-checks.json", checks)
                call()
                n.cleanup_program(n.binary(app), budget["hard_deadline_uptime_s"])
                n.verify_program(app, expected)
                row.update(after_sha256=R.sha(n.binary(app)), files_unchanged=True)
                R.save(evidence/"full-program-checks.json", checks)
            original = evidence/"original.xcresult"
            checkpoint("original-seven", lambda: run(["xcodebuild", "test-without-building", *common,
                "-resultBundlePath", original, "-only-testing:"+test_target+"/ShelfUITests",
                "-skip-testing:"+test_target+"/ShelfUITests/test08F08ScrollMetrics",
                "-skip-testing:"+test_target+"/ShelfUITests/test14F08NativeShelfAnimationSignposts"],
                "original-seven", required=False))
            run([sys.executable, "tests/apple_host/shelf/collect_shelf_evidence.py", "--platform", "macos",
                 "--xcresult", original, "--output", evidence/"original",
                 "--container", Path.home()/"Library/Application Support/EXReader", "--app", app,
                 "--seed", out/"seed/shelf-seed.json", "--sdk-root", installed["macos"]/"sdk",
                 "--sdk-identity", installed["macos"]/"sdk-identity.json", "--destination", destination],
                "original-evidence", required=False, timeout=600)
            report["original_ui_accepted"] = (evidence/"original/shelf-ui.json").is_file() and json.loads(
                (evidence/"original/shelf-ui.json").read_text()).get("accepted") is True
            _, load_results = n.load_native_tools()
            for group in h.PROFILE["numeric_groups"]:
                label = group["group"]; directory = numeric/label; directory.mkdir()
                receipt = {**ident, "group": label, "relative_path": label, "selectors": group["selectors"],
                           "program_before_sha256": R.sha(n.binary(app))}
                group_receipts.append(receipt); R.save(numeric/"numeric-groups.json", group_receipts)
                bundle = directory/"native.xcresult"
                checkpoint(label, lambda: run(["xcodebuild", "test-without-building", *common, "-resultBundlePath", bundle,
                    *["-only-testing:"+test_target+"/"+c for c in group["selectors"]]],
                    "numeric-"+label, required=False, timeout=1200 if group["kind"]=="shelf" else 480))
                receipt.update(program_after_sha256=R.sha(n.binary(app)), program_files_unchanged=True)
                objects, performance = R.extract_metrics(bundle, with_cases=True)
                R.save(directory/"xcresult-objects.json", objects); R.save(directory/"performance-cases.json", performance)
                R.save(directory/"test-cases.json", load_results(bundle))
                run(["xcrun", "xcresulttool", "export", "attachments", "--path", bundle,
                     "--output-path", directory/"attachments"], "attachments-"+label, required=False, timeout=90)
                R.save(directory/"observations.json", n.observations(directory))
                if group["kind"] in ("capture", "action_only"):
                    final_sidecars[label] = n.finalize_sidecars(directory, group["kind"])
                    receipt["sidecars_finalized_after_owned_cleanup"] = True
                R.save(numeric/"numeric-groups.json", group_receipts)
        finally:
            n.DEADLINE = budget["hard_deadline_uptime_s"]
            try:
                report["owned_application_cleanup"] = n.cleanup_program(n.binary(app), budget["hard_deadline_uptime_s"])
            except BaseException as error:
                report["owned_application_cleanup"] = {"verified": False, "error": repr(error)}
                report["problems"].append("owned application cleanup "+repr(error))
            if state["expected"] is not None and report["owned_application_cleanup"].get("verified") is True:
                n.verify_program(app, state["expected"])
                shutil.copytree(app, evidence/"program/EXReaderHost.app")
                report["program_post_cleanup_unchanged"] = True
            sticky = [line for group in h.PROFILE["numeric_groups"]
                      for path in [evidence/("numeric-"+group["group"]+".log")] if path.exists()
                      for line in path.read_text(errors="replace").splitlines() if "F08_BRIDGE_FAIL" in line]
            report["bridge_failure_log_lines"] = sticky
            if sticky:report["problems"].append("sticky app-main bridge failure in actual group log")
            execution = {**ident, "commands": report["commands"], "problems": list(report["problems"]),
                         "bridge_failure_log_lines": sticky,
                         "owned_application_cleanup": report["owned_application_cleanup"],
                         "final_sidecars": final_sidecars, "elapsed_s": time.monotonic()-started}
            R.save(evidence/"full-mac-execution.json", execution)
            n.DEADLINE = budget["soft_deadline_uptime_s"]
        numeric_result = h.assess_numeric(numeric, state["program"], ident, expected_producer_source=ident["source_sha"])
        R.save(numeric/"assessment.json", numeric_result)
        assessment = validate_mac_full(evidence, ident, state["program"]["program_sha256"])
        R.save(evidence/"full-mac-assessment.json", assessment)
        remaining(False)
        report.update(numeric_complete=assessment["numeric_complete"],
                      numeric_budgets_passed=assessment["numeric_budgets_passed"],
                      full_mac_gate_passed=assessment["mac_full_gate_passed"],
                      full_budgets_passed=assessment["full_budgets_passed"], full_peak_rss_bytes=assessment["full_peak_rss_bytes"],
                      collection_complete=assessment["complete"] and report["original_ui_accepted"] and not report["problems"],
                      full_main_elapsed_s=time.monotonic()-started)
        need(report["collection_complete"], "full Mac collection incomplete; original observations preserved")
    previous = R.command
    R.command = n.command
    try:
        R.native("macos", mac_prepare=prepare, mac_patch=patch, mac_execute=execute,
                 mac_remaining=remaining, mac_terminal=terminal,
                 mac_environment={k:v for k,v in os.environ.items() if k not in n.CREDENTIAL_NAMES})
    finally:
        R.command = previous
        n.DEADLINE = None


def seal_mac_full():
    """Refuse the legacy upload path unless this original full90 round is terminal."""
    import time
    control = ROOT/"build/f08-apple/macos/control"
    evidence = control.parent/"evidence"
    try:
        admission()
        budget = json.loads((control/"budget.json").read_text())
        ident = R.identity()
        need(all(budget[k] == v for k, v in ident.items()) and
             budget["soft_deadline_uptime_s"] == budget["started_uptime_s"]+FULL_SOFT_SECONDS and
             budget["hard_deadline_uptime_s"] == budget["started_uptime_s"]+FULL_HARD_SECONDS and
             budget["started_uptime_s"] <= time.monotonic() < budget["hard_deadline_uptime_s"], "original full90 budget")
        result = json.loads((evidence/"result.json").read_text())
        need(all(v.get("owned_group_terminal_verified") is True for v in result["commands"]), "owned writers unverified")
        if any(v["role"] == "full-build" for v in result["commands"]):
            need(result.get("owned_application_cleanup", {}).get("verified") is True, "owned app unverified")
        need(time.monotonic() < budget["hard_deadline_uptime_s"], "full90 sealing exhausted original deadline")
        R.seal("macos")
        need(time.monotonic() < budget["hard_deadline_uptime_s"], "full90 seal exceeded original deadline")
    except BaseException as error:
        (evidence/"f08-manifest.json").unlink(missing_ok=True)
        R.save(control/"UNSEALED.json", {**R.identity(), "kind": "unsealed-controller-receipt",
               "channel": "existing-apple-full90", "native_archive_sealed": False,
               "budget": locals().get("budget"), "reason": repr(error), "f08_accepted": False})
        raise


def audit_mac_full(raw, audit_root, deadline):
    """Called after the original audit has authenticated the complete archive bytes."""
    import time
    from pathlib import Path
    h, n = mac_modules()
    previous = n.DEADLINE
    n.DEADLINE = deadline
    try:
        n.prepare_png_tools(audit_root/"mac-full-validation-tools", audit_root/"mac-full-validation-tools-receipt")
        ident = R.identity(); program = json.loads((raw/"program-identity.json").read_text())
        n.verify_configuration(raw, "macos")
        need(n.verify_program(raw/"program/EXReaderHost.app") == program["program_files"], "full program inventory")
        need(R.sha(raw/"program/EXReaderHost.app/Contents/MacOS/EXReaderHost") == program["program_sha256"], "full program SHA")
        inputs = json.loads((raw/"full-mac-input.json").read_text())
        actual_resources = {k.removeprefix("Contents/Resources/"): v for k,v in program["program_files"].items() if k.startswith("Contents/Resources/")}
        need(actual_resources == inputs["resources"]["files"], "actual fresh sameHEAD resource bytes")
        budget = json.loads((raw/"full-native-budget.json").read_text())
        need(all(budget.get(k) == v for k,v in ident.items()) and budget["soft_deadline_uptime_s"] == budget["started_uptime_s"]+FULL_SOFT_SECONDS and budget["hard_deadline_uptime_s"] == budget["started_uptime_s"]+FULL_HARD_SECONDS, "independent original full90 budget")
        for target in ("macos", "iphonesimulator"):
            sdk = audit_root/(target+"-sdk")/"raw"
            need(inputs["sdk_inputs"][target]["installed_identity"] == json.loads((sdk/"sdk342-installed-identity.json").read_text()) and
                 inputs["sdk_inputs"][target]["sdk_identity"] == json.loads((sdk/"sdk-identity.json").read_text()), "same-run independently authenticated SDK "+target)
        expected = h.driver_sources(ident["source_sha"], program["built_executable_url"])
        for name, text in expected.items():need((raw/name).read_text() == text, "full generated driver "+name)
        need((raw/"ReaderApp.swift").read_text() == h.injected_reader_app((ROOT/"examples/apple/ReaderApp.swift").read_text()) and
             (raw/"Bridge.swift").read_bytes() == (MAC_HERE/"Bridge.swift").read_bytes(), "full test-only App/Bridge")
        _, load_results = n.load_native_tools()
        for group in h.PROFILE["numeric_groups"]:
            folder = raw/"numeric"/group["group"]; bundle = folder/"native.xcresult"
            _, performance = R.extract_metrics(bundle, with_cases=True)
            need(performance == json.loads((folder/"performance-cases.json").read_text()) and
                 load_results(bundle) == json.loads((folder/"test-cases.json").read_text()) and
                 n.observations(folder) == json.loads((folder/"observations.json").read_text()), "independent full native group "+group["group"])
        execution = json.loads((raw/"full-mac-execution.json").read_text())
        sticky = [line for group in h.PROFILE["numeric_groups"]
                  for line in (raw/("numeric-"+group["group"]+".log")).read_text(errors="replace").splitlines()
                  if "F08_BRIDGE_FAIL" in line]
        need(sticky == execution["bridge_failure_log_lines"] and not sticky, "independent sticky bridge log errors")
        assessment = validate_mac_full(raw, ident, program["program_sha256"])
        need(assessment == json.loads((raw/"full-mac-assessment.json").read_text()), "independent full assessment")
        R.save(audit_root/"mac-full-replay.json", assessment)
        need(assessment["complete"], "full Mac evidence incomplete")
        return {"full_mac_assessment": assessment, "original_cases_unchanged": True}
    finally:
        n.DEADLINE = previous

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("guard", "sdk", "native", "seal", "audit"))
    parser.add_argument("--target", choices=("macos", "iphonesimulator"))
    parser.add_argument("--platform", choices=("macos", "iphone", "ipad", "macos-sdk", "iphonesimulator-sdk"))
    args = parser.parse_args()
    need((args.target is not None) == (args.mode == "sdk"), "SDK target")
    need((args.platform is not None) == (args.mode in ("native", "seal")), "native/seal platform")
    if args.mode == "native" and args.platform == "macos":
        need(os.environ.get("F08_APPLE_DIAGNOSTIC", "").lower() != "true", "original full Mac channel")
        native_mac_full()
        return
    if args.mode == "seal" and args.platform == "macos":
        seal_mac_full()
        return
    if args.mode == "audit":
        audit()
        return
    admitted = admission()
    if args.mode == "guard":
        print(json.dumps(admitted))
    elif args.mode == "sdk":
        sdk(args.target)
    elif args.mode == "native":
        need(args.platform in ("macos", "iphone", "ipad"), "native target")
        need(os.environ.get("F08_APPLE_DIAGNOSTIC", "").lower() != "true", "full original Apple cohorts required")
        R.native(args.platform)
    elif args.mode == "seal":
        R.seal(args.platform)
    else:
        audit()


if __name__ == "__main__":
    main()
