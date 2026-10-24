#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Cloud-only acceptance checker for the installed EXReaderDiagnosticReport package.

Every verdict below is produced from observed bytes and exit statuses: the
installed library is exercised by installed C and C++ consumers, by a worker
built from package source with test hooks, and by independent secret scanning of
the produced files. The generator is never asked whether its own output is safe.
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

COMMON_START = "f43baf9182d75907c0cb5d6f77048f27bca8c950"
MAX_COUNT = 9007199254740991
MAX_UNIX = 4102444800
ALL_PLATFORMS = ("Linux", "Windows", "macOS")
KEYS = {
    "format", "format_version", "app_version", "platform", "operation", "sdk_abi",
    "sdk_version", "schema_version", "wire_version", "generated_at_unix",
    "account_configured", "sync_enabled", "offline_mode", "counters", "errors",
}
HEADER_CONTRACT = {
    "READER_DIAG_ABI_VERSION": 1,
    "READER_DIAG_FORMAT_VERSION": 1,
    "READER_DIAG_MAX_ERROR_ENTRIES": 32,
    "READER_DIAG_MAX_COUNTER_ENTRIES": 16,
    "READER_DIAG_MAX_APP_VERSION_BYTES": 32,
    "READER_DIAG_MAX_JSON_BYTES": 8192,
    "READER_DIAG_MAX_SUMMARY_BYTES": 4096,
    "READER_DIAG_MAX_COUNT": MAX_COUNT,
    "READER_DIAG_MAX_UNIX_TIME": MAX_UNIX,
}
# Planted values a diagnostic report must never carry and a refusal must never echo.
SECRETS = (
    "sk-live-9f2c8a1b7d",
    "https://reader:pa55w0rd@example.invalid/dav",
    "/home/alice/books/secret.epub",
    "C:\\Users\\alice\\Desktop\\private.epub",
    "-----BEGIN PRIVATE KEY-----",
    "Bearer eyJhbGciOiJIUzI1NiJ9",
    "example.invalid",
)
REQUIRED_CASES = (
    "installed-header-contract",
    "c-consumer",
    "cpp-consumer",
    "installed-consumers-compile",
    "abi-and-status-names",
    "defaults",
    "minimal-report",
    "typical-report-bytes",
    "canonical-order",
    "max-entries-fit",
    "entry-limits",
    "output-limits",
    "app-version-grammar",
    "refusal-no-echo",
    "field-closed-set",
    "duplicate-entries",
    "struct-and-abi-guards",
    "output-bytes-secret-scan",
    "publish-new-file",
    "publish-exists-not-replaced",
    "publish-directory-target",
    "dangling-symlink-target",
    "invalid-utf8-target",
    "publish-io-failure",
    "cancelled-build",
    "cancelled-write",
    "kill-before-commit",
    "kill-after-commit",
    "concurrent-writers",
    "unicode-target",
    "thread-safety",
    "output-lifetime",
)
# Cases that only one platform family can exercise, with the reason it is skipped
# elsewhere. The evidence job requires the exact per-platform set.
PLATFORM_CASES = {
    "dangling-symlink-target": ("Linux", "macOS"),
    "invalid-utf8-target": ("Windows",),
}
cases = []


class CheckFailure(RuntimeError):
    pass


def require(value, message):
    if not value:
        raise CheckFailure(message)


def record(name, function):
    try:
        function()
        cases.append({"name": name, "ok": True, "detail": ""})
        print("PASS", name, flush=True)
    except Exception as error:  # noqa: BLE001 - every failure is retained evidence
        cases.append({"name": name, "ok": False, "detail": str(error)[:900]})
        print("FAIL", name, str(error)[:900], flush=True)


def run(command, code=0, timeout=240):
    process = subprocess.run([str(item) for item in command], capture_output=True, text=True,
                             encoding="utf-8", errors="replace", timeout=timeout)
    if code is not None and process.returncode != code:
        raise CheckFailure("rc=%d expected %d: %s %s" % (
            process.returncode, code, process.stdout[-500:], process.stderr[-500:]))
    return process


def kv(process):
    values = {}
    for line in process.stdout.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            values[key] = value
    return values


