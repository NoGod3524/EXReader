#!/usr/bin/env python3
"""One Actions-only audit of retained failure evidence; never runs the product."""
import bisect
import copy
import hashlib
import io
import json
import os
import re
import select
import stat
import subprocess
import sys
import time
import zipfile
from pathlib import Path, PurePosixPath

REPO = "NoGod3524/EXReader"
BASE = "25a5d87f0b17a796dbd57dd2c2342893e36f4013"
SOURCE = "878a3f67a2bcfad51d49c67292548e5892185f3d"
RUN, ATTEMPT, ARTIFACT = 41169786301, 1, 13030394230
ZIP_BYTES = 4422645
ZIP_SHA = "d20d1b690625b914f16dadc958c7cbb1409c17681db96896190678d350d0c189"
NAME = "f08-causal-41169786301-1"
HOST_SHA = "1bc210ccef0a9bd9bc4b365cc0386e3127e1f0a52152b3487d1bd94ff2cdeeab"
BRANCH = "codex/dot-f08-causal-failure-audit-20261031"
WORKFLOW = "dot-f08-causal-failure-audit-20261031.yml"
OWNED = (
    "tests/reader_f08_causal_failure_audit_20261031/audit.py",
    ".github/workflows/" + WORKFLOW,
    "docs/reader-total-progress/DOT_F08_CAUSAL_FAILURE_AUDIT_20261031.md",
)
IDENT = dict(GITHUB_SHA=SOURCE, GITHUB_RUN_ID=str(RUN), GITHUB_RUN_ATTEMPT="1")
KINDS = ("page", "font", "shelf", "page", "font", "shelf")
PIDS = (11127, 11163, 11207, 11252, 11285, 11311)
FIELDS = ("sequence", "painted_generation", "book", "page", "font", "busy",
          "saving", "shelf_top_id", "shelf_pending", "shelf_loading", "shelf_restoring")
ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "build/f08-causal-failure-audit"


class Invalid(ValueError):
    pass


def need(ok, code):
    if not ok:
        raise Invalid(code)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def uint(value):
    return type(value) is int and 0 <= value < 2**63


def emit(label, value):
    print(label, json.dumps(value, sort_keys=True, allow_nan=False), flush=True)


def save(name, value):
    (OUT / name).write_text(json.dumps(value, indent=2, sort_keys=True,
                                     allow_nan=False) + "\n", encoding="utf-8")


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        need(key not in result, "duplicate_json_key")
        result[key] = value
    return result


def decode(data):
    return json.loads(data, object_pairs_hook=unique_object,
                      parse_constant=lambda _: need(False, "nonfinite_json"))


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True,
                                   timeout=60).strip()


def api(path):
    data = subprocess.check_output(["gh", "api", "repos/" + REPO + "/" + path],
                                   stderr=subprocess.DEVNULL, timeout=90)
    need(len(data) <= 8 * 1024 * 1024, "metadata_size")
    return decode(data)


def guard():
    need(os.environ.get("GITHUB_ACTIONS") == "true", "Actions_only")
    need(os.environ.get("GITHUB_REPOSITORY") == REPO, "audit_repository")
    need(os.environ.get("GITHUB_RUN_ATTEMPT") == "1", "no_audit_rerun")
    need(os.environ.get("GITHUB_EVENT_NAME") == "push", "audit_event")
    need(os.environ.get("GITHUB_REF") == "refs/heads/" + BRANCH, "audit_branch")
    need(git("rev-parse", "HEAD") == os.environ["GITHUB_SHA"], "audit_source")
    need(git("rev-parse", "HEAD^") == BASE, "audit_parent")
    changed = git("diff", "--name-status", BASE, "HEAD").splitlines()
    need(set(changed) == {"M\t" + p for p in (OWNED[0], OWNED[2])}, "exact_repair_paths")
    need(not git("status", "--porcelain", "--untracked-files=no"), "clean_source")
    listing = api("actions/workflows/" + WORKFLOW + "/runs?branch=" + BRANCH + "&per_page=100")
    save("audit-runs.json", listing)
    runs = listing.get("workflow_runs", [])
    need(listing.get("total_count") == 2 and len(runs) == 2, "two_bounded_audit_runs")
    by_id = {str(run["id"]): run for run in runs}
    need(set(by_id) == {"41174980081", os.environ["GITHUB_RUN_ID"]}, "known_prior_and_current")
    prior = by_id["41174980081"]
    need(prior["head_sha"] == "6725cbd3e496dd8daba81136240e79f70f28f5f3" and
         prior["run_attempt"] == 1 and prior["conclusion"] == "failure", "retained_failed_audit")
    current = by_id[os.environ["GITHUB_RUN_ID"]]
    need(str(current["id"]) == os.environ["GITHUB_RUN_ID"] and
         current["head_sha"] == os.environ["GITHUB_SHA"] and
         current["run_attempt"] == 1, "audit_run_identity")


