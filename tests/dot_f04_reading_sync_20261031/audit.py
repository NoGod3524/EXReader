#!/usr/bin/env python3
"""Actions-only F04 staged iPhone/Android strict audit.

Runs the unchanged prior relay assertions first, then verifies additional
application-authored bookmark/range bytes and explicit receiver landings.
A passing stage can NEVER set the complete six-target F04 flag.
"""
import argparse, base64, hashlib, io, json, os, subprocess, sys, zipfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
BASE = "94fb236a4a2da87dfbaf4f1dd2a47885d615a230"

def active_contract():
    contract = json.loads((HERE / "contract.json").read_text())
    scope_name = os.environ.get("F04_SCOPE")
    need(scope_name in contract["execution_scopes"], "approved execution scope")
    need(os.environ.get("GITHUB_REF") == "refs/heads/" + contract["canonical"]["branch"], "canonical execution branch")
    need(os.environ.get("F04_CONTROLLER_SHA") == os.environ["GITHUB_SHA"], "controller/source mismatch")
    scope = contract["execution_scopes"][scope_name]
    return contract, scope_name, scope

def producer_job_name(contract, name):
    scope = contract["execution_scopes"].get(os.environ.get("F04_SCOPE"), {})
    return scope.get("caller_job", contract["canonical"]["caller_job"]) + " / " + name

def same_run_head(fetch, current):
    run = fetch("actions/runs/" + current["run_id"])
    need(run["head_sha"] == current["source_sha"] == os.environ["F04_CONTROLLER_SHA"] and
         str(run["run_attempt"]) == current["attempt"], "controller/product/run head identity")

def need(value, message):
    if not value:
        raise AssertionError(message)

def revisions(state):
    rows = {}
    for path, entry in state["entries"].items():
        body = base64.b64decode(entry["body"], validate=True)
        need(hashlib.sha256(body).hexdigest() == entry["sha256"], "wire digest")
        if "/revisions/" in path and path.endswith(".json"):
            value = json.loads(body)
            need(value["id"] not in rows, "duplicate revision id")
            rows[value["id"]] = (value, body)
    return rows

def selected(rows, marker):
    marked = [(wire, body) for wire, body in rows.values()
              if wire.get("payload") and marker in wire["payload"].get("text", "")]
    need(marked, "missing application-authored marker " + marker)
    entities = {wire["entity_key"] for wire, _ in marked}
    need(len(entities) == 1, "ambiguous marker entity " + marker)
    entity = next(iter(entities))
    history = [wire for wire, _ in rows.values() if wire["entity_key"] == entity]
    by_id = {wire["id"]: wire for wire in history}
    for wire in history:
        need(len(wire["parents"]) == len(set(wire["parents"])), "duplicate parents")
        need(all(parent in by_id for parent in wire["parents"]), "missing or foreign parent")
    visiting, done = set(), set()
    def visit(revision):
        need(revision not in visiting, "cyclic revision history")
        if revision in done:
            return
        visiting.add(revision)
        for parent in by_id[revision]["parents"]:
            visit(parent)
        visiting.remove(revision)
        done.add(revision)
    for revision in by_id:
        visit(revision)
    parents = {parent for wire in history for parent in wire["parents"]}
    heads = [wire for wire in history if wire["id"] not in parents]
    need(len(heads) == 1 and heads[0].get("operation") != "delete", "not SAFE unique head")
    head = heads[0]
    need(head.get("payload") and marker in head["payload"].get("text", ""), "current marker absent")
    original = json.loads((HERE / "contract.json").read_text())["original"]
    expected_book = original["format"] + ":" + original["sha256"]
    need(head["entity_kind"] == "annotation" and head["payload"]["book_key"] == expected_book,
         "wrong original book")
    need(head["entity_key"] == expected_book + ":" + head["payload"]["annotation_id"],
         "global annotation identity")
    return head, rows[head["id"]][1]

def compare_location(location, observed):
    selector = location["selector"]
    for key in ("start", "end", "exact", "prefix", "suffix"):
        need(observed[key] == selector[key], "original selector changed: " + key)
    need(observed["part"] == location["part"] and observed["path"] == location["part_path"],
         "original EPUB routing changed")

def android_landing(frame, location):
    target = location["selector"]["start"]
    need(frame["part"] == location["part"] and frame["path"] == location["part_path"], "Android route")
    need(frame["start"] <= target < frame["end"], "Android displayed page does not contain original anchor")
    need(frame["bitmap_width"] > 0 and frame["bitmap_height"] > 0, "Android blank landing")

def apple_landing(checkpoint, location, original_sha):
    need(checkpoint["sdk_version"] == "3.42.0", "actual Apple SDK identity")
    books = checkpoint["books"]
    need(len(books) == 1, "Apple actual one-original library")
    book = books[0]
    need(book["storage"] == "epub" and not book["unresolved_progress"], "Apple unresolved target")
    need(book["part"] == location["part"] and book["path"] == location["part_path"], "Apple route")
    need(book["reading_offset"] == location["selector"]["start"], "Apple original anchor offset")
    need(len(book["page_text_sha256"]) == 64, "Apple rendered page identity missing")

def main():
    need(os.environ.get("GITHUB_ACTIONS") == "true", "Actions only")
    path = "tests/apple_android_relay/verify.py"
    source = (ROOT / path).read_text()
    need(source.encode() == subprocess.check_output(["git", "show", BASE + ":" + path], cwd=ROOT),
         "original strict verifier changed")
    old_root = "ROOT = Path(__file__).resolve().parents[2]"
    need(source.count(old_root) == 1, "original root drift")
    source = source.replace(old_root, "ROOT = Path(" + repr(str(ROOT)) + ")", 1)
    old_import = "sys.path.insert(0, str(Path(__file__).parent))"
    need(source.count(old_import) == 1, "original relay import drift")
    source = source.replace(old_import, "sys.path.insert(0, " + repr(str(HERE)) + ")", 1)
    # Authenticate the exact service used in this stage, not the retained old service.
    source = source.replace("ROOT / 'tests/apple_android_relay/relay.py'",
                            "ROOT / 'tests/dot_f04_reading_sync_20261031/relay.py'")
    generated = ROOT / "build/f04-driver/original-strict.py"
    generated.parent.mkdir(parents=True, exist_ok=True)
    generated.write_text(source)
    scope = {"__name__": "__f04_retained_strict__", "__file__": str(generated)}
    output = {"source_sha": os.environ["GITHUB_SHA"], "run_id": os.environ["GITHUB_RUN_ID"],
              "attempt": os.environ["GITHUB_RUN_ATTEMPT"], "stage_accepted": False,
              "F04_accepted": False, "six_target_accepted": False, "failures": [],
              "scope": "iPhone Simulator -> Android emulator -> fresh iPhone; single EPUB reading records"}
    try:
        exec(compile(source, str(generated), "exec"), scope)
        need(scope["summary"]["accepted"] is True, "retained original relay evidence failed")
        first, android, returned = scope["states"]
        for state in (first, android, returned):
            need(state["data"]["f04_stage"] == "iphone-android-reading-v1", "stage identity")
            need(state["data"]["sdk_version"] == "3.42.0", "SDK identity")
        initial_rows, middle_rows, final_rows = map(revisions, (first, android, returned))
        for revision, pair in initial_rows.items():
            need(middle_rows[revision][1] == pair[1] and final_rows[revision][1] == pair[1],
                 "original Apple wire changed")
        incoming = android["data"]["incoming_records"]
        outgoing = android["data"]["outgoing_records"]
        checked = []
        for role, marker in (("bookmark", "F04_APPLE_BOOKMARK"), ("note", "F04_APPLE_NOTE")):
            wire, raw = selected(initial_rows, marker)
            matches = [r for r in incoming if r["head"] == wire["id"]]
            need(len(matches) == 1, "Android must observe exact original head")
            observed = matches[0]
            need(base64.b64decode(observed["wire_b64"], validate=True) == raw,
                 "public retained API returned rewritten wire")
            location = wire["payload"]["location"]
            compare_location(location, observed)
            need((location["selector"]["start"] == location["selector"]["end"]) == (role == "bookmark"),
                 "point/range distinction")
            android_landing(android["data"]["incoming_" + role + "_frame"], location)
            checked.append({"direction": "iphone->android", "kind": role, "head": wire["id"],
                            "wire_sha256": hashlib.sha256(raw).hexdigest()})
        for role, marker in (("bookmark", "F04_ANDROID_BOOKMARK"), ("note", "F04_ANDROID_NOTE")):
            wire, raw = selected(middle_rows, marker)
            matches = [r for r in outgoing if r["head"] == wire["id"]]
            need(len(matches) == 1 and base64.b64decode(matches[0]["wire_b64"], validate=True) == raw,
                 "Android outgoing exact retained wire")
            need(final_rows[wire["id"]][1] == raw, "return transfer changed raw wire")
            location = wire["payload"]["location"]
            compare_location(location, matches[0])
            need((location["selector"]["start"] == location["selector"]["end"]) == (role == "bookmark"),
                 "point/range distinction")
            apple_landing(returned["data"]["f04_checkpoints"]["incoming-" + role],
                          location, scope["summary"]["original_sha256"])
            checked.append({"direction": "android->iphone", "kind": role, "head": wire["id"],
                            "wire_sha256": hashlib.sha256(raw).hexdigest()})
        need(set(android["data"]["f04_checks"]) ==
             {"peer_bookmark_and_annotation_originals_resolve", "create_return_bookmark_and_annotation"},
             "extra UI cases missing")
        output.update(stage_accepted=True, original_relay_accepted=True, record_checks=checked,
                      artifacts=scope["summary"]["artifacts"],
                      remaining_targets=["Windows", "Linux GTK", "macOS", "iPad"],
                      remaining_scope=["six-host connected bidirectional product graph", "retained protocol and host no-mislocation evidence"])
    except Exception as error:
        output["failures"].append(type(error).__name__ + ": " + str(error))
        raise
    finally:
        destination = ROOT / "build/apple-android/f04-summary.json"
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n")
        print(json.dumps(output, ensure_ascii=False), flush=True)

