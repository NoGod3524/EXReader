# SPDX-License-Identifier: MIT
"""Pure identity/archive/report checks for the Windows TTS acceptance artifacts.

Every value is recomputed from the bytes downloaded in this run; nothing in the
uploaded report is trusted on its own.
"""
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import PurePosixPath
import re
import stat
import struct
import zipfile
import zlib

WORKFLOW = ".github/workflows/reader-tts-windows.yml"
PRODUCER_JOB = "tts (windows-2022)"
REPORT_JOB = "same-source report"
MODULE = "EXReaderTTSWindows"
MODULE_VERSION = "0.1.0"
PHASES = [("basic", 45), ("speak", 21), ("unicode", 12), ("limits", 27), ("control", 28),
          ("chunks", 25), ("overflow", 9), ("service", 7), ("memory", 17), ("close", 11)]
TOTAL_CHECKS = sum(count for _, count in PHASES)
MAX_ZIP, MAX_EXPANDED, MAX_FILES = 64 * 1024 * 1024, 128 * 1024 * 1024, 1024
CHECK_LINE = re.compile(r"check ([a-z0-9][a-z0-9._]*) (pass|fail) (\S.*)\Z")
PHASE_LINE = re.compile(r"phase ([a-z0-9-]+) (\d+) (\d+)\Z")
WAV_LINE = re.compile(r"wavfile (.+) (\d+)\Z")
INFO_LINE = re.compile(r"info ([a-z0-9._]+) (\d+)\Z")


class EvidenceError(Exception):
    pass


def need(value, code):
    if not value:
        raise EvidenceError(code)


def integer(value, minimum=0):
    return type(value) is int and value >= minimum


def digest(data):
    return hashlib.sha256(data).hexdigest()


def decode_json(data):
    def pairs(rows):
        result = {}
        for key, value in rows:
            need(key not in result, "duplicate_json_key")
            result[key] = value
        return result

    def constant(_):
        raise EvidenceError("nonfinite_json")

    try:
        value = json.loads(data, object_pairs_hook=pairs, parse_constant=constant)
        need(type(value) is dict, "json_root")
        return value
    except (ValueError, UnicodeError):
        raise EvidenceError("json_format") from None


def safe_path(name):
    need(type(name) is str and name and "\\" not in name and "\0" not in name and ":" not in name,
         "archive_path")
    path = PurePosixPath(name)
    need(not path.is_absolute() and ".." not in path.parts and str(path) == name and name != ".",
         "archive_path")
    return name


def select(rows, name, code="named_evidence_missing_or_duplicate"):
    matches = [row for row in rows if row.get("name") == name]
    need(len(matches) == 1, code)
    return matches[0]


def unique(rows, code):
    need(type(rows) is list, code)
    ids, names = set(), set()
    for row in rows:
        need(type(row) is dict and integer(row.get("id"), 1) and type(row.get("name")) is str, code)
        need(row["id"] not in ids and row["name"] not in names, code)
        ids.add(row["id"])
        names.add(row["name"])


def artifact_identity(artifact, run, now):
    need(artifact.get("expired") is False and integer(artifact.get("size_in_bytes"), 1)
         and artifact["size_in_bytes"] <= MAX_ZIP, "artifact_expired_or_empty")
    try:
        expires = datetime.fromisoformat(artifact["expires_at"].replace("Z", "+00:00"))
        need(expires.tzinfo is not None and expires > now, "artifact_expired_time")
    except (ValueError, TypeError, AttributeError, KeyError):
        raise EvidenceError("artifact_expiry") from None
    need(type(artifact.get("digest")) is str and re.fullmatch(r"sha256:[a-f0-9]{64}", artifact["digest"]),
         "artifact_digest")
    origin = artifact.get("workflow_run", {})
    need(origin.get("id") == run["id"] and origin.get("head_sha") == run["head_sha"]
         and origin.get("repository_id") == run["repository"]["id"]
         and origin.get("head_repository_id") == run["head_repository"]["id"], "artifact_origin")


