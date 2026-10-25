#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Secret-form detection and diagnostic-export judging for S08.

Everything here is a pure function of bytes/values so the same detector is used
by the guard job (synthetic red actions), by the platform runner (live job
secrets) and by the same-source aggregator.
"""
from __future__ import annotations

import base64
import json
import re
import urllib.parse
from pathlib import Path

CRED_STATUS = {"OK": 0, "NOT_FOUND": 1, "UNAVAILABLE": 2, "ARGUMENT": 3, "IO": 4}
PROFILE_STATUS = {
    "OK": 0, "ARGUMENT": 1, "IO": 2, "FORMAT": 3, "VERSION": 4, "INVALID": 5,
    "SECRET": 6, "CANCELLED": 7, "LIMIT": 8, "NOT_FOUND": 9, "EXISTS": 10,
    "CONFLICT": 11, "LOCKED": 12, "UNSAFE_PATH": 13, "BINDING": 14,
}
OPDS_STATUS = {
    "ok": 0, "argument": 1, "memory": 2, "io": 3, "format": 4, "limit": 5,
    "cancelled": 6, "timeout": 7, "http": 8, "auth_required": 9,
    "unsupported": 10, "needs_host": 11, "exists": 12, "mismatch": 13,
    "unreadable": 14, "aborted": 15,
}
ALLOWED_KEYS = {
    "credentials": {"module", "op", "status", "code"},
    "profiles": {"module", "op", "status", "code", "system_error", "offset", "message"},
    "opds": {"module", "op", "status", "code", "http_status", "auth_scheme", "message", "log_line"},
    "opds-redact": {"module", "op", "status", "code", "expected_length", "got_length"},
}
LOG_LINE = re.compile(r"^GET \S+ -> \d{3}$")
PROFILE_KEYWORDS = ("root_url", "document", "store_dir", "profile", "generation", "account",
                    "url", "name", "cancel", "document version")
REQUIRED_PROFILE_STATUS = ("OK", "SECRET", "INVALID", "CANCELLED", "VERSION", "FORMAT", "IO",
                           "LIMIT", "NOT_FOUND")
REQUIRED_CREDENTIAL_STATUS = ("OK", "NOT_FOUND", "ARGUMENT")
REQUIRED_OPDS_STATUS = ("ok", "auth_required", "http", "aborted")


def value_forms(values: dict[str, bytes]) -> list[bytes]:
    """Every encoding a leaking writer could plausibly use for opaque bytes."""
    forms: list[bytes] = []
    for value in values.values():
        if not value:
            continue
        tail = value[-32:] if len(value) > 32 else value
        variants = {value, tail}
        for item in (value, tail):
            variants.add(item.hex().encode())
            variants.add(item.hex().upper().encode())
            variants.add(base64.b64encode(item))
            variants.add(base64.b64encode(item).rstrip(b"="))
            variants.add(base64.urlsafe_b64encode(item))
            variants.add(base64.urlsafe_b64encode(item).rstrip(b"="))
            variants.add(urllib.parse.quote_from_bytes(item).encode())
            variants.add(urllib.parse.quote_from_bytes(item).lower().encode())
            variants.add(item.decode("latin-1").encode("utf-16-le"))
        forms.extend(item for item in variants if item)
    return forms


def text_forms(values: dict[str, str]) -> list[bytes]:
    """Every encoding for ASCII secrets (tokens, headers, cookies, userinfo)."""
    forms: list[bytes] = []
    for value in values.values():
        if not value:
            continue
        raw = value.encode("utf-8")
        forms.append(raw)
        forms.append(raw.hex().encode())
        forms.append(raw.hex().upper().encode())
        forms.append(base64.b64encode(raw))
        forms.append(base64.b64encode(raw).rstrip(b"="))
        forms.append(urllib.parse.quote(raw, safe="").encode())
        forms.append(value.encode("utf-16-le"))
        forms.append(value.encode("utf-16-be"))
    return [item for item in forms if item]


def scan_paths(paths, forms: list[bytes]) -> dict:
    """Scans files byte for byte; returns counts and hit file names only."""
    files = 0
    total = 0
    hits: list[str] = []
    roots = [Path(path) for path in paths]
    for root in roots:
        candidates = [root] if root.is_file() else sorted(root.rglob("*")) if root.exists() else []
        for candidate in candidates:
            if not candidate.is_file():
                continue
            try:
                data = candidate.read_bytes()
            except OSError:
                continue
            files += 1
            total += len(data)
            if any(form in data for form in forms):
                hits.append(candidate.name)
    return {"files": files, "bytes": total, "hits": len(hits), "hit_files": hits[:10],
            "forms": len(forms)}


def _int(entry: dict, key: str) -> bool:
    return isinstance(entry.get(key), int) and not isinstance(entry.get(key), bool)


def judge_diagnostics(diags: list[dict], context: dict, coverage: bool = True) -> list[str]:
    """Validates retention (useful diagnostics) and shape of every diag line."""
    problems: list[str] = []
    forbidden = [value for value in context.get("forbidden", []) if value]
    seen: dict[str, set] = {}
    messages: list[str] = []
    opds_lines: list[str] = []
    http_lines = 0
    for index, entry in enumerate(diags):
        where = "diag[%d]" % index
        if not isinstance(entry, dict):
            problems.append(where + ": not an object")
            continue
        module = entry.get("module")
        if module not in ALLOWED_KEYS:
            problems.append(where + ": unknown module")
            continue
        unknown = set(entry) - ALLOWED_KEYS[module]
        if unknown:
            problems.append(where + ": unexpected keys " + ",".join(sorted(unknown)))
        for key in ("op", "status", "code"):
            if key not in entry:
                problems.append(where + ": missing " + key)
        if not isinstance(entry.get("op"), str) or not entry.get("op"):
            problems.append(where + ": empty op")
        status = entry.get("status")
        code = entry.get("code")
        if not isinstance(status, str) or not status:
            problems.append(where + ": empty status")
        if not _int(entry, "code"):
            problems.append(where + ": non-integer code")
        seen.setdefault(module, set()).add(status)

        if module == "credentials":
            if CRED_STATUS.get(status) != code:
                problems.append(where + ": status/code disagree")
            if "message" in entry or "log_line" in entry:
                problems.append(where + ": credentials must not carry text")
        elif module == "profiles":
            if PROFILE_STATUS.get(status) != code:
                problems.append(where + ": status/code disagree")
            if not _int(entry, "system_error") or not _int(entry, "offset"):
                problems.append(where + ": missing numeric system_error/offset")
            elif entry["offset"] < 0:
                problems.append(where + ": negative offset")
            message = entry.get("message")
            if not isinstance(message, str):
                problems.append(where + ": message is not a string")
                continue
            messages.append(message)
            if status != "OK":
                if not message.strip():
                    problems.append(where + ": failure diagnostic was redacted to empty")
                elif message.strip().upper() == "REDACTED":
                    problems.append(where + ": failure diagnostic is only REDACTED")
            if status == "IO" and entry.get("system_error") == 0:
                problems.append(where + ": IO without a system error")
            if entry.get("op") in ("load-format", "load-version") and entry.get("offset", 0) <= 0:
                problems.append(where + ": document damage lost its byte offset")
            for value in forbidden:
                if value in message:
                    problems.append(where + ": message carries " + context.get("label", "input"))
                    break
        elif module == "opds":
            line = entry.get("log_line")
            if not isinstance(line, str) or not LOG_LINE.match(line):
                problems.append(where + ": request line lost method/path/status")
            else:
                opds_lines.append(line)
                if status == "http":
                    http_lines += 1
            if not _int(entry, "http_status"):
                problems.append(where + ": missing http_status")
            if status == "http":
                if entry.get("code") != entry.get("http_status"):
                    problems.append(where + ": http line status disagrees")
            elif OPDS_STATUS.get(status) != code:
                problems.append(where + ": status/code disagree")
            if status == "auth_required" and not entry.get("auth_scheme"):
                problems.append(where + ": challenge scheme lost")
            if isinstance(line, str):
                for value in forbidden:
                    if value in line:
                        problems.append(where + ": request line carries " + context.get("label", "input"))
                        break
            message = entry.get("message")
            if isinstance(message, str):
                for value in forbidden:
                    if value in message:
                        problems.append(where + ": error message carries " +
                                        context.get("label", "input"))
                        break
        elif module == "opds-redact":
            if status not in ("ok", "mismatch"):
                problems.append(where + ": unexpected redaction status")
            if not _int(entry, "expected_length") or not _int(entry, "got_length"):
                problems.append(where + ": redaction lengths missing")
            if status != "ok":
                problems.append(where + ": documented redaction contract broke")

    if not coverage:
        return problems

    credentials = seen.get("credentials", set())
    if context.get("require_unavailable"):
        required = REQUIRED_CREDENTIAL_STATUS + ("UNAVAILABLE",)
    else:
        required = REQUIRED_CREDENTIAL_STATUS
    for status in required:
        if status not in credentials:
            problems.append("credentials coverage missing " + status)
    if "credentials" in seen and context.get("forbid_credentials_unavailable") and \
            "UNAVAILABLE" in credentials:
        problems.append("credentials unexpectedly reported UNAVAILABLE")
    for status in REQUIRED_PROFILE_STATUS:
        if status not in seen.get("profiles", set()):
            problems.append("profiles coverage missing " + status)
    for status in REQUIRED_OPDS_STATUS:
        if status not in seen.get("opds", set()):
            problems.append("opds coverage missing " + status)
    if http_lines < 6:
        problems.append("opds request-line coverage too small")
    if seen.get("opds-redact") != {"ok"}:
        problems.append("opds redaction contract not proven")

    if len(messages) < 5 or sum(len(item) for item in messages) < 60:
        problems.append("profile diagnostics were over-redacted")
    if not any(keyword in " ".join(messages).lower() for keyword in PROFILE_KEYWORDS):
        problems.append("profile diagnostics lost every identifying word")
    source = context.get("opds_source", "")
    path = context.get("opds_path", "")
    if not opds_lines:
        problems.append("no redacted request lines were produced")
    else:
        joined = "\n".join(opds_lines)
        if source and source not in joined:
            problems.append("request lines lost the origin")
        if path and path not in joined:
            problems.append("request lines lost the URL path")
    if len(diags) < context.get("minimum_diags", 40):
        problems.append("diagnostic export is too small")
    return problems


def detect(data: bytes, forms: list[bytes]) -> bool:
    return any(form in data for form in forms)


def selfcheck(values: dict[str, bytes], texts: dict[str, str], judge_context: dict) -> dict:
    """Red actions: the detector must catch planted leaks and the judge must
    reject over-redacted or content-dropping diagnostics.

    Every planted case is generated here and written to an isolated temporary
    directory; nothing is read from the repository.
    """
    import tempfile

    forms = value_forms(values) + text_forms(texts)
    results = []
    root = Path(tempfile.mkdtemp(prefix="exr-s08-selfcheck-"))
    raw = next(iter(values.values()))
    text = next(iter(texts.values()))
    cases = {
        "raw": raw,
        "tail": raw[-32:],
        "hex": raw.hex().encode(),
        "hex-upper": raw.hex().upper().encode(),
        "base64": base64.b64encode(raw),
        "base64url": base64.urlsafe_b64encode(raw),
        "percent": urllib.parse.quote_from_bytes(raw).encode(),
        "utf16": raw.decode("latin-1").encode("utf-16-le"),
        "text-raw": text.encode(),
        "text-hex": text.encode().hex().encode(),
        "text-percent": urllib.parse.quote(text, safe="").encode(),
        "text-utf16": text.encode("utf-16-le"),
    }
    for name, payload in cases.items():
        path = root / ("planted-" + name + ".log")
        path.write_bytes(b"prefix " + payload + b" suffix\n")
        detected = detect(path.read_bytes(), forms)
        results.append({"case": name, "detected": detected})
    clean = root / "clean.log"
    clean.write_bytes(b"status=OK code=0 offset=12 system_error=0\n")
    results.append({"case": "clean", "detected": detect(clean.read_bytes(), forms), "expected": False})

    # Judge red actions: a fabricated empty/over-redacted export must be rejected,
    # and a fabricated retained export with the same shape must be accepted.
    base_profile = {"module": "profiles", "op": "load-null", "status": "ARGUMENT", "code": 1,
                    "system_error": 0, "offset": 0, "message": "store_dir is null"}
    empty = dict(base_profile, message="")
    results.append({"case": "empty-message",
                    "rejected": bool(judge_diagnostics([empty], judge_context, coverage=False))})
    redacted_only = dict(base_profile, message="REDACTED")
    results.append({"case": "redacted-only-message",
                    "rejected": bool(judge_diagnostics([redacted_only], judge_context, coverage=False))})
    leaking_message = dict(base_profile, message="store_dir is null " + text)
    results.append({"case": "message-carries-forbidden",
                    "rejected": bool(judge_diagnostics([leaking_message], judge_context, coverage=False))})
    clean_profile = dict(base_profile)
    results.append({"case": "retained-message-accepted",
                    "rejected": bool(judge_diagnostics([clean_profile], judge_context, coverage=False))})
    for item in results:
        if item["case"] == "clean":
            item["passed"] = item["detected"] is False
        elif "rejected" in item:
            item["passed"] = bool(item["rejected"])
        else:
            item["passed"] = bool(item["detected"])
    for path in root.rglob("*"):
        if path.is_file():
            path.unlink()
    root.rmdir()
    return {"cases": results, "passed": all(item["passed"] for item in results),
            "forms": len(forms)}