def graph_audit(manifest_path):
    """Audit a real connected graph; no all-pairs or six-author requirement.

    This preparation checker establishes the wire/UI graph only. Final retained
    producer authentication and its CI budget are still explicit pending work;
    it cannot promote the F04 catalog.
    """
    need(os.environ.get("GITHUB_ACTIONS") == "true", "Actions only")
    from relay import load, input_metadata
    manifest = json.loads(manifest_path.read_text())
    contract, scope_name, scope = active_contract()
    required = set(scope["hosts"])
    nodes, edges, checked = {}, set(), []
    identity = {k: os.environ[v] for k, v in
                (("source_sha", "GITHUB_SHA"), ("run_id", "GITHUB_RUN_ID"), ("attempt", "GITHUB_RUN_ATTEMPT"))}
    for item in manifest["states"]:
        state, digest = load(manifest_path.parent / item["path"])
        need(digest == item["sha256"], "state identity")
        need(all(state[k] == v for k, v in identity.items()), "same-source/run/attempt")
        data = state["data"]; host = data["platform"]
        need(host in required and data["sdk_version"] == "3.42.0", "host/SDK identity")
        need(data["program"]["bytes"] > 0 and len(data["program"]["sha256"]) == 64, "real program identity")
        nodes[digest] = (host, state, revisions(state))
    for edge in manifest["edges"]:
        sender, source, source_rows = nodes[edge["from"]]
        receiver, destination, destination_rows = nodes[edge["to"]]
        need(sender != receiver, "edge must cross real host roles")
        need(destination["previous_sha256"] == edge["from"], "actual staged transport predecessor")
        data = destination["data"]
        for revision, pair in source_rows.items():
            need(revision in destination_rows and destination_rows[revision][1] == pair[1], "immutable wire changed in transport")
        expected_progress = input_metadata(source)["location"]
        progress_id = expected_progress["head"]
        need(destination_rows[progress_id][1] == source_rows[progress_id][1], "exact progress wire")
        if receiver in ("iphone-simulator", "ipad-simulator", "macos"):
            checkpoint = data["f04_checkpoints"].get("position")
            need(checkpoint is not None, "Apple position checkpoint")
            apple_landing(checkpoint, source_rows[progress_id][0]["payload"]["location"], data["original_sha256"])
        elif receiver == "android-api34-x86_64":
            android_landing(data["restored_frame"], source_rows[progress_id][0]["payload"]["location"])
        elif receiver == "windows":
            need("独立原书与当前绘图文档" in data["progress_navigation"]["native_message"], "Windows progress public FOUND")
        else:
            nav = data["progress_navigation"]; frame = nav["frame"]; target = expected_progress["start"]
            need(nav["record_state"]["match"] == "1" and frame["part"] == expected_progress["part"] and
                 frame["start"] <= target < frame["end"], "GTK progress exact target page")
        for role, marker in edge["markers"].items():
            need(role in ("bookmark", "note"), "supported record role")
            wire, raw = selected(source_rows, marker)
            location = wire["payload"]["location"]
            need((location["selector"]["start"] == location["selector"]["end"]) == (role == "bookmark"), "point/range preserved")
            if receiver in ("iphone-simulator", "ipad-simulator", "macos"):
                checkpoint = data["f04_checkpoints"]["incoming-" + role]
                apple_landing(checkpoint, location, data["original_sha256"])
                observed = checkpoint["retained_records"]
                need(any(row["revision_id"] == wire["id"] and
                         base64.b64decode(row["raw_base64"], validate=True) == raw for row in observed),
                     "Apple actual retained wire")
            elif receiver == "android-api34-x86_64":
                matched = [row for row in data["incoming_records"] if row["head"] == wire["id"]]
                need(len(matched) == 1 and base64.b64decode(matched[0]["wire_b64"], validate=True) == raw,
                     "Android public retained wire")
                android_landing(data["incoming_" + role + "_frame"], location)
            else:
                need(any(row["revision_id"] == wire["id"] and
                         base64.b64decode(row["raw_base64"], validate=True) == raw for row in data["incoming"]),
                     "desktop actual retained wire")
                navigation = [n for n in data["navigations"] if n["marker"] == marker]
                need(len(navigation) == 1, "real explicit record action")
                if receiver == "windows":
                    need("独立原书与当前绘图文档" in navigation[0]["native_message"], "native independent/current FOUND")
                else:
                    need(navigation[0]["record_state"]["match"] == "1", "GTK native FOUND")
                    frame = navigation[0]["frame"]; anchor = location["selector"]["start"]
                    need(frame["part"] == location["part"] and frame["start"] <= anchor < frame["end"],
                         "GTK frame contains original anchor")
            checked.append({"from": sender, "to": receiver, "kind": role,
                            "revision_id": wire["id"], "wire_sha256": hashlib.sha256(raw).hexdigest()})
        need(set(edge["markers"]) == {"bookmark", "note"}, "edge record coverage")
        need("remote_sync_does_not_move_active_reader" in data["checks"] or
             receiver in ("iphone-simulator", "ipad-simulator", "macos", "android-api34-x86_64"),
             "desktop receive non-navigation observation")
        edges.add((sender, receiver))
    observed_hosts = {host for host, _, _ in nodes.values()}
    need(observed_hosts == required, "actual host roles for fixed execution scope")
    for start in required:
        seen, pending = {start}, [start]
        while pending:
            current = pending.pop()
            for a, b in edges:
                if a == current and b not in seen: seen.add(b); pending.append(b)
        need(seen == required, "graph is not bidirectionally connected from " + start)
    report = dict(identity, scope=scope_name, graph_checked=True, graph_checks=checked, hosts=sorted(required),
                  F04_accepted=False, six_target_accepted=False,
                  remaining=["authenticate retained original protocol/host producers",
                             "same-source executable runtime verification; this preparation is not final acceptance"])
    target = manifest_path.parent / "f04-graph-summary.json"
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False), flush=True)