def producer_identity(run, artifact):
    need(run.get("id") == RUN and run.get("run_attempt") == ATTEMPT and
         run.get("head_sha") == SOURCE and run.get("event") == "push" and
         run.get("conclusion") == "failure" and
         run.get("repository", {}).get("full_name") == REPO, "producer_identity")
    need(artifact.get("id") == ARTIFACT and artifact.get("name") == NAME and
         artifact.get("size_in_bytes") == ZIP_BYTES and
         artifact.get("digest") == "sha256:" + ZIP_SHA and
         artifact.get("expired") is False and
         artifact.get("workflow_run", {}).get("id") == RUN and
         artifact.get("workflow_run", {}).get("head_sha") == SOURCE, "artifact_identity")


def zip_identity(data):
    need(len(data) == ZIP_BYTES and sha(data) == ZIP_SHA, "zip_identity")


def download():
    # Stream a bounded response; gh owns redirect authentication. No token is printed.
    command = ["gh", "api", "repos/" + REPO + "/actions/artifacts/" + str(ARTIFACT) + "/zip"]
    with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL) as proc:
        end, count = time.monotonic() + 90, 0
        try:
            with (OUT / "producer.zip").open("xb") as handle:
                while True:
                    remaining = end - time.monotonic()
                    need(remaining > 0, "download_timeout")
                    ready, _, _ = select.select([proc.stdout], [], [], min(remaining, 1))
                    if not ready:
                        continue
                    block = os.read(proc.stdout.fileno(), min(65536, ZIP_BYTES + 1 - count))
                    if not block:
                        break
                    count += len(block)
                    need(count <= ZIP_BYTES, "download_size")
                    handle.write(block)
            need(proc.wait(timeout=max(1, end - time.monotonic())) == 0, "download_status")
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait()
    data = (OUT / "producer.zip").read_bytes()
    zip_identity(data)
    return data


def inventory(data):
    # Parse in memory only. Retained host.bin/module.so are never extracted or executed.
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        infos = archive.infolist()
        need(0 < len(infos) <= 1000, "zip_member_count")
        need(sum(i.file_size for i in infos) <= 256 * 1024 * 1024, "zip_total_size")
        names, files, rows = set(), {}, []
        for info in infos:
            name = info.filename
            path = PurePosixPath(name)
            parts = name.rstrip("/").split("/")
            normal = str(path).casefold()
            need(info.orig_filename == name and re.fullmatch(r"[A-Za-z0-9_./-]+", name)
                 and not path.is_absolute() and all(p not in ("", ".", "..") for p in parts)
                 and normal not in names, "zip_path")
            names.add(normal)
            mode = stat.S_IFMT(info.external_attr >> 16)
            need(not info.flag_bits & (1 | 64) and
                 mode in (0, stat.S_IFREG, stat.S_IFDIR) and
                 info.compress_type in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED) and
                 0 <= info.file_size <= 64 * 1024 * 1024, "zip_entry_kind_or_size")
            need(mode != stat.S_IFDIR or info.is_dir(), "zip_directory_type")
            need(mode != stat.S_IFREG or not info.is_dir(), "zip_file_type")
            if info.is_dir():
                need(info.file_size == 0, "zip_directory_payload")
                rows.append(dict(name=name, directory=True, bytes=0))
            else:
                payload = archive.read(info)  # Checks CRC after size and member admission.
                need(len(payload) == info.file_size, "zip_member_size")
                files[name] = payload
                rows.append(dict(name=name, bytes=len(payload), sha256=sha(payload)))
        file_names = set(files)
        need(all(str(parent) not in file_names
                 for name in file_names for parent in PurePosixPath(name).parents
                 if str(parent) != "."), "zip_file_parent_collision")
    save("inventory.json", rows)
    emit("F08_INVENTORY", rows)
    return files