def archive_files(data, artifact):
    need(type(data) is bytes and len(data) == artifact["size_in_bytes"] and len(data) <= MAX_ZIP, "zip_size")
    need("sha256:" + digest(data) == artifact["digest"], "zip_digest")
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            infos = archive.infolist()
            need(0 < len(infos) <= MAX_FILES, "zip_file_limit")
            names, files, total = set(), {}, 0
            for info in infos:
                name = safe_path(info.filename.rstrip("/") if info.is_dir() else info.filename)
                need(name.casefold() not in names, "zip_duplicate_path")
                names.add(name.casefold())
                need(stat.S_IFMT(info.external_attr >> 16) in (0, stat.S_IFREG, stat.S_IFDIR)
                     and not info.flag_bits & 1, "zip_special_or_encrypted")
                if info.is_dir():
                    continue
                total += info.file_size
                need(total <= MAX_EXPANDED
                     and info.compress_type in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED),
                     "zip_expanded_or_compression")
                files[name] = archive.read(info)
            return files
    except (zipfile.BadZipFile, RuntimeError, OSError, NotImplementedError, zlib.error):
        raise EvidenceError("zip_format") from None


def upload_binding(log, artifact):
    need(type(log) is bytes and 0 < len(log) <= MAX_EXPANDED, "producer_log")
    text = log.decode("utf-8", "replace")
    matches = list(re.finditer(r"Artifact " + re.escape(artifact["name"])
                               + r" has been successfully uploaded! Final size is (\d+) bytes\. Artifact ID is (\d+)",
                               text))
    need(len(matches) == 1 and int(matches[0][1]) == artifact["size_in_bytes"]
         and int(matches[0][2]) == artifact["id"], "producer_artifact_binding")
    hashes = re.findall(r"SHA256 digest of uploaded artifact zip is ([a-f0-9]{64})", text[:matches[0].start()])
    need(hashes and "sha256:" + hashes[-1] == artifact["digest"], "producer_digest_binding")
    return digest(log)


