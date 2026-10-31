# SPDX-License-Identifier: MIT
"""Independent Apple app-UID authority, actual SQLite and retained bundle audit."""
import io
import json
import zipfile
import plistlib
import posixpath
import re
import stat
import struct
from protocols import SDK, need, sha, json_value
from posix_protocols import anchor, binding, states, metadata, observed_id, route, decode_route
from gtk_host import sqlite_books
from gtk_snapshots import pending_negative_controls
from macho_sdk import bind_sdk, sdk_negative_variants

PHASES = ("enrollment-crash", "pending-crash", "baseline", "fresh", "fresh-preserve")
CASES = {"model-admission-before-catalog", "explicit-enrollment-recovery", "unknown-check-never-creates",
         "clean-admits-before-sdk", "pending-refuses-before-sdk", "missing-binding-refuses-before-sdk",
         "replaced-target-refuses-before-sdk", "last-borrow-blocks-owner",
         "final-borrow-release-allows-owner", "independent-host-library-reopen",
         "fixed-last-owner", "publication-last-owner", "fresh-process-pending-refusal",
         "fresh-preserves-existing-library-and-catalog"}

def normalized(row, path):
    value = dict(row, path=path)
    if "nlink" in value:
        value["links"] = value.pop("nlink")
    if "size" in value:
        value["bytes"] = value.pop("size")
    value.setdefault("sha256", None)
    return value

def capture(files, phase, uid, home):
    manifest = json_value(files[phase + "-native-map.json"])
    need(manifest["canonical_home"] == home, "apple-fixed-native-home")
    scope = normalized(manifest["scope"], home)
    need(scope["euid"] == uid, "apple-native-map-observer-uid")
    metadata(scope, uid, directory=True, private=False, scope=True)
    roots = {"authority":home + "/.exreader-c02-admission",
             "libraries":home + "/Library/Application Support/EXReaderC02Review",
             "model":home + "/Library/Application Support/EXReader"}
    trees, retained = {}, set()
    for mapping in manifest["mappings"]:
        kind = mapping["kind"]
        need(kind in roots and kind not in trees and mapping["actual_root"] == roots[kind] and
             mapping["archive_root"] == "native/" + phase + "/" + kind, "apple-exact-native-mapping")
        prefix = mapping["archive_root"] + "/"
        objects, raw = {}, {}
        for relative, recorded in mapping["fstat"].items():
            need(relative == "." or (not relative.startswith("/") and
                 posixpath.normpath(relative) == relative and
                 all(part not in ("", ".", "..") for part in relative.split("/"))),
                 "apple-unambiguous-native-relative-path")
            path = roots[kind] + ("" if relative == "." else "/" + relative)
            row = normalized(recorded, path)
            need(row["euid"] == uid, "apple-fstat-real-app-uid")
            directory = stat.S_ISDIR(row["mode"])
            metadata(row, uid, directory=directory, private=kind == "authority")
            objects[relative] = row
            if not directory:
                archive = prefix + relative
                data = files[archive]
                need(len(data) == row["bytes"] and sha(data) == row["sha256"],
                     "apple-fstat-matches-retained-original-bytes")
                raw[relative] = data
                retained.add(archive)
        need("." in objects and stat.S_ISDIR(objects["."]["mode"]), "apple-captured-tree-root")
        trees[kind] = dict(root=roots[kind], objects=objects, raw=raw)
    need(retained == {name for name in files if name.startswith("native/" + phase + "/")},
         "apple-complete-raw-native-mapping")
    need("authority" in trees and "libraries" in trees, "apple-required-authority-and-sdk-trees")
    authority = trees["authority"]
    objects, raw = authority["objects"], authority["raw"]
    native = anchor(raw["authority"])
    root_id = observed_id(objects["."])
    need(native["root"] == root_id and native["registry"] == observed_id(objects["registry.lock"]) and
         native["identity"] == observed_id(objects["authority"]) and
         raw["registry.lock"] == b"PC02-REGISTRY\n\0\0", "apple-authority-native-root-self-registry")
    return dict(scope=scope, trees=trees, root=root_id)

