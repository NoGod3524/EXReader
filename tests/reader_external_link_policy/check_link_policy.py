#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Cloud-only acceptance checker for the installed EXReaderLinkPolicy package.

Every expectation below is fixed before any consumer runs: the fixture module
derives them from the written contract, and the platform checks assert documented
statuses and lifetimes. The checker only orchestrates installed consumers and
records named outcomes; it never re-derives expectations from library output.
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import link_fixtures  # noqa: E402

COMMON_START = "f43baf9182d75907c0cb5d6f77048f27bca8c950"
GROUPS = list(link_fixtures.REQUIRED_GROUPS)

# Symbols that would prove a network, process or file-system dependency. The
# static audit below must find none of them in the shipped library, and the
# negative control proves the audit can find them at all.
FORBIDDEN = {
    "socket", "connect", "bind", "listen", "accept", "send", "recv", "sendto",
    "recvfrom", "getaddrinfo", "gethostbyname", "inet_addr", "inet_ntoa",
    "setsockopt", "wsastartup", "wsasocket", "winsock", "winhttp",
    "internetopen", "internetopenurl", "internetreadfile", "urldownloadtofile",
    "system", "popen", "execve", "execl", "execv", "execvp", "fork", "vfork",
    "posix_spawn", "createprocessa", "createprocessw", "shellexecutea",
    "shellexecutew", "winexec", "dlopen", "dlsym", "loadlibrarya",
    "loadlibraryw", "getprocaddress", "fopen", "wfopen", "creat", "unlink",
    "remove", "rename", "stat", "open", "read", "write",
}

CHECKS = (
    "fixtures-shape",
    "default-cases-exact",
    "custom-cases-exact",
    *(("group-" + group) for group in GROUPS),
    "probe-limits",
    "probe-errors",
    "probe-lifetime",
    "probe-interleave",
    "worker-alloc",
    "worker-cancel",
    "worker-lifetime",
    "worker-limits",
    "cpp-consumer",
    "sdk-navigation-handoff",
    "installed-header-parity",
    "installed-library-unhooked",
    "no-network-or-process-symbols",
    "symbol-audit-negative-control",
)

checks = []
failures = []


class CheckFailure(RuntimeError):
    pass


def record(name, function):
    try:
        detail = function() or ""
        checks.append({"name": name, "status": "pass", "detail": str(detail)[:600]})
        print("PASS", name, str(detail)[:200], flush=True)
    except Exception as error:  # noqa: BLE001 - every failure is retained evidence
        message = str(error)[:600]
        checks.append({"name": name, "status": "fail", "detail": message})
        failures.append(name + ": " + message)
        print("FAIL", name, message, flush=True)


def run(command, code=0, timeout=600):
    process = subprocess.run([str(part) for part in command], capture_output=True, text=True,
                             encoding="utf-8", errors="replace", timeout=timeout)
    if code is not None and process.returncode != code:
        raise CheckFailure("rc=%d expected %d: %s %s" % (
            process.returncode, code, process.stdout[-500:], process.stderr[-500:]))
    return process


def chk(stdout):
    values = {}
    for line in stdout.splitlines():
        if line.startswith("CHK\t"):
            parts = line.split("\t")
            values[parts[1]] = parts[2:]
    return values


def expect_chk(values, expected, label):
    for name, fields in expected.items():
        actual = values.get(name)
        if actual is None:
            raise CheckFailure("%s: missing %s" % (label, name))
        if actual != list(fields):
            raise CheckFailure("%s: %s=%r expected %r" % (label, name, actual, list(fields)))
    return len(expected)


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def parse_cases(stdout):
    rows = {}
    total = None
    for line in stdout.splitlines():
        parts = line.split("\t")
        if parts[0] == "C":
            rows[parts[1]] = parts[2:]
        elif parts[0] == "T":
            total = int(parts[1])
    return rows, total


def expected_row(case, limit):
    data = case["input"]
    size = len(data)
    within = size <= limit
    return [
        "0",
        str(link_fixtures.ACTION[case["action"]]),
        str(link_fixtures.REASON[case["reason"]]),
        str(link_fixtures.KIND[case["kind"]]),
        str(case["flags"]),
        case["scheme"] or "-",
        str(case["path_len"]),
        str(case["frag_off"]),
        str(case["frag_len"]),
        str(size),
        str(size if within else 0),
        data.hex() if within else "-",
        "1" if within else "0",
        "1",
    ]


