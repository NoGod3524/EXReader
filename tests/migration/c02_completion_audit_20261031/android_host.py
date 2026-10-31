# SPDX-License-Identifier: MIT
"""Decode actual Android app-UID snapshots from the retained original artifact."""
import io
import json
import posixpath
import re
import stat
import struct
import tarfile
import zipfile
from protocols import SDK, need, sha, json_value
from posix_protocols import audit_snapshot, observed_id, metadata
from gtk_host import sqlite_books
from gtk_snapshots import pending_negative_controls

PHASES = ("source-held", "source-released", "pending-owner-live", "pending-owner-dead",
          "pending-fresh-host-refused", "clean-after-independent-proof", "final")
BASE = "device/files/c02-evidence/"

def normalized(row):
    value = dict(row)
    for old, new in (("dev", "device"), ("ino", "inode"), ("nlink", "links"), ("size", "bytes")):
        value[new] = value.pop(old)
    value.setdefault("sha256", None)
    return value

def original_tar(files):
    captured = {}
    with tarfile.open(fileobj=io.BytesIO(files["app-raw.tar"]), mode="r:") as archive:
        members = archive.getmembers()
        need(len(members) <= 10000 and sum(item.size for item in members) <= 512*1024*1024,
             "android-bounded-app-uid-tar")
        names = set()
        for item in members:
            name = item.name
            need(name not in names and not name.startswith("/") and
                 all(part not in ("", ".", "..") for part in name.rstrip("/").split("/")) and
                 (item.isdir() or item.isfile()), "android-original-tar-path")
            names.add(name)
            if item.isfile():
                raw = archive.extractfile(item).read()
                need(len(raw) == item.size, "android-tar-member-size")
                captured["device/" + name] = raw
    need(captured == {name:raw for name,raw in files.items() if name.startswith("device/")},
         "android-extracted-bytes-equal-original-app-uid-tar")

def snapshot(files, report, phase):
    prefix = BASE + phase + "/"
    observation = json_value(files[prefix + "observations.json"])
    uid = report["uid"]
    need(observation["phase"] == phase and observation["euid"] == uid and
         observation["pid"] == report["pid"], "android-app-uid-snapshot-observer")
    scope = normalized(observation["scope_fd"])
    need(scope["path"] == report["scope"], "android-fixed-os-container")
    metadata(scope, uid, directory=True, private=False, scope=True)
    authority = report["scope"] + "/" + report["authority_relative"]
    library_path = report["scope"] + "/" + report["library_relative"]
    objects, virtual, observed = [], {}, {}
    for row in observation["objects"]:
        row = normalized(row)
        path = row["path"]
        need(path not in observed and path.startswith(report["scope"] + "/"),
             "android-unique-object-below-context")
        observed[path] = row
        directory = stat.S_ISDIR(row["mode"])
        metadata(row, uid, directory=directory, private=path == authority or path.startswith(authority + "/"))
        if not directory:
            need(row["raw"].startswith(phase + "/") and ".." not in row["raw"].split("/"),
                 "android-captured-relative-object")
            raw = files[BASE + row["raw"]]
            need(len(raw) == row["bytes"] and sha(raw) == row["sha256"], "android-raw-fstat-stream")
        if path == authority or path.startswith(authority + "/"):
            row = dict(row, path="." if path == authority else path[len(authority) + 1:])
            objects.append(row)
            if not directory:
                virtual["authority/" + row["path"]] = raw
    library = dict(observed[library_path], parent=observed[posixpath.dirname(library_path)],
                   archive_path="library-0.sqlite")
    virtual["library-0.sqlite"] = files[prefix + "library.db"]
    manifest = dict(schema="pc02-native-snapshot-v1", euid=uid, authority_path=authority,
                    scope=scope, objects=objects, libraries=[library])
    value = audit_snapshot(virtual, manifest)
    need(len(value["libraries"]) == 1, "android-single-real-library-route")
    return value, manifest, virtual, observed

def events(raw, uid):
    result = []
    for line in raw.decode("ascii").splitlines():
        match = re.fullmatch(r"(\d+)\.(\d{9}) pid=(\d+) uid=(\d+) event=([a-z0-9_]+) dev=(\d+) ino=(\d+)", line)
        need(match is not None, "android-native-event-format")
        seconds, nanos, pid, observed_uid, name, device, inode = match.groups()
        need(int(observed_uid) == uid and int(pid) > 0, "android-native-event-app-uid")
        result.append(dict(time=int(seconds)*1000000000+int(nanos), pid=int(pid),
                           event=name, target=(int(device), int(inode))))
    need(result and all(a["time"] <= b["time"] for a,b in zip(result,result[1:])),
         "android-native-event-monotonic-order")
    return result

def pending_descriptor(raw, row):
    need(len(raw) == 208 and raw[72] == raw[137] == raw[202] == 0 and raw[203:] == bytes(5),
         "android-exact-native-pending-structure")
    need(struct.unpack_from("<Q", raw)[0] == row["generation"] and
         raw[8:72].decode("ascii") == row["seal"] and
         raw[73:137].decode("ascii") == row["manifest"] and
         raw[138:202].decode("ascii") == row["input"], "android-exact-pending-from-raw-state")