def bind_launches(top):
    need(top.get("identity") == IDENT, "driver_identity")
    need(top.get("planned_launches") == 6 and top.get("planned_actions") == 18, "producer_plan")
    need(top.get("accepted") is False and top.get("F08_accepted") is False and
         top.get("physical_display_presented") is False, "producer_failure_retained")
    rows = top.get("cohorts", [])
    need(type(rows) is list and len(rows) == 6 and
         [r.get("launch") for r in rows] == list(range(6)), "launch_inventory")
    need([r.get("kind") for r in rows] == list(KINDS) and
         [r.get("pid") for r in rows] == list(PIDS), "launch_pid_kind")
    for i, row in enumerate(rows):
        need(row.get("passed") is (KINDS[i] == "shelf") and
             len(row.get("actions", [])) == (3 if KINDS[i] == "shelf" else 1), "observed_coverage")
        need(row.get("host_sha256") == row.get("host_sha256_after") == top.get("host_sha256")
             and row.get("module_sha256") == top.get("module_sha256"), "launch_binary_hash")
    return rows


def validate_raw(raw, row):
    need(raw.get("pid") == row["pid"] and raw.get("source") == SOURCE and
         raw.get("run") == str(RUN) and raw.get("attempt") == "1", "raw_identity")
    need(raw.get("schema") == 1 and raw.get("capacity") == 65536, "raw_schema")
    need(uint(raw.get("clock_count")) and raw["clock_count"] <= 64, "clock_count")
    for name in ("states", "inputs", "draws", "frames"):
        need(type(raw.get(name)) is list and len(raw[name]) <= 65536, "bounded_rows")
    for state in raw["states"]:
        need(all(type(state.get(k)) is int and -1 <= state[k] < 2**63 for k in FIELDS)
             and uint(state.get("at")) and uint(state.get("end")) and
             state["end"] >= state["at"] and type(state.get("ok")) is bool, "state_schema")
    for event in raw["inputs"]:
        need(all(uint(event.get(k)) for k in ("at", "server_ms", "type", "code", "hardware", "clock")),
             "input_schema")
    for draw in raw["draws"]:
        need(all(uint(draw.get(k)) for k in ("at", "clock", "counter", "kind")), "draw_schema")
    for frame in raw["frames"]:
        need(all(uint(frame.get(k)) for k in ("clock", "counter", "before", "after",
                                            "frame_time", "predicted", "refresh")) and
             type(frame.get("complete")) is bool and
             (frame.get("presentation") is None or
              uint(frame["presentation"]) and frame["presentation"] > 0), "frame_schema")


def tri_all(values):
    return False if False in values else None if None in values else True


def predicates(state, action):
    field = action["field"]

    def known(keys, test):
        return bool(test()) if all(uint(state.get(k)) for k in keys) else None

    effect = known((field,), lambda: state[field] != action["before"] if field == "shelf_top_id"
                   else state[field] == action["expected"])
    painted = True if field == "shelf_top_id" else known(
        ("painted_generation",), lambda: state["painted_generation"] > action["previous_generation"])
    result = dict(
        effect=effect, painted=painted,
        same_book=known(("book",), lambda: state["book"] == action["book"]),
        settled=known(("busy", "saving"), lambda: not state["busy"] and not state["saving"]),
        not_shelf_loading=known(("shelf_loading",), lambda: not state["shelf_loading"]),
        not_shelf_restoring=known(("shelf_restoring",), lambda: not state["shelf_restoring"]),
    )
    result["original_changed"] = tri_all(list(result.values()))
    result["newer_sequence"] = known(("sequence",), lambda: state["sequence"] > action["previous_sequence"])
    result["write_ok"] = state["ok"]
    result["core_effect"] = tri_all([result[k] for k in
        ("effect", "painted", "same_book", "settled", "newer_sequence", "write_ok")])
    result["unavailable"] = [k for k in FIELDS if not uint(state.get(k))]
    return result


