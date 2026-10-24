#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Cloud-only acceptance checker for the installed EXReaderLocalization package.

Nothing here builds anything: it authenticates the installed tree, drives the
installed C and C++ consumers, drives the test-hook worker for the two paths a
shipped library must report or refuse, and compares every byte against
expectations frozen before the consumers started.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from localization_fixtures import (ABI_VERSION, CATALOG_FORMAT_VERSION, FORBIDDEN, GROUPS,
                                   LOCALES, MAX_MESSAGE_ID, MAX_OUTPUT_BYTES, MAX_SLOTS,
                                   MAX_VALUE_BYTES, MESSAGES, PACKAGE, VERSION_STRING,
                                   canonical_digest, capacity_exact_rows, refusal_rows, render,
                                   spec_for)

REQUIRED_CASES = (
    "installed-package-layout",
    "installed-c-consumer",
    "installed-cpp-consumer",
    "installed-consumer-binding",
    "abi-and-version",
    "limits-match-header",
    "hook-worker-manifest-parity",
    "catalog-coverage-zh-en",
    "catalog-template-parity",
    "catalog-digest-cross-implementation",
    "format-matrix-zh",
    "format-matrix-en",
    "refusal-arity-and-kind",
    "refusal-malformed-utf8",
    "value-limit-boundary",
    "capacity-atomicity",
    "output-limit",
    "fallback-missing-translation",
    "missing-base-translation",
    "catalog-corruption-refusal",
    "no-internal-diagnostics",
)
cases = []
expected = {row[0]: row for row in MESSAGES}
EXPECTED_IDS = [row[0] for row in MESSAGES]


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
    except Exception as error:  # noqa: BLE001 - every failure is evidence
        cases.append({"name": name, "ok": False, "detail": str(error)[:800]})
        print("FAIL", name, str(error)[:800], flush=True)


def run(command, code=0, timeout=300):
    process = subprocess.run(command, capture_output=True, text=True, encoding="utf-8",
                             errors="surrogateescape", timeout=timeout)
    if code is not None and process.returncode != code:
        raise CheckFailure("rc=%d expected %d: %s %s" % (
            process.returncode, code, process.stdout[-400:], process.stderr[-400:]))
    return process


def parse_kv(process):
    values = {}
    for line in process.stdout.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            values[key] = value
    return values


def parse_manifest(process):
    messages = []
    templates = []
    header = {}
    for line in process.stdout.splitlines():
        if not line:
            continue
        fields = line.split("\t")
        if fields[0] == "M":
            require(len(fields) == 4, "manifest M line shape: %r" % line)
            messages.append(tuple(fields[1:]))
        elif fields[0] == "T":
            require(len(fields) == 4, "manifest T line shape: %r" % line)
            templates.append(tuple(fields[1:]))
        elif fields[0] in ("MESSAGES", "TEMPLATES", "DIGEST"):
            header[fields[0]] = fields[1]
        else:
            raise CheckFailure("unexpected manifest line: %r" % line)
    require({"DIGEST", "MESSAGES", "TEMPLATES"} <= set(header), "manifest header incomplete")
    return header, messages, templates


def manifest_rows(messages, templates):
    rows = {}
    for message_id, locale, text in templates:
        require((message_id, locale) not in rows, "duplicate row %s/%s" % (message_id, locale))
        rows[(message_id, locale)] = text
    require(len(rows) == len(messages) * len(LOCALES), "template row count differs")
    return rows


def parse_matrix(process):
    results = []
    for line in process.stdout.splitlines():
        if not line.startswith("R\t"):
            continue
        fields = line.split("\t")
        require(len(fields) == 10, "matrix line shape: %r" % line)
        results.append({"id": fields[1], "locale": fields[2], "spec": fields[3], "cap": fields[4],
                        "status": fields[5], "hex": fields[6], "buffer": fields[7],
                        "measure_bytes": int(fields[8]), "fallback": int(fields[9])})
    return results