def loadable_elf(raw):
    need(len(raw) >= 64 and raw[:7] == b"\x7fELF\x02\x01\x01", "android-elf64-little-endian")
    need(struct.unpack_from("<H", raw, 18)[0] == 62 and
         struct.unpack_from("<H", raw, 52)[0] == 64, "android-qualified-x86-64-elf")
    offset = struct.unpack_from("<Q", raw, 32)[0]
    size, count = struct.unpack_from("<HH", raw, 54)
    need(size == 56 and 0 < count <= 128 and offset + size*count <= len(raw), "android-elf-program-table")
    normalized = bytearray(raw)
    normalized[40:48] = bytes(8)
    normalized[58:64] = bytes(6)
    headers, loads = [], []
    for index in range(count):
        header = struct.unpack_from("<IIQQQQQQ", raw, offset + size*index)
        kind, flags, start, address, physical, length, memory, alignment = header
        headers.append(header)
        if kind == 1:
            need(length <= memory and start + length <= len(raw), "android-bounded-elf-load")
            loads.append((flags,address,physical,length,memory,alignment,sha(normalized[start:start+length])))
    need(loads, "android-elf-loads-present")
    return bytes(normalized[:64]), headers, loads

def apk_provider(files):
    with zipfile.ZipFile(io.BytesIO(files["app-debug.apk"])) as archive:
        names = archive.namelist()
        need(len(names) == len(set(names)), "android-apk-unique-paths")
        provider = archive.read("lib/x86_64/libexreader.so")
        host = archive.read("lib/x86_64/libexreader_host.so")
    need(provider.startswith(b"\x7fELF") and host.startswith(b"\x7fELF") and
         files["libexreader_host.so"].startswith(b"\x7fELF"), "android-actual-apk-native-libraries")
    installed = json_value(files["sdk-installed.json"])
    candidates = [row for row in installed if row["path"] == "lib/libexreader.so"]
    need(len(candidates) == 1, "android-installed-shared-sdk-inventory")
    item = candidates[0]
    provider_bound = item["bytes"] == len(provider) and item["sha256"] == sha(provider)
    if "sdk-libexreader.installed.so" in files:
        installed_raw = files["sdk-libexreader.installed.so"]
        need(len(installed_raw) == item["bytes"] and sha(installed_raw) == item["sha256"],
             "android-retained-installed-sdk-bytes")
        need(loadable_elf(installed_raw) == loadable_elf(provider), "android-packaged-sdk-loadable-byte-equality")
        provider_bound = True
    symbols = files["host-defined-symbols.txt"].decode().splitlines()
    names = {line.split()[-1] for line in symbols if line.split()}
    need("exr_library_open" not in names and
         {"pc02_open_in", "pc02_check", "pc02_close", "pc02_sdk_enroll_in"} <= names and
         b"libexreader.so" in files["host-dynamic.txt"], "android-one-shared-sdk-and-native-admission")
    return dict(installed_sdk_byte_binding=provider_bound,
                apk_sha256=sha(files["app-debug.apk"]), shared_sdk_sha256=sha(provider),
                jni_sha256=sha(host))

