"""Read-only diagnostic classification; not the official F08 acceptance protocol."""
import argparse
import collections
import hashlib
import json
import pathlib
import subprocess
import sys

BASE = "6f60057deaae4dc123209b974c08de6d246a2f70"
BRANCH = "codex/f08-frame-identity-diagnostic-20261102"
HERE = pathlib.Path(__file__).resolve().parent
REL = "tests/f08_frame_identity_diagnostic_20261102"
PATHS = sorted([
    ".github/workflows/f08-frame-identity-diagnostic-20261102.yml",
    REL + "/diagnose.py", REL + "/test_identity.py", REL + "/INPUTS.json",
    REL + "/raw/native-window-4238-1.jsonl",
    REL + "/raw/reader-draw-window-4238-1.jsonl", REL + "/README.md",
])
PINS = {
    "raw/native-window-4238-1.jsonl": (
        "b63a9fd77f69956f827263c80cb76d4e5bda15962b71a901cb9aa902b952eaee", 124166),
    "raw/reader-draw-window-4238-1.jsonl": (
        "8648b82f857450991e84df38840e68210f47c931824c5e3594fc6f55e8f98406", 17024),
}
STAGES = ("unknown_ns", "input_ns", "animation_ns", "layout_measure_ns")
DURATIONS = STAGES + ("draw_ns", "total_ns")
def integer(value, minimum=0):
    return type(value) is int and value >= minimum

def owner(row):
    if not integer(row.get("pid"), 1) or not integer(row.get("window_id"), 1):
        raise ValueError("invalid owner")
    return row["pid"], row["window_id"]

def classify(events, frames):
    """Classify preserved observations without accepting, filtering, or deleting frames."""
    issues = []
    keys = collections.defaultdict(list)
    seqs = collections.defaultdict(list)
    natives = []
    for row in frames:
        if row.get("kind") != "frame":
            issues.append("unexpected native kind")
            continue
        try:
            own = owner(row)
            seq = row.get("sequence")
            if not integer(seq, 1):
                raise ValueError("invalid sequence")
            if not integer(row.get("vsync_ns"), 1) or not integer(row.get("intended_vsync_ns"), 1):
                raise ValueError("invalid clock")
            if any(not integer(row.get(k)) for k in DURATIONS):
                raise ValueError("invalid duration")
            if type(row.get("drop_count")) is not int or row["drop_count"] != 0:
                raise ValueError("dropped callback")
            start = row["intended_vsync_ns"] + sum(row[k] for k in STAGES)
            end = start + row["draw_ns"]
            if (not row["intended_vsync_ns"] <= row["vsync_ns"] <= start <= end
                    or end > row["intended_vsync_ns"] + row["total_ns"]):
                raise ValueError("invalid native interval")
            native = {"owner": own, "sequence": seq, "start": start, "end": end}
            natives.append(native)
            keys[(*own, row["vsync_ns"])].append(seq)
            seqs[(*own, seq)].append(row)
        except (ValueError, KeyError, TypeError) as exc:
            issues.append(str(exc))
    for key, rows in seqs.items():
        if len(rows) > 1:
            identical = all(row == rows[0] for row in rows[1:])
            issues.append("duplicate sequence identical" if identical else "duplicate sequence conflicting")
    accepts = {}
    latest = {}
    draw_ids = set()
    draws = []
    for event in events:
        kind = event.get("kind")
        if kind in ("start", "stop"):
            continue
        try:
            own = owner(event)
            if kind == "page_set":
                latest.pop(own, None)
                continue
            if kind == "accept":
                aid, gen = event.get("accept_id"), event.get("request_generation")
                if not integer(aid, 1) or not integer(gen, 1):
                    raise ValueError("invalid accept identity")
                if (*own, aid) in accepts:
                    raise ValueError("duplicate accept identity")
                accepts[(*own, aid)] = gen
                latest[own] = (aid, gen)
                continue
            if kind != "bitmap_draw":
                raise ValueError("unexpected event kind")
            did = event.get("draw_id")
            if not integer(did, 1) or (*own, did) in draw_ids:
                raise ValueError("invalid/duplicate draw identity")
            draw_ids.add((*own, did))
            aid, gen = event.get("accept_id"), event.get("request_generation")
            if (latest.get(own) != (aid, gen)
                    or accepts.get((*own, aid)) != gen
                    or not integer(aid, 1) or not integer(gen, 1)):
                raise ValueError("wrong owner/accept/generation")
            begin, end = event.get("draw_begin_mono_ns"), event.get("draw_end_mono_ns")
            if not integer(begin, 1) or not integer(end, 1) or begin >= end:
                raise ValueError("invalid bitmap clock")
            matches = [n for n in natives if n["owner"] == own and n["start"] <= begin < end <= n["end"]]
            classification = "unique_interval_candidate" if len(matches) == 1 else (
                "ambiguous_interval" if len(matches) > 1 else "unmatched_interval")
            draws.append({"draw_id": did, "owner": list(own), "accept_id": aid,
                          "request_generation": gen, "begin": begin, "end": end,
                          "classification": classification,
                          "candidate_sequences": [n["sequence"] for n in matches]})
            if len(matches) != 1:
                issues.append(classification)
        except (ValueError, KeyError, TypeError) as exc:
            issues.append(str(exc))
    if not frames or not draws:
        issues.append("empty observations")
    return {
        "diagnostic_only": True, "acceptance_override": False,
        "official_association_unchanged": True,
        "input_frame_count": len(frames), "retained_frame_count": len(frames),
        "sequence_identity_count": len(seqs),
        "shared_vsync_groups": [
            {"key": list(k), "sequences": v} for k, v in keys.items() if len(v) > 1],
        "issues": issues, "classification_valid": not issues, "draws": draws,
    }