def probe_health(raw):
    issues = []
    for key, expected in (("overflow", 0), ("event_hook", 1), ("draw_hook", 1)):
        if raw.get(key) != expected:
            issues.append(key)
    if not raw["clock_count"]:
        issues.append("no_clocks")
    previous, intervals, frame_keys = {}, [], set()
    for index, frame in enumerate(raw["frames"]):
        clock, counter = frame["clock"], frame["counter"]
        key = (clock, counter)
        if key in frame_keys:
            issues.append("duplicate_frame")
        frame_keys.add(key)
        if clock >= raw["clock_count"] or not 0 < frame["before"] <= frame["after"]:
            issues.append("frame_phase_or_clock")
        old = previous.get(clock)
        if old:
            ordered = counter > old["counter"] and frame["frame_time"] >= old["frame_time"]
            if not ordered:
                issues.append("frame_order")
            intervals.append(dict(clock=clock, previous=old["counter"], counter=counter,
                start=old["before"], end=frame["before"],
                delta_frame_us=frame["frame_time"]-old["frame_time"],
                counter_gap=counter != old["counter"]+1, ordered=ordered,
                classification="unknown"))
        previous[clock] = frame
    if any(d["clock"] >= raw["clock_count"] for d in raw["draws"]):
        issues.append("draw_clock")
    if any(b["at"] < a["at"] for a, b in zip(raw["states"], raw["states"][1:])):
        issues.append("state_time_order")
    return sorted(set(issues)), intervals