def library(captured, name):
    tree = captured["trees"]["model" if name == "model" else "libraries"]
    relative = "library.sqlite" if name == "model" else name + "/library.sqlite"
    parent = "." if name == "model" else name
    return dict(tree["objects"][relative], parent=tree["objects"][parent]), tree["raw"][relative]

def decode_library(captured, name, expected, uid):
    authority = captured["trees"]["authority"]
    objects, raw = authority["objects"], authority["raw"]
    current, database = library(captured, name)
    key = route(observed_id(current["parent"]), current["path"])
    need(key in objects, "apple-native-library-route")
    metadata(objects[key], uid, directory=True)
    present = {path[len(key)+1:] for path in objects if path.startswith(key + "/")}
    allowed = {"lease", "state", "enrollment"} | ({"binding-preserved"} if expected == "missing-binding" else
              set() if expected == "incomplete-enrollment" else {"binding"})
    need(present == allowed, "apple-exact-route-member-inventory")
    history = states(raw[key + "/state"])
    enrollment = binding(raw[key + "/enrollment"])
    need(enrollment["root"] == captured["root"] and enrollment["parent"] == observed_id(current["parent"]) and
         enrollment["route"] == key and enrollment["generation"] == 0 and enrollment["identity"] == (0,0) and
         enrollment["state"] == observed_id(objects[key + "/state"]) and
         enrollment["lease"] == observed_id(objects[key + "/lease"]) and
         enrollment["grant"] == history[0]["seal"] and enrollment["target"] == history[0]["target"],
         "apple-original-enrollment-native-custody")
    if expected == "incomplete-enrollment":
        need(len(history) == 1 and observed_id(current) == enrollment["target"] and
             raw[key + "/lease"] == b"", "apple-durable-unbound-initial-state")
        return dict(name=name, route=key, status=expected, history=history,
                    enrollment=enrollment, observed_target=observed_id(current)), database
    grant_name = "binding-preserved" if expected == "missing-binding" else "binding"
    grant = raw[key + "/" + grant_name]
    observed = {part:objects[key + "/" + (grant_name if part == "binding" else part)]
                for part in ("binding", "state", "lease")}
    target = current
    if expected == "replaced-target":
        tree = captured["trees"]["libraries"]
        old = tree["objects"][name + "/library.sqlite.retained"]
        need(observed_id(old) != observed_id(current) and tree["raw"][name + "/library.sqlite.retained"] == database,
             "apple-same-bytes-different-native-target")
        target = dict(old, path=current["path"], parent=current["parent"])
    decoded = decode_route(grant, raw[key + "/state"], observed, target, captured["root"], uid)
    need(decoded["status"] == ("pending" if expected == "pending" else "clean"),
         "apple-raw-native-library-state")
    need(decoded["binding"]["generation"] == 0 and decoded["binding"]["grant"] == history[0]["seal"] and
         len(history) == (2 if expected == "pending" else 1), "apple-exact-original-generation")
    decoded.update(name=name, path=current["path"], status=expected, observed_target=observed_id(current))
    return decoded, database

def macho_sdk(raw):
    need(len(raw) >= 32 and raw[:4] == b"\xcf\xfa\xed\xfe", "apple-actual-macho64")
    count, size = struct.unpack_from("<II", raw, 16)
    need(0 < count < 4096 and 32 + size <= len(raw), "apple-bounded-macho-commands")
    offset, libraries = 32, []
    for _ in range(count):
        kind, length = struct.unpack_from("<II", raw, offset)
        need(length >= 8 and offset + length <= 32 + size, "apple-macho-command-bounds")
        if kind in (0xc, 0x80000018, 0x8000001f):
            need(length >= 24, "apple-complete-dylib-load-command")
            name_offset = struct.unpack_from("<I", raw, offset+8)[0]
            need(24 <= name_offset < length, "apple-macho-dylib-name-offset")
            text = raw[offset+name_offset:offset+length].split(b"\0",1)[0].decode()
            if "libexreader" in text:
                libraries.append(text)
        offset += length
    need(offset == 32 + size and len(libraries) == 1 and libraries[0].startswith("@rpath/libexreader") and
         libraries[0].endswith(".dylib"), "apple-one-actual-shared-sdk-provider")
    return posixpath.basename(libraries[0])

