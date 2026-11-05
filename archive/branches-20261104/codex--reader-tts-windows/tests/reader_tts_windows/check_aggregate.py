#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Actions-only positive/negative fixtures for the acceptance verifier.

Builds one synthetic run whose producer artifact is internally consistent, proves
that the verifier accepts it in both modes, then tampers with single fields and
proves that each tamper is rejected with the expected evidence code. No fixture is
derived from a real run, and no production assertion is weakened by these cases.
"""
import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import io
import json
from pathlib import Path
import struct
import sys
import zipfile

from strict_contract import (EvidenceError, PRODUCER_JOB, REPORT_JOB, TOTAL_CHECKS, PHASES,
                             verify, verify_in_run)

RUN_ID = 4000000001
ATTEMPT = 1
SHA = "f43baf9182d75907c0cb5d6f77048f27bca8c950"
REPO = "NoGod3524/EXReader"
REPO_ID = 900000001
RUNNER = "20261024T000000Z"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def wav_bytes(duration_ms):
    rate, block = 22050, 2
    samples = (rate * block * duration_ms) // 1000
    if samples % 2:
        samples += 1
    fmt = struct.pack("<HHIIHH", 1, 1, rate, rate * block, block, 16)
    body = b"WAVE" + b"fmt " + struct.pack("<I", len(fmt)) + fmt + b"data" + struct.pack("<I", samples) + b"\0" * samples
    return b"RIFF" + struct.pack("<I", len(body)) + body


def pack(files):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name in sorted(files):
            archive.writestr(name, files[name])
    return buffer.getvalue()


WAV_LINES = {
    "speak": [("speak.wav", 1500)],
    "unicode": [("unicode.wav", 1500)],
    "chunks": [("chunk0.wav", 1000), ("chunk1.wav", 1000), ("chunk2.wav", 1000)],
}


class State:
    def __init__(self, fail_one=False):
        self.run_id, self.attempt, self.sha = RUN_ID, ATTEMPT, SHA
        self.files = {}
        self.wavs = {}
        self.report = self.build_report(fail_one)
        self.consumer = b"MZ" + b"\x90" * 64 + b"consumer"
        self.probe = b"MZ" + b"\x90" * 64 + b"probe"
        self.files["consumer/tts-consumer.exe"] = self.consumer
        self.files["consumer/tts-probe.exe"] = self.probe
        self.wavs["probe.wav"] = wav_bytes(5000)
        for label in PHASES:
            for name, minimum in WAV_LINES.get(label[0], []):
                self.wavs[name] = wav_bytes(minimum + 300)
        for name, data in self.wavs.items():
            self.files["wav/" + name] = data
        self.stage = {
            "include/reader_tts.h": b"/* header */\n",
            "include/reader_tts_windows.h": b"/* extras */\n",
            "lib/reader_tts.lib": b"!<arch>\nstatic\n",
            "lib/cmake/EXReaderTTSWindows/EXReaderTTSWindowsConfig.cmake": b"# config\n",
            "share/exreader-tts-windows/LICENSE.txt": b"MIT\n",
        }
        for name, data in self.stage.items():
            self.files["stage/" + name] = data
        self.finish_report()
        self.files["evidence/report.json"] = json.dumps(self.report, indent=2).encode()
        self.aggregate = {}
        self.rebuild()

    def build_report(self, fail_one):
        phases = []
        for index, (label, count) in enumerate(PHASES, start=1):
            log = "%02d-%s" % (index, label)
            checks = []
            for number in range(1, count + 1):
                result = "fail" if (fail_one and label == "speak" and number == 1) else "pass"
                checks.append({"id": "%s.%03d" % (label, number), "result": result, "detail": "ok"})
            phases.append({"label": label, "phase": label, "log": log, "exit": 0, "checks": checks,
                           "summaries": [{"phase": label, "passed": count, "total": count}],
                           "accepted": True})
        return {"schema": 1, "module": "EXReaderTTSWindows", "module_version": "0.1.0",
                "platform": "windows", "accepted": True, "source_sha": self.sha,
                "run_id": str(self.run_id), "run_attempt": str(self.attempt), "job": PRODUCER_JOB,
                "runner": {"os": "Windows", "image": "win22"}, "phases": phases,
                "phase_labels": [label for label, _ in PHASES], "checks": TOTAL_CHECKS,
                "passed": TOTAL_CHECKS, "expected_checks": TOTAL_CHECKS, "wavs": [],
                "consumer": {}, "probe": {}, "installed_files": [], "capabilities": {"pause": True, "range": True},
                "audio_scope": {"listening": "not verified"}, "not_exercised": ["human listening judgement"],
                "diagnostics": [], "unavailable_scenarios": []}

    def finish_report(self):
        """Fills every hash the verifier recomputes from the archive bytes."""
        wavs = []
        for name in sorted(self.wavs):
            data = self.wavs[name]
            wavs.append({"file": name, "bytes": len(data), "sha256": digest(data),
                         "duration_ms": (len(data) - 44) * 1000 // (22050 * 2)})
        self.report["wavs"] = wavs
        self.report["consumer"] = {"name": "tts-consumer.exe", "bytes": len(self.consumer),
                                   "sha256": digest(self.consumer)}
        probe_wav = next(row for row in wavs if row["file"] == "probe.wav")
        self.report["probe"] = {"name": "tts-probe.exe", "exit": 0, "bytes": len(self.probe),
                               "sha256": digest(self.probe), "wav": probe_wav,
                               "summary": {"result": "pass", "started": 1, "ranges": 12, "finished": 1,
                                           "failed": 0, "stopped": 0, "text_bytes": 240, "max_end": 239,
                                           "bad_range": 0, "state_after": "READY", "capabilities": 3}}
        self.report["installed_files"] = [{"path": name, "bytes": len(data), "sha256": digest(data)}
                                          for name, data in sorted(self.stage.items())]

    def render_logs(self):
        for index, (label, count) in enumerate(PHASES, start=1):
            entry = self.report["phases"][index - 1]
            lines = []
            for name, minimum in WAV_LINES.get(label, []):
                lines.append("wavfile %s\\%s %d" % ("C:\\wav", name, minimum))
            for check in entry["checks"]:
                lines.append("check %s %s %s" % (check["id"], check["result"], check["detail"]))
            lines.append("info wavfiles %d" % len(WAV_LINES.get(label, [])))
            lines.append("phase %s %d %d" % (label, count, count))
            name = "evidence/logs/" + entry["log"]
            self.files[name + ".stdout.log"] = ("\n".join(lines) + "\n").encode()
            self.files[name + ".stderr.log"] = b""

    def rebuild(self):
        self.render_logs()
        self.files["evidence/report.json"] = json.dumps(self.report, indent=2).encode()
        self.windows_zip = pack(self.files)
        self.windows_digest = "sha256:" + digest(self.windows_zip)
        aggregate = self.aggregate or {
            "schema": 2, "module": "EXReaderTTSWindows", "accepted": True, "source_sha": self.sha,
            "run_id": self.run_id, "attempt": self.attempt, "checks": TOTAL_CHECKS,
            "platforms": {"windows": {"granted": True, "checks": TOTAL_CHECKS,
                                     "artifact": {"id": 5001, "name": "reader-tts-windows-windows",
                                                  "size_in_bytes": len(self.windows_zip),
                                                  "digest": self.windows_digest,
                                                  "expired": False,
                                                  "expires_at": "2026-12-31T00:00:00Z"}}}}
        self.aggregate = aggregate
        self.report_zip = pack({"aggregate.json": json.dumps(self.aggregate, indent=2).encode()})
        expires = (datetime.now(timezone.utc) + timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
        origin = {"id": self.run_id, "head_sha": self.sha, "repository_id": REPO_ID,
                  "head_repository_id": REPO_ID}
        self.run = {"id": self.run_id, "run_attempt": self.attempt, "head_sha": self.sha,
                    "path": ".github/workflows/reader-tts-windows.yml", "status": "completed",
                    "conclusion": "success", "repository": {"id": REPO_ID, "full_name": REPO},
                    "head_repository": {"id": REPO_ID}}
        self.jobs = [
            {"id": 7001, "name": PRODUCER_JOB, "run_id": self.run_id, "run_attempt": self.attempt,
             "head_sha": self.sha, "status": "completed", "conclusion": "success"},
            {"id": 7002, "name": REPORT_JOB, "run_id": self.run_id, "run_attempt": self.attempt,
             "head_sha": self.sha, "status": "completed", "conclusion": "success"},
        ]
        self.artifacts = [
            {"id": 5001, "name": "reader-tts-windows-windows-%d-%d" % (self.run_id, self.attempt),
             "size_in_bytes": len(self.windows_zip), "digest": self.windows_digest, "expired": False,
             "expires_at": expires, "workflow_run": origin},
            {"id": 5002, "name": "reader-tts-windows-report-%d-%d" % (self.run_id, self.attempt),
             "size_in_bytes": len(self.report_zip), "digest": "sha256:" + digest(self.report_zip),
             "expired": False, "expires_at": expires, "workflow_run": origin},
        ]
        self.archives = {5001: self.windows_zip, 5002: self.report_zip}
        self.logs = {
            7001: ("Preparing artifact\nSHA256 digest of uploaded artifact zip is %s\nFinalizing artifact upload\n"
                   "Artifact %s has been successfully uploaded! Final size is %d bytes. Artifact ID is 5001\n"
                   % (self.windows_digest[7:], self.artifacts[0]["name"], len(self.windows_zip))).encode(),
            7002: ("Preparing artifact\nSHA256 digest of uploaded artifact zip is %s\nFinalizing artifact upload\n"
                   "Artifact %s has been successfully uploaded! Final size is %d bytes. Artifact ID is 5002\n"
                   % (digest(self.report_zip), self.artifacts[1]["name"], len(self.report_zip))).encode(),
        }

    @staticmethod
    def upload_log(zip_bytes, name, artifact_id):
        return ("Preparing artifact\nSHA256 digest of uploaded artifact zip is %s\n"
                "Finalizing artifact upload\nArtifact %s has been successfully uploaded! Final size is %d bytes. "
                "Artifact ID is %d\n" % (digest(zip_bytes), name, len(zip_bytes), artifact_id)).encode()

    def repack_files(self):
        """Re-packs the current files without regenerating the report hashes.

        Used by the negative cases: the artifact identity is recomputed, so the only
        inconsistency left is the one under test.
        """
        self.windows_zip = pack(self.files)
        self.archives[5001] = self.windows_zip
        self.artifacts[0]["size_in_bytes"] = len(self.windows_zip)
        self.windows_digest = "sha256:" + digest(self.windows_zip)
        self.artifacts[0]["digest"] = self.windows_digest
        self.logs[7001] = self.upload_log(self.windows_zip, self.artifacts[0]["name"], 5001)

    def strict(self):
        return verify(self.run, self.jobs, self.artifacts, self.archives, self.logs, REPO, self.sha,
                      self.run_id, self.attempt, True)

    def in_run(self):
        return verify_in_run(self.run, self.jobs, self.artifacts, self.archives, self.logs, REPO, self.sha,
                             self.run_id, self.attempt)


LAST = {"observed": ""}


def expect(code, action):
    try:
        action()
    except EvidenceError as error:
        LAST["observed"] = str(error)
        return str(error) == code
    LAST["observed"] = "accepted"
    return False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    results = []

    def record(name, ok, detail=""):
        if not ok:
            detail = (detail + " observed=" + LAST["observed"]).strip()
        results.append({"case": name, "result": "pass" if ok else "fail", "detail": detail})

    state = State()
    try:
        summary = state.strict()
        record("positive.strict", summary["accepted"] is True and summary["platforms"]["windows"]["checks"] == TOTAL_CHECKS,
               "checks=%d" % summary["platforms"]["windows"]["checks"])
    except EvidenceError as error:
        record("positive.strict", False, str(error))
    try:
        summary = state.in_run()
        record("positive.in_run", summary["accepted"] is True and summary["strict_complete"] is False, "")
    except EvidenceError as error:
        record("positive.in_run", False, str(error))

    case = State()
    case.run["head_sha"] = "0" * 40
    record("reject.run_sha", expect("run_identity", case.strict), "tested commit is not the run commit")

    case = State()
    case.run["run_attempt"] = 2
    record("reject.attempt", expect("run_identity", case.strict), "attempt mismatch")

    case = State()
    case.artifacts[0]["expired"] = True
    record("reject.artifact_expired", expect("artifact_expired_or_empty", case.strict), "expired flag")

    case = State()
    case.artifacts[0]["expires_at"] = "2000-01-01T00:00:00Z"
    record("reject.artifact_expiry_time", expect("artifact_expired_time", case.strict), "expiry in the past")

    case = State()
    case.archives[5001] = case.windows_zip + b"\0"
    record("reject.zip_bytes", expect("zip_size", case.strict), "downloaded bytes differ from size_in_bytes")

    case = State()
    case.files["stage/lib/extra.txt"] = b"unexpected\n"
    case.repack_files()
    record("reject.installed_coverage", expect("installed_coverage", case.strict),
           "file under stage/ that the manifest does not list")

    case = State()
    case.report["source_sha"] = "0" * 40
    case.files["evidence/report.json"] = json.dumps(case.report).encode()
    case.repack_files()
    record("reject.report_origin", expect("report_origin", case.strict), "report claims another commit")

    case = State(fail_one=True)
    record("reject.check_failed", expect("phase_incomplete", case.strict), "one named check reports fail")

    case = State()
    del case.files["evidence/logs/03-unicode.stderr.log"]
    case.repack_files()
    record("reject.missing_phase_log", expect("phase_logs_missing", case.strict), "phase log removed")

    case = State()
    case.files["wav/speak.wav"] = wav_bytes(6000)
    case.repack_files()
    record("reject.wav_hash", expect("wav_hash_or_duration", case.strict), "audio replaced after the report")

    case = State()
    case.files["wav/speak.wav"] = wav_bytes(10)
    case.repack_files()
    record("reject.wav_too_short", expect("wav_hash_or_duration", case.strict),
           "short audio cannot satisfy the announced minimum either")

    case = State()
    case.report["probe"]["summary"]["result"] = "fail"
    case.files["evidence/report.json"] = json.dumps(case.report).encode()
    case.repack_files()
    record("reject.probe", expect("probe_contract", case.strict), "probe did not pass")

    case = State()
    case.files["consumer/tts-consumer.exe"] = case.consumer + b"tamper"
    case.repack_files()
    record("reject.consumer_hash", expect("consumer_hash", case.strict), "consumer binary replaced")

    case = State()
    case.report["probe"]["summary"]["ranges"] = 0
    case.files["evidence/report.json"] = json.dumps(case.report).encode()
    case.repack_files()
    record("reject.probe_capability", expect("probe_range_capability", case.strict),
           "capability claimed without engine positions")

    case = State()
    case.artifacts.append(dict(case.artifacts[0]))
    record("reject.duplicate_artifact", expect("artifact_duplicate", case.strict), "same artifact twice")

    case = State()
    case.aggregate["platforms"]["windows"]["artifact"]["digest"] = "sha256:" + "0" * 64
    case.report_zip = pack({"aggregate.json": json.dumps(case.aggregate).encode()})
    case.archives[5002] = case.report_zip
    case.artifacts[1]["size_in_bytes"] = len(case.report_zip)
    case.artifacts[1]["digest"] = "sha256:" + digest(case.report_zip)
    case.logs[7002] = ("SHA256 digest of uploaded artifact zip is %s\nFinalizing artifact upload\n"
                       "Artifact %s has been successfully uploaded! Final size is %d bytes. Artifact ID is 5002\n"
                       % (digest(case.report_zip), case.artifacts[1]["name"], len(case.report_zip))).encode()
    record("reject.report_artifact_binding", expect("report_artifact_binding", case.strict),
           "summary points at another producer zip")

    case = State()
    case.logs[7001] = b"Preparing artifact\nno upload line here\n"
    record("reject.upload_binding", expect("producer_artifact_binding", case.strict),
           "log does not bind the artifact")

    case = State()
    case.artifacts[1]["expires_at"] = "2000-01-01T00:00:00Z"
    record("reject.report_artifact_expiry", expect("artifact_expired_time", case.strict), "expired summary zip")

    failures = [row for row in results if row["result"] != "pass"]
    report = {"schema": 1, "cases": len(results), "passed": len(results) - len(failures),
              "results": results, "accepted": not failures}
    (output / "rejections.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    for row in results:
        print("%-40s %s %s" % (row["case"], row["result"], row["detail"]))
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())