def action_report(raw, action, healthy=True):
    field = action["field"]
    need(field in ("page", "font", "shelf_top_id"), "action_field")
    need(all(uint(action.get(k)) for k in ("inject_start", "inject_end", "book", "before",
                 "previous_generation", "previous_sequence", "type", "code")), "action_baseline")
    need(action["inject_start"] <= action["inject_end"], "inject_order")
    need(action.get("expected") is None if field == "shelf_top_id"
         else uint(action.get("expected")), "expected_field")
    start = action["inject_start"]
    done = action.get("done")
    need(done is None or uint(done) and done >= action["inject_end"], "done_order")
    nominal = action["inject_end"] + 180000000
    end = done if done is not None else nominal
    timeline = []
    for index, state in enumerate(raw["states"]):
        phase = ("before_injection" if state["at"] < start else
                 "recorded_action_window" if state["at"] <= end else
                 "after_done" if done is not None else "after_nominal_deadline")
        timeline.append(dict(index=index, state={k: state[k] for k in ("at", "end", "ok") + FIELDS},
                             phase=phase, predicates=predicates(state, action)))
    candidates = [dict(index=i, **event) for i, event in enumerate(raw["inputs"])
                  if start <= event["at"] <= end and
                  event["type"] == action["type"] and event["code"] == action["code"]]
    groups = {}
    for event in candidates:
        key = tuple(event[k] for k in ("server_ms", "type", "code", "hardware"))
        groups.setdefault(key, []).append(event)
    event = min(candidates, key=lambda e: e["at"]) if len(groups) == 1 else None
    if event and event["clock"] >= raw["clock_count"]:
        event = None
    eligible = [r for r in timeline if event and event["at"] <= r["state"]["at"] <= end
                and r["predicates"]["core_effect"] is True]
    eligible.sort(key=lambda r: (r["state"]["at"], r["index"]))
    state_times = [r["state"]["at"] for r in eligible]
    frames = {(f["clock"], f["counter"]): (i, f) for i, f in enumerate(raw["frames"])}
    joins = []
    if event:
        for index, draw in enumerate(raw["draws"]):
            if (draw["clock"] != event["clock"] or
                draw["kind"] != (2 if field == "shelf_top_id" else 1) or
                not event["at"] <= draw["at"] <= end):
                continue
            pair = frames.get((draw["clock"], draw["counter"]))
            if pair is None:
                continue
            frame_index, frame = pair
            if not frame["before"] <= draw["at"] <= frame["after"] <= end:
                continue
            position = bisect.bisect_left(state_times, draw["at"])
            if position == len(eligible):
                continue
            state = eligible[position]
            if field != "shelf_top_id" and state["state"]["at"] > frame["after"]:
                continue
            only_restore = (field != "shelf_top_id" and
                            state["predicates"]["not_shelf_loading"] is True and
                            state["predicates"]["not_shelf_restoring"] is False)
            joins.append(dict(input_index=event["index"], draw_index=index,
                frame_index=frame_index, state_index=state["index"], clock=draw["clock"],
                counter=draw["counter"], shelf_restoring_only_in_this_state=only_restore,
                attribution="unknown_temporal_candidate" if field == "shelf_top_id"
                            else "same_frame_state_generation",
                event_to_matching_paint_us=None if field == "shelf_top_id"
                                          else frame["after"]-event["at"],
                event_to_candidate_paint_us=frame["after"]-event["at"] if field == "shelf_top_id" else None))
    full_true = [r["index"] for r in timeline if start <= r["state"]["at"] <= end and
                 r["state"]["ok"] and r["predicates"]["original_changed"] is True]
    baseline = [r["index"] for r in timeline if r["state"]["sequence"] == action["previous_sequence"]
                and r["state"][field] == action["before"] and r["state"]["book"] == action["book"]]
    baseline_paint = [i for i in baseline if field == "shelf_top_id" or
                      raw["states"][i]["painted_generation"] == action["previous_generation"]]
    reasons = []
    if not event:
        reasons.append("missing_ambiguous_or_unbound_input")
    if not baseline_paint:
        reasons.append("saved_baseline_not_bound_to_raw_state")
    if not eligible:
        reasons.append("no_known_same_book_settled_new_generation_effect")
    if not joins:
        reasons.append("no_matching_draw_frame_state")
    if not healthy:
        reasons.append("probe_or_process_integrity")
    linked = bool(healthy and event and baseline_paint and
                  any(j["shelf_restoring_only_in_this_state"] for j in joins))
    if done is None and full_true:
        reasons.append("contrary_raw_state_satisfies_original_predicate")
    return dict(
        id=action["id"], baseline={k: action.get(k) for k in
            ("field", "before", "expected", "book", "previous_sequence", "previous_generation")},
        injection={k: action[k] for k in ("inject_start", "inject_end", "type", "code")},
        recorded_done=done, recorded_effect_at=action.get("effect_at"),
        nominal_wait_end=nominal if done is None else None,
        exact_wait_start=None, exact_timeout_at=None,
        wait_timing_note="Failed wait starts after inject_end; its exact start/end were not saved.",
        baseline_state_indices=baseline_paint, matching_inputs=candidates,
        distinct_input_groups=len(groups), joins=joins, timeline=timeline,
        original_predicate_true_indices=full_true,
        linked_shelf_restoring_only_state=linked,
        supports_shelf_restoring_candidate=linked and not full_true,
        hidden_shelf_root_cause_confirmed=False,
        missing_evidence=["watcher_delivery_sequence", "watcher_predicate_evaluation",
                          "failed_wait_boundaries", "reader_visibility", "input_focus"],
        contrary_or_missing_reasons=reasons,
    )