def text_hex(text):
    return text.encode("utf-8").hex() if text else "-"


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--consumer", required=True)
    parser.add_argument("--cpp", required=True)
    parser.add_argument("--worker", required=True)
    parser.add_argument("--fixtures", required=True)
    parser.add_argument("--installed", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--platform", default="")
    arguments = parser.parse_args()

    require(os.environ.get("GITHUB_ACTIONS") == "true", "cloud only")
    consumer = str(Path(arguments.consumer).resolve())
    cpp = str(Path(arguments.cpp).resolve())
    worker = str(Path(arguments.worker).resolve())
    fixtures = Path(arguments.fixtures).resolve()
    installed = Path(arguments.installed).resolve()
    output = Path(arguments.output).resolve()
    source = os.environ["GITHUB_SHA"]
    run_id = int(os.environ["GITHUB_RUN_ID"])
    attempt = int(os.environ["GITHUB_RUN_ATTEMPT"])
    platform = arguments.platform or ("Windows" if os.name == "nt" else sys.platform)
    work = output / "work"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)

    for name in ("expectations.json", "matrix.tsv", "refusals.tsv"):
        require((fixtures / name).is_file(), "fixture %s was not frozen before the consumers" % name)

    state = {}

    def read_header():
        header = installed / "include" / "reader_localization.h"
        require(header.is_file(), "installed header missing: %s" % header)
        return header.read_text(encoding="utf-8")

    def refusal_table():
        if "refusal" not in state:
            results = parse_matrix(run([consumer, "--matrix", str(fixtures / "refusals.tsv")], 0))
            table = {}
            for result in results:
                key = (result["id"], result["locale"], result["spec"], result["cap"])
                require(key not in table, "duplicate refusal row %r" % (key,))
                table[key] = result
            require(len(table) == len(refusal_rows()) + len(capacity_exact_rows()),
                    "refusal rows differ: %d" % len(table))
            state["refusal"] = table
        return state["refusal"]

    def check_statuses(statuses):
        rows = [row for row in refusal_rows() if row[4] in statuses]
        require(len(rows) > 0, "no fixture for statuses %r" % (statuses,))
        table = refusal_table()
        for message_id, locale, spec, capacity, wanted in rows:
            result = table[(message_id, locale, spec, capacity)]
            require(result["status"] == wanted, "status for %s/%s/%s/%s was %s, expected %s" % (
                message_id, locale, spec, capacity, result["status"], wanted))
            if wanted != "OK":
                require(result["buffer"] == "unchanged", "buffer changed on refusal %s/%s" % (
                    message_id, locale))
                require(result["hex"] == "-", "refusal produced text for %s/%s" % (
                    message_id, locale))

    def installed_layout():
        require((installed / "include" / "reader_localization.h").is_file(), "header not installed")
        libraries = sorted(path.name for path in (installed / "lib").iterdir()
                           if path.name.startswith("reader_localization") or
                           path.name.startswith("libreader_localization"))
        require(libraries, "library not installed")
        config = installed / "lib" / "cmake" / "EXReaderLocalization"
        for name in ("EXReaderLocalizationConfig.cmake",
                     "EXReaderLocalizationConfigVersion.cmake",
                     "EXReaderLocalizationTargets.cmake"):
            require((config / name).is_file(), "package file missing: %s" % name)
        require("IMPORTED" in (config / "EXReaderLocalizationTargets.cmake").read_text(encoding="utf-8"),
                "installed target export is not imported")
        repository_header = Path(__file__).resolve().parents[2] / "apps" / "reader" / \
            "localization" / "include" / "reader_localization.h"
        require(repository_header.is_file(), "repository header missing")
        require((installed / "include" / "reader_localization.h").read_bytes() ==
                repository_header.read_bytes(), "installed header differs from the repository")
        state["library_files"] = libraries

    def installed_c():
        process = run([consumer], 0)
        require("FAIL " not in process.stdout, "installed C consumer reported failures")
        require("CONSUMER\tc\t0\tfailures" in process.stdout, "C consumer summary missing")

    def installed_cpp():
        process = run([cpp], 0)
        require("FAIL " not in process.stdout, "installed C++ consumer reported failures")
        require("CONSUMER\tcpp\t0\tfailures" in process.stdout, "C++ consumer summary missing")

    def installed_consumer_binding():
        """The installed consumers must be configured against the installed
        prefix, and every consumed binary and resource is recorded by digest so
        a hand-off can name exactly what ran."""
        consumer_directory = Path(consumer).parent
        cache = consumer_directory / "CMakeCache.txt"
        require(cache.is_file(), "consumer CMake cache missing")
        text = cache.read_text(encoding="utf-8", errors="replace")
        require("CMAKE_PREFIX_PATH" in text, "consumer was not configured with a prefix path")
        match = re.search(r"^EXReaderLocalization_DIR:[^=]*=(.+)$", text, re.MULTILINE)
        require(match is not None, "installed package directory is not in the consumer cache")
        configured = Path(match.group(1).strip())
        expected = (installed / "lib" / "cmake" / "EXReaderLocalization").resolve()
        require(configured.resolve() == expected,
                "consumer resolved the package from %s, not %s" % (configured, expected))
        bindings = {}
        candidates = [("header", installed / "include" / "reader_localization.h"),
                      ("c-consumer", Path(consumer)),
                      ("cpp-consumer", Path(cpp)),
                      ("worker", Path(worker))]
        for library in sorted((installed / "lib").iterdir()):
            if library.is_file() and (library.name.startswith("reader_localization") or
                                      library.name.startswith("libreader_localization")):
                candidates.append(("library", library))
        for name, path in candidates:
            require(path.is_file(), "bound artifact missing: %s" % path)
            size = path.stat().st_size
            require(size > 0, "bound artifact is empty: %s" % path)
            bindings[name] = {"path": str(path), "bytes": size, "sha256": sha256_file(path)}
        for fixture_file in sorted(fixtures.iterdir()):
            if fixture_file.is_file():
                bindings["fixture:" + fixture_file.name] = {
                    "path": str(fixture_file), "bytes": fixture_file.stat().st_size,
                    "sha256": sha256_file(fixture_file)}
        require("library" in bindings, "installed library was not bound")
        require(bindings["c-consumer"]["sha256"] != bindings["worker"]["sha256"],
                "the installed consumer and the hook worker are the same binary")
        state["bindings"] = bindings

    def abi_and_version():
        header = read_header()
        require('#define READER_LOCALIZATION_VERSION_STRING "%s"' % VERSION_STRING in header,
                "version string differs")
        require("#define READER_LOCALIZATION_ABI_VERSION %du" % ABI_VERSION in header,
                "ABI version differs")
        require("#define READER_LOCALIZATION_CATALOG_FORMAT_VERSION %d" % CATALOG_FORMAT_VERSION in header,
                "catalog format version differs")
        header_fields, messages, templates = parse_manifest(run([consumer, "--manifest"], 0))
        state["header"] = header_fields
        state["messages"] = messages
        state["templates"] = templates
        require(int(header_fields["MESSAGES"]) == len(EXPECTED_IDS), "message count differs")
        require(int(header_fields["TEMPLATES"]) == len(EXPECTED_IDS) * len(LOCALES),
                "template count differs")

    def limits_match_header():
        header = read_header()
        expectations_module = Path(__file__).resolve().parent / "localization_fixtures.py"
        module_text = expectations_module.read_text(encoding="utf-8")
        for name, value in (("MAX_MESSAGE_ID", MAX_MESSAGE_ID), ("MAX_SLOTS", MAX_SLOTS),
                            ("MAX_VALUE_BYTES", MAX_VALUE_BYTES),
                            ("MAX_OUTPUT_BYTES", MAX_OUTPUT_BYTES)):
            match = re.search(r"#define READER_LOCALIZATION_%s (\d+)u" % name, header)
            require(match is not None, "limit %s is not declared" % name)
            require(int(match.group(1)) == value, "%s differs: %s" % (name, match.group(1)))
            require(re.search(r"^%s = %d$" % (name, value), module_text, re.MULTILINE) is not None,
                    "the expectation for %s is not pinned" % name)
        for name in ("reader_localization_message_count", "reader_localization_template_count",
                     "reader_localization_format", "reader_localization_measure",
                     "reader_localization_catalog_digest", "reader_localization_resolve"):
            require(name + "(" in header, "public entry point %s is not declared" % name)
        state["limits"] = {"message_id": MAX_MESSAGE_ID, "slots": MAX_SLOTS,
                           "value_bytes": MAX_VALUE_BYTES, "output_bytes": MAX_OUTPUT_BYTES}

    def hook_worker_manifest_parity():
        installed_header, installed_messages, installed_templates = parse_manifest(
            run([consumer, "--manifest"], 0))
        worker_header, worker_messages, worker_templates = parse_manifest(run([worker, "manifest"], 0))
        require(installed_header == worker_header, "worker digest or counts differ")
        require(installed_messages == worker_messages, "worker message table differs")
        require(installed_templates == worker_templates, "worker template table differs")
        state["digest"] = installed_header["DIGEST"]

    def catalog_coverage():
        messages = state["messages"]
        rows = manifest_rows(messages, state["templates"])
        seen = {}
        for message_id, group, kinds in messages:
            require(message_id not in seen, "duplicate message id %s" % message_id)
            require(message_id in expected, "unexpected message id %s" % message_id)
            row = expected[message_id]
            require(group == row[1], "group differs for %s" % message_id)
            require(kinds == row[2], "slot layout differs for %s" % message_id)
            require(group in GROUPS, "unknown group %s" % group)
            seen[message_id] = kinds
        require(set(seen) == set(expected), "message set differs from the expectation table")
        for group in GROUPS:
            require(any(row[1] == group for row in MESSAGES), "group %s has no message" % group)
        for message_id, group, kinds, zh_text, en_text in MESSAGES:
            require(rows[(message_id, "zh-CN")] == zh_text, "zh-CN text differs for %s" % message_id)
            require(rows[(message_id, "en-US")] == en_text, "en-US text differs for %s" % message_id)

    def catalog_template_parity():
        rows = manifest_rows(state["messages"], state["templates"])
        for message_id, group, kinds, _zh, _en in MESSAGES:
            for locale in LOCALES:
                text = rows[(message_id, locale)]
                require(text, "empty template for %s" % message_id)
                require("\t" not in text and "\n" not in text,
                        "template contains a separator for %s" % message_id)
                indices = [int(match) for match in re.findall(r"\{(\d+)\}", text)]
                require(sorted(indices) == list(range(len(kinds))),
                        "placeholder layout differs for %s/%s" % (message_id, locale))
                require(len(indices) == len(set(indices)),
                        "duplicate placeholder for %s/%s" % (message_id, locale))
                require(len(text.encode("utf-8")) <= 256, "template too long for %s" % message_id)
                require("{" not in text.replace("{%d}" % 0, "").replace("{%d}" % 1, "")
                        .replace("{%d}" % 2, "").replace("{%d}" % 3, ""),
                        "template has an unmatched brace for %s" % message_id)

    def catalog_digest():
        identifiers = [row[0] for row in state["messages"]]
        require(identifiers == sorted(identifiers), "enumeration is not ascending")
        require(state["header"]["DIGEST"] == canonical_digest(),
                "library digest %s differs from the recomputed %s" % (
                    state["header"]["DIGEST"], canonical_digest()))
        require(re.fullmatch(r"[0-9a-f]{64}", state["header"]["DIGEST"]) is not None,
                "digest is not lowercase hex")
        state["recomputed_digest"] = canonical_digest()

    def matrix_for(locale):
        rows = manifest_rows(state["messages"], state["templates"])
        results = parse_matrix(run([consumer, "--matrix", str(fixtures / "matrix.tsv")], 0))
        require(len(results) == len(MESSAGES) * len(LOCALES), "matrix result count differs")
        covered = set()
        for result in results:
            if result["locale"] != locale:
                continue
            message_id = result["id"]
            message = expected[message_id]
            wanted = render(message[3] if locale == "zh-CN" else message[4], message[2])
            require(rows[(message_id, locale)] ==
                    (message[3] if locale == "zh-CN" else message[4]),
                    "manifest template differs for %s/%s" % (message_id, locale))
            require(result["status"] == "OK", "render failed for %s/%s: %s" % (
                message_id, locale, result["status"]))
            require(result["hex"] == text_hex(wanted),
                    "rendered text differs for %s/%s: %r != %r" % (
                        message_id, locale, result["hex"], text_hex(wanted)))
            require(result["fallback"] == 0, "unexpected fallback for %s/%s" % (message_id, locale))
            require(result["measure_bytes"] == len(wanted.encode("utf-8")) + 1,
                    "measured size differs for %s/%s" % (message_id, locale))
            require(result["buffer"] == "written", "buffer not written for %s/%s" % (
                message_id, locale))
            covered.add(message_id)
        require(covered == set(expected), "matrix did not cover every id for %s" % locale)

    def refusal_arity_and_kind():
        check_statuses({"PARAMETER_COUNT", "PARAMETER_TYPE", "ARGUMENT", "UNKNOWN_MESSAGE"})

    def refusal_malformed_utf8():
        check_statuses({"VALUE_INVALID"})

    def value_limit_boundary():
        table = refusal_table()
        missing = "reader.shelf.book.missing"
        at_limit = table[(missing, "en-US", "s:" + "78" * MAX_VALUE_BYTES, "4096")]
        require(at_limit["status"] == "OK", "value at the limit was refused: %s" % at_limit["status"])
        require(at_limit["hex"] == text_hex("x" * MAX_VALUE_BYTES + " is unavailable"),
                "value at the limit was altered")
        over = table[(missing, "en-US", "s:" + "78" * (MAX_VALUE_BYTES + 1), "4096")]
        require(over["status"] == "VALUE_TOO_LONG", "value over the limit was %s" % over["status"])
        require(over["buffer"] == "unchanged", "value over the limit wrote a buffer")
        check_statuses({"VALUE_TOO_LONG"})

    def capacity_atomicity():
        table = refusal_table()
        missing = "reader.shelf.book.missing"
        wanted = render(expected[missing][4], "s")
        short = table[(missing, "en-US", spec_for("s"), "8")]
        require(short["status"] == "CAPACITY", "short buffer was %s" % short["status"])
        require(short["buffer"] == "unchanged", "short buffer was modified")
        require(short["measure_bytes"] == len(wanted.encode("utf-8")) + 1,
                "CAPACITY did not report the required size")
        zero = table[("reader.shelf.title", "en-US", "-", "0")]
        require(zero["status"] == "CAPACITY" and zero["buffer"] == "unchanged",
                "zero capacity did not refuse cleanly")
        for message_id, locale, spec, capacity, status_name in capacity_exact_rows():
            result = table[(message_id, locale, spec, capacity)]
            message = expected[message_id]
            wanted_text = render(message[3] if locale == "zh-CN" else message[4], message[2])
            require(result["status"] == status_name,
                    "exact capacity failed for %s/%s: %s" % (message_id, locale, result["status"]))
            require(result["hex"] == text_hex(wanted_text),
                    "exact capacity text differs for %s/%s" % (message_id, locale))
            require(int(capacity) == len(wanted_text.encode("utf-8")) + 1,
                    "exact capacity fixture is not the measured size for %s" % message_id)

    def output_limit():
        table = refusal_table()
        spec = "s:" + "61" * MAX_VALUE_BYTES + "|s:" + "62" * MAX_VALUE_BYTES
        limit = table[("reader.organize.move", "en-US", spec, "4096")]
        require(limit["status"] == "LIMIT", "over-long render was %s" % limit["status"])
        require(limit["buffer"] == "unchanged", "over-long render wrote a buffer")
        require(limit["measure_bytes"] == 0, "over-long render published a size")
        require(len("Move " + "a" * MAX_VALUE_BYTES + " to " + "b" * MAX_VALUE_BYTES) >
                MAX_OUTPUT_BYTES, "the output limit fixture is not over the limit")

    def fallback_missing_translation():
        process = run([worker, "fallback", "reader.shelf.book.progress", "zh-CN", spec_for("d")], 0)
        values = parse_kv(process)
        require(values.get("status") == "OK", "fallback render failed: %s" % values.get("status"))
        require(values.get("fallback") == "1", "fallback flag was not reported")
        require(values.get("hex") == text_hex(render(expected["reader.shelf.book.progress"][4], "d")),
                "fallback did not use the en-US template")
        require(values.get("digest") == state["digest"], "a test hook changed the catalog digest")

    def missing_base_translation():
        process = run([worker, "en-missing", "reader.shelf.title", "en-US", "-"], None)
        values = parse_kv(process)
        require(values.get("resolve") == "UNKNOWN_MESSAGE",
                "missing base row resolved as %s" % values.get("resolve"))
        require(values.get("status") == "UNKNOWN_MESSAGE",
                "missing base row rendered as %s" % values.get("status"))
        require(values.get("hex") == "-", "missing base row produced text")

    def catalog_corruption():
        for template in ("{9}", "{0}{0}", "}{0}"):
            process = run([worker, "corrupt", "reader.shelf.count", "zh-CN", "d:5", template], None)
            values = parse_kv(process)
            require(values.get("status") == "CATALOG",
                    "template %r rendered as %s" % (template, values.get("status")))
            require(values.get("hex") == "-", "template %r produced text" % template)
            require(values.get("len") == "0", "template %r published a length" % template)

    def no_internal_diagnostics():
        _header, _messages, templates = parse_manifest(run([consumer, "--manifest"], 0))
        for _id, locale, text in templates:
            for marker in FORBIDDEN:
                require(marker.lower() not in text.lower(), "catalog %s carries %r" % (locale, marker))
            require("%p" not in text and "%n" not in text, "catalog text carries a C format verb")
            require("\\" not in text, "catalog text carries a path separator")
            require("reader." not in text, "catalog text exposes an internal message id")
        for status_name in ("OK", "ARGUMENT", "UNKNOWN_MESSAGE", "UNKNOWN_LOCALE", "PARAMETER_COUNT",
                            "PARAMETER_TYPE", "VALUE_INVALID", "VALUE_TOO_LONG", "CAPACITY", "LIMIT",
                            "CATALOG"):
            require(re.fullmatch(r"[A-Z_]+", status_name) is not None, "status is not a code")

    record("installed-package-layout", installed_layout)
    record("installed-c-consumer", installed_c)
    record("installed-cpp-consumer", installed_cpp)
    record("installed-consumer-binding", installed_consumer_binding)
    record("abi-and-version", abi_and_version)
    record("limits-match-header", limits_match_header)
    record("hook-worker-manifest-parity", hook_worker_manifest_parity)
    record("catalog-coverage-zh-en", catalog_coverage)
    record("catalog-template-parity", catalog_template_parity)
    record("catalog-digest-cross-implementation", catalog_digest)
    record("format-matrix-zh", lambda: matrix_for("zh-CN"))
    record("format-matrix-en", lambda: matrix_for("en-US"))
    record("refusal-arity-and-kind", refusal_arity_and_kind)
    record("refusal-malformed-utf8", refusal_malformed_utf8)
    record("value-limit-boundary", value_limit_boundary)
    record("capacity-atomicity", capacity_atomicity)
    record("output-limit", output_limit)
    record("fallback-missing-translation", fallback_missing_translation)
    record("missing-base-translation", missing_base_translation)
    record("catalog-corruption-refusal", catalog_corruption)
    record("no-internal-diagnostics", no_internal_diagnostics)

    problems = ["%s: %s" % (case["name"], case["detail"]) for case in cases if not case["ok"]]
    report = {
        "accepted": len(problems) == 0 and len(cases) == len(REQUIRED_CASES),
        "package": PACKAGE,
        "common_start": "f43baf9182d75907c0cb5d6f77048f27bca8c950",
        "source_sha": source,
        "run_id": run_id,
        "attempt": attempt,
        "platform": platform,
        "granted_platform": platform.lower(),
        "catalog_digest": state.get("digest", ""),
        "recomputed_digest": state.get("recomputed_digest", ""),
        "messages": len(state.get("messages", [])),
        "templates": len(state.get("templates", [])),
        "limits": state.get("limits", {}),
        "library_files": state.get("library_files", []),
        "bindings": state.get("bindings", {}),
        "checks": len(cases),
        "cases": cases,
        "problems": problems,
        "macos_accepted": platform.lower() == "macos",
        "performance_claimed": False,
        "host_ui_accepted": False,
        "six_platform_accepted": False,
        "complete_product": False,
        "sdk_changed": False,
        "schema_changed": False,
        "host_strings_changed": False,
    }
    output.mkdir(parents=True, exist_ok=True)
    (output / "result.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"accepted": report["accepted"], "cases": len(cases),
                      "digest": report["catalog_digest"]}), flush=True)
    raise SystemExit(0 if report["accepted"] else 1)


if __name__ == "__main__":
    main()