def bundles(files, receipt, platform, source, spec):
    mobile = platform == "iphonesimulator"
    paths = {"production":"bundles/production.app/" + ("EXReader" if mobile else "Contents/MacOS/EXReader"),
             "runtime":"bundles/runtime.app/" + ("C02Runtime" if mobile else "Contents/MacOS/C02Runtime")}
    sdk_identity = json_value(files["installed/c02-sdk-identity.json"])
    need(receipt["original_sdk_archive_prefix"] == "installed-sdk/" and
         files["installed-sdk/c02-sdk-identity.json"] == files["installed/c02-sdk-identity.json"],
         "apple-original-installed-sdk-identity")
    sdk_copies, sdk_bindings = [], {}
    for kind,path in paths.items():
        need(sha(files[path]) == receipt["binaries"][kind], "apple-qualified-bundle-binary-sha")
        provider = macho_sdk(files[path])
        app = "bundles/" + kind + ".app/"
        frameworks = app + ("Frameworks/" if mobile else "Contents/Frameworks/")
        sdk_raw = files[frameworks + provider]
        expected = sdk_identity["files"]["lib/" + provider]
        original = files["installed-sdk/lib/" + provider]
        need(sha(original) == expected, "apple-original-installed-sdk-byte-binding")
        sdk_bindings[kind] = dict(provider=provider, **bind_sdk(original, sdk_raw))
        sdk_copies.append(sdk_raw)
        plist = plistlib.loads(files[app + ("Info.plist" if mobile else "Contents/Info.plist")])
        need(plist["EXRSourceSHA"] == source, "apple-bundle-qualified-source")
        if kind == "runtime":
            need(str(plist["EXRRun"]) == str(spec["run"]) and
                 str(plist["EXRAttempt"]) == str(spec["attempt"]), "apple-runtime-bundle-producer")
    need(sdk_copies[0] == sdk_copies[1], "apple-both-bundles-same-sdk")
    build = json_value(files["build.json"])
    need(build["source_sha"] == source and build["sdk_version"] == "3.42.0" and
         build["c02_admission"] is True and build["c02_installed_files"], "apple-production-installed-admission")
    for name,digest in build["c02_installed_files"].items():
        need(sha(files["installed/" + name]) == digest, "apple-actual-installed-c02-byte-binding")
    for kind in ("sdk", "product"):
        identity = json_value(files["installed/c02-" + kind + "-identity.json"])
        need(identity["source"] == source and identity["frozen_sdk"] == SDK and
             identity["target"] == platform and str(identity["run"]) == str(spec["run"]) and
             str(identity["attempt"]) == str(spec["attempt"]), "apple-installed-provider-identity")
    symbols = files["runtime-symbols.txt"]
    need(b"_pc02_check" in symbols and b"_pc02_close" in symbols and
         (b"_pc02_scope_create" if mobile else b"_pc02_sdk_open_user") in symbols,
         "apple-executed-runtime-native-owner-symbols")
    return dict(production=sha(files[paths["production"]]), runtime=sha(files[paths["runtime"]]),
                installed_sdk_bindings=sdk_bindings)