def controls():
    run = dict(id=RUN, run_attempt=1, head_sha=SOURCE, event="push", conclusion="failure",
               repository=dict(full_name=REPO))
    artifact = dict(id=ARTIFACT, name=NAME, size_in_bytes=ZIP_BYTES, digest="sha256:"+ZIP_SHA,
                    expired=False, workflow_run=dict(id=RUN, head_sha=SOURCE))
    base = dict(at=10, end=11, ok=True, sequence=1, painted_generation=1, book=1, page=1,
                font=24, busy=0, saving=0, shelf_top_id=1, shelf_pending=0,
                shelf_loading=0, shelf_restoring=1)
    effect = dict(base, at=150, end=160, sequence=2, painted_generation=2, page=2)
    frame = dict(clock=0, counter=1, before=100, after=200, frame_time=90,
                 complete=True, presentation=None, predicted=0, refresh=0)
    raw = dict(clock_count=1, overflow=0, event_hook=1, draw_hook=1, states=[base, effect],
        inputs=[dict(at=120, server_ms=10, type=1, code=65473, hardware=70, clock=0)],
        draws=[dict(at=130, clock=0, counter=1, kind=1)],
        frames=[frame, dict(frame, counter=3, before=1000100, after=1000200, frame_time=1000090)])
    action = dict(id="synthetic", inject_start=90, inject_end=125, type=1, code=65473,
                  field="page", before=1, expected=2, book=1, previous_generation=1, previous_sequence=1)
    rows = [dict(launch=i, kind=kind, pid=PIDS[i], passed=kind=="shelf",
                 actions=[{}]*(3 if kind=="shelf" else 1),
                 host_sha256="h", host_sha256_after="h", module_sha256="m")
            for i, kind in enumerate(KINDS)]
    top = dict(identity=IDENT, planned_launches=6, planned_actions=18, accepted=False,
               F08_accepted=False, physical_display_presented=False, cohorts=rows,
               host_sha256="h", module_sha256="m")
    positive = action_report(raw, action)
    issues, intervals = probe_health(raw)
    need(positive["supports_shelf_restoring_candidate"] and
         positive["hidden_shelf_root_cause_confirmed"] is False and not issues and
         intervals[0]["delta_frame_us"] == 1000000 and intervals[0]["counter_gap"],
         "positive_control")
    results = []

    def rejection(name, expected, operation):
        actual = None
        try:
            operation()
        except Invalid as exc:
            actual = str(exc)
        need(actual == expected, "negative_control_" + name)
        results.append(dict(name=name, expected=expected, actual=actual))

    rejection("producer_identity", "producer_identity",
              lambda: producer_identity(dict(run, head_sha="0"*40), artifact))
    # Same length with a wrong digest, not a size-only rejection.
    rejection("zip_digest", "zip_identity", lambda: zip_identity(b"x"*ZIP_BYTES))
    rejection("missing_launch", "launch_inventory",
              lambda: bind_launches(dict(top, cohorts=rows[:-1])))
    rejection("duplicate_launch", "launch_inventory",
              lambda: bind_launches(dict(top, cohorts=rows[:-1]+[rows[0]])))
    mutations = (
        ("unavailable_effect", lambda r: r["states"][1].update(page=-1)),
        ("missing_input", lambda r: r.update(inputs=[])),
        ("unmet_target_effect", lambda r: r["states"][1].update(page=1)),
        ("wrong_book", lambda r: r["states"][1].update(book=2)),
        ("no_new_generation", lambda r: r["states"][1].update(painted_generation=1)),
        ("busy_saving", lambda r: r["states"][1].update(busy=1, saving=1)),
        ("missing_draw_frame", lambda r: r["draws"][0].update(counter=2)),
        ("shelf_loading", lambda r: r["states"][1].update(shelf_loading=1)),
    )
    for name, change in mutations:
        altered = copy.deepcopy(raw)
        change(altered)
        result = action_report(altered, action)
        need(not result["supports_shelf_restoring_candidate"] and
             not result["linked_shelf_restoring_only_state"], "negative_control_" + name)
        results.append(dict(name=name, expected=False,
                            actual=result["supports_shelf_restoring_candidate"]))
    need(len(results) == 12, "control_count")
    return dict(positive=1, negative=12, passed=True, results=results,
                scope="Synthetic audit checks, not the unexecuted producer 2+8 controls.")


