"""Check the bounded fifth-sync experiment; never awards F05 acceptance."""
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def main():
    if os.environ.get("GITHUB_ACTIONS") != "true":
        raise RuntimeError("Actions only")
    output = ROOT/"build/f05-r3"
    report = {"F05_accepted":False, "dry_run_passed":False, "controls":{},
              "source":os.environ["GITHUB_SHA"], "run":os.environ["GITHUB_RUN_ID"]}
    try:
        for mode in ("legacy", "ready"):
            coverage = json.loads((output/mode/"coverage.json").read_text())
            trace = json.loads((output/mode/"receive-observations.json").read_text())
            assert coverage["identity"]["source"] == os.environ["GITHUB_SHA"]
            assert coverage["dry_run"] is True and coverage["configuration_mode"] == mode
            assert coverage["F05_accepted"] is False
            assert len(trace["records"]) == 5, "control must reach the actual fifth sync"
            final = trace["records"][-1]
            fixture = final["fixture_before_sync"]
            assert fixture["tls_ready"] and fixture["thread_alive"]
            assert final["fixture_to_sync_seconds"] >= 0
            report["controls"][mode] = {"checkpoint":coverage.get("dry_run_checkpoint"),
                "errors":coverage["errors"], "cleanup_errors":coverage["cleanup_errors"],
                "cleanup_timings":coverage["cleanup_timings"],
                "credential_before_sync":final["credential_before_sync"],
                "fixture_before_sync":fixture, "completed":final["completed"],
                "generation":final.get("generation"),
                "configuration_events":coverage["configuration_events"]}
            assert not coverage["cleanup_errors"], "control cleanup failed"
            assert all(row["seconds"] <= 20 for row in coverage["cleanup_timings"]
                       if row["action"].startswith("native-close-")), "native close exceeded 20 seconds"
            if mode == "ready":
                checkpoint = coverage["dry_run_checkpoint"]
                assert not coverage["errors"] and checkpoint["passed"] is True
                assert checkpoint["sync_index"] == 5 and checkpoint["generation"] > 0
                assert checkpoint["old_pid"] != checkpoint["new_pid"]
                assert checkpoint["session_present_at_network_ready"] == "1"
                assert final["completed"] and final["generation"] > 0
                assert all(final["credential_before_sync"][k] == "1" for k in ("has_user","has_password"))
        legacy = report["controls"]["legacy"]
        report["legacy_failure_reproduced"] = not legacy["completed"]
        report["root_cause_proven"] = False
        report["interpretation"] = ("Readiness-only control differs; inspect both credential timelines"
            if not legacy["completed"] else "Legacy also passed; historical race not reproduced")
        report["dry_run_passed"] = True
    finally:
        (output/"result.json").write_text(json.dumps(report,indent=2)+"\n")
        print(json.dumps(report,indent=2))


if __name__ == "__main__":
    main()
