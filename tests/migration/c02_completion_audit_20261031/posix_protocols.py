# SPDX-License-Identifier: MIT
"""Independent POSIX authority decoder. Never loads the producer's native library."""
import posixpath
import re
import stat
import struct
from protocols import need, sha, hexadecimal, integer, json_value

ZERO = "0" * 64

def u64(data, offset):
    need(offset >= 0 and offset + 8 <= len(data), "posix-integer-bounds")
    return struct.unpack_from("<Q", data, offset)[0]

def native_id(data, offset):
    return (u64(data, offset), u64(data, offset + 8))

def digest_field(data, offset):
    raw = data[offset:offset + 64]
    need(len(raw) == 64 and all(c in b"0123456789abcdef" for c in raw), "posix-canonical-sha")
    return raw.decode("ascii")

def sealed(data, magic, prefix):
    need(len(data) == prefix + 64 and data[:8] == magic, "posix-record-size-magic")
    digest = digest_field(data, prefix)
    need(sha(data[:prefix]) == digest, "posix-record-seal")
    return digest

def anchor(data):
    seal = sealed(data, b"PC02A001", 56)
    return dict(root=native_id(data, 8), registry=native_id(data, 24),
                identity=native_id(data, 40), seal=seal)

def binding(data):
    seal = sealed(data, b"PC02B001", 240)
    return dict(root=native_id(data, 8), parent=native_id(data, 24),
                target=native_id(data, 40), lease=native_id(data, 56),
                state=native_id(data, 72), generation=u64(data, 88),
                grant=digest_field(data, 96), route=digest_field(data, 160),
                identity=native_id(data, 224), seal=seal)

def states(data):
    need(0 < len(data) <= 368 * 4096 and len(data) % 368 == 0, "posix-state-complete-bounded-records")
    records = []
    previous = ZERO
    for offset in range(0, len(data), 368):
        raw = data[offset:offset + 368]
        seal = sealed(raw, b"PC02S001", 304)
        need(raw[9:16] == bytes(7) and u64(raw, 16) == len(records) + 1 and
             digest_field(raw, 240) == previous, "posix-state-reserved-sequence-chain")
        row = dict(kind=chr(raw[8]), sequence=u64(raw, 16), generation=u64(raw, 24),
                   manifest=digest_field(raw, 32), input=digest_field(raw, 96),
                   terminal=digest_field(raw, 160), target=native_id(raw, 224), seal=seal)
        if not records:
            need(row["kind"] == "I" and row["generation"] == 0 and
                 row["manifest"] == row["input"] == row["terminal"] == ZERO, "posix-initial-state")
        elif row["kind"] == "B":
            prior = records[-1]
            need(prior["kind"] in ("I", "C") and row["generation"] == prior["generation"] + 1 and
                 row["target"] == prior["target"] and row["manifest"] != ZERO and
                 row["input"] != ZERO and row["terminal"] == ZERO, "posix-pending-transition")
        elif row["kind"] == "C":
            prior = records[-1]
            need(prior["kind"] == "B" and row["generation"] == prior["generation"] and
                 row["manifest"] == prior["manifest"] and row["input"] == prior["input"] and
                 row["terminal"] != ZERO, "posix-clean-transition")
        else:
            raise ValueError("posix-state-kind")
        records.append(row)
        previous = seal
    return records

def absolute_path(path):
    need(isinstance(path, str) and path.startswith("/") and len(path.encode()) < 4096 and
         "\x00" not in path and path != "/" and posixpath.normpath(path) == path and
         not path.endswith("/"), "posix-absolute-physical-path")
    return path

def observed_id(row):
    need(all(integer(row[key]) and 0 <= row[key] < 2 ** 64 for key in ("device", "inode")),
         "posix-native-identity-observation")
    need(row["inode"] > 0, "posix-native-inode")
    return row["device"], row["inode"]

def metadata(row, euid, directory=False, private=True, scope=False):
    identity = observed_id(row)
    mode = row["mode"]
    need(integer(mode) and integer(row["uid"]) and integer(row["links"]) and
         integer(row["bytes"]) and row["bytes"] >= 0, "posix-native-metadata-fields")
    need(stat.S_ISDIR(mode) if directory else stat.S_ISREG(mode), "posix-native-object-type")
    if directory:
        if private:
            need(row["uid"] == euid and mode & 0o7777 == 0o700, "posix-private-directory")
        else:
            need(row["uid"] in (0, euid) and not mode & 0o22, "posix-safe-directory")
        if scope:
            need(row["uid"] == euid and not mode & 0o7022 and mode & 0o700 == 0o700,
                 "posix-os-scope-permissions")
        need(row["sha256"] is None, "posix-directory-no-invented-content-sha")
    else:
        need(row["uid"] == euid and row["links"] == 1, "posix-native-file-owner-link")
        need(mode & 0o7777 == 0o600 if private else not mode & 0o22, "posix-native-file-mode")
        need(hexadecimal(row["sha256"], 64), "posix-native-file-digest")
    return identity

def route(parent, path):
    leaf = posixpath.basename(absolute_path(path))
    need(0 < len(leaf) < 256 and leaf not in (".", "..") and not leaf.endswith(".") and
         re.fullmatch(r"[a-zA-Z0-9._-]+", leaf) is not None, "posix-library-basename")
    return sha(("PC02-ROUTE1\n%016x%016x\n%s\n" % (*parent, leaf.lower())).encode("ascii"))

