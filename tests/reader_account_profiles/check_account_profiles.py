#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Cloud-only acceptance checker for the installed EXReaderAccountProfiles package.

Every case is named and independent: a failure is recorded, never replaced by a
different expectation. The package is only consumed through its installed CMake
package and public header; the worker alone is built from source with explicit
test hooks.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import time

FIXED_START = "f43baf9182d75907c0cb5d6f77048f27bca8c950"
REQUIRED_CASES = (
    "installed-c-consumer",
    "installed-cpp-session-consumer",
    "validate-unicode-names",
    "validate-utf8-refusals",
    "validate-uuid",
    "validate-url-rules",
    "secret-url-refused",
    "add-load-roundtrip-unicode",
    "duplicate-id-and-pair",
    "same-url-different-account-isolation",
    "same-account-different-url-isolation",
    "profile-count-limit",
    "file-limit-lowered",
    "unknown-version-preserved",
    "corrupt-format-preserved",
    "noncanonical-bytes-preserved",
    "cancelled-add-before-lock",
    "cancelled-save-preserves",
    "failed-save-preserves",
    "lock-timeout-and-recovery",
    "real-termination-releases-lock",
    "crash-before-rename-leftover",
    "concurrent-processes-no-lost-update",
    "thread-reentrancy",
    "generation-conflict",
    "argument-and-struct-size",
    "activation-derived-paths",
    "no-directory-before-activation",
    "unsafe-link-rejected",
    "hardlink-library-rejected",
    "binding-missing-refused",
    "binding-mismatch-refused",
    "binding-match-accepted",
    "verify-tampered-plan",
    "verify-stale-plan",
    "verify-missing-profile",
    "unicode-store-path",
    "secret-scan",
    "no-sdk-or-product-dependency",
    "cross-account-real-session",
)

PROBE = ""
SESSION = ""
WORKER = ""
ROOT = Path()
PREFIX = Path()
PLATFORM = ""
IS_WINDOWS = os.name == "nt"
cases = []


class CheckFailure(RuntimeError):
    pass


def record(name, function):
    try:
        function()
        cases.append({"name": name, "status": "pass", "ok": True, "detail": ""})
        print("PASS", name, flush=True)
    except Exception as error:  # noqa: BLE001 - every failure is evidence
        cases.append({"name": name, "status": "fail", "ok": False,
                      "detail": str(error)[:1200]})
        print("FAIL", name, str(error)[:1200], flush=True)


def run(command, code=0, timeout=300):
    process = subprocess.run([str(part) for part in command], capture_output=True,
                             text=True, encoding="utf-8", errors="replace", timeout=timeout)
    if code is not None and process.returncode != code:
        raise CheckFailure("rc=%d expected %d: %s %s" % (
            process.returncode, code, process.stdout[-600:], process.stderr[-600:]))
    return process


def kv(process):
    values = {}
    for line in process.stdout.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            values[key] = value
    return values


def status_of(process):
    return kv(process).get("status", "")


def expect(condition, message):
    if not condition:
        raise CheckFailure(message)


def expect_status(process, expected):
    actual = status_of(process)
    expect(actual == expected, "status %r != %r (%s)" % (
        actual, expected, kv(process).get("message", "")))


def uuid_pair(index):
    return ("a0000000-0000-4000-8000-%012d" % index,
            "b0000000-0000-4000-8000-%012d" % index)


def store(name):
    path = ROOT / name
    path.mkdir(parents=True, exist_ok=True)
    return str(path)


def document(store_path):
    return Path(store_path) / "profiles.json"


def temporary(store_path):
    return Path(store_path) / "profiles.json.tmp"


def document_bytes(store_path):
    path = document(store_path)
    return path.read_bytes() if path.exists() else None


def add(store_path, profile_id, account, url, name):
    process = run([PROBE, "add", store_path, profile_id, account, url, name])
    expect_status(process, "OK")
    return int(kv(process)["new_generation"])


def load(store_path):
    process = run([PROBE, "load", store_path])
    expect_status(process, "OK")
    values = kv(process)
    count = int(values["count"])
    items = []
    for index in range(count):
        items.append((values["p%d.id" % index], values["p%d.account" % index],
                      values["p%d.url" % index], values["p%d.name" % index]))
    return {"generation": int(values["generation"]), "count": count, "items": items}


def plan(store_path, profile_id):
    process = run([PROBE, "activation", store_path, profile_id])
    expect_status(process, "OK")
    return kv(process)


def activation_status(store_path, profile_id):
    return status_of(run([PROBE, "activation", store_path, profile_id]))