def inspect_launch(files, row):
    number = row["launch"]
    prefix = "launch-%02d/" % number
    need(decode(files[prefix+"driver.json"]) == row, "launch_driver_copy")
    raw_name = prefix + str(row["pid"]) + ".json"
    raw = decode(files[raw_name])
    validate_raw(raw, row)
    health, intervals = probe_health(raw)
    if row.get("exit") != 0 or row.get("observation_failure"):
        health.append("host_exit_or_watcher_failure")
    expected_executable = "/home/runner/work/EXReader/EXReader/build/perf-package/EXReader-Linux/bin/exreader-linux"
    if raw.get("executable") != expected_executable:
        health.append("executable_path")
    if any(a.get("done") is None or a["done"] >= b["inject_start"]
           for a, b in zip(row["actions"], row["actions"][1:])):
        health.append("single_inflight")
    actions = []
    for slot, action in enumerate(row["actions"]):
        kind = row["kind"]
        field = "shelf_top_id" if kind == "shelf" else kind
        code = (0 if slot == 1 else 1) if kind == "shelf" else (
            65473 if kind == "page" else 65475 if slot == 1 else 65474)
        expected = None if kind == "shelf" else action["before"] + (
            1 if kind == "page" else -2 if slot == 1 else 2)
        need(action.get("id") == "%02d-%d" % (number, slot) and
             action.get("slot") == slot and action.get("field") == field and
             action.get("type") == (2 if kind == "shelf" else 1) and
             action.get("code") == code and action.get("expected") == expected, "action_plan")
        actions.append(action_report(raw, action, not health))
    for interval in intervals:
        touched = [a["id"] for a in row["actions"] if
                   a["inject_start"] <= interval["end"] and
                   (a.get("done") or a["inject_end"]+180000000) >= interval["start"]]
        quiet = [q for q in row.get("quiet", []) if
                 q["start"] <= interval["start"] <= interval["end"] <= q["end"]]
        interval.update(touched_actions=touched,
                        classification="mixed_or_action_window" if touched else
                                       "driver_quiet_background_unknown" if quiet else "unknown")
    report = dict(launch=number, kind=row["kind"], pid=row["pid"],
        original_driver_passed=row["passed"], original_action_count=len(row["actions"]),
        host_exit_zero=row.get("exit")==0, observation_failure_present=bool(row.get("observation_failure")),
        raw_name=raw_name, raw_sha256=sha(files[raw_name]), probe_issues=sorted(set(health)),
        row_counts={k:len(raw[k]) for k in ("states", "inputs", "draws", "frames")},
        bundle_authentication="outer ZIP authenticated; binary and launch consistency checked",
        actions=actions, intervals=intervals,
        inputs=raw["inputs"], draws=raw["draws"], frames=raw["frames"],
        quiet_windows=row.get("quiet", []), preparation=row.get("preparation", []),
        presentation_count=sum(f["complete"] and f["presentation"] is not None for f in raw["frames"]),
        hidden_shelf_root_cause_confirmed=False, physical_display_presented=False, F08_accepted=False)
    save("launch-%02d.json" % number, report)
    for action in actions:
        emit("F08_ACTION", dict(launch=number, pid=row["pid"],
                               **{k:v for k,v in action.items() if k != "timeline"}))
        for state in action["timeline"]:
            emit("F08_STATE", dict(launch=number, pid=row["pid"], action=action["id"], **state))
    summary = {k:report[k] for k in ("launch", "kind", "pid", "original_driver_passed",
               "original_action_count", "host_exit_zero", "observation_failure_present", "probe_issues", "row_counts")}
    summary["actions"] = [dict(id=a["id"], input_groups=a["distinct_input_groups"],
        joins=len(a["joins"]), supports_shelf_restoring_candidate=a["supports_shelf_restoring_candidate"],
        contrary_or_missing_reasons=a["contrary_or_missing_reasons"]) for a in actions]
    emit("F08_LAUNCH", summary)
    return summary