def load_inputs():
    manifest = json.loads((HERE / "INPUTS.json").read_text())
    if manifest["measured_source"] != "1c4eac3eb5e2da98d535585f80fc3aba437661bd":
        raise ValueError("wrong measured source")
    if manifest["native_identity"] != "native-lap25002-20261102T055639Z/A1":
        raise ValueError("wrong native identity")
    if manifest["scope"] != "retained-prefix-not-complete-capture":
        raise ValueError("wrong prefix scope")
    listed = {row["path"]: row for row in manifest["files"]}
    if len(manifest["files"]) != 2 or set(listed) != set(PINS):
        raise ValueError("wrong input path set")
    result = {}
    for name, (digest, size) in PINS.items():
        data = (HERE / name).read_bytes()
        if (len(data) != size or hashlib.sha256(data).hexdigest() != digest
                or listed[name]["sha256"] != digest or listed[name]["bytes"] != size):
            raise ValueError("input bytes/hash mismatch")
        if not data.endswith(b"\n"):
            raise ValueError("partial JSON line")
        rows = [json.loads(line) for line in data.splitlines()]
        if not rows or rows[0].get("kind") != "start":
            raise ValueError("missing header")
        if any(owner(row) != (4238, 1) for row in rows):
            raise ValueError("input owner mismatch")
        if any(row.get("kind") == "stop" for row in rows):
            raise ValueError("unexpected completed-stream input")
        result[name] = rows
    return manifest, result

def verify_scope():
    root = HERE.parents[1]
    def git(*args):
        return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()
    changed = git("diff", "--name-status", BASE, "HEAD").splitlines()
    if sorted(changed) != ["A\t" + path for path in PATHS]:
        raise ValueError("candidate scope is not exact seven additions")
    if git("rev-parse", "HEAD^") != BASE:
        raise ValueError("unexpected parent")
    return git("rev-parse", "HEAD")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    candidate = verify_scope()
    manifest, data = load_inputs()
    report = classify(data["raw/reader-draw-window-4238-1.jsonl"],
                      data["raw/native-window-4238-1.jsonl"][1:])
    report.update({"candidate_source": candidate, "inputs": manifest,
                   "capture_complete": False, "official_f08_result": "unchanged_failure",
                   "not_a_replacement_acceptance_protocol": True})
    output = pathlib.Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"classification_valid": report["classification_valid"],
                      "issues": report["issues"], "official_f08_result": "unchanged_failure",
                      "input_frame_count": report["input_frame_count"],
                      "retained_frame_count": report["retained_frame_count"],
                      "sequence_identity_count": report["sequence_identity_count"],
                      "shared_vsync_groups": report["shared_vsync_groups"],
                      "draw9": [d for d in report["draws"] if d["draw_id"] == 9],
                      "output": str(output)}))
    return 0 if report["classification_valid"] else 1

if __name__ == "__main__":
    sys.exit(main())