def wav_container(data):
    need(type(data) is bytes and len(data) >= 44 and data[0:4] == b"RIFF" and data[8:12] == b"WAVE", "wav_header")
    riff_size = struct.unpack("<I", data[4:8])[0]
    need(riff_size + 8 <= len(data) and len(data) - (riff_size + 8) <= 1, "wav_riff_size")
    offset, fmt, samples = 12, None, None
    while offset + 8 <= len(data):
        chunk_id = data[offset:offset + 4]
        size = struct.unpack("<I", data[offset + 4:offset + 8])[0]
        body = data[offset + 8:offset + 8 + size]
        need(len(body) == size, "wav_truncated_chunk")
        if chunk_id == b"fmt ":
            need(size >= 16, "wav_fmt")
            fmt = struct.unpack("<HHIIHH", body[:16])
        elif chunk_id == b"data":
            samples = size
        offset += 8 + size + (size & 1)
    need(fmt is not None and samples is not None, "wav_chunks")
    tag, channels, rate, _byte_rate, block, bits = fmt
    need((tag, channels, rate, bits) == (1, 1, 22050, 16) and block == 2, "wav_pcm")
    need(samples > 0, "wav_empty")
    return {"samples": samples, "duration_ms": samples * 1000 // (rate * block)}


def phase_checks(files, entry, label, expected):
    need(type(entry) is dict and entry.get("label") == label and entry.get("phase") == label, "phase_contract")
    name = entry.get("log")
    need(type(name) is str and re.fullmatch(r"\d{2}-[a-z0-9-]+", name) and name.endswith("-" + label),
         "phase_log_name")
    out, err = "evidence/logs/" + name + ".stdout.log", "evidence/logs/" + name + ".stderr.log"
    need(out in files and err in files, "phase_logs_missing")
    checks, observed, wavs = [], [], []
    for line in files[out].decode("utf-8", "strict").splitlines():
        line = line.strip()
        if not line:
            continue
        match = CHECK_LINE.match(line)
        if match:
            checks.append({"id": match[1], "result": match[2], "detail": match[3]})
            continue
        match = PHASE_LINE.match(line)
        if match:
            observed.append({"phase": match[1], "passed": int(match[2]), "total": int(match[3])})
            continue
        match = WAV_LINE.match(line)
        if match:
            wavs.append({"path": match[1], "minimum_ms": int(match[2])})
            continue
        need(INFO_LINE.match(line), "phase_unparsed_output")
    need(entry.get("checks") == checks, "phase_raw_mismatch")
    need(entry.get("summaries") == observed, "phase_summary_mismatch")
    ids = [row["id"] for row in checks]
    need(len(ids) == len(expected) and len(ids) == len(set(ids)), "phase_check_count")
    need(all(row["id"].startswith(label + ".") for row in checks), "phase_check_prefix")
    complete = (all(row["result"] == "pass" for row in checks) and entry.get("exit") == 0
                and observed == [{"phase": label, "passed": len(ids), "total": len(ids)}]
                and entry.get("accepted") is True)
    need(complete, "phase_incomplete")
    return checks, wavs


def verify_report(files, run):
    need("evidence/report.json" in files and len(files["evidence/report.json"]) <= 4 * 1024 * 1024,
         "report_missing_or_large")
    report = decode_json(files["evidence/report.json"])
    need(report.get("schema") == 1 and report.get("module") == MODULE
         and report.get("module_version") == MODULE_VERSION and report.get("platform") == "windows"
         and report.get("accepted") is True, "report_contract")
    need(report.get("source_sha") == run["head_sha"] and report.get("run_id") == str(run["id"])
         and report.get("run_attempt") == str(run["run_attempt"]) and report.get("job") == PRODUCER_JOB,
         "report_origin")
    need(report.get("runner", {}).get("os") == "Windows", "report_runner")
    labels = [label for label, _ in PHASES]
    need(report.get("phase_labels") == labels, "phase_labels")
    phases = report.get("phases")
    need(type(phases) is list and len(phases) == len(PHASES), "phase_count")
    total, wav_lines = 0, []
    for entry, (label, expected) in zip(phases, PHASES):
        checks, wavs = phase_checks(files, entry, label, range(expected))
        total += len(checks)
        wav_lines.extend((label, row) for row in wavs)
    need(report.get("checks") == total == TOTAL_CHECKS and report.get("passed") == total
         and report.get("expected_checks") == TOTAL_CHECKS, "report_counts")
    wavs = report.get("wavs")
    need(type(wavs) is list and len(wavs) >= len(wav_lines), "wav_list")
    by_file = {}
    for row in wavs:
        need(type(row) is dict and type(row.get("file")) is str and integer(row.get("bytes"), 1)
             and type(row.get("sha256")) is str and integer(row.get("duration_ms"), 1), "wav_record")
        need(row["file"] not in by_file, "wav_duplicate")
        by_file[row["file"]] = row
    for label, line in wav_lines:
        name = PurePosixPath(line["path"].replace("\\", "/")).name
        need(name in by_file, "wav_missing")
        path = "wav/" + safe_path(name)
        need(path in files, "wav_archive_missing")
        data = files[path]
        measure = wav_container(data)
        record = by_file[name]
        need(record["bytes"] == len(data) and record["sha256"] == digest(data)
             and record["duration_ms"] == measure["duration_ms"], "wav_hash_or_duration")
        need(measure["duration_ms"] >= line["minimum_ms"], "wav_too_short")
    probe = report.get("probe")
    need(type(probe) is dict and probe.get("exit") == 0 and probe.get("summary", {}).get("result") == "pass",
         "probe_contract")
    need(probe["summary"].get("started") == 1 and probe["summary"].get("finished") == 1
         and probe["summary"].get("failed") == 0 and probe["summary"].get("bad_range") == 0
         and probe["summary"].get("state_after") == "READY", "probe_summary")
    need(probe["summary"]["ranges"] >= 5 and 0 < probe["summary"]["max_end"] <= probe["summary"]["text_bytes"],
         "probe_ranges")
    probe_wav = by_file.get(probe.get("wav", {}).get("file"))
    need(probe_wav is not None and probe_wav["sha256"] == digest(files["wav/" + safe_path(probe_wav["file"])]),
         "probe_wav_record")
    need("consumer/tts-consumer.exe" in files, "consumer_archive_missing")
    consumer = report.get("consumer", {})
    need(consumer.get("name") == "tts-consumer.exe" and consumer.get("bytes") == len(files["consumer/tts-consumer.exe"])
         and consumer.get("sha256") == digest(files["consumer/tts-consumer.exe"]), "consumer_hash")
    need("consumer/tts-probe.exe" in files, "probe_archive_missing")
    need(probe.get("bytes") == len(files["consumer/tts-probe.exe"])
         and probe.get("sha256") == digest(files["consumer/tts-probe.exe"]), "probe_hash")
    manifest = report.get("installed_files")
    need(type(manifest) is list and 0 < len(manifest) <= MAX_FILES, "installed_manifest")
    stage = set()
    for row in manifest:
        need(type(row) is dict and set(row) == {"path", "bytes", "sha256"}, "installed_record")
        name = "stage/" + safe_path(row["path"])
        need(name not in stage, "installed_duplicate")
        stage.add(name)
        need(name in files and integer(row["bytes"], 1) and row["bytes"] == len(files[name])
             and row["sha256"] == digest(files[name]), "installed_hash")
    need(stage == {name for name in files if name.startswith("stage/")}, "installed_coverage")
    for required in ("stage/include/reader_tts.h", "stage/include/reader_tts_windows.h",
                     "stage/lib/reader_tts.lib",
                     "stage/lib/cmake/EXReaderTTSWindows/EXReaderTTSWindowsConfig.cmake"):
        need(required in stage, "installed_required_file")
    need(report.get("audio_scope", {}).get("listening") == "not verified", "audio_scope")
    need(isinstance(report.get("not_exercised"), list) and report["not_exercised"], "not_exercised")
    return {"checks": total, "passed": total, "phase_labels": labels,
            "wavs": len(wav_lines), "report_sha256": digest(files["evidence/report.json"]),
            "consumer_sha256": consumer["sha256"], "probe_sha256": probe.get("sha256"),
            "not_exercised": report["not_exercised"], "installed_files": len(manifest)}


def verify_report_artifact(files, windows_digest, run):
    need("aggregate.json" in files and len(files["aggregate.json"]) <= 1024 * 1024, "report_artifact")
    aggregate = decode_json(files["aggregate.json"])
    need(aggregate.get("accepted") is True and aggregate.get("source_sha") == run["head_sha"]
         and aggregate.get("run_id") == run["id"] and aggregate.get("attempt") == run["run_attempt"],
         "report_artifact_identity")
    platform = aggregate.get("platforms", {}).get("windows", {})
    need(platform.get("artifact", {}).get("digest") == windows_digest, "report_artifact_binding")
    need(platform.get("granted") is True and platform.get("checks") == TOTAL_CHECKS, "report_artifact_checks")
    return digest(files["aggregate.json"])


def verify_checked(run, jobs, artifacts, archives, logs, repo, sha, run_id, attempt, completed=True, now=None):
    now = now or datetime.now(timezone.utc)
    need(integer(run_id, 1) and integer(attempt, 1) and type(sha) is str and re.fullmatch(r"[a-f0-9]{40}", sha),
         "target_identity")
    need(type(run.get("id")) is int and type(run.get("run_attempt")) is int
         and run.get("id") == run_id and run.get("head_sha") == sha and run.get("run_attempt") == attempt
         and run.get("path") == WORKFLOW, "run_identity")
    need(run.get("repository", {}).get("full_name") == repo and integer(run["repository"].get("id"), 1)
         and run.get("head_repository", {}).get("id") == run["repository"]["id"], "run_repository")
    need((run.get("status") == "completed" and run.get("conclusion") == "success") if completed else
         (run.get("status") == "in_progress" and run.get("conclusion") is None), "run_conclusion")
    unique(jobs, "job_duplicate")
    unique(artifacts, "artifact_duplicate")
    need({row["name"] for row in jobs} == {PRODUCER_JOB, REPORT_JOB}, "job_set")
    for job in jobs:
        need(job.get("run_id") == run_id and job.get("run_attempt") == attempt and job.get("head_sha") == sha,
             "job_origin")
        need(job.get("status") == "completed" and job.get("conclusion") == "success", "job_conclusion")
    windows_name = "reader-tts-windows-windows-%d-%d" % (run_id, attempt)
    report_name = "reader-tts-windows-report-%d-%d" % (run_id, attempt)
    relevant = [row for row in artifacts if row["name"].endswith("-%d-%d" % (run_id, attempt))]
    need({row["name"] for row in relevant} == {windows_name, report_name}, "artifact_set")
    for artifact in relevant:
        artifact_identity(artifact, run, now)
    producer = select(jobs, PRODUCER_JOB)
    reporter = select(jobs, REPORT_JOB)
    windows = select(artifacts, windows_name)
    report_artifact = select(artifacts, report_name)
    need(windows["id"] in archives and report_artifact["id"] in archives, "archive_missing")
    need(producer["id"] in logs and reporter["id"] in logs, "log_missing")
    producer_log = upload_binding(logs[producer["id"]], windows)
    reporter_log = upload_binding(logs[reporter["id"]], report_artifact)
    files = archive_files(archives[windows["id"]], windows)
    item = verify_report(files, run)
    report_files = archive_files(archives[report_artifact["id"]], report_artifact)
    aggregate_sha = verify_report_artifact(report_files, windows["digest"], run)
    result = {"schema": 2, "module": MODULE, "module_version": MODULE_VERSION, "accepted": True,
              "source_sha": sha, "run_id": run_id, "attempt": attempt, "verified_at": now.isoformat(),
              "complete_product": False, "physical_device_execution": False,
              "scope": "Windows SAPI component: synthesis to WAV, event stream, owner/argument/limit/memory/close rules",
              "platforms": {"windows": dict(item, job_id=producer["id"], job_attempt=producer["run_attempt"],
                                            job_source_sha=producer["head_sha"], producer_log_sha256=producer_log,
                                            granted=True,
                                            artifact={field: windows[field] for field in
                                                      ("id", "name", "size_in_bytes", "digest", "expired", "expires_at")})},
              "report_artifact": dict({field: report_artifact[field] for field in
                                       ("id", "name", "size_in_bytes", "digest", "expired", "expires_at")},
                                      producer_log_sha256=reporter_log, aggregate_sha256=aggregate_sha),
              "zip_digests_recomputed": 2, "granted": ["windows"],
              "pending": ["host wiring (root)", "playback through a physical audio device", "listening judgement"]}
    return result


def verify_in_run(run, jobs, artifacts, archives, logs, repo, sha, run_id, attempt, now=None):
    """Verifies the producer artifact of this very run from inside the report job.

    The report artifact does not exist yet, so the run is still in progress and the
    report job cannot be required to be complete here; verify_checked() does that in
    the retrospective verify job.
    """
    now = now or datetime.now(timezone.utc)
    need(integer(run_id, 1) and integer(attempt, 1) and type(sha) is str
         and re.fullmatch(r"[a-f0-9]{40}", sha), "target_identity")
    need(run.get("id") == run_id and run.get("head_sha") == sha and run.get("run_attempt") == attempt
         and run.get("path") == WORKFLOW, "run_identity")
    need(run.get("repository", {}).get("full_name") == repo and integer(run["repository"].get("id"), 1)
         and run.get("head_repository", {}).get("id") == run["repository"]["id"], "run_repository")
    unique(jobs, "job_duplicate")
    unique(artifacts, "artifact_duplicate")
    producer = select(jobs, PRODUCER_JOB)
    need(producer.get("run_id") == run_id and producer.get("run_attempt") == attempt
         and producer.get("head_sha") == sha, "job_origin")
    need(producer.get("status") == "completed" and producer.get("conclusion") == "success", "job_conclusion")
    windows_name = "reader-tts-windows-windows-%d-%d" % (run_id, attempt)
    windows = select(artifacts, windows_name)
    artifact_identity(windows, run, now)
    need(windows["id"] in archives and producer["id"] in logs, "archive_or_log_missing")
    producer_log = upload_binding(logs[producer["id"]], windows)
    files = archive_files(archives[windows["id"]], windows)
    item = verify_report(files, run)
    return {"schema": 2, "module": MODULE, "module_version": MODULE_VERSION, "accepted": True,
            "strict_complete": False, "source_sha": sha, "run_id": run_id, "attempt": attempt,
            "verified_at": now.isoformat(), "complete_product": False,
            "platforms": {"windows": dict(item, job_id=producer["id"], job_attempt=producer["run_attempt"],
                                          job_source_sha=producer["head_sha"], producer_log_sha256=producer_log,
                                          granted=True,
                                          artifact={field: windows[field] for field in
                                                    ("id", "name", "size_in_bytes", "digest", "expired", "expires_at")})},
            "granted": ["windows"],
            "pending": ["report artifact identity (retrospective verify job)",
                        "host wiring (root)", "playback through a physical audio device",
                        "listening judgement"]}


def verify(*args, **kwargs):
    try:
        return verify_checked(*args, **kwargs)
    except (KeyError, AttributeError, TypeError, ValueError, UnicodeError, RecursionError):
        raise EvidenceError("malformed_evidence") from None