def audit_android_host(files, spec, source, expected_cases, original, fixture):
    receipt = json_value(files["receipt.json"])
    build = json_value(files["build-receipt.json"])
    for value in (receipt, build):
        need(value["source"] == source and str(value["run"]) == str(spec["run"]) and
             str(value["attempt"]) == str(spec["attempt"]), "android-qualified-producer")
        need(value["actual_android_host"] is True and value["actual_migration"] is False,
             "android-host-only-scope")
    need(build["frozen_sdk"] == SDK and build["sdk_version"] == "3.42.0" and
         receipt["actual_sdk"] is True and receipt["full_c02_acceptance"] is False,
         "android-frozen-sdk-scope")
    original_tar(files)
    report = json_value(files[BASE + "device-report.json"])
    uid = report["uid"]
    need(type(uid) is int and uid >= 10000 and uid == report["euid"] == receipt["uid"] and
         type(report["pid"]) is int and report["pid"] > 0, "android-actual-app-uid")
    need(report["schema"] == 1 and report["actual_sdk"] is True and report["actual_android_host"] is True and
         report["actual_migration"] is False and report["failure"] is None and
         report["authority_relative"] == "no_backup/c02-admission" and
         report["library_relative"] == "files/library.db", "android-production-context-factory")
    rows = report["cases"]
    need(len(rows) == len(expected_cases) == receipt["cases"] == report["passed"] == 14 and
         {row["name"] for row in rows} == expected_cases and all(row["passed"] is True for row in rows) and
         receipt["checks"] == report["checks"] and report["checks"] >= 361 and
         b"OK (14 tests)" in files["instrumentation.stdout"], "android-original-14-live-cases")
    decoded, snapshots, all_events = {}, {}, {}
    for phase in PHASES:
        value, manifest, virtual, observed = snapshot(files, report, phase)
        library = value["libraries"][0]
        expected = "pending" if phase.startswith("pending-") else "clean"
        count = 2 if expected == "pending" else (3 if phase in PHASES[-2:] else 1)
        need(library["status"] == expected and len(library["history"]) == count,
             "android-native-exact-phase:" + phase)
        books = sqlite_books(virtual["library-0.sqlite"])
        need(len(books) == 1 and type(books[0][0]) is int and books[0][0] > 0 and
             bytes(books[0][2]) == original, "android-independent-sqlite-original")
        event_raw = files[BASE + phase + "/native-events.log"]
        all_events[phase] = events(event_raw, uid)
        decoded[phase] = value
        snapshots[phase] = (manifest, virtual)
        if expected == "pending":
            pending = library["history"][-1]
            need(pending["manifest"] == fixture["manifest"] and pending["input"] == fixture["input"],
                 "android-source-bound-debug-pending")
            pending_descriptor(files[BASE + phase + "/pending-descriptor.bin"], pending)
        if count == 3:
            need(library["history"][-1]["terminal"] == fixture["terminal"],
                 "android-independent-proof-terminal")
    initial = decoded[PHASES[0]]
    first = initial["libraries"][0]
    for phase, value in decoded.items():
        library = value["libraries"][0]
        need(value["root"] == initial["root"] and library["route"] == first["route"] and
             library["observed_target"] == first["observed_target"] and
             library["binding"]["lease"] == first["binding"]["lease"] and
             library["binding"]["state"] == first["binding"]["state"] and
             library["history"][0] == first["history"][0], "android-same-native-authority-custody")
        if phase not in PHASES[-2:]:
            need(library["binding"] == first["binding"], "android-pending-never-promotes-grant")
        if phase.startswith("pending-"):
            need(library["history"] == decoded["pending-owner-live"]["libraries"][0]["history"],
                 "android-process-death-retains-exact-pending")
    need(decoded["final"]["libraries"] == decoded["clean-after-independent-proof"]["libraries"],
         "android-old-descriptor-replay-preserves-clean")
    held, released = all_events["source-held"], all_events["source-released"]
    actor_pids = {row["pid"] for row in held if row["event"] == "source_open" and row["pid"] != report["pid"]}
    need(len(actor_pids) == 1, "android-source-owned-by-independent-app-process")
    actor_pid = actor_pids.pop()
    actor_held = [row["event"] for row in held if row["pid"] == actor_pid]
    actor_released = [row["event"] for row in released if row["pid"] == actor_pid]
    need("sdk_close" in actor_held and "source_open" in actor_held and "lease_close" not in actor_held and
         "source_release_end" not in actor_held and
         actor_released.index("source_open") < actor_released.index("sdk_close") <
         actor_released.index("source_release_begin") < actor_released.index("source_release_end") <
         actor_released.index("lease_close"), "android-source-retains-shared-lease-past-primary-sdk-close")
    main_events = [row["event"] for row in held if row["pid"] == report["pid"]]
    need(main_events.index("shared_acquired") < main_events.index("sdk_open") < main_events.index("catalog_open"),
         "android-real-catalog-after-native-admission")
    for left,right in zip(PHASES, PHASES[1:]):
        need(all_events[right][:len(all_events[left])] == all_events[left], "android-native-event-prefix-custody")
    pending_events = all_events["pending-owner-live"]
    owner = [row for row in pending_events if row["event"] == "native_phase_1102"]
    need(len(owner) == 1 and owner[0]["pid"] not in (actor_pid, report["pid"]),
         "android-durable-pending-before-separate-owner-reply")
    before = all_events["pending-owner-dead"]
    after = all_events["pending-fresh-host-refused"]
    need(not any(row["event"] in ("sdk_open", "catalog_open") for row in after[len(before):]),
         "android-fresh-actual-activity-refuses-before-sdk-and-catalog")
    need(any(row["event"] == "native_phase_1202" for row in all_events["final"]) and
         any(row["event"] == "native_phase_1205" for row in all_events["final"]),
         "android-durable-clean-and-binding")
    return dict(capabilities=["android-actual-app-uid", "android-fixed-context-fd",
                              "android-native-authority-byte-decoder", "android-original-sqlite",
                              "android-native-source-final-owner", "android-process-death-pending"],
                runtime_cases=14, checks=report["checks"], app_uid=uid, native_snapshots=decoded,
                binaries=apk_provider(files), actual_migration=False)

def android_negative_controls(files, output):
    report = json_value(files[BASE + "device-report.json"])
    _, manifest, raw, _ = snapshot(files, report, "pending-owner-dead")
    prefix = "snapshots/pending/"
    selected = {prefix + name:data for name,data in raw.items()}
    selected[prefix + "native-identities.json"] = (json.dumps(manifest) + "\n").encode()
    return pending_negative_controls(selected, "", output)