def worker(*arguments, code=0, timeout=240):
    process = subprocess.run([WORKER] + [str(item) for item in arguments], capture_output=True,
                             text=True, encoding="utf-8", errors="replace", timeout=timeout)
    if code is not None and process.returncode != code:
        raise CheckFailure("worker %s rc=%d: %s %s" % (
            arguments[0], process.returncode, process.stdout[-500:], process.stderr[-500:]))
    return process, kv(process)


def hexarg(value):
    return "hex:" + value.hex()


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def statistics(path):
    info = Path(path).stat()
    return (info.st_size, info.st_mtime_ns, digest(path))


def temp_leftovers(directory):
    return sorted(str(p) for p in Path(directory).iterdir()
                  if ".reader-diagnostic.tmp-" in p.name)


def expect_status(values, status, message=None):
    require(values.get("status") == status,
            "status=%r expected %r (message=%r)" % (values.get("status"), status,
                                                    values.get("message")))
    require(values.get("out_null", "0") == "0", "report was refused")
    if message is not None:
        require(values.get("message") == message,
                "message=%r expected %r" % (values.get("message"), message))


def expect_refusal_status(values, status):
    require(values.get("status") == status,
            "status=%r expected %r (message=%r)" % (values.get("status"), status,
                                                    values.get("message")))


def expect_refusal(values, status, field):
    require(values.get("status") == status,
            "status=%r expected %r (message=%r)" % (values.get("status"), status,
                                                    values.get("message")))
    require(values.get("out_null") == "1", "refusal allocated a report")
    require(field in values.get("message", ""),
            "message %r does not name %r" % (values.get("message"), field))


def load_json(path):
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    require(isinstance(payload, dict), "report is not a JSON object")
    require(set(payload) == KEYS, "unexpected key set: %s" % sorted(set(payload) ^ KEYS))
    return payload


def build(preset, name, json_limit=0, summary_limit=0):
    json_path = work / (name + ".json")
    summary_path = work / (name + ".summary")
    process, values = worker("build", preset, json_path, summary_path, json_limit, summary_limit)
    return values, json_path, summary_path


def scan_bytes(raw, label):
    for index, byte in enumerate(raw):
        require(byte == 0x0A or 0x20 <= byte <= 0x7E,
                "%s has a byte outside printable ASCII at %d: 0x%02x" % (label, index, byte))
    require(b"/" not in raw, label + " contains a path separator")
    require(b"\\" not in raw, label + " contains a backslash")
    require(b"://" not in raw, label + " contains a URL scheme")
    require(b"@" not in raw, label + " contains an at sign")
    lowercase = raw.lower()
    for secret in SECRETS:
        needle = secret.lower().encode("utf-8")
        require(needle not in lowercase,
                label + " contains a planted secret: " + secret)
    require(raw.endswith(b"\n"), label + " does not end with a newline")


