# SPDX-License-Identifier: MIT
"""Actions-only F05 receipt contract gate, not a host producer or final audit.

The independent artifact authenticator must precede this gate. This gate never
turns missing hosts, direct receiver injections, skipped scenarios, or component
results into client acceptance. Current capability blocker is intentionally fatal.
"""
import argparse
import json
import os
from pathlib import Path

HOSTS = {"windows", "linux", "android", "macos", "iphone", "ipad"}
CASES = {
    "offline_reconnect", "concurrent_heads_explicit_resolution",
    "delete_put_tombstone_explicit_restore", "cancel_receive_retry",
    "kill_commit_ack_replay", "restart_offline_read",
}

def require(condition, reason):
    if not condition:
        raise ValueError(reason)

def exact_set(values, expected, name):
    require(isinstance(values, list), name + ": list required")
    require(len(values) == len(set(values)) and set(values) == expected,
            name + ": missing, duplicate, or extra identities")

def check(manifest, bundle, source, run, attempt):
    require(manifest["state"] == "ready-for-client-validation",
            "production capability unresolved; do not dispatch full host CI")
    require(manifest["requirement"] == "F05", "wrong requirement")
    require(bundle["identity"] == {"source": source, "run": run, "attempt": attempt},
            "aggregate source/run/attempt mismatch")
    rows = bundle["hosts"]
    exact_set([row["host"] for row in rows], HOSTS, "hosts")
    for row in rows:
        host = row["host"]
        require(row["identity"] == bundle["identity"], host + ": mixed-source result")
        require(row["program_sha256"] == row["authenticated_program_sha256"]
                and len(row["program_sha256"]) == 64, host + ": program identity")
        require(row["sdk_freeze"] == manifest["sdk_freeze"], host + ": SDK freeze")
        require(row["artifact_authenticated"] is True, host + ": authentication absent")
        require(row["retained_assertions_complete"] is True,
                host + ": retained tests incomplete")
        cases = row["cases"]
        exact_set([case["name"] for case in cases], CASES, host + ": cases")
        for case in cases:
            label = host + ":" + case["name"]
            require(case["outcome"] == "passed", label + ": failed/not-run/skipped")
            require(case["actual_host_actions"] is True, label + ": missing real host")
            require(case["receiver_database_injection"] is False,
                    label + ": direct receiver insertion is not peer synchronization")
            require(case["peer_wire_observed"] is True, label + ": missing wire peer")
            require(case["original_identity_preserved"] is True,
                    label + ": original bytes/SDK mapping changed")
            require(case["reopened_host_readable"] is True, label + ": reopen absent")
            require(case["revision_bytes_preserved"] is True,
                    label + ": replay rewrote immutable bytes")
            require(case["source_evidence"], label + ": missing evidence references")
            if case["name"] == "concurrent_heads_explicit_resolution":
                heads = case["competing_heads"]
                require(len(heads) >= 2 and len(set(heads)) == len(heads),
                        label + ": not actually concurrent")
                exact_set(case["resolution_parents"], set(heads), label + ": parents")
                require(case["explicit_user_resolution"] is True,
                        label + ": implicit conflict winner")
                exact_set(case["final_heads"], {case["resolution_revision"]},
                          label + ": unresolved head set")
            elif case["name"] == "delete_put_tombstone_explicit_restore":
                require(case["stale_peer_did_not_resurrect"] is True,
                        label + ": stale put resurrected deletion")
                require(case["tombstone"] in case["restore_parents"]
                        and case["explicit_user_restore"] is True,
                        label + ": missing explicit tombstone restoration")
            elif case["name"] == "kill_commit_ack_replay":
                require(case["terminated_pid"] != case["reopened_pid"],
                        label + ": no new process")
                require(case["actual_process_termination"] is True
                        and case["duplicate_commits"] == 0, label + ": replay failure")
    return {"receipt_contract_passed": True, "F05_accepted": False,
            "reason": "Contract check alone is not independent full acceptance"}

def main():
    require(os.environ.get("GITHUB_ACTIONS") == "true", "Actions execution only")
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = {"receipt_contract_passed": False, "F05_accepted": False, "errors": []}
    try:
        result.update(check(json.loads(args.manifest.read_text()),
                            json.loads(args.bundle.read_text()),
                            os.environ["GITHUB_SHA"], os.environ["GITHUB_RUN_ID"],
                            os.environ["GITHUB_RUN_ATTEMPT"]))
    except (KeyError, TypeError, ValueError, OSError) as error:
        result["errors"].append(str(error))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    require(result["receipt_contract_passed"], "F05 receipt contract rejected")

if __name__ == "__main__":
    main()