def authenticated_builds(contract, current, jobs, artifacts):
    from check_parallel_integration import download_artifact_zip
    ids = json.loads(os.environ["F04_BUILD_IDS"])
    need(set(ids) == set(active_contract()[2]["build_keys"]), "build artifact ID map")
    receipts = {}
    for binding in [b for b in contract["build_producers"] if b["key"] in active_contract()[2]["build_keys"]]:
        found_jobs = [j for j in jobs if j["name"] == producer_job_name(contract, binding["job"])]
        need(len(found_jobs) == 1 and found_jobs[0]["conclusion"] == "success" and
             found_jobs[0]["head_sha"] == current["source_sha"], "build producer job")
        rows = [a for a in artifacts if a["id"] == ids[binding["key"]]]
        need(len(rows) == 1 and not rows[0]["expired"], "build artifact ID")
        artifact = rows[0]
        need(artifact["workflow_run"]["head_sha"] == current["source_sha"] and
             str(artifact["workflow_run"]["id"]) == current["run_id"], "build artifact source/run")
        blob = download_artifact_zip(artifact["id"])
        need(len(blob) == artifact["size_in_bytes"] and
             "sha256:" + hashlib.sha256(blob).hexdigest() == artifact["digest"], "build original ZIP identity")
        with zipfile.ZipFile(io.BytesIO(blob)) as archive:
            names = archive.namelist()
            need(len(set(names)) == len(names) and all(not PurePosixPath(n).is_absolute() and
                 ".." not in PurePosixPath(n).parts and "\\" not in n and not n.endswith(".key")
                 for n in names), "build unsafe/private archive")
            receipt_raw = archive.read("build-receipt.json")
            receipt = json.loads(receipt_raw)
            need(all(str(receipt[k]) == v for k, v in current.items()), "build receipt identity")
            need(receipt["platform"] == binding["platform"] and receipt["sdk_version"] == "3.42.0" and
                 receipt["sdk_source"] == contract["sdk_source"], "build target/SDK")
            expected_recipe = {"windows": "tests/windows_sdk342/build.py",
                "gtk": "tests/gtk_sdk342_package/run.py", "android": "tests/android_sdk342_package/run.py",
                "macos": "tests/apple_sdk342_host/build.py", "iphonesimulator": "tests/apple_sdk342_host/build.py"}[binding["platform"]]
            need(receipt["recipe"] == expected_recipe, "build recipe path")
            recipe = ROOT / expected_recipe
            need(hashlib.sha256(recipe.read_bytes()).hexdigest() == receipt["recipe_sha256"], "build recipe identity")
            if receipt["program"] is not None:
                binary = archive.read("program.bin")
                need(len(binary) == receipt["program"]["bytes"] and
                     hashlib.sha256(binary).hexdigest() == receipt["program"]["sha256"], "built program bytes")
            else:
                manifest_raw = archive.read("sdk342-installed-identity.json")
                need(hashlib.sha256(manifest_raw).hexdigest() == receipt["installed_identity_sha256"], "installed SDK manifest")
                manifest = json.loads(manifest_raw)
                need(all(str(manifest[k]) == v for k, v in current.items()), "installed SDK identity")
                for root, entries in (("sdk", manifest["sdk_files"]), ("raw-products", manifest["raw_files"])):
                    for path, identity in entries.items():
                        content = archive.read(root + "/" + path)
                        need(len(content) == identity["bytes"] and hashlib.sha256(content).hexdigest() == identity["sha256"],
                             "installed SDK/product bytes")
        receipts[binding["key"]] = receipt_raw
    return receipts

def authenticate_graph():
    """Original Actions ZIP/API authentication before the graph checker.

    Artifact IDs come from the current producer upload outputs, never a name-only
    selection among uploaded files. This does not waive the separate retained-protocol audit.
    """
    need(os.environ.get("GITHUB_ACTIONS") == "true", "Actions only")
    sys.path.insert(0, str(ROOT / "tools"))
    from check_parallel_integration import fetch, pages, download_artifact_zip
    from relay import identity
    current = identity()
    run_id, attempt = current["run_id"], current["attempt"]
    contract = json.loads((HERE / "contract.json").read_text())
    contract, scope_name, scope = active_contract()
    bindings = [b for b in contract["graph_producers"] if b["artifact"] in scope["graph_artifacts"]]
    same_run_head(fetch, current)
    jobs = pages("actions/runs/" + run_id + "/attempts/" + attempt + "/jobs", "jobs")
    artifacts = pages("actions/runs/" + run_id + "/artifacts", "artifacts")
    producer_ids = json.loads(os.environ["F04_ARTIFACT_IDS"])
    need(set(producer_ids) == {b["artifact"] for b in bindings}, "producer artifact ID map")
    need(all(type(v) is int and v > 0 for v in producer_ids.values()), "positive producer artifact IDs")
    need(len(set(producer_ids.values())) == len(producer_ids), "one artifact ID reused across producers")
    out = ROOT / "build/f04-graph-auth"
    out.mkdir(parents=True, exist_ok=False)
    manifest = {"states": [], "edges": [], "artifact_identities": [], "producer_jobs": []}
    accepted_states = {}
    build_receipts = authenticated_builds(contract, current, jobs, artifacts)
    for binding in bindings:
        matches = [j for j in jobs if j["name"] == producer_job_name(contract, binding["job"])]
        need(len(matches) == 1 and matches[0]["conclusion"] == "success" and
             matches[0]["head_sha"] == current["source_sha"], "failed/missing/duplicate graph producer")
        manifest["producer_jobs"].append({k: matches[0][k] for k in ("id", "name", "head_sha", "conclusion")})
        artifact_id = producer_ids[binding["artifact"]]
        matches = [a for a in artifacts if a["id"] == artifact_id]
        need(len(matches) == 1 and not matches[0]["expired"], "missing or expired producer artifact ID")
        row = matches[0]
        need(row["workflow_run"]["head_sha"] == current["source_sha"] and
             str(row["workflow_run"]["id"]) == run_id, "artifact source/run")
        raw = download_artifact_zip(row["id"])
        need(len(raw) == row["size_in_bytes"] and "sha256:" + hashlib.sha256(raw).hexdigest() == row["digest"], "original ZIP identity")
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            names = archive.namelist()
            need(len(names) == len(set(names)) and all(not PurePosixPath(n).is_absolute() and
                 ".." not in PurePosixPath(n).parts and "\\" not in n for n in names), "unsafe archive members")
            need(all(PurePosixPath(n).name != "key.pem" and
                     "private" not in PurePosixPath(n).parts and "profile" not in PurePosixPath(n).parts
                     for n in names), "private fixture/profile files must not be handoff artifacts")
            # No extraction of producer-controlled paths.
            state_raw = archive.read("state.json"); state = json.loads(state_raw)
            result_name = "report.json" if binding["host"] == "android-api34-x86_64" else "result.json"
            result = json.loads(archive.read(result_name))
            for value in (state, state["data"], result):
                need(all(str(value[k]) == v for k, v in current.items()), "phase source/run/attempt")
            need(state["data"]["passed"] is True and result["passed"] is True and
                 not result.get("cleanup_errors"), "producer result/cleanup failure")
            need(state["data"]["platform"] == binding["host"], "producer host role")
            receipt_raw = archive.read("build-receipt.json")
            need(receipt_raw == build_receipts[binding["build_key"]], "phase/build receipt bytes")
            built = json.loads(receipt_raw)
            program = archive.read("program.bin")
            need(len(program) == state["data"]["program"]["bytes"] and
                 hashlib.sha256(program).hexdigest() == state["data"]["program"]["sha256"], "actual program bytes")
            if built["program"] is not None:
                need(built["program"]["sha256"] == state["data"]["program"]["sha256"] and
                     built["program"]["bytes"] == len(program), "installed/build program differs")
            else:
                need(hashlib.sha256(archive.read("installed-identity.json")).hexdigest() ==
                     built["installed_identity_sha256"], "phase installed SDK differs")
                need(state["data"]["program"]["bundle_source_sha"] == current["source_sha"] and
                     state["data"]["program"]["bundle_id"] == "org.exreader.host", "actual Apple bundle identity")
            need(state["server"]["certificate_sha256"] == hashlib.sha256(archive.read("cert.pem")).hexdigest(), "phase certificate identity")
            need(state["server"]["implementation_sha256"] == hashlib.sha256((HERE / "relay.py").read_bytes()).hexdigest(), "relay source")
            need(state["server"]["dav_implementation_sha256"] ==
                 hashlib.sha256((ROOT / "tests/reader_d23_relay/relay.py").read_bytes()).hexdigest(), "DAV source")
            requests = json.loads(archive.read("requests.json"))
            need(requests and all(r["authenticated"] for r in requests), "actual authenticated request evidence")
            need(any(r["method"] == "PUT" and "/revisions/" in r["path"] for r in requests) or
                 binding["role"] == "return", "actual app publication")
            if binding["role"] != "seed" and binding["fresh_profile"]:
                need(any(r["method"] == "GET" and "/objects/" in r["path"] for r in requests), "fresh-profile actual app original receive")
            original = contract["original"]
            originals = [base64.b64decode(v["body"], validate=True) for path, v in state["entries"].items() if "/objects/" in path]
            need(len(originals) == 1 and len(originals[0]) == original["bytes"] and
                 hashlib.sha256(originals[0]).hexdigest() == original["sha256"], "fixed original bytes")
        digest = hashlib.sha256(state_raw).hexdigest()
        filename = binding["artifact"] + ".json"
        (out / filename).write_bytes(state_raw)
        manifest["states"].append({"path": filename, "sha256": digest})
        manifest["artifact_identities"].append({k: row[k] for k in ("id", "name", "digest", "size_in_bytes")})
        accepted_states[binding["artifact"]] = (state, digest)
    for binding in bindings:
        if binding["role"] == "seed": continue
        source, source_digest = accepted_states[binding["previous"]]
        destination, destination_digest = accepted_states[binding["artifact"]]
        need(destination["previous_sha256"] == source_digest, "exact staged predecessor")
        manifest["edges"].append({"from": source_digest, "to": destination_digest,
            "markers": {"bookmark": binding["incoming_prefix"] + "_BOOKMARK",
                        "note": binding["incoming_prefix"] + "_NOTE"}})
    path = out / "manifest.json"
    path.write_text(json.dumps(manifest, indent=2))
    graph_audit(path)