def wait_file(path, timeout=30.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if Path(path).exists():
            return
        time.sleep(0.02)
    raise CheckFailure("ready file %s never appeared" % path)


def spawn(command, **kwargs):
    return subprocess.Popen([str(part) for part in command], stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True, encoding="utf-8",
                            errors="replace", **kwargs)


def terminate(process):
    process.kill()
    try:
        process.wait(timeout=60)
    except subprocess.TimeoutExpired as error:
        raise CheckFailure("process did not terminate: %s" % error)


def make_link(target, link, directory=True):
    link = str(link)
    if Path(link).exists() or Path(link).is_symlink():
        raise CheckFailure("link path already exists: %s" % link)
    if IS_WINDOWS:
        command = ["cmd", "/c", "mklink"]
        command.append("/J" if directory else "/H")
        command.extend([link, str(target)])
        result = subprocess.run(command, capture_output=True, text=True)
        expect(result.returncode == 0, "mklink failed: %s %s" % (result.stdout, result.stderr))
    else:
        os.symlink(str(target), link, target_is_directory=directory)


# --------------------------------------------------------------------------- cases

def case_installed_c_consumer():
    process = run([PROBE, "info"])
    values = kv(process)
    expect(values.get("abi") == "1", "abi differs")
    expect(values.get("version") == "0.1.0", "version differs")
    expect(values.get("max_profiles") == "32", "profile limit differs")
    expect(values.get("status.OK") == "OK", "OK name differs")
    expect(values.get("status.SECRET") == "SECRET", "SECRET name differs")
    expect(values.get("status.UNSAFE_PATH") == "UNSAFE_PATH", "UNSAFE_PATH name differs")
    expect(values.get("status.BINDING") == "BINDING", "BINDING name differs")
    expect(values.get("status.UNKNOWN") == "UNKNOWN", "unknown status name differs")


def case_installed_cpp_session_consumer():
    expect(Path(SESSION).exists(), "the session consumer was not built")
    process = run([SESSION], code=2, timeout=120)
    expect("usage" in (process.stderr + process.stdout), "usage line missing")


def case_validate_unicode_names():
    profile_id, account = uuid_pair(1)
    names = ["阅读器", "Léa — 书架", "📚 Books", "مكتبة", "e\u0301tude", "a" * 128]
    for name in names:
        process = run([PROBE, "validate", profile_id, account, "https://one.example/reader/", name])
        expect_status(process, "OK")
    for name in ["", " leading", "trailing "]:
        process = run([PROBE, "validate", profile_id, account, "https://one.example/reader/", name])
        expect(status_of(process) == "INVALID",
               "name %r -> %s" % (name, status_of(process)))
    store_path = store("name-document")
    add(store_path, profile_id, account, "https://one.example/reader/", "one")
    original = document_bytes(store_path)
    altered = original.replace(b'"one"', b'"' + (b"a" * 129) + b'"', 1)
    expect(altered != original, "fixture did not change the name")
    document(store_path).write_bytes(altered)
    expect_status(run([PROBE, "load", store_path]), "FORMAT")
    expect(document_bytes(store_path) == altered,
           "a document with an oversized name was overwritten")


def case_validate_utf8_refusals():
    profile_id, account = uuid_pair(2)
    for name in ["\u0001bad", "\u0085c1", "\u001funit"]:
        process = run([PROBE, "validate", profile_id, account, "https://one.example/reader/", name])
        expect(status_of(process) == "INVALID",
               "control character %r -> %s" % (name, status_of(process)))
    store_path = store("utf8-document")
    add(store_path, profile_id, account, "https://one.example/reader/", "one")
    original = document_bytes(store_path)
    for label, replacement in [("overlong", b"\xc0\x80"), ("surrogate", b"\xed\xa0\x80"),
                               ("truncated", b"\xe4\xb8")]:
        altered = original.replace(b'"one"', b'"' + replacement + b'"', 1)
        expect(altered != original, "fixture did not change the name")
        document(store_path).write_bytes(altered)
        process = run([PROBE, "load", store_path])
        expect(status_of(process) == "INVALID",
               "%s name -> %s" % (label, status_of(process)))
        expect(document_bytes(store_path) == altered,
               "a document with invalid UTF-8 was overwritten")


def case_validate_uuid():
    account = "b0000000-0000-4000-8000-000000000001"
    for bad in ["A0000000-0000-4000-8000-000000000001",
                "00000000-0000-0000-0000-000000000000",
                "a0000000-0000-4000-8000-00000000000",
                "a0000000-0000-4000-8000-00000000000g",
                "a0000000_0000-4000-8000-000000000001"]:
        expect_status(run([PROBE, "validate", bad, account, "https://one.example/reader/", "n"]),
                      "INVALID")
    expect_status(run([PROBE, "validate", "a0000000-0000-4000-8000-000000000001", account,
                       "https://one.example/reader/", "n"]), "OK")


def case_validate_url_rules():
    profile_id, account = uuid_pair(3)
    good = ["https://one.example/reader/", "https://host:8443/a/b/",
            "https://127.0.0.1:9/reader/"]
    bad = ["http://one.example/reader/", "https://one.example", "https:///reader/",
           "https://one.example:abc/reader/", "https://one.example:/reader/",
           "https://one.example/re ader/", "https://one.example/pa\u0442h/",
           "https://one.example/" + "a" * 1010]
    for url in good:
        expect_status(run([PROBE, "validate", profile_id, account, url, "n"]), "OK")
    for url in bad:
        process = run([PROBE, "validate", profile_id, account, url, "n"])
        expect(status_of(process) == "INVALID", "accepted invalid URL %r -> %s" % (
            url, status_of(process)))


def case_secret_url_refused():
    profile_id, account = uuid_pair(4)
    store_path = store("secret")
    for url in ["https://user:secret@one.example/reader/", "https://one.example/reader/?a=1",
                "https://one.example/reader/#frag"]:
        process = run([PROBE, "validate", profile_id, account, url, "n"])
        expect_status(process, "SECRET")
        message = kv(process).get("message", "")
        expect("https://" not in message and "@" not in message,
               "the error message repeats the URL")
        process = run([PROBE, "add", store_path, profile_id, account, url, "n"])
        expect_status(process, "SECRET")
    expect(document_bytes(store_path) is None, "a refused URL wrote a document")


def case_add_load_roundtrip_unicode():
    store_path = store("roundtrip")
    entries = [
        (uuid_pair(10)[0], uuid_pair(10)[1], "https://one.example/reader/", "阅读器"),
        (uuid_pair(11)[0], uuid_pair(11)[1], "https://two.example/a/", "Léa — 书架"),
        (uuid_pair(12)[0], uuid_pair(12)[1], "https://three.example/b/", "📚 e\u0301tude"),
    ]
    for index, entry in enumerate(entries):
        expect(add(store_path, *entry) == index + 1, "generation did not increase")
    loaded = load(store_path)
    expect(loaded["generation"] == 3, "generation differs")
    expect(loaded["items"] == entries, "roundtrip changed a stored field")
    raw = document_bytes(store_path)
    expect(raw.endswith(b"}\n"), "document does not end with a newline")
    expect(b"\r" not in raw, "document contains CR")
    for text in ["阅读器", "📚", "Léa"]:
        expect(text.encode("utf-8") in raw, "UTF-8 name is not stored byte for byte")


def case_duplicate_id_and_pair():
    store_path = store("duplicates")
    first, account = uuid_pair(20)
    add(store_path, first, account, "https://one.example/reader/", "one")
    expect_status(run([PROBE, "add", store_path, first, uuid_pair(21)[1],
                       "https://two.example/reader/", "dup-id"]), "EXISTS")
    expect_status(run([PROBE, "add", store_path, uuid_pair(22)[0], account,
                       "https://one.example/reader/", "dup-pair"]), "EXISTS")
    add(store_path, uuid_pair(23)[0], uuid_pair(23)[1], "https://one.example/reader/", "other-acct")
    add(store_path, uuid_pair(24)[0], uuid_pair(24)[1], "https://four.example/reader/", "other-url")
    expect(load(store_path)["count"] == 3, "accepted profiles differ")


def case_same_url_different_account_isolation():
    store_path = store("same-url")
    url = "https://shared.example/reader/"
    left_id, left_account = uuid_pair(30)
    right_id, right_account = uuid_pair(31)
    add(store_path, left_id, left_account, url, "left")
    add(store_path, right_id, right_account, url, "right")
    left = plan(store_path, left_id)
    right = plan(store_path, right_id)
    expect(left["plan.product"] != right["plan.product"], "two accounts share a product path")
    expect(left["plan.private"] != right["plan.private"], "two accounts share a private directory")
    expect(left["plan.originals"] != right["plan.originals"], "two accounts share originals")
    for values, profile_id in ((left, left_id), (right, right_id)):
        expect(Path(values["plan.product"]) == Path(store_path) / "profiles" / profile_id / "library.sqlite",
               "product path is not derived from the profile id")
        expect(Path(values["plan.private"]).name == "private", "private directory name differs")
        expect(Path(values["plan.originals"]).name == "originals", "original directory name differs")


def case_same_account_different_url_isolation():
    store_path = store("same-account")
    account = "c0000000-0000-4000-8000-000000000040"
    first, second = uuid_pair(40)[0], uuid_pair(41)[0]
    add(store_path, first, account, "https://one.example/reader/", "one")
    add(store_path, second, account, "https://two.example/reader/", "two")
    left = plan(store_path, first)
    right = plan(store_path, second)
    expect(left["plan.product"] != right["plan.product"], "one account shares a product path")
    expect(left["plan.url"] != right["plan.url"], "the plan lost the exact root URL")


def case_profile_count_limit():
    store_path = store("count-limit")
    for index in range(32):
        profile_id, account = uuid_pair(100 + index)
        add(store_path, profile_id, account, "https://limit.example/reader/", "p%d" % index)
    expect_status(run([PROBE, "add", store_path, uuid_pair(200)[0], uuid_pair(200)[1],
                       "https://limit.example/reader/", "overflow"]), "LIMIT")
    loaded = load(store_path)
    expect(loaded["count"] == 32 and loaded["generation"] == 32,
           "the refused add changed the document")


def case_file_limit_lowered():
    store_path = store("file-limit")
    add(store_path, uuid_pair(50)[0], uuid_pair(50)[1], "https://one.example/reader/", "one")
    expect_status(run([PROBE, "load-limit", store_path, "200"]), "LIMIT")
    expect_status(run([PROBE, "load-limit", store_path, "200000"]), "ARGUMENT")
    expect_status(run([PROBE, "load-limit", store_path, "4096"]), "OK")


def case_unknown_version_preserved():
    store_path = store("version")
    add(store_path, uuid_pair(51)[0], uuid_pair(51)[1], "https://one.example/reader/", "one")
    original = document_bytes(store_path)
    altered = original.replace(b'"version": 1', b'"version": 2', 1)
    expect(altered != original, "fixture did not change the version")
    document(store_path).write_bytes(altered)
    process = run([PROBE, "load", store_path])
    expect_status(process, "VERSION")
    expect(int(kv(process).get("offset", "0")) > 0, "VERSION offset is not reported")
    expect(document_bytes(store_path) == altered, "an unknown version was overwritten")


def case_corrupt_format_preserved():
    store_path = store("corrupt")
    add(store_path, uuid_pair(52)[0], uuid_pair(52)[1], "https://one.example/reader/", "one")
    original = document_bytes(store_path)
    truncated = original[: len(original) // 2]
    document(store_path).write_bytes(truncated)
    expect_status(run([PROBE, "load", store_path]), "FORMAT")
    expect(document_bytes(store_path) == truncated, "a damaged document was overwritten")
    document(store_path).write_bytes(b"")
    expect_status(run([PROBE, "load", store_path]), "FORMAT")
    expect(document_bytes(store_path) == b"", "an empty document was overwritten")
    document(store_path).write_bytes(b"{\"format\":\"reader-account-profiles\"}\n")
    expect_status(run([PROBE, "load", store_path]), "FORMAT")
    expect(document_bytes(store_path) == b"{\"format\":\"reader-account-profiles\"}\n",
           "a foreign document was overwritten")


def case_noncanonical_bytes_preserved():
    store_path = store("noncanonical")
    add(store_path, uuid_pair(53)[0], uuid_pair(53)[1], "https://one.example/reader/", "one")
    original = document_bytes(store_path)
    variants = [
        original.replace(b'  "generation"', b' "generation"', 1),
        original.replace(b'"version": 1', b'"version": 01', 1),
        original[:-1],
        original.replace(b'"profiles": [', b'"profiles":[', 1),
    ]
    for variant in variants:
        expect(variant != original, "fixture did not change the document")
        document(store_path).write_bytes(variant)
        expect_status(run([PROBE, "load", store_path]), "FORMAT")
        expect(document_bytes(store_path) == variant, "a non-canonical document was rewritten")


def case_cancelled_add_before_lock():
    store_path = store("cancel-add")
    profile_id, account = uuid_pair(54)
    expect_status(run([PROBE, "cancel-add", store_path, profile_id, account,
                       "https://one.example/reader/", "one"]), "CANCELLED")
    expect(document_bytes(store_path) is None, "a cancelled add created a document")
    expect(not (Path(store_path) / ".lock").exists(), "a cancelled add created the lock file")


def case_cancelled_save_preserves():
    store_path = store("cancel-save")
    add(store_path, uuid_pair(55)[0], uuid_pair(55)[1], "https://one.example/reader/", "one")
    original = document_bytes(store_path)
    process = run([WORKER, "add", store_path, uuid_pair(56)[0], uuid_pair(56)[1],
                   "https://one.example/reader/", "two", "--cancel-before-rename"])
    expect_status(process, "CANCELLED")
    expect(document_bytes(store_path) == original, "a cancelled save replaced the document")
    expect(not temporary(store_path).exists(), "a cancelled save left a temporary file")


def case_failed_save_preserves():
    store_path = store("failed-save")
    add(store_path, uuid_pair(57)[0], uuid_pair(57)[1], "https://one.example/reader/", "one")
    original = document_bytes(store_path)
    process = run([WORKER, "add", store_path, uuid_pair(58)[0], uuid_pair(58)[1],
                   "https://one.example/reader/", "two", "--fail-before-rename"])
    expect_status(process, "IO")
    expect(document_bytes(store_path) == original, "a failed save replaced the document")
    expect(not temporary(store_path).exists(), "a failed save left a temporary file")


def case_lock_timeout_and_recovery():
    store_path = store("lock-timeout")
    ready = ROOT / "lock-ready.txt"
    holder = spawn([WORKER, "hold", store_path, ready, "1500", "1"])
    try:
        wait_file(ready)
        process = run([PROBE, "add", store_path, uuid_pair(60)[0], uuid_pair(60)[1],
                       "https://one.example/reader/", "blocked", "100"])
        expect_status(process, "LOCKED")
        expect(document_bytes(store_path) is None, "a blocked writer changed the document")
        holder.wait(timeout=120)
        expect(holder.returncode == 0, "the holder failed")
        add(store_path, uuid_pair(61)[0], uuid_pair(61)[1], "https://one.example/reader/", "after")
        expect(load(store_path)["count"] == 2, "the holder or the next writer lost a record")
    finally:
        if holder.poll() is None:
            terminate(holder)


def case_real_termination_releases_lock():
    store_path = store("terminate")
    ready = ROOT / "terminate-ready.txt"
    holder = spawn([WORKER, "hold", store_path, ready, "60000", "2"])
    try:
        wait_file(ready)
        terminate(holder)
    finally:
        if holder.poll() is None:
            terminate(holder)
    process = run([PROBE, "add", store_path, uuid_pair(62)[0], uuid_pair(62)[1],
                   "https://one.example/reader/", "after-kill", "5000"])
    expect_status(process, "OK")
    loaded = load(store_path)
    expect(loaded["count"] == 1 and loaded["generation"] == 1, "termination state differs")


def case_crash_before_rename_leftover():
    store_path = store("crash-rename")
    add(store_path, uuid_pair(63)[0], uuid_pair(63)[1], "https://one.example/reader/", "one")
    original = document_bytes(store_path)
    ready = ROOT / "rename-ready.txt"
    writer = spawn([WORKER, "add", store_path, uuid_pair(64)[0], uuid_pair(64)[1],
                    "https://one.example/reader/", "two", "--pause-before-rename", ready, "60000"])
    try:
        wait_file(ready)
        terminate(writer)
    finally:
        if writer.poll() is None:
            terminate(writer)
    expect(document_bytes(store_path) == original, "a killed writer replaced the document")
    expect(temporary(store_path).exists(), "the killed writer left no temporary file")
    add(store_path, uuid_pair(65)[0], uuid_pair(65)[1], "https://one.example/reader/", "three")
    expect(not temporary(store_path).exists(), "the next writer did not remove the leftover")
    expect(load(store_path)["count"] == 2, "the recovered document differs")


def case_concurrent_processes_no_lost_update():
    store_path = store("concurrent")
    processes = []
    for index in range(8):
        processes.append(spawn([WORKER, "race", store_path, str(index * 2), "2"]))
    for process in processes:
        process.wait(timeout=240)
        expect(process.returncode == 0, "a concurrent writer failed")
    loaded = load(store_path)
    expect(loaded["count"] == 16, "concurrent count is %d" % loaded["count"])
    expect(loaded["generation"] == 16, "concurrent generation is %d" % loaded["generation"])
    expect(len({item[0] for item in loaded["items"]}) == 16, "concurrent ids repeat")


def case_thread_reentrancy():
    store_path = store("threads")
    process = run([PROBE, "threads", store_path, "4"], timeout=240)
    values = kv(process)
    for index in range(4):
        expect(values.get("thread%d" % index) == "OK",
               "thread %d status %r" % (index, values.get("thread%d" % index)))
    expect(values.get("failures") == "0", "thread failures reported")
    expect(values.get("count") == "4", "thread count differs")
    expect(values.get("generation") == "4", "thread generation differs")


def case_generation_conflict():
    store_path = store("generation")
    profile_id, account = uuid_pair(70)
    process = run([PROBE, "add-gen", store_path, profile_id, account,
                   "https://one.example/reader/", "one", "0"])
    expect_status(process, "OK")
    expect(kv(process)["new_generation"] == "1", "first generation differs")
    expect_status(run([PROBE, "add-gen", store_path, uuid_pair(71)[0], uuid_pair(71)[1],
                       "https://one.example/reader/", "two", "0"]), "CONFLICT")
    process = run([PROBE, "add-gen", store_path, uuid_pair(72)[0], uuid_pair(72)[1],
                   "https://one.example/reader/", "three", "1"])
    expect_status(process, "OK")
    expect(kv(process)["new_generation"] == "2", "second generation differs")


def case_argument_and_struct_size():
    process = run([PROBE, "struct-size"])
    statuses = [line.split("=", 1)[1] for line in process.stdout.splitlines()
                if line.startswith("status=")]
    expect(len(statuses) == 3 and all(value == "ARGUMENT" for value in statuses),
           "struct_size or null-argument checks differ: %r" % statuses)
    expect_status(run([PROBE, "relative"]), "ARGUMENT")


def case_activation_derived_paths():
    store_path = store("activation")
    profile_id, account = uuid_pair(80)
    add(store_path, profile_id, account, "https://one.example/reader/", "one")
    values = plan(store_path, profile_id)
    expect(Path(values["plan.product"]) == Path(store_path) / "profiles" / profile_id / "library.sqlite",
           "product path is not derived")
    expect(Path(values["plan.private"]) == Path(store_path) / "profiles" / profile_id / "private",
           "private path is not derived")
    expect(Path(values["plan.originals"]) == Path(store_path) / "profiles" / profile_id / "originals",
           "original path is not derived")
    expect(values["plan.generation"] == "1", "plan generation differs")
    expect(values["plan.account"] == account, "plan account differs")
    expect(values["plan.url"] == "https://one.example/reader/", "plan URL differs")
    process = run([PROBE, "verify", store_path, profile_id])
    expect(kv(process).get("prepare") == "OK" and kv(process).get("verify") == "OK",
           "a fresh plan did not verify")


def case_no_directory_before_activation():
    store_path = store("layout")
    profile_id, account = uuid_pair(81)
    add(store_path, profile_id, account, "https://one.example/reader/", "one")
    expect(not (Path(store_path) / "profiles").exists(),
           "add created the profile directory tree")
    plan(store_path, profile_id)
    profile_dir = Path(store_path) / "profiles" / profile_id
    for directory in (profile_dir, profile_dir / "private", profile_dir / "originals"):
        expect(directory.is_dir(), "missing directory %s" % directory)
        if not IS_WINDOWS:
            mode = stat.S_IMODE(directory.stat().st_mode)
            expect(mode == 0o700, "%s mode is %o" % (directory, mode))
    expect(not (profile_dir / "library.sqlite").exists(),
           "activation created a product library")


def case_unsafe_link_rejected():
    outside = ROOT / "link-outside"
    outside.mkdir(parents=True, exist_ok=True)

    linked_profiles = store("unsafe-profiles")
    profile_id, account = uuid_pair(82)
    add(linked_profiles, profile_id, account, "https://one.example/reader/", "one")
    make_link(outside, Path(linked_profiles) / "profiles")
    expect(activation_status(linked_profiles, profile_id) == "UNSAFE_PATH",
           "a linked profiles directory was accepted")

    linked_profile = store("unsafe-profile")
    profile_id, account = uuid_pair(83)
    add(linked_profile, profile_id, account, "https://one.example/reader/", "one")
    (Path(linked_profile) / "profiles").mkdir()
    make_link(outside, Path(linked_profile) / "profiles" / profile_id)
    expect(activation_status(linked_profile, profile_id) == "UNSAFE_PATH",
           "a linked profile directory was accepted")

    real_store = store("unsafe-store")
    profile_id, account = uuid_pair(84)
    add(real_store, profile_id, account, "https://one.example/reader/", "one")
    link_store = str(ROOT / "unsafe-store-link")
    make_link(real_store, link_store)
    expect(activation_status(link_store, profile_id) == "UNSAFE_PATH",
           "a linked store directory was accepted")


def case_hardlink_library_rejected():
    store_path = store("hardlink")
    profile_id, account = uuid_pair(85)
    add(store_path, profile_id, account, "https://one.example/reader/", "one")
    values = plan(store_path, profile_id)
    product = Path(values["plan.product"])
    product.write_bytes(b"SQLite format 3\x00" + b"\x00" * 96)
    os.link(product, str(product) + ".second")
    expect(activation_status(store_path, profile_id) == "UNSAFE_PATH",
           "a multiply linked product library was accepted")


def write_binding(store_path, profile_id, account, url, library=b"SQLite format 3\x00" + b"\x00" * 96):
    values = plan(store_path, profile_id)
    product = Path(values["plan.product"])
    product.write_bytes(library)
    Path(str(product) + ".sync-account").write_bytes(
        ("EXReader account v1\n%s\n%s\n" % (account, url)).encode("utf-8"))
    return values


def case_binding_missing_refused():
    store_path = store("binding-missing")
    profile_id, account = uuid_pair(86)
    add(store_path, profile_id, account, "https://one.example/reader/", "one")
    values = plan(store_path, profile_id)
    Path(values["plan.product"]).write_bytes(b"SQLite format 3\x00" + b"\x00" * 96)
    actual = activation_status(store_path, profile_id)
    expect(actual == "BINDING", "a non-empty unbound library -> %s" % actual)


def case_binding_mismatch_refused():
    store_path = store("binding-other")
    profile_id, account = uuid_pair(87)
    add(store_path, profile_id, account, "https://one.example/reader/", "one")
    write_binding(store_path, profile_id, uuid_pair(88)[1], "https://one.example/reader/")
    actual = activation_status(store_path, profile_id)
    expect(actual == "BINDING", "a library bound to another account -> %s" % actual)
    store_path = store("binding-url")
    profile_id, account = uuid_pair(89)
    add(store_path, profile_id, account, "https://one.example/reader/", "one")
    write_binding(store_path, profile_id, account, "https://two.example/reader/")
    actual = activation_status(store_path, profile_id)
    expect(actual == "BINDING", "a library bound to another URL -> %s" % actual)


def case_binding_match_accepted():
    store_path = store("binding-match")
    profile_id, account = uuid_pair(90)
    add(store_path, profile_id, account, "https://one.example/reader/", "one")
    write_binding(store_path, profile_id, account, "https://one.example/reader/")
    actual = activation_status(store_path, profile_id)
    expect(actual == "OK", "a library bound to this account -> %s" % actual)
    process = run([PROBE, "verify", store_path, profile_id])
    expect(kv(process).get("verify") == "OK", "a bound library did not verify")


def case_verify_tampered_plan():
    store_path = store("verify-tampered")
    profile_id, account = uuid_pair(91)
    add(store_path, profile_id, account, "https://one.example/reader/", "one")
    process = run([PROBE, "verify-tampered", store_path, profile_id])
    expect(kv(process).get("prepare") == "OK", "prepare failed")
    expect(kv(process).get("verify") == "ARGUMENT", "a tampered plan was accepted")


def case_verify_stale_plan():
    store_path = store("verify-stale")
    profile_id, account = uuid_pair(92)
    add(store_path, profile_id, account, "https://one.example/reader/", "one")
    process = run([PROBE, "verify-stale", store_path, profile_id, uuid_pair(93)[1]])
    expect(kv(process).get("prepare") == "OK", "prepare failed")
    expect(kv(process).get("remove") == "OK" and kv(process).get("readd") == "OK",
           "the plan profile could not be replaced")
    expect(kv(process).get("verify") == "CONFLICT", "a stale plan was accepted")


def case_verify_missing_profile():
    store_path = store("verify-missing")
    profile_id, account = uuid_pair(94)
    add(store_path, profile_id, account, "https://one.example/reader/", "one")
    process = run([PROBE, "verify-missing", store_path, profile_id])
    expect(kv(process).get("prepare") == "OK", "prepare failed")
    expect(kv(process).get("verify") == "NOT_FOUND", "a removed profile still verified")


def case_unicode_store_path():
    base = ROOT / "库 空间" / "账户 A"
    base.mkdir(parents=True, exist_ok=True)
    store_path = str(base)
    first, second = uuid_pair(95)[0], uuid_pair(96)[0]
    add(store_path, first, uuid_pair(95)[1], "https://one.example/reader/", "阅读器")
    add(store_path, second, uuid_pair(96)[1], "https://two.example/reader/", "📚 Bücher")
    loaded = load(store_path)
    expect(loaded["items"][0][3] == "阅读器" and loaded["items"][1][3] == "📚 Bücher",
           "a Unicode store path changed a name")
    expect(activation_status(store_path, first) == "OK", "activation in a Unicode path failed")


def case_secret_scan():
    store_path = store("secret-scan")
    add(store_path, uuid_pair(97)[0], uuid_pair(97)[1], "https://one.example/reader/", "one")
    add(store_path, uuid_pair(98)[0], uuid_pair(98)[1], "https://two.example/reader/", "two")
    raw = document_bytes(store_path).decode("utf-8")
    document_json = json.loads(raw)
    expect(set(document_json) == {"format", "version", "generation", "profiles"},
           "the document has unexpected top-level keys")
    for item in document_json["profiles"]:
        expect(set(item) == {"profile_id", "account_id", "root_url", "display_name"},
               "a profile has unexpected keys")
    for token in ("Authorization", "Bearer", "password", "secret", "Cookie", "token"):
        expect(token.lower() not in raw.lower(), "the document contains %r" % token)
    expect("@" not in raw and "?" not in raw, "the document contains URL userinfo or a query")
    patterns = [
        rb"-----BEGIN [A-Z ]*PRIVATE KEY",
        rb"AKIA[0-9A-Z]{16}",
        rb"ghp_[A-Za-z0-9]{20,}",
        rb"xox[baprs]-[A-Za-z0-9-]{10,}",
        rb"password\s*=\s*[\"'][^\"']+",
        rb"secret\s*=\s*[\"'][^\"']+",
    ]
    source_root = Path(__file__).resolve().parents[2] / "apps" / "reader" / "account-profiles"
    expect(source_root.is_dir(), "the package source tree is missing")
    for path in sorted(source_root.rglob("*")):
        if not path.is_file():
            continue
        data = path.read_bytes()
        for pattern in patterns:
            expect(re.search(pattern, data) is None,
                   "secret-like literal %r in %s" % (pattern, path))


def case_no_sdk_or_product_dependency():
    package = PREFIX / "lib" / "cmake" / "EXReaderAccountProfiles"
    expect((package / "EXReaderAccountProfilesConfig.cmake").is_file(), "package config missing")
    targets = (package / "EXReaderAccountProfilesTargets.cmake").read_text(encoding="utf-8")
    for token in ("EXReader::", "sqlite", "reader_session", "reader_catalog", "reader_revisions"):
        expect(token not in targets, "the installed target references %r" % token)
    expect((PREFIX / "include" / "reader_account_profiles.h").is_file(), "public header missing")
    libraries = sorted((PREFIX / "lib").glob("*reader_account_profiles*"))
    expect(bool(libraries), "no installed library")
    expect(all(path.stat().st_size > 0 for path in libraries), "an installed library is empty")


def case_cross_account_real_session():
    store_path = store("session")
    url = "https://127.0.0.1:9/reader/"
    id_a, account_a = uuid_pair(300)
    id_b, account_b = uuid_pair(301)
    add(store_path, id_a, account_a, url, "session A")
    add(store_path, id_b, account_b, url, "session B")
    process = run([SESSION, store_path, id_a, id_b], timeout=600)
    expect(process.returncode == 0, "session consumer failed: %s" % process.stderr[-800:])
    line = [row for row in process.stdout.splitlines() if row.strip().startswith("{")][-1]
    values = json.loads(line)
    expect(values["prepare_a"] == 0 and values["prepare_b"] == 0, "a plan was refused")
    expect(values["distinct"] is True, "the two accounts share a product path")
    expect(values["create_a"] == 0, "the first session was not created")
    expect(values["status_a"] == 5, "the first session status is %r" % values["status_a"])
    expect(values["binding_a"] is True,
           "the real session did not write the documented binding file")
    expect(values["verify_a"] == 0, "verify refused the binding the real session wrote")
    expect(values["borrow_create"] == 0, "the borrow session was not created")
    expect(values["borrow_status"] == 4,
           "the session did not refuse another account (%r)" % values["borrow_status"])
    expect(values["own_b_create"] == 0, "the second account session was not created")
    expect(values["binding_b"] is True, "the second account binding was not written")
    expect(values["verify_b"] == 0, "verify refused the second account binding")


CASES = (
    ("installed-c-consumer", case_installed_c_consumer),
    ("installed-cpp-session-consumer", case_installed_cpp_session_consumer),
    ("validate-unicode-names", case_validate_unicode_names),
    ("validate-utf8-refusals", case_validate_utf8_refusals),
    ("validate-uuid", case_validate_uuid),
    ("validate-url-rules", case_validate_url_rules),
    ("secret-url-refused", case_secret_url_refused),
    ("add-load-roundtrip-unicode", case_add_load_roundtrip_unicode),
    ("duplicate-id-and-pair", case_duplicate_id_and_pair),
    ("same-url-different-account-isolation", case_same_url_different_account_isolation),
    ("same-account-different-url-isolation", case_same_account_different_url_isolation),
    ("profile-count-limit", case_profile_count_limit),
    ("file-limit-lowered", case_file_limit_lowered),
    ("unknown-version-preserved", case_unknown_version_preserved),
    ("corrupt-format-preserved", case_corrupt_format_preserved),
    ("noncanonical-bytes-preserved", case_noncanonical_bytes_preserved),
    ("cancelled-add-before-lock", case_cancelled_add_before_lock),
    ("cancelled-save-preserves", case_cancelled_save_preserves),
    ("failed-save-preserves", case_failed_save_preserves),
    ("lock-timeout-and-recovery", case_lock_timeout_and_recovery),
    ("real-termination-releases-lock", case_real_termination_releases_lock),
    ("crash-before-rename-leftover", case_crash_before_rename_leftover),
    ("concurrent-processes-no-lost-update", case_concurrent_processes_no_lost_update),
    ("thread-reentrancy", case_thread_reentrancy),
    ("generation-conflict", case_generation_conflict),
    ("argument-and-struct-size", case_argument_and_struct_size),
    ("activation-derived-paths", case_activation_derived_paths),
    ("no-directory-before-activation", case_no_directory_before_activation),
    ("unsafe-link-rejected", case_unsafe_link_rejected),
    ("hardlink-library-rejected", case_hardlink_library_rejected),
    ("binding-missing-refused", case_binding_missing_refused),
    ("binding-mismatch-refused", case_binding_mismatch_refused),
    ("binding-match-accepted", case_binding_match_accepted),
    ("verify-tampered-plan", case_verify_tampered_plan),
    ("verify-stale-plan", case_verify_stale_plan),
    ("verify-missing-profile", case_verify_missing_profile),
    ("unicode-store-path", case_unicode_store_path),
    ("secret-scan", case_secret_scan),
    ("no-sdk-or-product-dependency", case_no_sdk_or_product_dependency),
    ("cross-account-real-session", case_cross_account_real_session),
)


def main():
    global PROBE, SESSION, WORKER, ROOT, PREFIX, PLATFORM
    parser = argparse.ArgumentParser()
    parser.add_argument("--probe", required=True)
    parser.add_argument("--session", required=True)
    parser.add_argument("--worker", required=True)
    parser.add_argument("--prefix", required=True)
    parser.add_argument("--work", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--platform", required=True)
    arguments = parser.parse_args()
    PROBE = arguments.probe
    SESSION = arguments.session
    WORKER = arguments.worker
    PREFIX = Path(arguments.prefix).resolve()
    ROOT = Path(arguments.work).resolve()
    PLATFORM = arguments.platform
    if ROOT.exists():
        shutil.rmtree(ROOT)
    ROOT.mkdir(parents=True, exist_ok=True)
    output = Path(arguments.output)
    output.mkdir(parents=True, exist_ok=True)
    expect(tuple(name for name, _ in CASES) == REQUIRED_CASES,
           "the case order differs from REQUIRED_CASES")
    for name, function in CASES:
        record(name, function)
    failed = [case for case in cases if not case["ok"]]
    result = {
        "package": "EXReaderAccountProfiles 0.1.0",
        "fixed_start": FIXED_START,
        "platform": PLATFORM,
        "source_sha": os.environ.get("GITHUB_SHA", ""),
        "run_id": os.environ.get("GITHUB_RUN_ID", ""),
        "attempt": os.environ.get("GITHUB_RUN_ATTEMPT", ""),
        "cloud": os.environ.get("GITHUB_ACTIONS") == "true",
        "accepted": not failed,
        "checks": len(cases),
        "required_checks": len(REQUIRED_CASES),
        "cases": cases,
        "limits": {
            "profiles": 32,
            "name_bytes": 128,
            "url_bytes": 1024,
            "store_path_bytes": 2048,
            "path_bytes": 2304,
            "file_bytes": 131072,
            "lock_timeout_ms": {"default": 2000, "maximum": 10000},
        },
        "sdk_changed": False,
        "schema_changed": False,
        "product_sql_written": False,
        "host_ui_accepted": False,
        "product_integration_accepted": False,
        "android_apple_accepted": False,
    }
    (output / "result.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n",
                                        encoding="utf-8")
    print(json.dumps({"accepted": result["accepted"], "platform": PLATFORM,
                      "cases": len(cases), "failed": len(failed)}), flush=True)
    raise SystemExit(0 if result["accepted"] else 1)


if __name__ == "__main__":
    main()