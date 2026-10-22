#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Gate for the WP12 legacy-migration cloud evidence.

  check_legacy_migration.py identity --out FILE --label NAME --tool EXE --sdk DIR --exporter JS --inputs FILE...
  check_legacy_migration.py gate --evidence DIR --require linux windows [--out SUMMARY.json]

`gate` fails (exit 1) unless every required platform produced scenario evidence with every named
case passing, an end-to-end browser chain that passed, and an identity record. Nothing is inferred:
a missing file is a failure, never a skip."""
import argparse
import glob
import hashlib
import json
import os
import platform
import re
import sys

REQUIRED_CASES = """
metadata_roundtrip status_favorite_mapping original_bytes_exact sdk_rejects_garbage_original dedup_is_content_not_name_or_size
reflow_progress_cfi_anchor reflow_progress_percent_is_approximate note_unique_quote_located note_whitespace_equivalent_quote
note_cjk_quote note_ambiguous_quote_unlocated note_missing_quote_unlocated note_cfi_range_exact note_cfi_disambiguates_repeated_quote
bookmark_with_cfi_is_a_point bookmark_without_cfi_unlocated fixed_progress_is_one_based_to_zero_based fixed_page_note_located
fixed_page_bookmark fixed_missing_quote_unlocated_and_rects_recorded cbz_percent_progress_is_page_estimate audio_positions_and_bookmarks
audio_original_is_unsupported_so_strict_rejects missing_fields_get_defaults unknown_fields_reported_and_kept wrong_type_record_is_item_rejection
missing_original_distinguished unsupported_format_reported orphan_note_preserved memory_metering rerun_same_pack_is_stable
interrupted_run_then_retry_equals_clean_run ledger_loss_does_not_duplicate same_original_different_legacy_id_merges
same_id_changed_original_is_conflict same_note_id_changed_content_is_conflict existing_target_content_is_preserved
corrupt_bad_magic corrupt_unknown_container_version corrupt_truncated corrupt_manifest_digest corrupt_original_digest
corrupt_unknown_manifest_version corrupt_unknown_manifest_format corrupt_duplicate_legacy_ids corrupt_manifest_is_not_json
corrupt_schema_missing_arrays target_not_a_library target_old_schema_not_upgraded target_occupied_by_lock_file target_held_open_exclusively
ledger_without_library_refused ledger_with_unknown_version_refused cancel_midway_keeps_target read_failure_keeps_target
write_failure_after_partial_writes_keeps_target verification_failure_keeps_target publish_failure_keeps_target
ledger_publish_failure_rolls_back_library failed_rollback_is_reported_and_pre_image_kept dry_run_publishes_nothing
new_target_failure_leaves_nothing legacy_backup_zip_converts_to_equivalent_pack inspect_command verify_detects_a_pack_that_was_not_migrated
""".split()
REQUIRED_AREAS = {"metadata", "originals", "progress", "annotations", "fixed", "audio", "fields", "idempotence", "conflicts", "corrupt", "target", "atomicity", "commands"}
NOT_EXECUTED = [
    "Originals above 128 MiB (the SDK in-memory import bound) are rejected as limit-exceeded; streaming migration is not implemented and was not exercised.",
    "Unlocated annotations cannot be stored in the library because no public API accepts an unresolved range; they are preserved only in the ledger sidecar.",
    "Audio originals cannot be stored (the SDK has no audio original format); only positions and bookmarks are migrated.",
    "No installed Tauri desktop build was run: the Tauri shell stores nothing outside its webview IndexedDB, so the same export path applies, but an actual Tauri webview profile was not exercised.",
    "Browsers other than Chromium (Firefox, WebKit) were not exercised.",
    "macOS was not exercised.",
    "Real user libraries from the old application were not available; the dataset is synthetic but created through the old application's own store and library modules.",
]


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def identity(a):
    files = {}
    for root, _, names in os.walk(a.sdk):
        for n in sorted(names):
            if n.endswith((".a", ".lib", ".so", ".dll", ".h", ".cmake")):
                p = os.path.join(root, n)
                files[os.path.relpath(p, a.sdk).replace("\\", "/")] = sha(p)
    record = {
        "schema": 1, "kind": "wp12-legacy-migration-identity", "label": a.label, "platform": platform.platform(),
        "git": {"sha": os.environ.get("GITHUB_SHA"), "ref": os.environ.get("GITHUB_REF")},
        "workflow": {"run_id": os.environ.get("GITHUB_RUN_ID"), "attempt": os.environ.get("GITHUB_RUN_ATTEMPT"), "job": os.environ.get("GITHUB_JOB"), "runner": os.environ.get("RUNNER_NAME"), "image": os.environ.get("ImageVersion")},
        "tool": {"file": os.path.basename(a.tool), "sha256": sha(a.tool)},
        "exporter": {"file": os.path.basename(a.exporter), "sha256": sha(a.exporter)},
        "sdk": {"prefix_files": len(files), "files_sha256": files},
        "inputs": {os.path.basename(p): sha(p) for p in a.inputs if os.path.exists(p)},
    }
    json.dump(record, open(a.out, "w", encoding="utf-8"), indent=1)
    print("identity", a.label, len(files), "SDK files hashed")
    return 0


def gate(a):
    problems, platforms = [], {}
    for label in a.require:
        entry = {"scenarios": None, "e2e": None, "identity": None}
        for kind, pattern in (("scenarios", "scenarios-%s.json"), ("e2e", "e2e-%s.json"), ("identity", "identity-%s.json")):
            path = os.path.join(a.evidence, pattern % label)
            if not os.path.exists(path):
                problems.append("%s: missing %s" % (label, os.path.basename(path)))
                continue
            entry[kind] = json.load(open(path, encoding="utf-8"))
        s = entry["scenarios"]
        if s:
            names = {c["name"]: c for c in s["cases"]}
            recomputed_checks = [check for case in s['cases'] for check in case['checks']]
            if (len(names) != len(s['cases']) or s['summary']['cases'] != len(s['cases']) or
                    s['summary']['passed'] != sum(case['passed'] is True for case in s['cases']) or
                    s['summary']['failed'] != sum(case['passed'] is not True for case in s['cases']) or
                    s['summary']['checks'] != len(recomputed_checks) or
                    s['summary']['checks_passed'] != sum(check['ok'] is True for check in recomputed_checks) or
                    not all(check['ok'] is True for check in recomputed_checks) or
                    any(case['passed'] is not True for case in s['cases'])):
                problems.append('%s: duplicate cases or inconsistent per-check accounting' % label)
            if s["summary"]["cases"] < 30:
                problems.append("%s: only %d scenarios" % (label, s["summary"]["cases"]))
            for name in REQUIRED_CASES:
                if name not in names:
                    problems.append("%s: required case %s did not run" % (label, name))
                elif not names[name]["passed"]:
                    problems.append("%s: case %s failed" % (label, name))
            for c in s["cases"]:
                if not c["passed"]:
                    problems.append("%s: case %s failed" % (label, c["name"]))
                if not c["checks"]:
                    problems.append("%s: case %s asserted nothing" % (label, c["name"]))
            if not REQUIRED_AREAS <= set(s["summary"]["areas"]):
                problems.append("%s: areas missing: %s" % (label, sorted(REQUIRED_AREAS - set(s["summary"]["areas"]))))
        e = entry["e2e"]
        if e:
            if not e["passed"]:
                problems.append("%s: browser end-to-end chain failed" % label)
            if e["indexeddb"]["version"] != 1:
                problems.append("%s: IndexedDB version is %s, not 1" % (label, e["indexeddb"]["version"]))
            if len(e['checks']) != 17 or not all(check['ok'] is True for check in e['checks']):
                problems.append('%s: incomplete browser-chain checks' % label)
        identity = entry['identity']
        if identity:
            if (identity['git']['sha'] != os.environ['GITHUB_SHA'] or
                    identity['workflow']['run_id'] != os.environ['GITHUB_RUN_ID'] or
                    identity['workflow']['attempt'] != os.environ['GITHUB_RUN_ATTEMPT'] or identity['label'] != label):
                problems.append('%s: source, run, attempt or platform identity mismatch' % label)
            files = identity['sdk']['files_sha256']
            hashes = list(files.values()) + [identity['tool']['sha256'], identity['exporter']['sha256']]
            if not files or len(files) != identity['sdk']['prefix_files'] or not all(re.fullmatch('[0-9a-f]{64}', value) for value in hashes):
                problems.append('%s: incomplete SDK or program identity' % label)
            if s and s['tool']['sha256'] != identity['tool']['sha256']:
                problems.append('%s: scenario program differs from identity' % label)
            if e and (e['tool_sha256'] != identity['tool']['sha256'] or e['exporter_sha256'] != identity['exporter']['sha256'] or
                      e['pack']['sha256'] != identity['inputs'].get('legacy.exrpack') or
                      set(e['legacy_sources']) != {'store.js', 'library.js', 'registry.js'} or
                      any(value != identity['inputs'].get(name) for name, value in e['legacy_sources'].items())):
                problems.append('%s: browser-chain inputs or program differ from identity' % label)
            review = os.path.join(a.evidence, 'review-%s.json' % label)
            if not os.path.isfile(review):
                problems.append('%s: missing migration review regressions' % label)
            else:
                record = json.load(open(review, encoding='utf-8'))
                if (record.get('passed') is not True or record.get('source_sha') != os.environ['GITHUB_SHA'] or
                        record.get('run_id') != os.environ['GITHUB_RUN_ID'] or
                        record.get('tool_sha256') != identity['tool']['sha256'] or len(record.get('checks', [])) != 20 or
                        not all(check['passed'] is True for check in record['checks'])):
                    problems.append('%s: incomplete or mismatched migration review regressions' % label)
        platforms[label] = {
            "scenario_cases": s["summary"]["cases"] if s else None, "scenario_passed": s["summary"]["passed"] if s else None,
            "checks": s["summary"]["checks"] if s else None, "checks_passed": s["summary"]["checks_passed"] if s else None,
            "max_peak_rss_bytes": s["summary"]["max_peak_rss_bytes"] if s else None,
            "e2e_passed": e["passed"] if e else None, "browser": e["browser"] if e else None,
            "tool_sha256": entry["identity"]["tool"]["sha256"] if entry["identity"] else None,
            "exporter_sha256": entry["identity"]["exporter"]["sha256"] if entry["identity"] else None,
            "sdk_files": entry["identity"]["sdk"]["prefix_files"] if entry["identity"] else None,
        }
    summary = {"schema": 1, "kind": "wp12-legacy-migration-summary", "complete": not problems, "problems": problems, "required_platforms": a.require,
               "source_sha": os.environ['GITHUB_SHA'], "run_id": os.environ['GITHUB_RUN_ID'], "run_attempt": os.environ['GITHUB_RUN_ATTEMPT'],
               "platforms": platforms, "required_cases": len(REQUIRED_CASES), "not_executed": NOT_EXECUTED,
               "claim": "Legacy IndexedDB/backup migration tool only; this is not complete WP12 high-fidelity conversion."}
    if a.out:
        json.dump(summary, open(a.out, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    print(json.dumps({"complete": summary["complete"], "problems": problems, "platforms": platforms}, indent=1))
    return 0 if summary["complete"] else 1


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    i = sub.add_parser("identity")
    i.add_argument("--out", required=True); i.add_argument("--label", required=True); i.add_argument("--tool", required=True)
    i.add_argument("--sdk", required=True); i.add_argument("--exporter", required=True); i.add_argument("--inputs", nargs="*", default=[])
    g = sub.add_parser("gate")
    g.add_argument("--evidence", required=True); g.add_argument("--require", nargs="+", required=True); g.add_argument("--out")
    a = ap.parse_args()
    return identity(a) if a.cmd == "identity" else gate(a)


if __name__ == "__main__":
    sys.exit(main())