def main():
    global work, WORKER, CONSUMER, CPP_CONSUMER, HEADER
    parser = argparse.ArgumentParser()
    parser.add_argument("--consumer-dir", required=True)
    parser.add_argument("--installed", required=True)
    parser.add_argument("--build-log", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--platform", required=True)
    arguments = parser.parse_args()
    require(os.environ.get("GITHUB_ACTIONS") == "true", "cloud only")
    platform = arguments.platform
    require(platform in ALL_PLATFORMS, "unknown platform " + platform)
    suffix = ".exe" if os.name == "nt" else ""
    consumer_dir = Path(arguments.consumer_dir).resolve()
    CONSUMER = str(consumer_dir / ("diagnostic-c-consumer" + suffix))
    CPP_CONSUMER = str(consumer_dir / ("diagnostic-cpp-consumer" + suffix))
    WORKER = str(consumer_dir / ("diagnostic-worker" + suffix))
    installed = Path(arguments.installed).resolve()
    HEADER = installed / "include" / "reader_diagnostic_report.h"
    output = Path(arguments.output).resolve()
    work = output / "work"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    build_log = Path(arguments.build_log).resolve()

    limits = {}

    def installed_header_contract():
        require(HEADER.is_file(), "installed header missing: %s" % HEADER)
        text = HEADER.read_text(encoding="utf-8")
        for name, expected in HEADER_CONTRACT.items():
            match = re.search(r"#define\s+" + name + r"\s+(\d+)[uUlL]*\b", text)
            require(match is not None, "installed header lacks " + name)
            value = int(match.group(1))
            require(value == expected,
                    "installed header %s=%d expected %d" % (name, value, expected))
            limits[name] = value
        require("READER_DIAGNOSTIC_TEST_HOOKS" not in text,
                "installed header exposes test hooks")
        require("rd_test_" not in text, "installed header exposes test-only symbols")

    def c_consumer():
        directory = work / "c-consumer"
        directory.mkdir()
        process = run([CONSUMER, directory], 0)
        require("c-consumer-ok" in process.stdout, process.stdout + process.stderr)
        require("failures=0" in process.stdout, "consumer reported failures")
        payload = load_json(directory / "c-report.json")
        require(payload["app_version"] == "2.0.1-rc.7", "c report app version")
        require(payload["platform"] == "macos" and payload["operation"] == "reading",
                "c report enumerators")
        require(payload["counters"] == [{"id": "books_total", "value": 128},
                                        {"id": "import_failures", "value": 2},
                                        {"id": "sync_conflicts", "value": 1}],
                "c report counters: %r" % (payload["counters"],))
        require(payload["errors"] == [{"domain": "import", "kind": "IO", "count": 2},
                                      {"domain": "reading", "kind": "FORMAT", "count": 1}],
                "c report errors: %r" % (payload["errors"],))
        summary = (directory / "c-summary.txt").read_text(encoding="utf-8")
        require(summary.startswith("EXReader diagnostic report (format 1)\n"), "c summary header")
        require("  import IO x2\n" in summary, "c summary detail")

    def cpp_consumer():
        directory = work / "cpp-consumer"
        directory.mkdir()
        process = run([CPP_CONSUMER, directory], 0)
        require("cpp-consumer-ok" in process.stdout, process.stdout + process.stderr)
        require("failures=0" in process.stdout, "cpp consumer reported failures")
        payload = load_json(directory / "cpp-report.json")
        require(payload["app_version"] == "3.0.0-beta", "cpp report app version")
        require(payload["errors"] == [{"domain": "search", "kind": "LIMIT", "count": 4}],
                "cpp report errors")
        summary = (directory / "cpp-summary.txt").read_text(encoding="utf-8")
        require(summary.startswith("EXReader diagnostic report"), "cpp summary header")

    def installed_consumers_compile():
        require(build_log.is_file(), "consumer build log missing")
        lines = [line.replace("\\", "/") for line in
                 build_log.read_text(encoding="utf-8", errors="replace").splitlines()]
        include = str(installed).replace("\\", "/").lower()
        seen = [line for line in lines if "c_consumer.c" in line]
        require(seen, "build log has no c_consumer.c compile line")
        for line in seen:
            require(include in line.lower(),
                    "consumer did not compile against the installed include directory: " + line[:300])
            require("apps/reader/diagnostic-report" not in line.lower(),
                    "consumer compile line reached the package sources: " + line[:300])

    def abi_and_status_names():
        _, values = worker("abi")
        require(values.get("abi") == "1" and values.get("abi_macro") == "1",
                "abi mismatch: %r" % (values,))
        require(values.get("format_macro") == "1", "format version mismatch")
        _, names = worker("status-names")
        expected = ["OK", "ARGUMENT", "FIELD", "DUPLICATE", "LIMIT", "IO", "EXISTS",
                    "CANCELLED", "MEMORY", "UNKNOWN"]
        got = [names.get("name_%d" % index, "") for index in range(10)]
        require(got == expected, "status names %r expected %r" % (got, expected))

    def defaults():
        _, values = worker("defaults")
        require(values.get("struct_size") == values.get("sizeof_input"),
                "defaults struct_size %r != sizeof %r" % (values.get("struct_size"),
                                                          values.get("sizeof_input")))
        require(values.get("abi_version") == "1", "defaults abi_version")
        require(values.get("app_version_null") == "1", "defaults app_version is not NULL")
        for key in ("platform", "operation", "generated", "counter_count", "error_count"):
            require(values.get(key) == "0", "defaults %s=%r" % (key, values.get(key)))

    def minimal_report():
        values, json_path, summary_path = build("minimal", "minimal")
        expect_status(values, "OK")
        payload = load_json(json_path)
        require(payload["format"] == "exreader-diagnostic-report", "format name")
        require(payload["format_version"] == 1, "format_version")
        require(payload["app_version"] == "0.1.0", "minimal app_version")
        require(payload["platform"] == "other" and payload["operation"] == "other",
                "minimal enumerators")
        require(payload["sdk_version"] == "0.0.0" and payload["sdk_abi"] == 0,
                "minimal sdk")
        require(payload["generated_at_unix"] == 0, "minimal timestamp")
        require(payload["account_configured"] == "unknown"
                and payload["sync_enabled"] == "unknown"
                and payload["offline_mode"] == "unknown", "minimal tri states")
        require(payload["counters"] == [] and payload["errors"] == [], "minimal empty lists")
        require(json_path.stat().st_size == int(values["json_size"]), "json byte count")
        require(summary_path.stat().st_size == int(values["summary_size"]), "summary byte count")
        require(values["json_size"] == values["json_strlen"], "json size excludes NUL")
        require(values["summary_size"] == values["summary_strlen"], "summary size excludes NUL")

    def typical_report_bytes():
        values, json_path, summary_path = build("typical", "typical")
        expect_status(values, "OK")
        payload = load_json(json_path)
        require(payload["app_version"] == "1.4.2", "typical app_version")
        require(payload["platform"] == "windows" and payload["operation"] == "import",
                "typical enumerators")
        require(payload["sdk_abi"] == 1 and payload["sdk_version"] == "3.40.0",
                "typical sdk")
        require(payload["schema_version"] == 1 and payload["wire_version"] == 1,
                "typical schema and wire")
        require(payload["generated_at_unix"] == 1761600000, "typical timestamp")
        require((payload["account_configured"], payload["sync_enabled"],
                 payload["offline_mode"]) == ("yes", "yes", "no"), "typical tri states")
        require(payload["counters"] == [{"id": "books_total", "value": 42},
                                        {"id": "import_failures", "value": 3},
                                        {"id": "pending_changes", "value": 0}],
                "typical counters %r" % (payload["counters"],))
        require(payload["errors"] == [{"domain": "import", "kind": "IO", "count": 2},
                                      {"domain": "sync", "kind": "CONFLICT", "count": 1}],
                "typical errors %r" % (payload["errors"],))
        expected = (
            "EXReader diagnostic report (format 1)\n"
            "App 1.4.2 on windows, SDK 3.40.0 (ABI 1), schema 1, wire 1\n"
            "Operation: import\n"
            "Account configured: yes, sync enabled: yes, offline mode: no\n"
            "Generated: 1761600000\n"
            "Errors: 2 kinds, 3 occurrences\n"
            "  import IO x2\n"
            "  sync CONFLICT x1\n"
            "Counters: 3\n"
            "  books_total = 42\n"
            "  import_failures = 3\n"
            "  pending_changes = 0\n"
        )
        actual = summary_path.read_text(encoding="utf-8")
        require(actual == expected, "summary bytes differ:\n%r\n%r" % (actual, expected))
        order = re.findall(r'^  "([a-z_]+)"', json_path.read_text(encoding="utf-8"), re.M)
        require(order == ["format", "format_version", "app_version", "platform", "operation",
                          "sdk_abi", "sdk_version", "schema_version", "wire_version",
                          "generated_at_unix", "account_configured", "sync_enabled",
                          "offline_mode", "counters", "errors"],
                "json key order changed: %r" % (order,))

    def canonical_order():
        _, first_json, _ = build("typical", "order-a")
        _, second_json, _ = build("typical-reversed", "order-b")
        require(first_json.read_bytes() == second_json.read_bytes(),
                "entry order changed the report bytes")

    def max_entries_fit():
        values, json_path, summary_path = build("max", "max")
        expect_status(values, "OK")
        require(int(values["json_size"]) <= limits["READER_DIAG_MAX_JSON_BYTES"],
                "json over the hard limit")
        require(int(values["summary_size"]) <= limits["READER_DIAG_MAX_SUMMARY_BYTES"],
                "summary over the hard limit")
        payload = load_json(json_path)
        require(len(payload["counters"]) == 10, "max counters")
        require(len(payload["errors"]) == 32, "max errors")
        require(all(entry["value"] == MAX_COUNT for entry in payload["counters"]),
                "max counter values")
        require(all(entry["count"] == MAX_COUNT for entry in payload["errors"]),
                "max error counts")
        order = [entry["id"] for entry in payload["counters"]]
        require(order == sorted(order), "counters are not canonical: %r" % (order,))
        pairs = [(entry["domain"], entry["kind"]) for entry in payload["errors"]]
        require(pairs == sorted(pairs), "errors are not canonical")
        summary = summary_path.read_text(encoding="utf-8")
        require("\nErrors: 32 kinds, %d occurrences\n" % (32 * MAX_COUNT) in summary,
                "max summary total")
        require(summary.count(" x%d\n" % MAX_COUNT) == 32, "max summary detail lines")

    def entry_limits():
        _, values = worker("case", "counter-limit")
        expect_refusal(values, "LIMIT", "input.counter_count")
        _, values = worker("case", "error-limit")
        expect_refusal(values, "LIMIT", "input.error_count")

    def output_limits():
        json_path = work / "limit.json"
        summary_path = work / "limit.summary"
        _, values = worker("build", "max", json_path, summary_path, 64, 0)
        expect_refusal(values, "LIMIT", "json output limit")
        require(not json_path.exists(), "a refused build still saved json")
        _, values = worker("build", "max", json_path, summary_path, 0, 64)
        expect_refusal(values, "LIMIT", "summary output limit")
        require(not summary_path.exists(), "a refused build still saved a summary")

    valid_versions = ("0.1.0", "1.2.3", "9.9.9-alpha", "1.0.0-beta.7", "2.4.6-rc",
                      "123456.654321.999999-rc.999", "0.0.0", "10.20.30-alpha.123")
    invalid_versions = ("", "1.2", "1.2.3.4", "1.2.3+build", "01.2.3", "1.2.3-",
                        "1.2.3-alpha.1234", "a.b.c", "1.2.3-ALPHA", "1.2.3 ", " 1.2.3",
                        "1.2.3-alpha.0x1", "1234567.1.1", "1.2.3-rc.1.2") + SECRETS

    def app_version_grammar():
        for version in valid_versions:
            _, values = worker("app-version", hexarg(version.encode("utf-8")))
            expect_status(values, "OK")
        for version in invalid_versions:
            _, values = worker("app-version", hexarg(version.encode("utf-8")))
            expect_refusal(values, "FIELD", "input.app_version")

    def refusal_no_echo():
        for version in invalid_versions:
            process, values = worker("app-version", hexarg(version.encode("utf-8")))
            require(values.get("status") == "FIELD", "vector %r was not refused" % (version,))
            require(values.get("out_null") == "1", "refusal allocated a report")
            if len(version) >= 4:
                require(version not in process.stdout,
                        "refusal echoed the rejected value: %r" % (version,))
            for secret in SECRETS:
                require(secret not in process.stdout,
                        "refusal echoed a planted secret: " + secret)
            require(len(values.get("message", "")) < 160, "message over its bound")

    def field_closed_set():
        expected = {
            "platform-zero": "input.platform", "platform-high": "input.platform",
            "operation-zero": "input.operation", "operation-high": "input.operation",
            "kind-zero": "error.kind", "kind-high": "error.kind",
            "domain-zero": "error.domain", "domain-high": "error.domain",
            "tri-state": "input.state", "counter-id-zero": "counter.id",
            "counter-id-high": "counter.id", "counter-value": "counter.value",
            "error-count-zero": "error.count", "generated-at": "input.generated_at_unix",
            "sdk-abi": "input.sdk_abi", "schema": "input.schema_version",
            "wire": "input.wire_version", "sdk-major": "input.sdk_version",
        }
        for name, field in expected.items():
            _, values = worker("case", name)
            expect_refusal(values, "FIELD", field)

    def duplicate_entries():
        _, values = worker("case", "duplicate-counter")
        expect_refusal(values, "DUPLICATE", "counter.id")
        _, values = worker("case", "duplicate-error")
        expect_refusal(values, "DUPLICATE", "error.domain_kind")

    def struct_and_abi_guards():
        for name, field in (("struct-size-zero", "input.struct_size"),
                            ("struct-size-small", "input.struct_size"),
                            ("abi-version", "input.abi_version"),
                            ("reserved", "input.reserved"),
                            ("flag-reserved", "input.flag_reserved"),
                            ("entries-null", "input.entries"),
                            ("errors-null", "input.entries"),
                            ("input-null", "null argument")):
            _, values = worker("case", name)
            expect_refusal(values, "ARGUMENT", field)
        _, values = worker("build-bad-options", "typical")
        expect_refusal(values, "ARGUMENT", "options.struct_size")

    def output_bytes_secret_scan():
        for preset in ("minimal", "typical", "max"):
            values, json_path, summary_path = build(preset, "scan-" + preset)
            expect_status(values, "OK")
            scan_bytes(json_path.read_bytes(), preset + " json")
            scan_bytes(summary_path.read_bytes(), preset + " summary")
            require(json_path.stat().st_size == int(values["json_size"]), "json size mismatch")
            require(summary_path.stat().st_size == int(values["summary_size"]),
                    "summary size mismatch")

    def publish_new_file():
        directory = work / "publish"
        directory.mkdir()
        reference = (work / "typical.json").read_bytes()
        target = directory / "report.json"
        _, values = worker("write", target, "typical", 0, -1)
        expect_status(values, "OK")
        require(target.read_bytes() == reference, "published bytes differ from the report")
        require(str(values.get("system_error")) == "0", "success kept a system error")
        require(not temp_leftovers(directory), "a temporary survived a successful publish")

    def publish_exists_not_replaced():
        directory = work / "publish-exists"
        directory.mkdir()
        target = directory / "report.json"
        _, values = worker("write", target, "typical", 0, -1)
        expect_status(values, "OK")
        before = statistics(target)
        _, values = worker("write", target, "max", 0, -1)
        expect_refusal_status(values, "EXISTS")
        require(str(values.get("system_error")) == "0", "EXISTS reported a system error")
        require(statistics(target) == before, "an existing report was modified")
        require(not temp_leftovers(directory), "a temporary survived EXISTS")

    def publish_directory_target():
        directory = work / "publish-directory"
        directory.mkdir()
        target = directory / "report.json"
        target.mkdir()
        _, values = worker("write", target, "typical", 0, -1)
        expect_refusal_status(values, "EXISTS")
        require(target.is_dir() and not any(target.iterdir()), "a directory target was modified")
        require(not temp_leftovers(directory), "a temporary survived a directory target")

    def dangling_symlink_target():
        if platform not in PLATFORM_CASES["dangling-symlink-target"]:
            raise CheckFailure("not applicable on this platform")
        directory = work / "publish-symlink"
        directory.mkdir()
        target = directory / "report.json"
        os.symlink(str(directory / "missing.json"), str(target))
        _, values = worker("write", target, "typical", 0, -1)
        expect_refusal_status(values, "EXISTS")
        require(os.path.islink(target), "the dangling link was replaced")
        require(not os.path.exists(target), "the link now resolves")
        require(not temp_leftovers(directory), "a temporary survived a dangling link")

    def invalid_utf8_target():
        if platform not in PLATFORM_CASES["invalid-utf8-target"]:
            raise CheckFailure("not applicable on this platform")
        directory = work / "publish-invalid"
        directory.mkdir()
        bad = str(directory).encode("utf-8") + b"/report-\xff\xfe.json"
        _, values = worker("write", "hex:" + bad.hex(), "typical", 0, -1)
        expect_refusal_status(values, "ARGUMENT")
        require(values.get("message") == "target path encoding",
                "message=%r for an invalid UTF-8 target" % (values.get("message"),))
        require(not list(directory.iterdir()), "an invalid path created a file")

    def publish_io_failure():
        directory = work / "publish-missing"
        directory.mkdir()
        target = directory / "absent" / "report.json"
        before = sorted(directory.iterdir())
        _, values = worker("write", target, "typical", 0, -1)
        expect_refusal_status(values, "IO")
        require(values.get("system_error") not in ("", "0"), "IO did not report a system error")
        require(not target.exists(), "IO created the target")
        require(sorted(directory.iterdir()) == before, "IO left a temporary behind")

    def cancelled_build():
        _, values = worker("build-cancel", "typical", 1)
        expect_refusal_status(values, "CANCELLED")
        require(values.get("out_null") == "1", "cancelled build allocated a report")
        _, values = worker("build-cancel", "typical", 2)
        expect_refusal_status(values, "CANCELLED")
        _, values = worker("build-cancel", "typical", 0)
        expect_status(values, "OK")

    def cancelled_write():
        directory = work / "cancel-write"
        directory.mkdir()
        for point in (1, 2, 3):
            target = directory / ("report-%d.json" % point)
            _, values = worker("write", target, "typical", 0, point)
            expect_refusal_status(values, "CANCELLED")
            require(not target.exists(), "a cancelled write published the target")
            require(not temp_leftovers(directory),
                    "a cancelled write left a temporary behind (point %d)" % point)
        target = directory / "report-late.json"
        _, values = worker("write", target, "typical", 0, 0)
        expect_status(values, "OK")
        require(target.read_bytes() == (work / "typical.json").read_bytes(),
                "the late-cancel publish did not write the whole report")

    def wait_marker(marker, suffix, process, timeout=60):
        ready = Path(str(marker) + "." + suffix)
        deadline = time.time() + timeout
        while not ready.exists():
            if process.poll() is not None:
                out, err = process.communicate()
                raise CheckFailure("paused write exited early rc=%r %s %s" % (
                    process.returncode, out[-400:], err[-400:]))
            if time.time() > deadline:
                process.kill()
                out, err = process.communicate()
                raise CheckFailure("paused write never signalled %s: %s %s" % (
                    suffix, out[-400:], err[-400:]))
            time.sleep(0.05)
        time.sleep(0.25)

    def kill_before_commit():
        directory = work / "kill-before"
        directory.mkdir()
        target = directory / "report.json"
        marker = work / "kill-before-marker"
        process = subprocess.Popen([WORKER, "pause-before", str(target), str(marker), "typical"],
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                   encoding="utf-8", errors="replace")
        wait_marker(marker, "before", process)
        process.kill()
        process.wait(timeout=60)
        require(not target.exists(), "a killed write published the target")
        leftovers = temp_leftovers(directory)
        require(len(leftovers) <= 1, "more than one temporary survived: %r" % (leftovers,))
        _, values = worker("write", target, "typical", 0, -1)
        expect_status(values, "OK")
        require(target.read_bytes() == (work / "typical.json").read_bytes(),
                "a leftover temporary changed the next publish")

    def kill_after_commit():
        directory = work / "kill-after"
        directory.mkdir()
        target = directory / "report.json"
        marker = work / "kill-after-marker"
        process = subprocess.Popen([WORKER, "pause-after", str(target), str(marker), "typical"],
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                   encoding="utf-8", errors="replace")
        wait_marker(marker, "after", process)
        process.kill()
        process.wait(timeout=60)
        require(target.exists(), "a killed-after-commit write lost the target")
        require(target.read_bytes() == (work / "typical.json").read_bytes(),
                "the committed report is not the whole report")
        load_json(target)

    def concurrent_writers():
        directory = work / "concurrent"
        directory.mkdir()
        target = directory / "report.json"
        processes = [subprocess.Popen([WORKER, "write", str(target), "typical", "0", "-1"],
                                      stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                      encoding="utf-8", errors="replace") for _ in range(8)]
        statuses = []
        for process in processes:
            out, _ = process.communicate(timeout=180)
            values = {}
            for line in out.splitlines():
                if "=" in line:
                    key, value = line.split("=", 1)
                    values[key] = value
            statuses.append(values.get("status"))
        require(statuses.count("OK") == 1, "expected exactly one OK: %r" % (statuses,))
        require(statuses.count("EXISTS") == 7, "expected seven EXISTS: %r" % (statuses,))
        require(target.read_bytes() == (work / "typical.json").read_bytes(),
                "the winning report does not match the canonical bytes")
        require(not temp_leftovers(directory), "a temporary survived the race")

    def unicode_target():
        directory = work / "unicode-\u8bca\u65ad\u62a5\u544a-\U0001f4da"
        directory.mkdir()
        target = directory / ("\u62a5\u544a 1-e\u0301.json")
        encoded = str(target).encode("utf-8")
        _, values = worker("write", "hex:" + encoded.hex(), "typical", 0, -1)
        expect_status(values, "OK")
        require(target.read_bytes() == (work / "typical.json").read_bytes(),
                "the Unicode target does not carry the report")
        load_json(target)

    def thread_safety():
        _, values = worker("threads", "typical", 200)
        require(values.get("mismatches") == "0", "threads disagreed: %r" % (values,))
        require(values.get("iterations") == "1600", "thread iteration count")
        require(values.get("json_size") == str((work / "typical.json").stat().st_size),
                "thread json size")

    def output_lifetime():
        target = work / "lifetime.json"
        _, values = worker("lifetime", target)
        require(values.get("stable") == "1", "a report changed after a second build")
        require(target.read_bytes() == (work / "typical.json").read_bytes(),
                "the first report's bytes changed after a second build was freed")

    mapping = [
        ("installed-header-contract", installed_header_contract),
        ("c-consumer", c_consumer),
        ("cpp-consumer", cpp_consumer),
        ("installed-consumers-compile", installed_consumers_compile),
        ("abi-and-status-names", abi_and_status_names),
        ("defaults", defaults),
        ("minimal-report", minimal_report),
        ("typical-report-bytes", typical_report_bytes),
        ("canonical-order", canonical_order),
        ("max-entries-fit", max_entries_fit),
        ("entry-limits", entry_limits),
        ("output-limits", output_limits),
        ("app-version-grammar", app_version_grammar),
        ("refusal-no-echo", refusal_no_echo),
        ("field-closed-set", field_closed_set),
        ("duplicate-entries", duplicate_entries),
        ("struct-and-abi-guards", struct_and_abi_guards),
        ("output-bytes-secret-scan", output_bytes_secret_scan),
        ("publish-new-file", publish_new_file),
        ("publish-exists-not-replaced", publish_exists_not_replaced),
        ("publish-directory-target", publish_directory_target),
        ("dangling-symlink-target", dangling_symlink_target),
        ("invalid-utf8-target", invalid_utf8_target),
        ("publish-io-failure", publish_io_failure),
        ("cancelled-build", cancelled_build),
        ("cancelled-write", cancelled_write),
        ("kill-before-commit", kill_before_commit),
        ("kill-after-commit", kill_after_commit),
        ("concurrent-writers", concurrent_writers),
        ("unicode-target", unicode_target),
        ("thread-safety", thread_safety),
        ("output-lifetime", output_lifetime),
    ]
    applicable = [name for name, _ in mapping
                  if platform in PLATFORM_CASES.get(name, ALL_PLATFORMS)]
    skipped = {name: "not applicable on " + platform for name, _ in mapping
               if name not in applicable}
    for name, function in mapping:
        if name in applicable:
            record(name, function)
        else:
            cases.append({"name": name, "ok": True, "applicable": False,
                          "detail": "skipped: " + skipped[name]})
    failed = [case["name"] for case in cases if not case["ok"]]
    result = {
        "accepted": not failed,
        "package": "EXReaderDiagnosticReport 0.1.0",
        "common_start": COMMON_START,
        "source_sha": os.environ.get("GITHUB_SHA", ""),
        "run_id": int(os.environ.get("GITHUB_RUN_ID", "0")),
        "attempt": int(os.environ.get("GITHUB_RUN_ATTEMPT", "0")),
        "job": os.environ.get("GITHUB_JOB", ""),
        "platform": platform,
        "granted_platform": platform.lower(),
        "host_ui_accepted": False,
        "auto_upload": False,
        "limits": limits,
        "checks": len(applicable),
        "required_cases": list(REQUIRED_CASES),
        "skipped": sorted(skipped),
        "cases": cases,
        "failed": failed,
    }
    (output / "result.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n",
                                        encoding="utf-8")
    print(json.dumps({"platform": platform, "checks": len(applicable), "failed": failed}),
          flush=True)
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