def retained_evidence(bundle, current):
    """Pure acceptance of original reports and their actual probe programs."""
    receipt, sdk, raw, legacy, wire, wire_raw = (bundle[k] for k in
        ("receipt", "sdk", "raw", "legacy", "wire", "wire_raw"))
    for report in (receipt, sdk, wire):
        need(all(str(report[k]) == v for k, v in current.items()), "retained identity")
    need(receipt["sdk_version"] == "3.42.0" and
         receipt["sdk_source"] == "8357eafa28423a7ab93ba08b823af80f01ad1505", "retained SDK")
    need(receipt["original_four_zip_aggregate"] == "not-run", "retained aggregate scope")
    need(receipt.get("legacy_catalog_source") == "210403d121d6484a8fff4ea7ffd911efa3163535" and
         receipt.get("legacy_revisions_source") == receipt["legacy_catalog_source"] and
         receipt.get("legacy_product_prefix") == "build/v1-product-stage" and
         receipt.get("current_product_prefix") == "build/v2-product-stage", "legacy provider identity")
    def cache_value(text, key):
        rows = [line.split("=", 1)[1] for line in text.splitlines()
                if line.startswith(key + ":") and "=" in line]
        need(len(rows) == 1, "legacy cache field")
        return rows[0].replace("\\", "/")
    caches = bundle["legacy_caches"]
    need(cache_value(caches["v1-product"], "CMAKE_HOME_DIRECTORY").endswith("/build/v1-source/apps/reader/store/native"),
         "legacy catalog source path")
    need(cache_value(caches["v1-revisions"], "READER_PRODUCT_PREFIX").endswith("/build/v1-product-stage"),
         "legacy revisions product prefix")
    for name in ("v1-adapter", "v1-consumer"):
        prefix = cache_value(caches[name], "CMAKE_PREFIX_PATH")
        need("build/v1-product-stage" in prefix and "build/v2-product-stage" not in prefix, "legacy consumer product prefix")
    link = bundle["legacy_link"].replace("\\", "/")
    need("v1-product-stage/lib/" in link and "v2-product-stage/" not in link, "legacy linked catalog")

    need(sdk["accepted"] is True and wire["accepted"] is True, "retained report refused")
    need(all(str(legacy["identity"][variable]) == current[key] for key, variable in
         (("source_sha", "GITHUB_SHA"), ("run_id", "GITHUB_RUN_ID"), ("attempt", "GITHUB_RUN_ATTEMPT"))),
         "legacy identity")
    need(legacy["sdk_version"] == "3.42.0", "legacy actual SDK")
    need(bundle["legacy_report_sha256"] == legacy["report_sha256"] and
         len(bundle["legacy_raw"]["checks"]) == legacy["checks_total"] and
         all(c["pass"] is True for c in bundle["legacy_raw"]["checks"]), "legacy summary/raw")
    need(not legacy["problems"] and legacy["v1_highlight_roundtrip_accepted"] is True and
         legacy["checks_total"] >= 121 and legacy["checks_failed"] == 0, "original 121 checks")
    need(raw["failures"] == 0 and raw["checks"] and all(c["pass"] is True for c in raw["checks"]),
         "original capture raw checks")
    need(sdk["checks"] == len(raw["checks"]) and sdk["cases"] == raw["cases"], "capture summary/raw")
    sys.path.insert(0, str(ROOT / "tests/reader_reading_v2"))
    from check_sdk import EXPECTED
    for report in (sdk, wire):
        need([c["id"] for c in report["cases"]] == EXPECTED, "original 18 cases")
        need(report["receiver_found"] == 17 and report["receiver_mislocated"] == 0, "original anchor outcomes")
        need(all(c["state"] == ("AMBIGUOUS" if c["id"] == "txt-ambiguous" else "FOUND")
                 for c in report["cases"]), "original ambiguous/FOUND outcomes")
    need(wire_raw["cases"] == wire["cases"] and wire_raw["failures"] == 0 and wire_raw["checks"] and
         all(c["pass"] is True for c in wire_raw["checks"]), "native transport raw checks")
    need(wire_raw["native_webdav"] is True and wire_raw["originals_exported"] == 4 and
         wire_raw["network_pushed"] == 22 and wire_raw["metadata_projected"] == 4 and
         wire_raw["network_pulled"] >= 22, "native transport raw outcomes")
    need(all(wire[k] == wire_raw[k] for k in ("originals_exported", "network_pushed",
         "metadata_projected", "network_pulled")), "native transport summary/raw counters")
    need(wire["originals_exported"] == 4 and wire["network_pushed"] == 22 and
         wire["network_pulled"] >= 22 and wire["metadata_projected"] == 4 and
         wire["request_count"] > 0, "native original/record transport")
    need(bundle["sdk_program_sha256"] == sdk["consumer_sha256"] and
         bundle["wire_program_sha256"] == wire["consumer_sha256"], "retained program identity")
    need(bundle["legacy_program_sha256"] == legacy["probe_sha256"] and
         bundle["legacy_c_sha256"] == legacy["c_consumer_sha256"], "legacy program identity")
    fields = ("id", "mode", "kind", "part", "start", "end", "state")
    normalized = [{k: c[k] for k in fields} for c in sdk["cases"]]
    need(normalized == [{k: c[k] for k in fields} for c in wire["cases"]], "transport anchor changed")
    return normalized