def compare_cases(rows, total, cases, limit, label):
    names = [case["name"] for case in cases]
    if total != len(cases):
        raise CheckFailure("%s: probe reported %r cases, expected %d" % (label, total, len(cases)))
    missing = [name for name in names if name not in rows]
    extra = sorted(set(rows) - set(names))
    if missing or extra:
        raise CheckFailure("%s: missing=%r extra=%r" % (label, missing[:6], extra[:6]))
    for case in cases:
        want = expected_row(case, limit)
        got = rows[case["name"]]
        if got != want:
            keys = ("status", "action", "reason", "kind", "flags", "scheme", "path_len",
                    "frag_off", "frag_len", "input_bytes", "display_len", "display_hex",
                    "display_nul", "display_indep")
            diff = ", ".join("%s=%r expected %r" % (keys[i], got[i], want[i])
                             for i in range(min(len(got), len(want))) if got[i] != want[i])
            raise CheckFailure("%s: %s: %s" % (label, case["name"], diff))
    return len(cases)


def normalise_symbol(name):
    text = name.strip()
    if text.startswith("_"):
        text = text[1:]
    text = re.sub(r"@[0-9]+$", "", text)
    return text.lower()


def library_symbols(path):
    text = Path(path).read_bytes()
    symbols = set()
    for token in text.split(b"\x00"):
        if not token or len(token) > 96:
            continue
        try:
            value = token.decode("ascii")
        except UnicodeDecodeError:
            continue
        if re.fullmatch(r"[A-Za-z_@?$][A-Za-z0-9_@?$]*", value):
            symbols.add(normalise_symbol(value))
    if os.name == "nt":
        output = run(["dumpbin", "/symbols", str(path)], 0).stdout
        for line in output.splitlines():
            if "UNDEF" in line and "|" in line:
                symbols.add(normalise_symbol(line.rsplit("|", 1)[1]))
    else:
        output = run(["nm", "-u", str(path)], 0).stdout
        for line in output.splitlines():
            match = re.search(r"\bU\s+(\S+)$", line)
            if match:
                symbols.add(normalise_symbol(match.group(1)))
        defined = run(["nm", str(path)], 0).stdout
        for line in defined.splitlines():
            parts = line.split()
            if len(parts) == 3:
                symbols.add(normalise_symbol(parts[2]))
    return symbols