def decode_route(raw_binding, raw_state, observed, library, root_id, euid):
    grant = binding(raw_binding)
    history = states(raw_state)
    target = metadata(library, euid, private=False)
    parent = metadata(library["parent"], euid, directory=True, private=False)
    need(posixpath.dirname(absolute_path(library["path"])) == absolute_path(library["parent"]["path"]),
         "posix-library-parent-path")
    expected_route = route(parent, library["path"])
    need(grant["root"] == root_id and grant["parent"] == parent and grant["route"] == expected_route,
         "posix-binding-root-parent-route")
    for name in ("binding", "state", "lease"):
        identity = metadata(observed[name], euid)
        need(identity == grant["identity" if name == "binding" else name], "posix-binding-native-" + name)
    matches = [index for index, row in enumerate(history) if row["seal"] == grant["grant"]]
    need(len(matches) == 1, "posix-grant-in-actual-state")
    index = matches[0]
    clean = history[index]
    need(clean["kind"] in ("I", "C") and clean["generation"] == grant["generation"] and
         clean["target"] == grant["target"], "posix-binding-clean-grant")
    remaining = history[index + 1:]
    if not remaining:
        status = "clean"
        need(target == clean["target"], "posix-clean-target-identity")
    else:
        need(len(remaining) in (1, 2) and remaining[0]["kind"] == "B" and
             remaining[0]["generation"] == clean["generation"] + 1, "posix-ungranted-exact-transaction")
        status = "pending" if len(remaining) == 1 else "unbound-clean"
        if status == "unbound-clean":
            need(remaining[1]["kind"] == "C", "posix-unbound-terminal")
    return dict(route=expected_route, status=status, binding=grant, history=history,
                observed_target=target)

def audit_snapshot(files, manifest, prefix=""):
    need(manifest["schema"] == "pc02-native-snapshot-v1" and integer(manifest["euid"]) and
         manifest["euid"] > 0, "posix-actual-nonroot-snapshot")
    euid = manifest["euid"]
    absolute_path(manifest["authority_path"])
    rows = manifest["objects"]
    need(isinstance(rows, list) and rows, "posix-native-object-inventory")
    objects = {}
    regular = set()
    for row in rows:
        path = row["path"]
        need(isinstance(path, str) and (path == "." or
             (not path.startswith("/") and posixpath.normpath(path) == path and
              all(part not in ("", ".", "..") for part in path.split("/")))), "posix-object-relative-path")
        need(path not in objects, "posix-duplicate-native-object")
        directory = stat.S_ISDIR(row["mode"])
        metadata(row, euid, directory=directory)
        objects[path] = row
        if not directory:
            raw_path = prefix + "authority/" + path
            need(raw_path in files and len(files[raw_path]) == row["bytes"] and
                 sha(files[raw_path]) == row["sha256"], "posix-captured-native-file-bytes")
            regular.add(raw_path)
    need(regular == {path for path in files if path.startswith(prefix + "authority/")},
         "posix-complete-original-byte-inventory")
    need("." in objects and "authority" in objects and "registry.lock" in objects, "posix-root-authority-present")
    root_id = metadata(objects["."], euid, directory=True)
    control = anchor(files[prefix + "authority/authority"])
    need(control["root"] == root_id and control["registry"] == observed_id(objects["registry.lock"]) and
         control["identity"] == observed_id(objects["authority"]), "posix-authority-native-identities")
    need(files[prefix + "authority/registry.lock"] == b"PC02-REGISTRY\n\0\0", "posix-registry-lock-bytes")
    if "scope" in manifest:
        metadata(manifest["scope"], euid, directory=True, private=False, scope=True)
        scoped_path = absolute_path(manifest["scope"]["path"])
        need(manifest["authority_path"].startswith(scoped_path + "/"), "posix-authority-inside-os-scope")
    libraries = manifest["libraries"]
    need(isinstance(libraries, list) and libraries, "posix-library-identity-inventory")
    decoded = []
    seen = set()
    for library in libraries:
        parent = observed_id(library["parent"])
        name = route(parent, library["path"])
        need(name not in seen and name in objects, "posix-route-unique-directory")
        metadata(objects[name], euid, directory=True)
        seen.add(name)
        observed = {key:objects[name + "/" + key] for key in ("binding", "state", "lease")}
        relative = library["archive_path"]
        need(re.fullmatch(r"library-[0-9]+\.sqlite", relative) is not None, "posix-library-retained-name")
        raw = files[prefix + relative]
        need(len(raw) == library["bytes"] and sha(raw) == library["sha256"], "posix-retained-library-bytes")
        value = decode_route(files[prefix + "authority/" + name + "/binding"],
                             files[prefix + "authority/" + name + "/state"],
                             observed, library, root_id, euid)
        value["path"] = library["path"]
        decoded.append(value)
    need({name for name in objects if "/" not in name} == seen | {".", "authority", "registry.lock"},
         "posix-all-authority-routes-accounted")
    return dict(euid=euid, root=root_id, objects=len(objects), libraries=decoded)