def authenticate_retained():
    """Authenticate IDs from upload outputs, never promote the historical aggregate."""
    import copy
    from relay import identity
    sys.path.insert(0, str(ROOT / "tools"))
    from check_parallel_integration import fetch, pages, download_artifact_zip
    current = identity()
    contract, scope_name, scope = active_contract()
    same_run_head(fetch, current)
    bindings = [b for b in contract["retained_producers"] if b["key"] in scope["retained_keys"]]
    ids = json.loads(os.environ["F04_RETAINED_IDS"])
    need(set(ids) == {b["key"] for b in bindings}, "retained artifact ID map")
    jobs = pages("actions/runs/" + current["run_id"] + "/attempts/" + current["attempt"] + "/jobs", "jobs")
    artifacts = pages("actions/runs/" + current["run_id"] + "/artifacts", "artifacts")
    normalized, receipts = [], []
    for binding in bindings:
        job = [j for j in jobs if j["name"] == producer_job_name(contract, binding["job"])]
        need(len(job) == 1 and job[0]["conclusion"] == "success" and
             job[0]["head_sha"] == current["source_sha"], "retained producer job")
        rows = [a for a in artifacts if a["id"] == ids[binding["key"]]]
        need(len(rows) == 1 and not rows[0]["expired"], "retained artifact ID")
        row = rows[0]
        need(row["workflow_run"]["head_sha"] == current["source_sha"] and
             str(row["workflow_run"]["id"]) == current["run_id"], "retained artifact source/run")
        blob = download_artifact_zip(row["id"])
        need(len(blob) == row["size_in_bytes"] and
             "sha256:" + hashlib.sha256(blob).hexdigest() == row["digest"], "retained original ZIP identity")
        with zipfile.ZipFile(io.BytesIO(blob)) as archive:
            names = archive.namelist()
            need(len(set(names)) == len(names) and
                 all(not PurePosixPath(n).is_absolute() and ".." not in PurePosixPath(n).parts and
                     "\\" not in n and not n.endswith(".key") for n in names), "retained unsafe/private archive")
            def read_json(path): return json.loads(archive.read(path))
            suffix = ".exe" if binding["platform"] == "win32" else ""
            def program(path): return hashlib.sha256(archive.read(path + suffix)).hexdigest()
            bundle = dict(receipt=read_json("f04-driver/retained-receipt.json"),
                sdk=read_json("v2-sdk-evidence/result.json"), raw=read_json("v2-sdk-evidence/probe.json"),
                legacy=read_json("v2-sdk-evidence/legacy/summary.json"),
                legacy_raw=read_json("v2-sdk-evidence/legacy/report.json"),
                legacy_report_sha256=hashlib.sha256(archive.read("v2-sdk-evidence/legacy/report.json")).hexdigest(),
                wire=read_json("v2-webdav-evidence/result.json"), wire_raw=read_json("v2-webdav-evidence/probe.json"),
                sdk_program_sha256=program("v2-consumer/reading-v2-probe"),
                wire_program_sha256=program("v2-webdav-consumer/reading-v2-probe"),
                legacy_program_sha256=program("v1-consumer/reading-state-probe"),
                legacy_c_sha256=program("v1-consumer/reading-state-c-consumer"),
                legacy_caches={name: archive.read(name + "/CMakeCache.txt").decode("utf-8") for name in
                               ("v1-product", "v1-revisions", "v1-adapter", "v1-consumer")},
                legacy_link=archive.read("v1-consumer/reading-state-link.map").decode("utf-8"))
        need(bundle["receipt"]["platform"] == binding["platform"], "retained platform")
        normalized.append(retained_evidence(bundle, current))  # Qualified positive first.
        negatives = [
            ("wrong-source", "retained identity", lambda b: b["sdk"].update(source_sha="0" * 40)),
            ("missing-anchor", "capture summary/raw", lambda b: b["sdk"]["cases"].pop()),
            ("old-check-failure", "original 121 checks", lambda b: b["legacy"].update(checks_failed=1)),
            ("changed-program", "retained program identity", lambda b: b.update(sdk_program_sha256="0" * 64)),
        ]
        rejected = []
        for label, reason, mutate in negatives:
            candidate = copy.deepcopy(bundle)  # Never mutate an already-invalid case.
            mutate(candidate)
            try:
                retained_evidence(candidate, current)
            except AssertionError as error:
                need(str(error) == reason, "negative rejected for unrelated reason: " + label)
                rejected.append({"case": label, "reason": reason, "positive_artifact_id": row["id"]})
            else:
                raise AssertionError("negative unexpectedly accepted: " + label)
        receipts.append({"artifact": {k: row[k] for k in ("id", "name", "size_in_bytes", "digest")},
                         "job_id": job[0]["id"], "negative_checks": rejected})
    need(len(normalized) == len(scope["retained_keys"]) and all(n == normalized[0] for n in normalized),
         "retained selected-scope outcomes")
    out = ROOT / "build/f04-retained-auth"
    out.mkdir(parents=True, exist_ok=False)
    (out / "result.json").write_text(json.dumps(dict(current, retained_18_121_checked=True, scope=scope_name, cross_platform_comparison=len(normalized) > 1,
        producers=receipts, original_four_zip_aggregate="not-run", F04_accepted=False), indent=2))


