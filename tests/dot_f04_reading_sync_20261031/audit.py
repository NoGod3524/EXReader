#!/usr/bin/env python3
"""Actions-only F04 staged iPhone/Android strict audit.

Runs the unchanged prior relay assertions first, then verifies additional
application-authored bookmark/range bytes and explicit receiver landings.
A passing stage can NEVER set the complete six-target F04 flag.
"""
import base64, hashlib, json, os, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
BASE = "94fb236a4a2da87dfbaf4f1dd2a47885d615a230"

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
    parents = {parent for wire in history for parent in wire["parents"]}
    heads = [wire for wire in history if wire["id"] not in parents]
    need(len(heads) == 1 and heads[0].get("operation") != "delete", "not SAFE unique head")
    head = heads[0]
    need(head.get("payload") and marker in head["payload"].get("text", ""), "current marker absent")
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
                      remaining_scope=["four-format cross-host coverage", "six-host no-mislocation negatives"])
    except Exception as error:
        output["failures"].append(type(error).__name__ + ": " + str(error))
        raise
    finally:
        destination = ROOT / "build/apple-android/f04-summary.json"
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n")
        print(json.dumps(output, ensure_ascii=False), flush=True)
if __name__ == "__main__":
    main()