def audit_apple_host(files, spec, source, report):
    receipt = json_value(files["receipt.json"])
    uid, home = receipt["actual_app_uid"], receipt["scope_home"]
    need(type(uid) is int and uid > 0 and receipt["passed"] is True and
         receipt["runtime_cases"] == 14 and receipt["producer_native_map"] == "*-native-map.json",
         "apple-actual-app-uid-receipt")
    rows = report["cases"] + report["extended_cases"]
    need(len(rows) == len({row["name"] for row in rows}) == 14 and {row["name"] for row in rows} == CASES and
         all(row["passed"] is True for row in rows), "apple-all-original-runtime-cases")
    phases = report["phases"]
    need([phase["phase"] for phase in phases] == list(PHASES), "apple-all-actual-native-phases")
    captures, decoded, by_name = {}, {}, {row["name"]:row["observation"] for row in rows}
    expected = {"enrollment":"clean", "pending":"pending", "model":"clean", "clean":"clean",
                "missing-binding":"missing-binding", "replacement":"replaced-target",
                "borrow":"clean", "fixed":"clean", "publication":"clean"}
    phase_rows = []
    for phase in phases:
        name = phase["phase"]
        captured = capture(files, name, uid, home)
        captures[name] = captured
        cases = ({"enrollment":"incomplete-enrollment"} if name == "enrollment-crash" else
                 {"enrollment":"incomplete-enrollment","pending":"pending"} if name == "pending-crash" else expected)
        decoded[name] = {}
        for case,status in cases.items():
            value, database = decode_library(captured, case, status, uid)
            decoded[name][case] = value
            books = sqlite_books(database)
            if case in ("borrow", "fixed", "publication"):
                need(len(books) == 1 and type(books[0][0]) is int and books[0][0] > 0,
                     "apple-actual-imported-sdk-book")
                original = (b"C02 original UTF-8 text.\n" if case == "borrow" else
                            files["bundles/runtime.app/" + ("" if spec["platform"] == "iphonesimulator" else "Contents/Resources/") +
                                  ("Sample.pdf" if case == "fixed" else "Sample.epub")])
                need(bytes(books[0][2]) == original, "apple-independent-original-content")
            else:
                need(not books, "apple-independently-empty-sdk-original")
        authority = captured["trees"]["authority"]
        routes = {key for key in authority["objects"] if "/" not in key} - {".","authority","registry.lock"}
        need(routes == {value["route"] for value in decoded[name].values()}, "apple-all-native-routes-classified")
        if name.endswith("-crash"):
            barrier = phase["barrier"]
            need(barrier == json_value(files["runtime/" + name + "/" + name + "-barrier.json"]) and
                 barrier["phase"] == (1002 if name == "enrollment-crash" else 1102) and
                 barrier["uid"] == uid and barrier["source"] == source and barrier["pid"] > 0,
                 "apple-original-killed-app-barrier")
            need(phase["kill_method"] == ("simctl terminate" if spec["platform"] == "iphonesimulator" else "SIGKILL") and
                 (spec["platform"] == "iphonesimulator" or phase["exit"] == -9),
                 "apple-actual-process-death-method")
        else:
            actual = phase["report"]
            need(actual == json_value(files["runtime/" + name + "/" + name + ".json"]) and
                 actual["phase"] == name and actual["complete"] is True and actual["passed"] is True and
                 actual["source"] == source and str(actual["run"]) == str(spec["run"]) and
                 str(actual["attempt"]) == str(spec["attempt"]) and actual["platform"] == spec["platform"] and
                 actual["actual_sdk"] is True and phase["exit"] == 0 and
                 actual["authority"] == authority["root"], "apple-original-process-phase-report")
            phase_rows.extend(actual["cases"])
            emitted = [json_value(line.split("C02-HOST-OBS ",1)[1])
                       for line in files[name + ".log"].decode().splitlines() if "C02-HOST-OBS " in line]
            need(emitted == [row["observation"] for row in actual["cases"]],
                 "apple-actual-process-stdout-observations")
            need(set(actual["native"]) == set(authority["objects"]), "apple-runtime-and-driver-native-inventory")
            for key,raw_row in actual["native"].items():
                row = normalized(raw_row, authority["objects"][key]["path"])
                need(all(row[field] == authority["objects"][key][field]
                         for field in ("device","inode","mode","uid","links","bytes","sha256")),
                     "apple-app-and-independent-driver-fstat-agree")
            if spec["platform"] == "iphonesimulator" and name != "fresh-preserve":
                need(actual["scope_factory"], "apple-real-os-scope-factory-observations")
                for scope in actual["scope_factory"]:
                    need(scope["canonical_home"] == home and scope["uid"] == scope["euid"] == uid and
                         scope["fd_cloexec"] is True and
                         (scope["device"],scope["inode"]) == (scope["expected_device"],scope["expected_inode"]) ==
                         observed_id(captured["scope"]), "apple-os-attested-context-fd-identity")
    need(sorted(phase_rows,key=lambda row:row["name"]) == sorted(rows,key=lambda row:row["name"]),
         "apple-complete-report-to-actual-phase-binding")
    baseline = captures["baseline"]
    for name in PHASES:
        need(captures[name]["root"] == baseline["root"] and
             observed_id(captures[name]["scope"]) == observed_id(baseline["scope"]), "apple-same-authority-across-processes")
    for name in ("fresh", "fresh-preserve"):
        need(captures[name]["trees"]["authority"] == baseline["trees"]["authority"],
             "apple-fresh-refusal-preserves-exact-native-state")
        for database in ("library.sqlite", "reader-catalog.db"):
            need(captures[name]["trees"]["model"]["raw"][database] == baseline["trees"]["model"]["raw"][database],
                 "apple-fresh-preserves-actual-sdk-and-catalog-bytes")
    pending = decoded["baseline"]["pending"]["history"][-1]
    need(pending["manifest"] == sha(("host-admission:" + source).encode()) and
         pending["input"] == sha(("host-input:" + source).encode()) and
         all(decoded[name]["pending"] == decoded["baseline"]["pending"]
             for name in ("pending-crash", "fresh", "fresh-preserve")), "apple-original-pending-never-auto-clean")
    need(by_name["fresh-process-pending-refusal"]["pid"] != by_name["pending-refuses-before-sdk"]["pid"],
         "apple-fresh-process-pending-refusal")
    for name,observation in by_name.items():
        need(observation["name"] == name and observation["source"] == source and
             str(observation["run"]) == str(spec["run"]) and str(observation["attempt"]) == str(spec["attempt"]) and
             observation["uid"] == uid and observation["pid"] > 0, "apple-app-observation-provenance")
    for name in ("unknown-check-never-creates", "replaced-target-refuses-before-sdk",
                 "fresh-preserves-existing-library-and-catalog"):
        need(by_name[name]["admitted"] is False and by_name[name]["sdk_open_count"] == 0,
             "apple-all-extra-before-sdk-refusals")
    unknown_parent = baseline["trees"]["libraries"]["objects"]["unknown"]
    need("unknown/library.sqlite" not in baseline["trees"]["libraries"]["objects"] and
         route(observed_id(unknown_parent),unknown_parent["path"] + "/library.sqlite") not in
         baseline["trees"]["authority"]["objects"], "apple-unknown-check-created-no-library-or-registration")
    preserved = by_name["fresh-preserves-existing-library-and-catalog"]["before_sha256"]
    need(preserved == [sha(baseline["trees"]["model"]["raw"][name])
                       for name in ("library.sqlite","reader-catalog.db")], "apple-original-fresh-preserve-hashes")
    return dict(capabilities=["apple-actual-app-uid","apple-native-authority-byte-decoder",
                              "apple-original-sdk-and-catalog","apple-real-enrollment-and-pending-crashes",
                              "apple-document-publication-fixed-final-owner","apple-production-bundle",
                              "apple-installed-shared-sdk-byte-binding"],
                runtime_cases=14, native_snapshots=decoded, app_uid=uid,
                binaries=bundles(files,receipt,spec["platform"],source,spec), actual_migration=False)

