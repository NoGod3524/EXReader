"""Inspect only three pinned historical G16 archives; never execute their payload."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import plistlib
import re
import signal
import stat
import subprocess
import tempfile
import zipfile

REPO = "repos/NoGod3524/EXReader/"
SOURCE = "e9e20eada714bc6b8045d3e943ac46ff26844559"
RUN = 41363868404
PINS = [
    ("macos", 13106229495, 5431651, "0f8aef287a742778eceb2b25844c0209d879d77686e7818c612f9aa181069d18"),
    ("iphone", 13106354573, 151712130, "b5083d8dc48d0cc7a79788bb834ec75f372a304a83710a3402282d33fbba2da2"),
    ("ipad", 13107061378, 88419007, "e26850c738007e51bf0569c010443f10856db57d5402fe5a9a3da260ea5f88de"),
]
OUT = Path("build/f09-g16-raw-identity")
LIMITS = {"download_bytes": 245562788, "declared_expanded_bytes": 2*1024**3,
          "member_bytes": 512*1024**2, "members": 30000,
          "text_member_bytes": 16*1024**2, "selected_text_bytes": 128*1024**2}
SENSITIVE = re.compile(r"password|passphrase|authorization|cookie|access.?token|client.?secret|credential|private.?key", re.I)
HEX = re.compile(r"^[0-9a-f]{40}$|^[0-9a-f]{64}$", re.I)
REPORT = {"acceptance_eligible": False, "archive_inspection_complete": False,
          "source": SOURCE, "run": RUN, "attempt": 1, "limits": LIMITS,
          "artifacts": [], "failures": [], "remaining_historical_blockers_not_reclassified": 6}
TOTAL = {"download": 0, "declared": 0, "members": 0, "text": 0, "payload_read": 0}
BUDGET_END = None

def clean(value, key=""):
    if SENSITIVE.search(key):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {k: clean(v, str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [clean(v) for v in value]
    if isinstance(value, str):
        value = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", value)
        value = re.sub(r"\b(?:gh[pousr]_[A-Za-z0-9_]+|github_pat_[A-Za-z0-9_]+)\b", "[REDACTED]", value)
        value = re.sub(r"(?i)(authorization|password|access_token|client_secret|cookie)\s*[:=]\s*[^\s,;]+", r"\1=[REDACTED]", value)
        # Preserve scheme/host/path only; remove URL userinfo, all query/fragment.
        def url(m):
            from urllib.parse import urlsplit, urlunsplit
            u = urlsplit(m.group(0))
            return urlunsplit((u.scheme, (u.hostname or "") + ((":"+str(u.port)) if u.port else ""), u.path, "", ""))
        return re.sub(r"https?://[^\s\"<>]+", url, value)
    return value

def api(path):
    return json.loads(subprocess.check_output(["gh", "api", REPO+path], timeout=60))

def digest(data):
    return hashlib.sha256(data).hexdigest()

def summarize_json(obj):
    stats = {"dict_nodes": 0, "element_like_nodes": 0, "state_names": [],
             "identity_fields": [], "reader_state_mentions": 0, "library_empty_mentions": 0,
             "identity_fields_truncated": False}
    states = set()
    def walk(x, path="$", depth=0):
        if depth > 80:
            raise ValueError("JSON depth limit")
        if isinstance(x, dict):
            stats["dict_nodes"] += 1
            if any(k in x for k in ("identifier", "accessibilityIdentifier", "elementType")) or (
                    "id" in x and any(k in x for k in ("role", "label", "name", "frame"))):
                stats["element_like_nodes"] += 1
            for k, v in x.items():
                kp = path+"."+str(k)
                if k in ("state", "state_name", "scenario") and isinstance(v, str):
                    states.add(v[:120])
                if isinstance(v, (str, int, bool)) and (
                    re.search(r"sha|digest|source|run_id|attempt|artifact|bundle|mode|compilation|swift_flags", str(k), re.I)):
                    if len(stats["identity_fields"]) < 40:
                        stats["identity_fields"].append({"path": kp[:240], "value": clean(str(v)[:300], str(k))})
                    else:
                        stats["identity_fields_truncated"] = True
                if isinstance(v, str):
                    stats["reader_state_mentions"] += v.count("reader.state")
                    stats["library_empty_mentions"] += v.count("library.empty")
                if isinstance(v, (dict, list)):
                    walk(v, kp, depth+1)
        elif isinstance(x, list):
            for i, v in enumerate(x):
                walk(v, path+"["+str(i)+"]", depth+1)
    walk(obj)
    stats["state_names"] = sorted(states)[:30]
    return stats

def ax_records(text, parsed=None):
    """Exact original state records; producer flatten caps nodes at240."""
    records = []
    invalid = 0
    marker_count = 0
    candidates = []
    for number, line in enumerate(text.splitlines(), 1):
        index = line.find("EXR_A11Y_STATE ")
        if index >= 0:
            marker_count += 1
            try:
                candidates.append((number, json.loads(line[index+len("EXR_A11Y_STATE "):])))
            except ValueError:
                invalid += 1
    if isinstance(parsed, dict) and parsed.get("kind") == "state" and "elements" in parsed:
        candidates.append((None, parsed))
    for number, payload in candidates:
        if not isinstance(payload, dict) or payload.get("kind") != "state" or not isinstance(payload.get("elements"), list):
            invalid += 1
            continue
        elements = payload["elements"]
        if len(elements) > 240 or any(not isinstance(x, dict) for x in elements):
            invalid += 1
            continue
        targets = [clean(x) for x in elements if x.get("id") in ("reader.state", "library.empty")]
        records.append({
            "line": number, "record_sha256": digest(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()),
            "step": payload.get("step"), "platform": payload.get("platform"), "test": payload.get("test"),
            "app_state": payload.get("app_state"), "declared_element_count": payload.get("element_count"),
            "actual_element_count": len(elements), "count_matches": payload.get("element_count") == len(elements),
            "targets": targets, "identity_fields_present": {k: clean(payload[k], k) for k in
                ("source_sha", "program_sha256", "executable_sha256", "run_id", "attempt", "artifact_id") if k in payload},
            "anonymous_controls": payload.get("anonymous_controls"), "collector_cap_may_apply": len(elements) >= 240,
        })
    return {"marker_count": marker_count, "valid_records": len(records), "invalid_records": invalid,
            "records": records, "producer_full_tree_claim": False,
            "producer_limit": "flatten keeps at most240 nodes; elements omits anonymous nodes"}

def report_bindings(obj):
    found = []
    def walk(value, depth=0):
        if depth > 30 or len(found) >= 10:
            return
        if isinstance(value, dict):
            if isinstance(value.get("program"), dict) and isinstance(value.get("log_sha256"), dict):
                found.append(clean({k: value.get(k) for k in ("program", "log_sha256", "sdk", "platform", "runtime", "xcode")}))
            for child in value.values():
                if isinstance(child, (dict, list)):
                    walk(child, depth+1)
        elif isinstance(value, list):
            for child in value:
                walk(child, depth+1)
    walk(obj)
    return found

def download(pin, path):
    platform, artifact, size, sha = pin
    meta = api("actions/artifacts/"+str(artifact))
    if meta.get("name") != "f09-apple-audit-"+platform+"-41363868404-1" or meta["size_in_bytes"] != size or meta.get("digest") != "sha256:"+sha or meta.get("expired"):
        raise ValueError("artifact metadata pin mismatch")
    wr = meta["workflow_run"]
    if wr["id"] != RUN or wr["head_sha"] != SOURCE:
        raise ValueError("artifact producer mismatch")
    proc = subprocess.Popen(["gh", "api", REPO+"actions/artifacts/"+str(artifact)+"/zip"],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    h = hashlib.sha256()
    count = 0
    try:
        with path.open("wb") as f:
            while True:
                data = proc.stdout.read(1024*1024)
                if not data:
                    break
                count += len(data)
                if count > size:
                    raise ValueError("download exceeds pinned size")
                h.update(data)
                f.write(data)
        err = proc.stderr.read()
        if proc.wait(timeout=60) != 0:
            raise ValueError("archive download failed: "+clean(err.decode(errors="replace")[:500]))
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()
    if count != size or h.hexdigest() != sha:
        raise ValueError("archive byte/hash mismatch")
    TOTAL["download"] += count
    if TOTAL["download"] > LIMITS["download_bytes"]:
        raise ValueError("total download budget exceeded")
    return meta

def inspect(pin, path, meta):
    platform, artifact, size, sha = pin
    result = {"platform": platform, "artifact_id": artifact, "archive_bytes": size,
              "archive_sha256": sha, "producer_source": SOURCE, "producer_run": RUN,
              "producer_attempt": 1, "members": [], "text_evidence": [],
              "application_identities": [], "missing_or_unverified": [],
              "mode_binding_verified": False, "real_ax_reassessment_performed": False}
    with zipfile.ZipFile(path) as z:
        seen = set()
        entries = {}
        for info in z.infolist():
            name = info.filename
            normalized = str(PurePosixPath(name))
            mode = stat.S_IFMT(info.external_attr >> 16)
            if (not name or "\x00" in info.orig_filename or "\\" in name or
                name.startswith("/") or ":" in name or ".." in PurePosixPath(name).parts or
                name.rstrip("/") != normalized or normalized in seen or
                info.flag_bits & 1 or mode not in (0, stat.S_IFREG, stat.S_IFDIR) or
                (mode == stat.S_IFDIR and not info.is_dir()) or (mode == stat.S_IFREG and info.is_dir())):
                raise ValueError("unsafe ZIP member")
            seen.add(normalized)
            TOTAL["members"] += 1
            TOTAL["declared"] += info.file_size
            if TOTAL["members"] > LIMITS["members"] or TOTAL["declared"] > LIMITS["declared_expanded_bytes"] or info.file_size > LIMITS["member_bytes"]:
                raise ValueError("ZIP declared budget exceeded")
            entries[name] = info
            result["members"].append({"path": clean(name), "bytes": info.file_size})
        for name, info in entries.items():
            if info.is_dir():
                continue
            low = name.lower()
            is_plist = low.endswith("/info.plist") and ".app/" in low
            is_text = low.endswith((".json", ".log", ".txt", ".xml", ".jsonl")) and bool(
                re.search(r"report|summary|manifest|a11y|accessib|snapshot|tree|build|setting|compile|\.log$|\.jsonl$", low))
            if not (is_plist or is_text):
                continue
            if info.file_size > LIMITS["text_member_bytes"] or TOTAL["text"]+info.file_size > LIMITS["selected_text_bytes"]:
                result["missing_or_unverified"].append("selected text exceeds limit: "+clean(name))
                continue
            raw = z.read(info)
            TOTAL["text"] += len(raw)
            TOTAL["payload_read"] += len(raw)
            if TOTAL["payload_read"] > LIMITS["declared_expanded_bytes"]:
                raise ValueError("total payload read budget exceeded")
            item = {"path": clean(name), "bytes": len(raw), "sha256": digest(raw)}
            if is_plist:
                try:
                    obj = plistlib.loads(raw)
                    exe = obj.get("CFBundleExecutable")
                    identity = {"plist": name, "plist_sha256": digest(raw),
                                "bundle_id": obj.get("CFBundleIdentifier"),
                                "embedded_source": obj.get("EXRSourceSHA"), "executable": exe}
                    if isinstance(exe, str) and "/" not in exe and exe not in ("", ".", ".."):
                        parent = name.rsplit("/", 1)[0]
                        candidates = [parent+"/"+exe]
                        if parent.endswith("/Contents"):
                            candidates.append(parent+"/MacOS/"+exe)
                        found = [n for n in candidates if n in entries]
                        if len(found) == 1:
                            h = hashlib.sha256()
                            with z.open(found[0]) as stream:
                                for chunk in iter(lambda: stream.read(1024*1024), b""):
                                    TOTAL["payload_read"] += len(chunk)
                                    if TOTAL["payload_read"] > LIMITS["declared_expanded_bytes"]:
                                        raise ValueError("total payload read budget exceeded")
                                    h.update(chunk)
                            identity["executable_member"] = found[0]
                            identity["executable_sha256"] = h.hexdigest()
                        else:
                            identity["unverified"] = "executable member missing or ambiguous"
                    result["application_identities"].append(clean(identity))
                except (ValueError, TypeError, plistlib.InvalidFileException) as e:
                    item["parse_error"] = str(e)[:200]
            else:
                try:
                    text = raw.decode("utf-8")
                except UnicodeDecodeError:
                    item["parse_error"] = "not UTF-8 text"
                    result["text_evidence"].append(item)
                    continue
                parsed = None
                if low.endswith(".json"):
                    try:
                        parsed = json.loads(text)
                        item["json_summary"] = summarize_json(parsed)
                        item["audit_report_bindings"] = report_bindings(parsed)
                    except (ValueError, TypeError, RecursionError) as e:
                        item["parse_error"] = str(e)[:200]
                item["raw_ax_records"] = ax_records(text, parsed)
                lines = text.splitlines()
                matches = []
                for i, line in enumerate(lines, 1):
                    if re.search(r"SWIFT_ACTIVE_COMPILATION_CONDITIONS|OTHER_SWIFT_FLAGS|swiftc.*EXR_APPLE_|EXRSourceSHA|program_sha|executable_sha|libsqlite3|build.mode", line):
                        if len(matches) < 16:
                            matches.append({"line": i, "text": clean(line[:900])})
                item["build_identity_lines"] = matches
                item["reader_state_mentions"] = text.count("reader.state")
                item["library_empty_mentions"] = text.count("library.empty")
                # Full selected text is not published; raw member hashes preserve source identity.
            result["text_evidence"].append(item)
    by_basename = {}
    for item in result["text_evidence"]:
        by_basename.setdefault(PurePosixPath(item["path"]).name, []).append(item)
    result["report_to_log_bindings"] = []
    for item in result["text_evidence"]:
        for binding in item.get("audit_report_bindings", []):
            checks = []
            for name, expected in binding.get("log_sha256", {}).items():
                matching = by_basename.get(name, [])
                checks.append({"log": name, "expected_sha256": expected,
                               "matches_original_member": len(matching) == 1 and matching[0]["sha256"] == expected,
                               "matching_member_count": len(matching)})
            result["report_to_log_bindings"].append({"report": item["path"], "program": binding.get("program"),
                                                    "log_checks": checks})
    result["missing_or_unverified"].extend([
        "Historical artifact producer identity is pinned; mode-to-AX-to-program binding requires independent review of listed original members.",
        "No candidate contract evaluation or six-blocker reclassification performed.",
        "Member matches and compile tokens alone do not establish a complete trustworthy AX snapshot.",
    ])
    return result

def main():
    if os.environ.get("GITHUB_ACTIONS") != "true":
        raise RuntimeError("Actions only")
    signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(TimeoutError("480-second diagnostic budget")))
    signal.alarm(480)
    OUT.mkdir(parents=True, exist_ok=True)
    try:
        producer = api("actions/runs/"+str(RUN)+"/attempts/1")
        if producer["id"] != RUN or producer["run_attempt"] != 1 or producer["head_sha"] != SOURCE or producer["status"] != "completed":
            raise ValueError("producer attempt mismatch")
        for pin in PINS:
            with tempfile.TemporaryDirectory(prefix="f09-g16-") as tmp:
                path = Path(tmp)/"pinned.zip"
                meta = download(pin, path)
                REPORT["artifacts"].append(inspect(pin, path, meta))
        REPORT["archive_inspection_complete"] = True
    except Exception as error:
        REPORT["failures"].append(clean(type(error).__name__+": "+str(error)))
    finally:
        signal.alarm(0)
        REPORT["totals"] = TOTAL
        (OUT/"report.json").write_text(json.dumps(clean(REPORT), ensure_ascii=False, indent=2)+"\n")
        summary = copy_summary(REPORT)
        print("F09_G16_RAW_IDENTITY_BEGIN")
        print(json.dumps(clean(summary), ensure_ascii=True, indent=2))
        print("F09_G16_RAW_IDENTITY_END")
    return 0 if REPORT["archive_inspection_complete"] else 1

def copy_summary(report):
    summary = {k: v for k, v in report.items() if k != "artifacts"}
    summary["artifacts"] = []
    for artifact in report["artifacts"]:
        entry = {k: v for k, v in artifact.items() if k != "members"}
        evidence = artifact["text_evidence"]
        def priority(item):
            return (bool(item.get("audit_report_bindings")),
                    item.get("raw_ax_records", {}).get("valid_records", 0) > 0,
                    bool(item.get("build_identity_lines")), item.get("reader_state_mentions", 0))
        chosen = sorted(evidence, key=priority, reverse=True)[:16]
        entry["text_evidence"] = []
        for item in chosen:
            item = dict(item)
            if "raw_ax_records" in item:
                ax = dict(item["raw_ax_records"])
                records = ax["records"]
                ax["records"] = records[:80]
                ax["records_omitted"] = max(0, len(records)-80)
                item["raw_ax_records"] = ax
            item["build_identity_lines"] = [
                {"line": x["line"], "text": x["text"][:500]}
                for x in item.get("build_identity_lines", [])[:5]]
            if "json_summary" in item:
                js = dict(item["json_summary"])
                js["identity_fields"] = js["identity_fields"][:10]
                item["json_summary"] = js
            entry["text_evidence"].append(item)
        entry["selected_text_members_total"] = len(evidence)
        entry["stdout_text_members_omitted"] = max(0, len(evidence)-16)
        entry["stdout_detail_may_be_truncated"] = True
        entry["member_count"] = len(artifact["members"])
        entry["member_inventory_in_report"] = True
        summary["artifacts"].append(entry)
    return summary

if __name__ == "__main__":
    raise SystemExit(main())
