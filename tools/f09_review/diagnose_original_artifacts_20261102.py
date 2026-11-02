#!/usr/bin/env python3
"""Read six fixed F09 archives. Never run product code or change acceptance."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import signal
import stat
import subprocess
import sys
import tempfile
import zipfile
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

REPO = "NoGod3524/EXReader"
SOURCE = "e9e20eada714bc6b8045d3e943ac46ff26844559"
MIB = 1024 * 1024
DOWNLOAD_LIMIT, UNPACK_LIMIT, MEMBER_LIMIT = 16*MIB, 256*MIB, 32*MIB
FILE_LIMIT, OUTPUT_LIMIT = 2000, 8*MIB
SPECS = [
    (13106548189, 41363865966, 1, "f09-windows-41363865966-1", 1427630, "3aa5f70fede4d7a1d05b14d7f6d49f93c8d790654902c73427b69c2cd2f61280"),
    (13106488337, 41363865966, 1, "f09-linux-41363865966-1", 1674860, "84662bbce311cf0b45479305814d14ea0ddb55ce3c90a8bd4662b69d7598bbd5"),
    (13106609827, 41363868404, 1, "f09-apple-checks-iphone-41363868404-1", 770823, "f0f95ab344f4ebec7c1778775c8813f5162fa32bb030cb588e61d292ffdc756f"),
    (13108011698, 41363868404, 2, "f09-apple-checks-iphone-41363868404-2", 6427999, "41737f04dd618e40de0673bfa52f47f5f3e23578d639d0b71475994acadd5931"),
    (13108402666, 41363868404, 3, "f09-apple-checks-iphone-41363868404-3", 770829, "1b2085228ef79c5e40427074e1248e4393af586c436d7a3f0b77612e6f7e8c63"),
    (13107172229, 41363868404, 1, "f09-apple-validation-41363868404-1", 5428, "77a8d6c5d12efd6ef6a1e68dc5ce4a133d935f26d8e5ec38f483a84c90e59b55"),
]
OUT = Path("f09-original-evidence-output")
OUT.mkdir(exist_ok=True)
report = {
    "schema": 1, "acceptance_eligible": False, "ledger_change": False,
    "diagnostic_complete": False, "archive_inspection_complete": False,
    "product_evidence_complete": False, "original_source": SOURCE,
    "diagnostic_commit": os.environ.get("GITHUB_SHA"),
    "diagnostic_run": os.environ.get("GITHUB_RUN_ID"),
    "diagnostic_attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
    "scope": "six fixed archives; text evidence only; no product/build/test execution",
    "budgets": {"archive_bytes": DOWNLOAD_LIMIT, "unpacked_bytes": UNPACK_LIMIT,
                "member_bytes": MEMBER_LIMIT, "members": FILE_LIMIT, "output_bytes": OUTPUT_LIMIT},
    "runs": [], "artifacts": [], "counters": {"downloaded": 0, "unpacked": 0, "members": 0},
    "limitations": [
        "Diagnostic success is not product acceptance. Retain every original failure.",
        "Source compilation configuration is not actual artifact build-settings proof.",
        "Manifest hashes are not independently verified executable bytes.",
        "No macOS/iPad raw G16 archives in this six-archive package.",
        "Missing VoiceOver/physical-device evidence cannot be inferred from structure tests.",
        "Text matches are evidence candidates, not an automatic stale-test adjudication."
    ],
}
TEXT_EXT = {".json", ".jsonl", ".ndjson", ".log", ".txt", ".plist", ".md",
            ".yaml", ".yml", ".status", ".sha256", ".out"}
PATTERN = re.compile(r"fail|error|blocked|blocking|not.verified|unanswered_tap|"
                     r"reader[.]state|library[.]empty|KB-06|import_edit|"
                     r"SWIFT_ACTIVE_COMPILATION_CONDITIONS|EXR_APPLE_HOST_REVIEW|"
                     r"executable_sha256|info_plist_sha256|program_files_sha256", re.I)
SECRET = re.compile(r"(?i)(authorization\s*[:=]\s*(?:bearer\s+|token\s+)?)[^\s,;]+")
TOKEN = re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,})\b")
SENSITIVE = {"password", "passwd", "passphrase", "authorization", "cookie", "setcookie",
             "accesstoken", "refreshtoken", "idtoken", "authtoken", "bearertoken",
             "clientsecret", "credentials", "apikey", "privatekey", "sessiontoken"}
def sensitive(key):
    return re.sub(r"[^a-z0-9]", "", str(key).lower()) in SENSITIVE

def clean_url(match):
    original = match.group(0)
    try:
        u = urlsplit(original)
        netloc = u.netloc.rsplit("@", 1)[-1]
        return urlunsplit((u.scheme, netloc, u.path, "", ""))
    except ValueError:
        return "[REDACTED_UNPARSEABLE_URL]"

def clean(text):
    text = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", text)
    text = TOKEN.sub("[REDACTED]", SECRET.sub(r"\1[REDACTED]", text))
    text = re.sub(r'https?://[^\s<>"\']+', clean_url, text)
    keys = r"password|passwd|passphrase|client_secret|access_token|refresh_token|api_key|cookie"
    text = re.sub(r'(?i)(\b(?:'+keys+r')\b["\']?\s*[:=]\s*)("[^"]*"|\'[^\']*\'|[^\s,;]+)',
                  r'\1[REDACTED]', text)
    return text

def redact(value):
    if isinstance(value, dict):
        return {clean(str(k)): "[REDACTED]" if sensitive(k) else redact(v)
                for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v) for v in value]
    return clean(value) if isinstance(value, str) else value

def alarm_handler(_signal, _frame):
    raise TimeoutError("420-second diagnostic budget reached")
signal.signal(signal.SIGALRM, alarm_handler)
signal.signal(signal.SIGTERM, alarm_handler)
signal.alarm(420)

def api(path):
    raw = subprocess.check_output(["gh", "api", "repos/"+REPO+"/"+path],
                                  timeout=60)
    if len(raw) > 4*MIB:
        raise ValueError("API response exceeds 4 MiB")
    return json.loads(raw)

def download(artifact_id, target, expected_size, expected_hash):
    proc = subprocess.Popen(["gh", "api", "repos/"+REPO+"/actions/artifacts/"+str(artifact_id)+"/zip"],
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    h, size = hashlib.sha256(), 0
    try:
        with target.open("wb") as out:
            while True:
                chunk = proc.stdout.read(65536)
                if not chunk:
                    break
                size += len(chunk)
                report["counters"]["downloaded"] += len(chunk)
                if size > expected_size or report["counters"]["downloaded"] > DOWNLOAD_LIMIT:
                    raise ValueError("download byte budget exceeded")
                out.write(chunk)
                h.update(chunk)
        if proc.wait(timeout=60):
            raise ValueError("archive download failed")
        if size != expected_size or h.hexdigest() != expected_hash:
            raise ValueError("archive size/digest mismatch")
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()
        proc.stdout.close()

def inspect_archive(path, item):
    with zipfile.ZipFile(path) as archive:
        members = archive.infolist()
        report["counters"]["members"] += len(members)
        if report["counters"]["members"] > FILE_LIMIT:
            raise ValueError("member count budget exceeded")
        names = set()
        selected = []
        item["members_inventory"] = []
        for z in members:
            p = PurePosixPath(z.filename)
            normalized = p.as_posix()
            kind = stat.S_IFMT(z.external_attr >> 16)
            if ("\x00" in z.orig_filename or z.filename.rstrip("/") != normalized or
                normalized in names or p.is_absolute() or
                ".." in p.parts or "\\" in z.filename or ":" in z.filename or
                (not z.is_dir() and normalized in {"", "."}) or
                z.flag_bits & 1 or kind not in (0, stat.S_IFREG, stat.S_IFDIR)):
                raise ValueError("unsafe, encrypted, nonregular or duplicate archive member")
            names.add(normalized)
            if z.file_size > MEMBER_LIMIT:
                raise ValueError("single member budget exceeded")
            report["counters"]["unpacked"] += z.file_size
            if report["counters"]["unpacked"] > UNPACK_LIMIT:
                raise ValueError("unpacked byte budget exceeded")
            chosen = not z.is_dir() and p.suffix.lower() in TEXT_EXT
            item["members_inventory"].append({"path": clean(z.filename),
                "bytes": z.file_size, "compressed_bytes": z.compress_size,
                "kind": "directory" if z.is_dir() else "regular",
                "selected_text": chosen})
            if chosen:
                selected.append(z)
        item["archive_member_count"] = len(members)
        item["selected_text_count"] = len(selected)
        item["text_evidence"] = []
        for z in selected:
            with archive.open(z) as src:
                raw = src.read(MEMBER_LIMIT + 1)
            if len(raw) != z.file_size or len(raw) > MEMBER_LIMIT:
                raise ValueError("member length mismatch")
            evidence = {"path": clean(z.filename), "bytes": len(raw),
                        "sha256": hashlib.sha256(raw).hexdigest()}
            try:
                text = raw.decode("utf-8-sig")
            except UnicodeDecodeError:
                evidence["unreadable_text"] = "binary/non-UTF8; not parsed"
                item["text_evidence"].append(evidence)
                continue
            matches = []
            for n, line in enumerate(text.splitlines(), 1):
                if PATTERN.search(line):
                    matches.append({"line": n, "text": clean(line[:1500])})
            evidence["matching_line_count"] = len(matches)
            evidence["matching_lines"] = matches[:80]
            evidence["matches_omitted"] = max(0, len(matches)-80)
            # Full small JSON reports preserve original assertion budgets/failures.
            # Large reports remain in the unchanged input artifact and are indexed.
            if z.filename.lower().endswith(".json") and len(raw) <= 128*1024:
                try:
                    evidence["original_json"] = redact(json.loads(text))
                    evidence["json_view"] = "redacted structured view; not original bytes; raw sha256 retained"
                except (ValueError, RecursionError):
                    evidence["json_parse_error"] = True
            item["text_evidence"].append(evidence)
            if len(json.dumps(report, ensure_ascii=False).encode()) > 6*MIB:
                raise ValueError("diagnostic report content exceeds 6 MiB; no silent trimming")

def main():
    if os.environ.get("GITHUB_ACTIONS") != "true":
        raise ValueError("Actions-only diagnostic")
    if sum(s[4] for s in SPECS) != 11077569:
        raise ValueError("fixed input size guard")
    for rid, attempts in [(41363865966, [1]), (41363868404, [1, 2, 3])]:
        run = api("actions/runs/"+str(rid))
        if run.get("id") != rid or run.get("head_sha") != SOURCE or run.get("status") != "completed":
            raise ValueError("run source mismatch")
        rec = {k: run.get(k) for k in ("id", "head_sha", "status", "conclusion", "run_attempt", "html_url")}
        rec["attempts"] = []
        for attempt in attempts:
            original = api("actions/runs/"+str(rid)+"/attempts/"+str(attempt))
            if (original.get("id") != rid or original.get("head_sha") != SOURCE or
                original.get("run_attempt") != attempt or original.get("status") != "completed"):
                raise ValueError("original attempt identity/state mismatch")
            attempt_identity = {k: original.get(k) for k in
                ("id", "head_sha", "run_attempt", "status", "conclusion", "created_at", "updated_at")}
            jobs = api("actions/runs/"+str(rid)+"/attempts/"+str(attempt)+"/jobs?per_page=100")
            if jobs["total_count"] > 100:
                raise ValueError("unread job pagination")
            rec["attempts"].append({"attempt": attempt, "identity": attempt_identity, "jobs": [
                {k: j.get(k) for k in ("id", "name", "status", "conclusion", "started_at", "completed_at")}
                for j in jobs["jobs"]]})
        report["runs"].append(rec)
    with tempfile.TemporaryDirectory(prefix="f09-evidence-") as tmp:
        for aid, rid, attempt, name, size, digest in SPECS:
            meta = api("actions/artifacts/"+str(aid))
            if (meta.get("id") != aid or meta.get("name") != name or
                meta.get("size_in_bytes") != size or meta.get("digest") != "sha256:"+digest or
                meta.get("expired") is not False or
                meta.get("workflow_run", {}).get("id") != rid or
                meta.get("workflow_run", {}).get("head_sha") != SOURCE):
                raise ValueError("artifact metadata identity mismatch: "+str(aid))
            item = {"id": aid, "run": rid, "attempt": attempt, "name": name, "bytes": size,
                    "archive_sha256": digest, "metadata_verified": True}
            report["artifacts"].append(item)
            path = Path(tmp)/(str(aid)+".zip")
            download(aid, path, size, digest)
            item["download_digest_verified"] = True
            inspect_archive(path, item)
            path.unlink()
    candidates = {"actual_build_settings": [], "executable_identity_manifest": [],
                  "original_failures": [], "unanswered_tap": []}
    for item in report["artifacts"]:
        for evidence in item["text_evidence"]:
            for hit in evidence.get("matching_lines", []):
                text = hit["text"]
                ref = {"artifact": item["id"], "path": evidence["path"], "line": hit["line"]}
                if re.search(r"SWIFT_ACTIVE_COMPILATION_CONDITIONS|EXR_APPLE_HOST_REVIEW", text):
                    candidates["actual_build_settings"].append(ref)
                if re.search(r"executable_sha256|info_plist_sha256|program_files_sha256", text):
                    candidates["executable_identity_manifest"].append(ref)
                if re.search(r"fail|error|blocking|not.verified", text, re.I):
                    candidates["original_failures"].append(ref)
                if "unanswered_tap" in text:
                    candidates["unanswered_tap"].append(ref)
    report["coverage"] = {name: {"status": "candidate_text_found" if rows else "missing_in_selected_text",
                                     "references": rows, "adjudicated": False}
                          for name, rows in candidates.items()}
    report["coverage"].update({
        "archive_identity": {"status": "verified", "count": len(report["artifacts"])},
        "binary_identity": {"status": "unverified", "reason": "No binary bytes read or hashed"},
        "raw_g16_platform_archives": {"status": "not_in_scope", "reason": "Only G16 summary selected"},
        "voiceover_iphone_ipad": {"status": "unverified", "reason": "No new screen-reader execution"},
        "product_tests": {"status": "not_run", "reason": "Original-artifact-only diagnostic"},
        "iphone_flake_root_cause": {"status": "unverified", "reason": "Evidence extraction is not a fix"}
    })
    report["missing_or_unverified"] = [
        {"item": name, "status": value["status"]}
        for name, value in report["coverage"].items() if value["status"] != "verified"]
    report["archive_inspection_complete"] = True
    report["diagnostic_complete"] = True

code = 0
try:
    main()
except Exception as exc:
    code = 1
    report["diagnostic_error"] = clean(type(exc).__name__+": "+str(exc))[:2000]
finally:
    signal.alarm(0)
    payload = json.dumps(report, ensure_ascii=False, indent=2).encode()
    if len(payload) > OUTPUT_LIMIT - 16384:
        # Fail closed without claiming complete evidence; preserve identity and error.
        report = {k: v for k, v in report.items() if k != "artifacts"}
        report.update(diagnostic_complete=False, archive_inspection_complete=False, diagnostic_error="Output budget exceeded; evidence omitted explicitly")
        payload = json.dumps(report, ensure_ascii=False, indent=2).encode()
        code = 1
    (OUT/"report.json").write_bytes(payload)
    lines = ["# F09 original-artifact diagnostic", "",
             "Acceptance eligible: **false**. No ledger changes.", "",
             "Original source: "+SOURCE,
             "Diagnostic complete: "+str(report["diagnostic_complete"]), "",
             "Original failures remain in report.json. This is not a product test rerun.",
             "Missing files/settings/package identities remain unverified.", "",
             "## Limits"] + ["- "+s for s in report["limitations"]]
    if "diagnostic_error" in report:
        lines += ["", "Diagnostic error: "+report["diagnostic_error"]]
    (OUT/"report.md").write_text("\n".join(lines)+"\n")
    total = sum(p.stat().st_size for p in OUT.iterdir() if p.is_file())
    if total > OUTPUT_LIMIT:
        raise RuntimeError("output hard limit exceeded")
sys.exit(code)