def apple_negative_controls(files, output):
    receipt = json_value(files["receipt.json"])
    uid, home = receipt["actual_app_uid"], receipt["scope_home"]
    captured = capture(files, "pending-crash", uid, home)
    decoded, database = decode_library(captured, "pending", "pending", uid)
    key = decoded["route"]
    authority = captured["trees"]["authority"]
    selected = {name:row for name,row in authority["objects"].items()
                if name in (".","authority","registry.lock",key) or name.startswith(key + "/")}
    objects = [dict(row,path=name) for name,row in selected.items()]
    target, _ = library(captured, "pending")
    target["archive_path"] = "library-0.sqlite"
    manifest = dict(schema="pc02-native-snapshot-v1",euid=uid,authority_path=authority["root"],
                    scope=captured["scope"],objects=objects,libraries=[target])
    prefix = "snapshots/pending/"
    virtual = {prefix + "authority/" + name:data for name,data in authority["raw"].items() if name in selected}
    virtual[prefix + "library-0.sqlite"] = database
    virtual[prefix + "native-identities.json"] = (json.dumps(manifest) + "\n").encode()
    return (pending_negative_controls(virtual,"",output) +
            sdk_repacked_controls(files,receipt,output / "sdk"))

def sdk_repacked_controls(files, receipt, output):
    executables = [path for path in ("bundles/production.app/Contents/MacOS/EXReader",
                                    "bundles/production.app/EXReader") if path in files]
    need(len(executables) == 1, "apple-sdk-control-one-production-bundle")
    executable = executables[0]
    provider = macho_sdk(files[executable])
    frameworks = "Contents/Frameworks/" if "/Contents/" in executable else "Frameworks/"
    original_path = "installed-sdk/lib/" + provider
    bundled_path = "bundles/production.app/" + frameworks + provider
    original, bundled = files[original_path], files[bundled_path]
    expected_reasons = {
        "sdk-code-byte":"macho-sdk-cd-page-hashes",
        "sdk-code-byte-rehashed":"macho-sdk-resigning-changed-payload",
        "sdk-linkedit-payload-rehashed":"macho-sdk-resigning-changed-payload",
        "sdk-original-payload-rehashed":"macho-sdk-resigning-changed-payload",
        "sdk-forged-page-hash":"macho-sdk-cd-page-hashes",
        "sdk-signature-out-of-bounds":"macho-sdk-signature-file-range",
        "sdk-linkedit-out-of-bounds":"macho-sdk-signature-tail-linkedit-size",
        "sdk-linkedit-vmsize-rehashed":"macho-sdk-signature-tail-linkedit-size",
    }
    output.mkdir(parents=True, exist_ok=True)
    controls = []
    for variant in sdk_negative_variants(original, bundled):
        name = variant["name"]
        need(name in expected_reasons, "apple-known-sdk-negative")
        context = dict(schema="apple-sdk-original-byte-negative-v1", name=name,
                       source=receipt["source"],run=receipt["run"],attempt=receipt["attempt"],
                       original_path=original_path,bundled_path=bundled_path,
                       original_baseline_sha256=sha(original),bundled_baseline_sha256=sha(bundled))
        packet = {"original-sdk.dylib":variant["original"],"bundled-sdk.dylib":variant["bundled"],
                  "control.json":(json.dumps(context,indent=2)+"\n").encode()}
        packet["file-hashes.json"] = (json.dumps([
            dict(path=key,bytes=len(value),sha256=sha(value))
            for key,value in sorted(packet.items())],indent=2)+"\n").encode()
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer,"w",zipfile.ZIP_DEFLATED) as archive:
            for key,value in sorted(packet.items()):
                archive.writestr(key,value)
        raw = buffer.getvalue()
        (output / (name + ".zip")).write_bytes(raw)
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            need(archive.namelist() == sorted(packet), "apple-sdk-negative-zip-inventory")
            decoded = {key:archive.read(key) for key in archive.namelist()}
        for row in json_value(decoded["file-hashes.json"]):
            need(len(decoded[row["path"]]) == row["bytes"] and sha(decoded[row["path"]]) == row["sha256"],
                 "apple-sdk-negative-rehashed-original-files")
        need(json_value(decoded["control.json"]) == context, "apple-sdk-negative-exact-context")
        try:
            bind_sdk(decoded["original-sdk.dylib"],decoded["bundled-sdk.dylib"])
        except ValueError as error:
            reason = str(error)
            need(reason == expected_reasons[name], "apple-sdk-negative-expected-refusal:" + name + ":" + reason)
        else:
            raise ValueError("accepted-repacked-apple-sdk-negative:" + name)
        controls.append(dict(name=name,rejected=True,reason=reason,bytes=len(raw),sha256=sha(raw),
                             scope="repacked-original-sdk-byte-pair"))
    need(len(controls) == len(expected_reasons), "apple-all-sdk-negative-controls")
    return controls