def diagnose_fixed():
    """One authenticated historical failure ZIP, no build and no program execution."""
    from run import diagnostic_text
    from relay import identity
    sys.path.insert(0, str(ROOT / "tools"))
    from check_parallel_integration import fetch, download_artifact_zip
    need(os.environ.get("GITHUB_ACTIONS") == "true", "Actions only")
    contract = json.loads((HERE / "contract.json").read_text())
    controller = identity()
    need(os.environ.get("F04_SCOPE") == "f04/diagnose-round2" and
         os.environ.get("GITHUB_REF") == "refs/heads/" + contract["canonical"]["branch"] and
         os.environ.get("F04_CONTROLLER_SHA") == controller["source_sha"], "diagnostic controller")
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    need(head == controller["source_sha"], "diagnostic checkout")
    paths = subprocess.check_output(["git", "diff", "--name-only", BASE, head], cwd=ROOT, text=True).splitlines()
    need(set(paths) == set(contract["canonical"]["union_paths"]), "diagnostic exact union")
    pin = contract["fixed_diagnostic"]
    run = fetch("actions/runs/" + pin["run_id"])
    need(run["head_sha"] == pin["source_sha"] and str(run["run_attempt"]) == pin["attempt"] and
         run["conclusion"] == "failure", "diagnostic producer run")
    job = fetch("actions/jobs/" + str(pin["job_id"]))
    need(str(job["run_id"]) == pin["run_id"] and str(job["run_attempt"]) == pin["attempt"] and
         job["head_sha"] == pin["source_sha"] and job["conclusion"] == "failure", "diagnostic producer job")
    row = fetch("actions/artifacts/" + str(pin["artifact_id"]))
    need(row["id"] == pin["artifact_id"] and row["size_in_bytes"] == pin["size_in_bytes"] and
         row["digest"] == pin["digest"] and not row["expired"] and
         str(row["workflow_run"]["id"]) == pin["run_id"] and
         row["workflow_run"]["head_sha"] == pin["source_sha"], "diagnostic artifact identity")
    blob = download_artifact_zip(pin["artifact_id"])
    need(len(blob) == pin["size_in_bytes"] and "sha256:" + hashlib.sha256(blob).hexdigest() == pin["digest"],
         "diagnostic original ZIP digest")
    out = ROOT / "build/f04-fixed-diagnostic"
    out.mkdir(parents=True, exist_ok=False)
    (out / "original.zip").write_bytes(blob)
    text_names = {"exception.txt", "window.json", "application.txt", "result.json", "manifest.json", "diagnostic-refused.json"}
    allowed = text_names | {"import-window.png"}
    reports = []
    with zipfile.ZipFile(io.BytesIO(blob)) as archive:
        names = archive.namelist()
        need(len(names) == len(set(names)) and set(names) <= allowed, "diagnostic member whitelist")
        for entry in archive.infolist():
            need(entry.file_size <= (2000000 if entry.filename.endswith(".png") else 262144),
                 "diagnostic member size")
            if entry.filename not in text_names:
                continue
            raw = archive.read(entry.filename).decode("utf-8", errors="strict")
            cleaned = diagnostic_text(raw)
            (out / entry.filename).write_text(cleaned, encoding="utf-8")
            print("DIAGNOSTIC TEXT " + entry.filename, flush=True)
            print(cleaned, flush=True)
            reports.append(entry.filename)
    result = {"diagnostic_controller": controller, "producer": pin,
              "original_archive": {"bytes": len(blob), "digest": pin["digest"]},
              "printed_texts": reports, "missing_texts": sorted(text_names - set(reports)),
              "diagnostic_only": True, "product_executed": False, "F04_accepted": False}
    (out / "diagnosis.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result), flush=True)


def diagnose_artifact_inventory():
    """Read-only historical inventory; never an alternate acceptance path."""
    import base64
    from relay import identity
    sys.path.insert(0, str(ROOT / "tools"))
    from check_parallel_integration import fetch, download_artifact_zip
    need(os.environ.get("GITHUB_ACTIONS") == "true", "Actions only")
    contract = json.loads((HERE / "contract.json").read_text())
    pin = contract["artifact_inventory_diagnostic"]
    controller = identity()
    need(os.environ.get("F04_SCOPE") == pin["case"] and
         os.environ.get("GITHUB_REF") == "refs/heads/" + contract["canonical"]["branch"] and
         os.environ.get("F04_CONTROLLER_SHA") == controller["source_sha"], "inventory controller")
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    need(head == controller["source_sha"], "inventory checkout")
    changed = subprocess.check_output(["git", "diff", "--name-only", pin["producer_source"], head],
                                      cwd=ROOT, text=True).splitlines()
    need(set(changed) == set(pin["allowed_changed_paths"]), "inventory exact source delta")
    producer = fetch("actions/runs/" + pin["run_id"])
    need(producer["head_sha"] == pin["producer_source"] and
         str(producer["run_attempt"]) == pin["attempt"] and producer["conclusion"] == "failure",
         "inventory historical run")
    need(len(pin["artifacts"]) == 17 and len({p["artifact_id"] for p in pin["artifacts"]}) == 17,
         "inventory seventeen fixed artifacts")
    expected_identity = dict(source_sha=pin["producer_source"], run_id=pin["run_id"], attempt=pin["attempt"])
    out = ROOT / "build/f04-artifact-inventory"
    out.mkdir(parents=True, exist_ok=False)
    report = dict(controller=controller, producer=expected_identity, original_run_conclusion="failure",
                  diagnostic_only=True, F04_accepted=False, product_executed=False,
                  archives_modified=False, artifacts=[])
    cross = {}
    phase_files = {"state.json", "result.json", "report.json", "requests.json", "cert.pem",
                   "program.bin", "build-receipt.json", "installed-identity.json"}
    sdk_metadata = {"build-receipt.json", "sdk342-installed-identity.json", "wave3-packages.json",
                    "sdk-identity.json", "raw-identity.json"}
    retained_files = {"f04-driver/retained-receipt.json", "v2-sdk-evidence/result.json",
        "v2-sdk-evidence/probe.json", "v2-sdk-evidence/legacy/summary.json",
        "v2-sdk-evidence/legacy/report.json", "v2-webdav-evidence/result.json",
        "v2-webdav-evidence/probe.json", "v2-webdav-evidence/native-requests.json",
        "v2-consumer/reading-v2-probe", "v2-webdav-consumer/reading-v2-probe",
        "v1-consumer/reading-state-probe", "v1-consumer/reading-state-c-consumer",
        "v1-consumer/reading-state-link.map", "v1-product/CMakeCache.txt",
        "v1-revisions/CMakeCache.txt", "v1-adapter/CMakeCache.txt", "v1-consumer/CMakeCache.txt"}
    for binding in pin["artifacts"]:
        row = dict(binding=binding, missing=[], unexpected=[], hash_mismatch=[], identity_errors=[],
                   inspection_errors=[], missing_critical=[], members=[], expected=[])
        report["artifacts"].append(row)
        try:
            job = fetch("actions/jobs/" + str(binding["job_id"]))
            need(job["head_sha"] == pin["producer_source"] and str(job["run_id"]) == pin["run_id"] and
                 str(job["run_attempt"]) == pin["attempt"] and job["conclusion"] == "success" and
                 job["name"] == binding["job_name"], "inventory producer job")
            artifact = fetch("actions/artifacts/" + str(binding["artifact_id"]))
            need(artifact["id"] == binding["artifact_id"] and not artifact["expired"] and
                 artifact["name"] == binding["name"] and artifact["size_in_bytes"] == binding["size_in_bytes"] and
                 artifact["digest"] == binding["digest"] and
                 artifact["workflow_run"]["head_sha"] == pin["producer_source"] and
                 str(artifact["workflow_run"]["id"]) == pin["run_id"], "inventory artifact metadata")
            blob = download_artifact_zip(binding["artifact_id"])
            need(len(blob) == binding["size_in_bytes"] and
                 "sha256:" + hashlib.sha256(blob).hexdigest() == binding["digest"], "inventory original bytes")
            row["original_archive_authenticated"] = True
            with zipfile.ZipFile(io.BytesIO(blob)) as archive:
                entries = archive.infolist()
                names = [e.filename for e in entries]
                need(len(names) == len(set(names)) and len(names) <= 50000, "inventory duplicate/member limit")
                need(sum(e.file_size for e in entries) <= 500000000 and
                     all(e.file_size <= 250000000 for e in entries), "inventory expanded size")
                need(all(not PurePosixPath(n).is_absolute() and ".." not in PurePosixPath(n).parts and
                         "\\" not in n and ":" not in n and "\x00" not in n and not n.endswith(".key") and
                         PurePosixPath(n).name != "key.pem" and
                         not ({"private", "profile"} & set(PurePosixPath(n).parts)) for n in names),
                     "inventory unsafe paths")
                need(all(((e.external_attr >> 16) & 0o170000) in (0, 0o100000, 0o040000)
                         and not (e.flag_bits & 1) for e in entries), "inventory special/encrypted entries")
                files = {e.filename for e in entries if not e.is_dir()}
                hashes = {}
                objects = {}
                for name in sorted(files):
                    raw = archive.read(name)
                    hashes[name] = {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
                    row["members"].append(dict(path=name, hidden=any(p.startswith(".") for p in PurePosixPath(name).parts),
                                               **hashes[name]))
                    if name.endswith(".json"):
                        try:
                            objects[name] = json.loads(raw)
                        except (ValueError, UnicodeError):
                            row["inspection_errors"].append("invalid JSON: " + name)
                def check_identity(value, path):
                    if isinstance(value, dict):
                        if "source_sha" in value and "run_id" in value and "attempt" in value:
                            for key, expected in expected_identity.items():
                                if str(value[key]) != expected: row["identity_errors"].append(path + ":" + key)
                        if "sdk_version" in value and value["sdk_version"] != "3.42.0":
                            row["identity_errors"].append(path + ":sdk_version")
                        for key, child in value.items():
                            if key not in ("body", "raw_b64", "entries"):
                                check_identity(child, path + "/" + key)
                    elif isinstance(value, list):
                        for i, child in enumerate(value): check_identity(child, path + "/" + str(i))
                for name, value in objects.items(): check_identity(value, name)
                def require_fields(value, keys, label):
                    if not isinstance(value, dict):
                        row["missing_critical"].append(label + ":object")
                        return False
                    missing = [k for k in keys if k not in value or value[k] is None]
                    row["missing_critical"].extend(label + ":" + k for k in missing)
                    return not missing
                def identity_required(value, label):
                    if require_fields(value, expected_identity, label):
                        for key, expected in expected_identity.items():
                            if str(value[key]) != expected: row["identity_errors"].append(label + ":" + key)
                def equal_field(value, key, expected, label):
                    if require_fields(value, [key], label) and value[key] != expected:
                        row["identity_errors"].append(label + ":" + key)
                def expected_hash(path, value, keys=("bytes", "sha256"), label=None):
                    label = label or path
                    valid = require_fields(value, keys, label + ":reference")
                    if path not in files:
                        row["missing"].append(path)
                    elif valid and any(hashes[path][key] != value[key] for key in keys):
                        row["hash_mismatch"].append(label)
                receipt = objects.get("build-receipt.json")
                if binding["category"] in ("sdk-build", "program-build", "phase"):
                    identity_required(receipt, "build-receipt")
                    equal_field(receipt, "sdk_version", "3.42.0", "build-receipt")
                    equal_field(receipt, "sdk_source", contract["sdk_source"], "build-receipt")
                    platform = binding["platform"]
                    if binding["category"] == "phase":
                        graph = next((b for b in contract["graph_producers"]
                                      if binding["name"] == b["artifact"] + "-" + pin["run_id"] + "-" + pin["attempt"]), None)
                        if graph is None: row["missing_critical"].append("phase:contract-binding")
                        else:
                            platform = next(b["platform"] for b in contract["build_producers"]
                                            if b["key"] == graph["build_key"])
                    recipe = {"windows": "tests/windows_sdk342/build.py", "gtk": "tests/gtk_sdk342_package/run.py",
                              "android": "tests/android_sdk342_package/run.py",
                              "macos": "tests/apple_sdk342_host/build.py",
                              "iphonesimulator": "tests/apple_sdk342_host/build.py"}.get(platform)
                    equal_field(receipt, "platform", platform, "build-receipt")
                    equal_field(receipt, "recipe", recipe, "build-receipt")
                    if recipe:
                        equal_field(receipt, "recipe_sha256", hashlib.sha256((ROOT / recipe).read_bytes()).hexdigest(),
                                    "build-receipt")
                cross[binding["name"]] = dict(hashes=hashes, receipt=receipt)
                if binding["category"] == "sdk-build":
                    expected = set(sdk_metadata)
                    manifest = objects.get("sdk342-installed-identity.json", {})
                    receipt = objects.get("build-receipt.json", {})
                    if not isinstance(manifest, dict): manifest = {}
                    for root, key in (("sdk", "sdk_files"), ("raw-products", "raw_files")):
                        values = manifest.get(key)
                        if not isinstance(values, dict):
                            row["inspection_errors"].append("missing/invalid manifest map: " + key)
                            continue
                        for path, value in values.items():
                            name = root + "/" + path
                            expected.add(name); expected_hash(name, value)
                    expected_hash("sdk342-installed-identity.json",
                                  {"sha256": receipt.get("installed_identity_sha256") if isinstance(receipt, dict) else None},
                                  ("sha256",))
                    identity_required(manifest, "installed-sdk-manifest")
                    equal_field(manifest, "target", binding["platform"], "installed-sdk-manifest")
                    equal_field(manifest, "sdk_version", "3.42.0", "installed-sdk-manifest")
                    equal_field(manifest, "sdk_content_candidate", contract["sdk_source"], "installed-sdk-manifest")
                    for name in ("wave3-packages.json", "raw-identity.json"):
                        identity_required(objects.get(name), name)
                        equal_field(objects.get(name), "target", binding["platform"], name)
                    sdk_identity = objects.get("sdk-identity.json", {})
                    identity_required(sdk_identity, "sdk-identity")
                    equal_field(sdk_identity, "platform", binding["platform"], "sdk-identity")
                    equal_field(sdk_identity, "job", "build_" + binding["platform"], "sdk-identity")
                    equal_field(sdk_identity, "sdk_version", "3.42.0", "sdk-identity")
                    equal_field(sdk_identity, "abi", 1, "sdk-identity")
                    equal_field(sdk_identity, "reading_sdk_baseline",
                                "9854061be331fe603a1822d9b2b36ee357154927", "sdk-identity")
                    if require_fields(sdk_identity, ["files_sha256", "runtime_ids"], "sdk-identity"):
                        sdk_files = sdk_identity["files_sha256"]
                        if isinstance(sdk_files, dict):
                            for path, digest in sdk_files.items():
                                expected.add("sdk/" + path)
                                expected_hash("sdk/" + path, {"sha256": digest}, ("sha256",), "sdk-identity:" + path)
                            committed = manifest.get("sdk_files", {})
                            if isinstance(committed, dict) and sdk_files != {
                                    path: value.get("sha256") for path, value in committed.items() if isinstance(value, dict)}:
                                row["identity_errors"].append("sdk-identity/installed-manifest sdk file map")
                        else: row["missing_critical"].append("sdk-identity:files_sha256 map")
                    raw_identity = objects.get("raw-identity.json", {})
                    if require_fields(raw_identity, ["raw_files"], "raw-identity"):
                        if raw_identity["raw_files"] != manifest.get("raw_files"):
                            row["identity_errors"].append("raw-identity/installed-manifest raw file map")
                    equal_field(objects.get("wave3-packages.json"), "sdk_frozen_source",
                                contract["sdk_source"], "wave3-packages")
                elif binding["category"] == "phase":
                    expected = {"state.json", "requests.json", "cert.pem", "program.bin", "build-receipt.json"}
                    state = objects.get("state.json", {})
                    data = state.get("data", {}) if isinstance(state, dict) else {}
                    result_name = "report.json" if binding["platform"] == "android" else "result.json"
                    expected.add(result_name)
                    result = objects.get(result_name, {})
                    for label, value in (("state", state), ("state.data", data), (result_name, result)):
                        identity_required(value, label)
                    program = data.get("program") if isinstance(data, dict) else None
                    expected_hash("program.bin", program, label="state.data.program")
                    if isinstance(receipt, dict) and receipt.get("program") is not None:
                        expected_hash("program.bin", receipt["program"], label="receipt.program")
                    else:
                        expected.add("installed-identity.json")
                        expected_hash("installed-identity.json",
                                      {"sha256": receipt.get("installed_identity_sha256") if isinstance(receipt, dict) else None},
                                      ("sha256",))
                        equal_field(program, "bundle_source_sha", pin["producer_source"], "Apple program")
                        equal_field(program, "bundle_id", "org.exreader.host", "Apple program")
                    server = state.get("server", {}) if isinstance(state, dict) else {}
                    expected_hash("cert.pem", {"sha256": server.get("certificate_sha256")}, ("sha256",))
                    equal_field(server, "implementation_sha256", hashlib.sha256((HERE / "relay.py").read_bytes()).hexdigest(), "server")
                    equal_field(server, "dav_implementation_sha256",
                                hashlib.sha256((ROOT / "tests/reader_d23_relay/relay.py").read_bytes()).hexdigest(), "server")
                    if graph is not None:
                        cross[binding["name"]]["graph"] = graph
                        cross[binding["name"]]["previous_sha256"] = state.get("previous_sha256")
                        if graph["role"] != "seed":
                            require_fields(state, ["previous_sha256"], "state")
                        equal_field(data, "platform", graph["host"], "state.data")
                    for label, value in (("state.data", data), (result_name, result)):
                        equal_field(value, "passed", True, label)
                        if isinstance(value, dict) and value.get("cleanup_errors"):
                            row["identity_errors"].append(label + ":cleanup_errors")
                    if isinstance(state, dict):
                        row["phase"] = state.get("phase")
                        for key, value in state.get("entries", {}).items():
                            try:
                                raw = base64.b64decode(value["body"], validate=True)
                                if hashlib.sha256(raw).hexdigest() != value["sha256"]:
                                    row["hash_mismatch"].append("state-entry:" + key)
                            except (ValueError, KeyError, TypeError):
                                row["inspection_errors"].append("invalid state-entry:" + key)
                elif binding["category"] == "retained":
                    expected = set(retained_files)
                    for name in ("f04-driver/retained-receipt.json", "v2-sdk-evidence/result.json",
                                 "v2-webdav-evidence/result.json"):
                        identity_required(objects.get(name), name)
                    retained_receipt = objects.get("f04-driver/retained-receipt.json")
                    equal_field(retained_receipt, "sdk_version", "3.42.0", "retained receipt")
                    equal_field(retained_receipt, "sdk_source", contract["sdk_source"], "retained receipt")
                    legacy = objects.get("v2-sdk-evidence/legacy/summary.json", {})
                    legacy_identity = legacy.get("identity", {}) if isinstance(legacy, dict) else {}
                    for key, variable in (("source_sha", "GITHUB_SHA"), ("run_id", "GITHUB_RUN_ID"), ("attempt", "GITHUB_RUN_ATTEMPT")):
                        if require_fields(legacy_identity, [variable], "legacy identity") and str(legacy_identity[variable]) != expected_identity[key]:
                            row["identity_errors"].append("legacy identity:" + variable)
                    for path, document, key in (
                        ("v2-consumer/reading-v2-probe", "v2-sdk-evidence/result.json", "consumer_sha256"),
                        ("v2-webdav-consumer/reading-v2-probe", "v2-webdav-evidence/result.json", "consumer_sha256"),
                        ("v1-consumer/reading-state-probe", "v2-sdk-evidence/legacy/summary.json", "probe_sha256"),
                        ("v1-consumer/reading-state-c-consumer", "v2-sdk-evidence/legacy/summary.json", "c_consumer_sha256"),
                        ("v2-sdk-evidence/legacy/report.json", "v2-sdk-evidence/legacy/summary.json", "report_sha256")):
                        document_value = objects.get(document, {})
                        expected_hash(path, {"sha256": document_value.get(key) if isinstance(document_value, dict) else None},
                                      ("sha256",), document + ":" + key)
                else:
                    expected = {"build-receipt.json", "program.bin"}
                    if binding["platform"] == "android":
                        expected |= {"app-debug.apk", "relay-debug-androidTest.apk"}
                    elif binding["platform"] == "windows":
                        expected.add("Reader.otf")
                    receipt = objects.get("build-receipt.json", {})
                    expected_hash("program.bin", receipt.get("program") if isinstance(receipt, dict) else None)
                    # Package contents are inventoried, not silently promoted to an exhaustive manifest.
                    row["uncommitted_package_members"] = sorted(n for n in files if n.startswith("package/"))
                row["expected"] = sorted(expected)
                row["missing"] = sorted(set(row["missing"]) | (expected - files))
                optional = phase_files - expected if binding["category"] == "phase" else set()
                row["declared_optional_present"] = sorted(optional & files)
                row["declared_optional_missing"] = sorted(optional - files)
                row["unexpected"] = sorted(files - expected - optional)
                row["identity_documents"] = sorted(objects)
                row["inventory_complete"] = True
        except Exception as error:
            row["inspection_errors"].append(type(error).__name__ + ": " + str(error))
            row["inventory_complete"] = False
        # Evidence only; no source/archive content, credentials or raw state values printed.
    # Cross-archive references use original state/receipt bytes, never rewritten identities.
    for row in report["artifacts"]:
        name = row["binding"]["name"]
        data = cross.get(name, {})
        graph = data.get("graph")
        if graph is not None:
            build_name = graph["build_key"] + "-" + pin["run_id"] + "-" + pin["attempt"]
            build = cross.get(build_name)
            own_receipt = data["hashes"].get("build-receipt.json")
            if not build or not own_receipt or "build-receipt.json" not in build["hashes"]:
                row["missing_critical"].append("phase/build receipt reference unavailable")
            elif own_receipt != build["hashes"]["build-receipt.json"]:
                row["hash_mismatch"].append("phase/build receipt bytes")
            if graph["role"] != "seed":
                previous_name = graph["previous"] + "-" + pin["run_id"] + "-" + pin["attempt"]
                previous = cross.get(previous_name, {}).get("hashes", {}).get("state.json")
                if previous is None:
                    row["missing_critical"].append("predecessor original state unavailable")
                elif data.get("previous_sha256") != previous["sha256"]:
                    row["hash_mismatch"].append("exact staged predecessor")
        (out / (str(row["binding"]["artifact_id"]) + ".json")).write_text(json.dumps(row, indent=2) + "\n")
        print("F04 ARTIFACT INVENTORY " + json.dumps(row), flush=True)
    report["inventory_complete"] = all(r.get("inventory_complete", False) for r in report["artifacts"])
    report["has_findings"] = any(r["missing"] or r["unexpected"] or r["hash_mismatch"] or
                               r["identity_errors"] or r["inspection_errors"] or r["missing_critical"] for r in report["artifacts"])
    report["acceptance"] = "not-evaluated; original audit failure retained"
    (out / "inventory.json").write_text(json.dumps(report, indent=2) + "\n")
    print("F04 INVENTORY SUMMARY " + json.dumps({k:v for k,v in report.items() if k != "artifacts"}), flush=True)



if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--graph", type=Path)
    parser.add_argument("--authenticate-graph", action="store_true")
    parser.add_argument("--authenticate-retained", action="store_true")
    parser.add_argument("--diagnose-fixed", action="store_true")
    parser.add_argument("--diagnose-artifact-inventory", action="store_true")
    args = parser.parse_args()
    need(sum((bool(args.graph), args.authenticate_graph, args.authenticate_retained, args.diagnose_fixed, args.diagnose_artifact_inventory)) <= 1, "choose one audit entry")
    if args.diagnose_artifact_inventory: diagnose_artifact_inventory()
    elif args.diagnose_fixed: diagnose_fixed()
    elif args.authenticate_retained: authenticate_retained()
    elif args.authenticate_graph: authenticate_graph()
    elif args.graph: graph_audit(args.graph)
    else: main()