def main():
    need(os.environ.get("GITHUB_ACTIONS") == "true", "Actions_only")
    OUT.mkdir(parents=True, exist_ok=False)
    audit_identity = {k:os.environ.get(k) for k in
                      ("GITHUB_SHA", "GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT")}
    receipt = dict(audit_identity=audit_identity, producer_identity=IDENT,
        producer_artifact_id=ARTIFACT, producer_zip_sha256=ZIP_SHA,
        audit_completed=False, producer_accepted=False, F08_accepted=False,
        physical_display_presented=False, formal_progress="95/108",
        original_counts=dict(launches=44, samples=760, positive=2, negative=24),
        producer_plan=dict(launches=6, actions=18, positive=2, negative=8),
        producer_controls_executed=False, launches=[])
    try:
        guard()
        receipt["controls"] = controls()
        save("controls.json", receipt["controls"])
        emit("F08_AUDIT_CONTROLS", receipt["controls"])
        run = api("actions/runs/%d/attempts/%d" % (RUN, ATTEMPT))
        artifact = api("actions/artifacts/" + str(ARTIFACT))
        save("producer-run.json", run)
        save("producer-artifact.json", artifact)
        producer_identity(run, artifact)
        listing = api("actions/runs/%d/artifacts?per_page=100&name=%s" % (RUN, NAME))
        save("producer-artifact-list.json", listing)
        need(listing.get("total_count") == 1 and len(listing.get("artifacts", [])) == 1 and
             listing["artifacts"][0].get("id") == ARTIFACT, "unique_producer_artifact")
        files = inventory(download())
        receipt["producer_zip_authenticated"] = True
        receipt["producer_bundle_present"] = "bundle.json" in files
        receipt["producer_summary_present"] = "summary.json" in files
        receipt["completed_producer_bundle_authenticated"] = False
        if "bundle.json" in files:
            bundle = decode(files["bundle.json"])
            need(bundle.get("identity") == IDENT and
                 bundle.get("files") == {n:sha(data) for n,data in files.items() if n!="bundle.json"},
                 "existing_bundle_inventory")
        receipt["bundle_note"] = ("Producer bundle absent; verification stopped before bundle creation."
                                  if "bundle.json" not in files else
                                  "Manifest hashes checked; this does not accept the failed producer.")
        top = decode(files["driver.json"])
        rows = bind_launches(top)
        need(sha(files["host.bin"]) == top.get("host_sha256") == HOST_SHA, "retained_host")
        need(sha(files["module.so"]) == top.get("module_sha256"), "retained_module")
        receipt["binary_hashes"] = {n:sha(files[n]) for n in ("host.bin", "module.so")}
        expected_launch_files = {"launch-%02d/%s" % (i, name) for i in range(6)
                                 for name in ("driver.json", str(PIDS[i])+".json")}
        actual_launch_files = {name for name in files if name.startswith("launch-")}
        need(actual_launch_files == expected_launch_files, "raw_launch_inventory")
        receipt["attempted_actions"] = sum(len(r["actions"]) for r in rows)
        for row in rows:
            try:
                receipt["launches"].append(inspect_launch(files, row))
            except (Invalid, KeyError, TypeError, ValueError) as exc:
                failure = dict(launch=row["launch"], kind=row["kind"], pid=row["pid"],
                    original_driver_passed=row["passed"],
                    audit_error=str(exc) if isinstance(exc, Invalid) else type(exc).__name__)
                receipt["launches"].append(failure)
                emit("F08_LAUNCH", failure)
        receipt["audit_completed"] = all("audit_error" not in row for row in receipt["launches"])
        receipt["hidden_shelf_root_cause_confirmed"] = False
        receipt["interpretation"] = (
            "Linked rows can identify the only false recorded driver term. "
            "Watcher delivery/evaluation, exact failed wait boundaries, visibility and focus were not retained. "
            "A supporting row does not prove the hidden-shelf root cause or authorize performance acceptance. "
            "Shelf joins remain unknown temporal candidates.")
    except Exception as exc:
        receipt["audit_error"] = str(exc) if isinstance(exc, Invalid) else type(exc).__name__
    save("receipt.json", receipt)
    emit("F08_FAILURE_AUDIT", receipt)
    need(receipt["audit_completed"], "audit_incomplete")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        emit("F08_AUDIT_STOP", dict(code=str(error) if isinstance(error, Invalid) else type(error).__name__))
        sys.exit(1)
