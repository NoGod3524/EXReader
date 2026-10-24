# SPDX-License-Identifier: MIT
"""Evidence collection: key/UIA trace, named check results, source evidence."""
from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

TRACE_NAME = "key-trace.jsonl"

STATUS_VALUES = ("pass", "fail", "gap", "not_verified", "error")
SEVERITIES = ("blocking", "serious", "moderate", "info")


class Trace(object):
    """Append-only JSONL record of every input event and wait in the audit."""

    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = self.path.open("w", encoding="utf-8")
        self.started = time.time()
        self.count = 0
        self.events = []

    def event(self, kind, payload=None):
        self.count += 1
        record = {
            "seq": self.count,
            "t_ms": int((time.time() - self.started) * 1000),
            "kind": kind,
            "payload": payload if payload is not None else {},
        }
        self.handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
        self.handle.flush()
        self.events.append(record)
        return record

    def close(self):
        try:
            self.handle.close()
        except Exception:
            pass


class Recorder(object):
    """Named accessibility checks with element locators, steps and fixes."""

    def __init__(self, trace=None):
        self.trace = trace
        self.checks = []

    def record(self, identifier, scope, title, severity, status, expected, actual,
               steps=None, element=None, fix=None, evidence=None, reason=None,
               automated=True):
        if status not in STATUS_VALUES:
            raise ValueError("bad status %r for %s" % (status, identifier))
        if severity not in SEVERITIES:
            raise ValueError("bad severity %r for %s" % (severity, identifier))
        for value, label in ((expected, "expected"), (actual, "actual")):
            if not isinstance(value, str) or not value.strip():
                raise ValueError("%s needs a non-empty %s" % (identifier, label))
        check = {
            "id": identifier,
            "scope": scope,
            "title": title,
            "severity": severity,
            "status": status,
            "automated": bool(automated),
            "expected": expected.strip(),
            "actual": actual.strip(),
            "steps": [str(item) for item in (steps or [])],
            "element": element or {},
            "minimal_fix": fix or "",
            "evidence": evidence or {},
        }
        if reason:
            check["reason"] = str(reason)
        self.checks.append(check)
        if self.trace is not None:
            self.trace.event("check", {"id": identifier, "status": status,
                                       "severity": severity})
        return check

    def error(self, identifier, scope, title, reason, steps=None):
        return self.record(identifier, scope, title, "blocking", "error",
                           "the audit step runs to completion on the real host",
                           "the audit step did not complete: %s" % (reason,),
                           steps=steps, reason=reason, fix="fix the audit harness, "
                           "then re-run the same source; findings stay separate")

    def by_status(self, status):
        return [check for check in self.checks if check["status"] == status]

    def counts(self):
        result = {status: 0 for status in STATUS_VALUES}
        for check in self.checks:
            result[check["status"]] += 1
        result["checks"] = len(self.checks)
        result["blocking"] = len([c for c in self.checks
                                  if c["severity"] == "blocking"
                                  and c["status"] in ("fail", "gap", "error")])
        return result


def static_evidence(repo_root, patterns, limit=6):
    """Search the host sources for accessibility plumbing (read-only)."""
    root = Path(repo_root)
    paths = ["examples/reader.c", "apps/reader/desktop"]
    result = {}
    for name, pattern in patterns.items():
        command = ["git", "grep", "-n", "-I", "-E", pattern, "--"] + paths
        try:
            completed = subprocess.run(command, cwd=str(root), capture_output=True,
                                       text=True, encoding="utf-8", errors="replace",
                                       timeout=120)
            lines = [line.strip() for line in (completed.stdout or "").splitlines() if line.strip()]
        except Exception as exc:
            result[name] = {"pattern": pattern, "error": str(exc), "count": 0, "hits": []}
            continue
        result[name] = {
            "pattern": pattern,
            "count": len(lines),
            "hits": lines[:limit],
        }
    return result


def write_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