def find_library(prefix):
    for name in ("libreader_link_policy.a", "reader_link_policy.lib"):
        candidate = Path(prefix) / "lib" / name
        if candidate.exists():
            return candidate
    matches = sorted(Path(prefix).rglob("reader_link_policy*"))
    if not matches:
        raise CheckFailure("installed library not found under %s" % prefix)
    return matches[0]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--probe", required=True)
    parser.add_argument("--cpp", required=True)
    parser.add_argument("--worker", required=True)
    parser.add_argument("--sdk", required=True)
    parser.add_argument("--reporters", nargs="*", default=[])
    parser.add_argument("--control-lib", required=True)
    parser.add_argument("--prefix", required=True)
    parser.add_argument("--epub", required=True)
    parser.add_argument("--source", required=True)
    parser.add_argument("--source-header", required=True)
    parser.add_argument("--installed-header", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--platform", default="")
    args = parser.parse_args()

    output = Path(args.output).resolve()
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)
    fixtures = output / "fixtures"
    source = os.environ.get("GITHUB_SHA", "")
    platform = args.platform or ("Windows" if os.name == "nt" else sys.platform)
    report = {
        "ok": False,
        "source": source,
        "common_start": COMMON_START,
        "platform": platform,
        "run_id": os.environ.get("GITHUB_RUN_ID", ""),
        "attempt": os.environ.get("GITHUB_RUN_ATTEMPT", ""),
        "checks": checks,
        "failures": failures,
        "cases": {},
        "consumers": {},
        "library": {},
        "headers": {},
    }

    default_cases = link_fixtures.default_cases()
    custom_cases = link_fixtures.custom_cases()
    written = link_fixtures.write(fixtures)

    def fixtures_check():
        if written != (len(default_cases), len(custom_cases)):
            raise CheckFailure("writer reported %r" % (written,))
        counts = {}
        for case in default_cases:
            counts[case["group"]] = counts.get(case["group"], 0) + 1
        for group, minimum in link_fixtures.REQUIRED_GROUPS.items():
            if counts.get(group, 0) < minimum:
                raise CheckFailure("group %s has %d cases, expected >= %d" % (
                    group, counts.get(group, 0), minimum))
        report["cases"] = {"default": len(default_cases), "custom": len(custom_cases),
                           "groups": counts}
        return "%d default, %d custom, %d groups" % (
            len(default_cases), len(custom_cases), len(counts))

    record("fixtures-shape", fixtures_check)

    def default_check():
        process = run([args.probe, "classify", fixtures / "default.tsv"], 0)
        if "link-probe-ok" not in process.stdout:
            raise CheckFailure("probe marker missing")
        rows, total = parse_cases(process.stdout)
        return compare_cases(rows, total, default_cases, link_fixtures.DEFAULT_LIMIT, "default")

    def custom_check():
        process = run([args.probe, "classify", fixtures / "custom.tsv"], 0)
        rows, total = parse_cases(process.stdout)
        return compare_cases(rows, total, custom_cases, link_fixtures.CUSTOM_LIMIT, "custom")

    record("default-cases-exact", default_check)
    record("custom-cases-exact", custom_check)

    rows_by_name = {}
    try:
        rows_by_name, _ = parse_cases(run([args.probe, "classify", fixtures / "default.tsv"], 0).stdout)
    except Exception:  # noqa: BLE001 - reported by the case checks above
        rows_by_name = {}

    def group_check(group):
        def check():
            names = [case["name"] for case in default_cases if case["group"] == group]
            if not names:
                raise CheckFailure("no cases for %s" % group)
            for name in names:
                if name not in rows_by_name:
                    raise CheckFailure("case %s was not classified" % name)
            return "%d cases" % len(names)
        return check

    for group in GROUPS:
        record("group-" + group, group_check(group))

    def probe_limits():
        values = chk(run([args.probe, "limits"], 0).stdout)
        return expect_chk(values, {
            "limits-default-create": ["ok"],
            "limits-default-status": ["OK"],
            "limits-max-ceiling": ["OK"],
            "limits-max-over": ["ARGUMENT", "1"],
            "limits-options-struct-size": ["ARGUMENT", "1"],
            "limits-schemes-null": ["ARGUMENT"],
            "limits-schemes-too-many": ["ARGUMENT"],
            "limits-scheme-denied": ["ARGUMENT"],
            "limits-scheme-ms": ["ARGUMENT"],
            "limits-scheme-bad-syntax": ["ARGUMENT"],
            "limits-scheme-too-long": ["ARGUMENT"],
            "limits-scheme-empty": ["ARGUMENT"],
            "limits-duplicate-scheme": ["OK"],
            "limits-scheme-normalised": ["tel"],
            "limits-null-out": ["ARGUMENT"],
            "limits-destroy-null": ["ok"],
            "limits-name-tables": ["ok"],
        }, "limits")

    def probe_errors():
        values = chk(run([args.probe, "errors"], 0).stdout)
        return expect_chk(values, {
            "errors-null-result": ["ARGUMENT"],
            "errors-result-struct-size": ["ARGUMENT"],
            "errors-null-policy": ["ARGUMENT", "1"],
            "errors-null-text": ["ARGUMENT"],
            "errors-base-absolute": ["ARGUMENT"],
            "errors-base-backslash": ["ARGUMENT"],
            "errors-base-too-long": ["ARGUMENT"],
            "errors-optional-pointers": ["OK", "1"],
            "errors-reject-action": ["REJECT"],
            "errors-empty-reason": ["EMPTY"],
        }, "errors")

    def probe_lifetime():
        values = chk(run([args.probe, "lifetime"], 0).stdout)
        return expect_chk(values, {
            "lifetime-no-alias": ["ok"],
            "lifetime-survives-policy-and-input": ["ok"],
            "lifetime-independent-results": ["ok"],
            "lifetime-free-clears": ["ok"],
            "lifetime-double-free": ["ok"],
        }, "lifetime")

    def probe_interleave():
        values = chk(run([args.probe, "interleave"], 0).stdout)
        return expect_chk(values, {
            "interleave-policies-independent": ["ok"],
            "interleave-survives-other-destroy": ["ok"],
        }, "interleave")

    record("probe-limits", probe_limits)
    record("probe-errors", probe_errors)
    record("probe-lifetime", probe_lifetime)
    record("probe-interleave", probe_interleave)

    def worker_alloc():
        process = run([args.worker, "alloc"], 0)
        if "link-worker-ok" not in process.stdout:
            raise CheckFailure("worker marker missing")
        values = chk(process.stdout)
        return expect_chk(values, {
            "alloc-create-fail1": ["MEMORY", "0", "1"],
            "alloc-classify-fail1": ["MEMORY", "0", "1"],
            "alloc-classify-no-fail2": ["OK", "1"],
            "alloc-classify-no-fail3": ["OK", "1"],
            "alloc-count": ["OK", "1"],
            "alloc-released": ["0"],
        }, "alloc")

    def worker_cancel():
        values = chk(run([args.worker, "cancel"], 0).stdout)
        return expect_chk(values, {
            "cancel-entry": ["CANCELLED", "1", "0", "1"],
            "cancel-mid": ["CANCELLED", "2", "0", "1"],
            "cancel-late": ["CANCELLED", "3", "0", "1"],
            "cancel-before-commit": ["CANCELLED", "4", "0", "1"],
            "cancel-never": ["OK", "4", "1", "0"],
            "cancel-reentrant-classify": ["ok"],
        }, "cancel")

    def worker_lifetime():
        values = chk(run([args.worker, "lifetime"], 0).stdout)
        return expect_chk(values, {
            "worker-lifetime-after-policy": ["ok"],
            "worker-lifetime-released": ["ok"],
        }, "lifetime")

    def worker_limits():
        values = chk(run([args.worker, "limits"], 0).stdout)
        return expect_chk(values, {
            "limit-ceiling-accepted": ["OK"],
            "limit-ceiling-action": ["TOO_LONG", "1"],
            "limit-over-rejected": ["OK", "TOO_LONG"],
        }, "worker-limits")

    record("worker-alloc", worker_alloc)
    record("worker-cancel", worker_cancel)
    record("worker-lifetime", worker_lifetime)
    record("worker-limits", worker_limits)

    def cpp_consumer():
        process = run([args.cpp], 0)
        if "cpp-consumer-ok" not in process.stdout:
            raise CheckFailure(process.stdout[-400:] + process.stderr[-400:])
        values = chk(process.stdout)
        return expect_chk(values, {
            "cpp-installed-header": ["ok"],
            "cpp-raii-lifetime": ["ok"],
            "cpp-threaded-classify": ["ok"],
            "cpp-thread-results-identical": ["ok"],
            "cpp-reentrant-cancel": ["ok"],
            "cpp-reject-keeps-display": ["ok"],
        }, "cpp")

    def sdk_handoff():
        process = run([args.sdk, args.epub], 0)
        if "sdk-consumer-ok" not in process.stdout:
            raise CheckFailure(process.stdout[-400:] + process.stderr[-400:])
        values = chk(process.stdout)
        if values.get("sdk-open") != ["ok"]:
            raise CheckFailure("sdk-open %r" % (values.get("sdk-open"),))
        count = values.get("sdk-navigation-count")
        if not count or len(count) != 2:
            raise CheckFailure("navigation count missing")
        if int(count[0]) < 4 or int(count[1]) < 1:
            raise CheckFailure("navigation count %r too small" % (count,))
        base = values.get("sdk-navigation-base")
        if not base or not base[0].strip():
            raise CheckFailure("navigation base %r" % (base,))
        internal = values.get("sdk-internal-resolved")
        if not internal or len(internal) != 3:
            raise CheckFailure("internal summary missing")
        if int(internal[0]) < 3 or int(internal[1]) != int(internal[0]) or int(internal[2]) < 2:
            raise CheckFailure("internal hand-off %r" % (internal,))
        external = values.get("sdk-external-refused")
        if not external or len(external) != 2:
            raise CheckFailure("external summary missing")
        if int(external[0]) < 1 or int(external[1]) != int(external[0]):
            raise CheckFailure("external refusal %r" % (external,))
        for name in ("sdk-cfi-kind", "sdk-unknown-scheme-agreement"):
            if values.get(name) != ["ok"]:
                raise CheckFailure("%s=%r" % (name, values.get(name)))
        return "nav=%s internal=%s external=%s" % (count[0], internal[0], external[0])

    record("cpp-consumer", cpp_consumer)
    record("sdk-navigation-handoff", sdk_handoff)

    def header_parity():
        source_bytes = Path(args.source_header).read_bytes()
        installed_bytes = Path(args.installed_header).read_bytes()
        if source_bytes != installed_bytes:
            raise CheckFailure("installed header differs from the source header")
        digest = hashlib.sha256(installed_bytes).hexdigest()
        report["headers"] = {"sha256": digest, "bytes": len(installed_bytes)}
        return digest

    library = find_library(args.prefix)
    report["library"] = {"path": str(library), "sha256": sha256_file(library),
                         "bytes": library.stat().st_size}
    report["consumers"] = {
        "probe": {"sha256": sha256_file(args.probe), "bytes": Path(args.probe).stat().st_size},
        "cpp": {"sha256": sha256_file(args.cpp), "bytes": Path(args.cpp).stat().st_size},
        "worker": {"sha256": sha256_file(args.worker), "bytes": Path(args.worker).stat().st_size},
        "sdk": {"sha256": sha256_file(args.sdk), "bytes": Path(args.sdk).stat().st_size},
        "control": {"sha256": sha256_file(args.control_lib),
                    "bytes": Path(args.control_lib).stat().st_size},
    }
    for reporter in args.reporters:
        report["consumers"][Path(reporter).name] = {
            "sha256": sha256_file(reporter), "bytes": Path(reporter).stat().st_size}

    record("installed-header-parity", header_parity)

    def unhooked():
        symbols = library_symbols(library)
        leaked = sorted(name for name in symbols if name.startswith("rlp_test"))
        if leaked:
            raise CheckFailure("shipped library exposes test hooks: %r" % (leaked,))
        if "g_track" in symbols:
            raise CheckFailure("shipped library retains hook state")
        return "%d symbols" % len(symbols)

    def no_network():
        symbols = library_symbols(library)
        hits = sorted(symbols & FORBIDDEN)
        if hits:
            raise CheckFailure("forbidden references: %r" % (hits,))
        text = Path(library).read_bytes()
        raw = {token.decode("ascii", "ignore").lower()
               for token in text.split(b"\x00") if 0 < len(token) < 96}
        raw_hits = sorted(raw & FORBIDDEN)
        if raw_hits:
            raise CheckFailure("forbidden byte tokens: %r" % (raw_hits,))
        return "%d symbols, no network/process/file references" % len(symbols)

    def audit_control():
        symbols = library_symbols(Path(args.control_lib))
        hits = symbols & {"system", "remove", "getaddrinfo", "fopen"}
        if len(hits) < 3:
            raise CheckFailure("audit missed the negative control: %r" % (sorted(hits),))
        return "detected %r" % sorted(hits)

    record("installed-library-unhooked", unhooked)
    record("no-network-or-process-symbols", no_network)
    record("symbol-audit-negative-control", audit_control)

    report["ok"] = not failures and len(checks) == len(CHECKS) and \
        [row["name"] for row in checks] == list(CHECKS)
    if len(checks) != len(CHECKS):
        report["ok"] = False
        report.setdefault("failures", []).append(
            "check count %d != %d" % (len(checks), len(CHECKS)))
    with open(output / "report.json", "w", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2, sort_keys=True)
    if not report["ok"]:
        print("FAILED:", failures, flush=True)
        return 1
    print("all %d named checks passed on %s" % (len(checks), platform), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
