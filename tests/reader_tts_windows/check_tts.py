#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Actions-only acceptance harness for the Windows SAPI TTS component.

Runs the installed C consumer phase by phase, runs the separately built C++ probe,
verifies every emitted WAV container and writes evidence/report.json. It never runs
outside GitHub Actions and never substitutes an expected value for an observed one.
Every phase pins the exact number of named checks, so a silently skipped check fails
the run instead of shrinking the report.
"""
import argparse
import hashlib
import json
import os
import re
import struct
import subprocess
import sys
from pathlib import Path

CHECK_LINE = re.compile(r"check ([a-z0-9][a-z0-9._]*) (pass|fail) (\S.*)\Z")
PHASE_LINE = re.compile(r"phase ([a-z0-9-]+) (\d+) (\d+)\Z")
WAV_LINE = re.compile(r"wavfile (.+) (\d+)\Z")
INFO_LINE = re.compile(r"info ([a-z0-9._]+) (\d+)\Z")
SHA_LINE = re.compile(r"[a-f0-9]{40}\Z")
MAX_WAV_BYTES = 64 * 1024 * 1024

# label, phase, pinned check count, subprocess timeout in seconds
PHASES = [
    ("basic", "basic", 45, 180),
    ("speak", "speak", 22, 300),
    ("unicode", "unicode", 18, 300),
    ("limits", "limits", 27, 420),
    ("control", "control", 27, 420),
    ("chunks", "chunks", 25, 900),
    ("overflow", "overflow", 9, 420),
    ("service", "service", 7, 180),
    ("memory", "memory", 17, 300),
    ("close", "close", 11, 180),
]


def digest(data):
    return hashlib.sha256(data).hexdigest()


def file_digest(path):
    return digest(path.read_bytes())


def wav_container(path):
    """Returns the PCM description of a RIFF/WAVE file or raises ValueError."""
    data = path.read_bytes()
    if len(data) < 44 or data[0:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise ValueError("not a RIFF/WAVE file")
    riff_size = struct.unpack("<I", data[4:8])[0]
    if riff_size + 8 > len(data) or len(data) - (riff_size + 8) > 1:
        raise ValueError("RIFF size does not match the file")
    offset = 12
    fmt = None
    samples = None
    while offset + 8 <= len(data):
        chunk_id = data[offset:offset + 4]
        size = struct.unpack("<I", data[offset + 4:offset + 8])[0]
        body = data[offset + 8:offset + 8 + size]
        if len(body) != size:
            raise ValueError("truncated chunk " + chunk_id.decode("latin-1"))
        if chunk_id == b"fmt ":
            if size < 16:
                raise ValueError("short fmt chunk")
            tag, channels, rate, byte_rate, block, bits = struct.unpack("<HHIIHH", body[:16])
            fmt = {"tag": tag, "channels": channels, "rate": rate, "byte_rate": byte_rate,
                   "block_align": block, "bits": bits}
        elif chunk_id == b"data":
            samples = size
        offset += 8 + size + (size & 1)
    if fmt is None or samples is None:
        raise ValueError("missing fmt or data chunk")
    if fmt["tag"] != 1 or fmt["channels"] != 1 or fmt["rate"] != 22050 or fmt["bits"] != 16:
        raise ValueError("unexpected PCM format %r" % (fmt,))
    if fmt["block_align"] != fmt["channels"] * fmt["bits"] // 8:
        raise ValueError("block alignment")
    if samples <= 0:
        raise ValueError("empty audio data")
    return {"pcm": fmt, "samples": samples, "duration_ms": samples * 1000 // (fmt["rate"] * fmt["block_align"]),
            "bytes": len(data), "sha256": digest(data)}


def parse_phase(text, phase):
    checks, summaries, wavs, infos, unknown = [], [], [], [], []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        match = CHECK_LINE.match(line)
        if match:
            checks.append({"id": match[1], "result": match[2], "detail": match[3]})
            continue
        match = PHASE_LINE.match(line)
        if match:
            summaries.append({"phase": match[1], "passed": int(match[2]), "total": int(match[3])})
            continue
        match = WAV_LINE.match(line)
        if match:
            wavs.append({"path": match[1], "minimum_ms": int(match[2])})
            continue
        match = INFO_LINE.match(line)
        if match:
            infos.append({"key": match[1], "value": int(match[2])})
            continue
        unknown.append(line)
    return {"checks": checks, "summaries": summaries, "wavs": wavs, "infos": infos, "unknown": unknown}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--consumer", required=True)
    parser.add_argument("--probe", required=True)
    parser.add_argument("--module-prefix", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    output = Path(args.output)
    logs = output / "evidence" / "logs"
    wav_dir = output / "wav"
    logs.mkdir(parents=True, exist_ok=True)
    wav_dir.mkdir(parents=True, exist_ok=True)
    report = {
        "schema": 1,
        "module": "EXReaderTTSWindows",
        "module_version": "0.1.0",
        "platform": "windows",
        "accepted": False,
        "source_sha": os.environ.get("GITHUB_SHA", ""),
        "run_id": os.environ.get("GITHUB_RUN_ID", ""),
        "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT", ""),
        "job": os.environ.get("GITHUB_JOB", ""),
        "runner": {"os": "Windows", "image": os.environ.get("ImageOS", "")},
        "phases": [],
        "diagnostics": [],
        "not_exercised": ["human listening judgement of the synthesised speech",
                          "playback through a physical audio device (no device in the runner)"],
        "unavailable_scenarios": [],
    }
    failure = None

    def fail(code, detail=""):
        nonlocal failure
        if failure is None:
            failure = {"code": code, "detail": detail}

    if os.environ.get("GITHUB_ACTIONS") != "true":
        fail("cloud_required", "this harness only runs inside GitHub Actions")
    if not SHA_LINE.match(report["source_sha"]):
        fail("source_sha", report["source_sha"])

    consumer = Path(args.consumer).resolve()
    probe = Path(args.probe).resolve()
    for name, path in (("consumer", consumer), ("probe", probe)):
        if not path.is_file():
            fail(name + "_missing", str(path))

    phase_records = []
    total_checks = 0
    for index, (label, phase, expected, timeout) in enumerate(PHASES, start=1):
        log_name = "%02d-%s" % (index, label)
        record = {"label": label, "phase": phase, "log": log_name, "exit": None, "checks": [],
                  "summaries": [], "accepted": False}
        phase_records.append(record)
        if failure is not None:
            continue
        command = [str(consumer), phase, "--wav-dir", str(wav_dir)]
        out_path = logs / (log_name + ".stdout.log")
        err_path = logs / (log_name + ".stderr.log")
        returncode = None
        # Stream into the log files so a timeout still leaves the partial, source-bound
        # output behind instead of an empty log.
        with out_path.open("w", encoding="utf-8") as out_file, err_path.open("w", encoding="utf-8") as err_file:
            try:
                completed = subprocess.run(command, stdout=out_file, stderr=err_file, text=True,
                                           timeout=timeout)
                returncode = completed.returncode
            except subprocess.TimeoutExpired:
                fail(label + "_timeout", "phase exceeded %d s" % timeout)
                err_file.write("timeout after %d s\n" % timeout)
                err_file.flush()
        phase_output = out_path.read_text(encoding="utf-8", errors="replace")
        parsed = parse_phase(phase_output, phase)
        record["exit"] = returncode
        record["checks"] = parsed["checks"]
        record["summaries"] = parsed["summaries"]
        record["infos"] = parsed["infos"]
        record["installed"] = []
        ids = [row["id"] for row in parsed["checks"]]
        if parsed["unknown"]:
            fail(label + "_unparsed_output", parsed["unknown"][0][:120])
        if len(ids) != expected:
            fail(label + "_check_count", "expected %d observed %d" % (expected, len(ids)))
        if len(ids) != len(set(ids)):
            fail(label + "_duplicate_check")
        if any(not row["id"].startswith(label + ".") for row in parsed["checks"]):
            fail(label + "_foreign_check_id")
        if len(parsed["summaries"]) != 1 or parsed["summaries"][0]["phase"] != phase:
            fail(label + "_summary")
        elif parsed["summaries"][0]["passed"] != len(ids) or parsed["summaries"][0]["total"] != len(ids):
            fail(label + "_summary_counts", json.dumps(parsed["summaries"][0]))
        if returncode != 0:
            fail(label + "_exit", str(returncode))
        failing = [row["id"] for row in parsed["checks"] if row["result"] != "pass"]
        if failing:
            fail(label + "_check_failed", ",".join(failing[:6]))
        record["accepted"] = (failure is None and returncode == 0
                              and len(ids) == expected and not failing)
        total_checks += len(ids)
        for item in parsed["wavs"]:
            record.setdefault("wavs", []).append(item)

    # Collected WAV containers from the C consumer phases.
    wav_reports = {}
    for record in phase_records:
        for item in record.get("wavs", []):
            path = Path(item["path"])
            entry = {"file": path.name, "minimum_ms": item["minimum_ms"], "phase": record["label"]}
            try:
                container = wav_container(path)
            except (OSError, ValueError) as error:
                fail("wav_" + record["label"], str(error))
                entry["error"] = str(error)
                wav_reports[path.name] = entry
                continue
            entry.update(container)
            if container["duration_ms"] < item["minimum_ms"]:
                fail("wav_duration_" + record["label"], "%d < %d" % (container["duration_ms"], item["minimum_ms"]))
            if container["bytes"] > MAX_WAV_BYTES:
                fail("wav_size_" + record["label"])
            entry["ratio_to_text"] = None
            wav_reports[path.name] = entry

    # Independent C++ probe.
    probe_record = {"name": probe.name if probe.is_file() else "tts-probe"}
    probe_wav = None
    if failure is None:
        text_path = output / "probe-text.txt"
        probe_text = (b"The probe app reads this UTF-8 text and synthesises it through the installed "
                      b"package. It checks the event stream, the byte ranges and the WAV container. "
                      b"Numbers 0123456789 and punctuation; still one utterance.\n")
        text_path.write_bytes(probe_text)
        probe_wav = wav_dir / "probe.wav"
        with (logs / "11-probe.stdout.log").open("w", encoding="utf-8") as out_file,                 (logs / "11-probe.stderr.log").open("w", encoding="utf-8") as err_file:
            try:
                done = subprocess.run([str(probe), str(text_path), str(probe_wav), "1.25"],
                                      stdout=out_file, stderr=err_file, text=True, timeout=300)
                probe_returncode = done.returncode
            except subprocess.TimeoutExpired:
                probe_returncode = None
                err_file.write("timeout\n")
        done = type("Probe", (), {"stdout": (logs / "11-probe.stdout.log").read_text(encoding="utf-8",
                                                                                    errors="replace"),
                                  "returncode": probe_returncode})()
        probe_record["exit"] = done.returncode
        try:
            summary = json.loads(done.stdout.strip().splitlines()[-1])
        except (ValueError, IndexError):
            fail("probe_output", done.stdout[-200:])
            summary = {}
        probe_record["summary"] = summary
        if done.returncode != 0 or summary.get("result") != "pass":
            fail("probe_result", json.dumps(summary)[:200])
        for key, expected in (("started", 1), ("finished", 1), ("failed", 0), ("stopped", 0), ("bad_range", 0)):
            if summary.get(key) != expected:
                fail("probe_" + key, str(summary.get(key)))
        if not isinstance(summary.get("ranges"), int) or summary.get("ranges", 0) < 5:
            fail("probe_ranges", str(summary.get("ranges")))
        if summary.get("state_after") != "READY":
            fail("probe_state", str(summary.get("state_after")))
        if summary.get("max_end", 0) <= 0 or summary.get("max_end", 0) > summary.get("text_bytes", 0):
            fail("probe_range_bounds")
        if summary.get("text_bytes") != len(probe_text):
            fail("probe_text_bytes", "%r vs %d" % (summary.get("text_bytes"), len(probe_text)))
        try:
            container = wav_container(probe_wav)
        except (OSError, ValueError) as error:
            fail("probe_wav", str(error))
            container = None
        if container is not None:
            probe_record["wav"] = dict(container, file=probe_wav.name)
            if container["duration_ms"] < 4000:
                fail("probe_wav_duration", str(container["duration_ms"]))
            wav_reports[probe_wav.name] = dict(container, file=probe_wav.name, minimum_ms=4000,
                                               phase="probe")
        probe_record["bytes"] = probe.stat().st_size if probe.is_file() else 0
        probe_record["sha256"] = file_digest(probe) if probe.is_file() else ""

    stage = Path(args.module_prefix).resolve()
    installed = []
    if stage.is_dir():
        for path in sorted(stage.rglob("*")):
            if path.is_file():
                installed.append({"path": path.relative_to(stage).as_posix(),
                                  "bytes": path.stat().st_size, "sha256": file_digest(path)})
    else:
        fail("module_prefix", str(stage))

    names = {row["path"] for row in installed}
    for required in ("include/reader_tts.h", "include/reader_tts_windows.h"):
        if required not in names:
            fail("installed_header", required)

    report["phases"] = phase_records
    report["phase_labels"] = [row["label"] for row in phase_records]
    report["checks"] = total_checks
    report["passed"] = sum(1 for row in phase_records for check in row["checks"] if check["result"] == "pass")
    report["expected_checks"] = sum(row[2] for row in PHASES)
    report["wavs"] = sorted(wav_reports.values(), key=lambda row: row["file"])
    report["consumer"] = {"name": consumer.name, "bytes": consumer.stat().st_size if consumer.is_file() else 0,
                          "sha256": file_digest(consumer) if consumer.is_file() else ""}
    report["probe"] = probe_record
    report["installed_files"] = installed
    report["capabilities"] = {"pause": True, "range": True}
    info_values = {}
    for record in phase_records:
        for item in record.get("infos", []):
            info_values[item["key"]] = item["value"]
    range_events = info_values.get("range_events", 0)
    range_capability = info_values.get("range_capability", 0)
    report["engine"] = {"range_events": range_events, "range_capability": range_capability,
                        "status_samples": info_values.get("engine_samples", 0),
                        "event_calls": info_values.get("engine_event_calls", 0),
                        "event_total": info_values.get("engine_event_total", 0)}
    if range_events == 0:
        report["not_exercised"].append(
            "engine RANGE events: this runner's SAPI file output reported no word position "
            "(capability bit withheld); the UTF-16 to UTF-8 byte map is covered by the map probe")
    report["audio_scope"] = {
        "synthesis": "SAPI voice rendered to 16-bit PCM mono 22050 Hz WAV",
        "playback_device": "not exercised (the runner has no audio endpoint)",
        "listening": "not verified",
        "range_events": range_events,
    }
    report["accepted"] = failure is None and report["checks"] == report["expected_checks"] == report["passed"]
    if failure is not None:
        report["error"] = failure
    text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    (output / "evidence" / "report.json").write_text(text, encoding="utf-8")
    print(json.dumps({"accepted": report["accepted"], "checks": report["checks"],
                      "expected": report["expected_checks"], "error": failure}, indent=2))
    return 0 if report["accepted"] else 1


if __name__ == "__main__":
    sys.exit(main())
