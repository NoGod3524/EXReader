#!/usr/bin/env python3
"""S13 CBZ leading-slash candidate: independent fixtures, oracle and checks.

Everything here runs inside GitHub Actions only. The script never edits the
candidate patch, the pristine base tree, the real archives or the frozen SDK. It
declares the fixtures and expectations, builds the synthetic archives, reads the
probe JSON reports, and recomputes every claim from the untouched inputs.
Member names are handled as raw bytes end to end, so nothing is normalised by a
library on the way to a comparison.
"""
import argparse
import functools
import hashlib
import json
import os
import struct
import subprocess
import sys
import urllib.request
import zlib
from pathlib import Path

IMAGE_EXT = (b".png", b".jpg", b".jpeg", b".gif", b".webp", b".bmp", b".avif", b".tif", b".tiff")
FIXTURE_PNG = (2, 2, (((255, 0, 0, 255), (0, 255, 0, 255)), ((0, 0, 255, 255), (255, 255, 0, 255))))
COMIC_INFO = "<ComicInfo><Title>S13 Slash Comic</Title><Writer>S13</Writer></ComicInfo>"


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path, payload):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(payload, indent=1, ensure_ascii=True) + "\n", encoding="ascii")


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def display_name(raw):
    return raw.decode("utf-8", "replace")


def name_bytes(identifier):
    return identifier.encode("utf-8", "surrogateescape")


# ------------------------------------------------------------------ zip io --
class ZipArchive:
    """Read-only central directory and member bytes, mirroring the local-header
    rule the candidate reader uses. No library normalises the member names."""

    def __init__(self, path):
        self.path = Path(path)
        self.data = self.path.read_bytes()
        self.entries = self._central()

    def _central(self):
        end = self.data.rfind(b"PK\x05\x06")
        if end < 0 or end + 22 > len(self.data):
            raise SystemExit("%s: no end of central directory" % self.path)
        total, cd_size, cd_offset = struct.unpack_from("<HII", self.data, end + 10)
        if cd_offset + cd_size > len(self.data):
            raise SystemExit("%s: central directory exceeds the archive" % self.path)
        entries = []
        position = cd_offset
        for _ in range(total):
            fields = struct.unpack_from("<IHHHHHHIIIHHHHHII", self.data, position)
            (signature, _, _, flags, method, _, _, crc, csize, usize,
             nlen, elen, clen, _, _, external, offset) = fields
            if signature != 0x02014B50:
                raise SystemExit("%s: bad central directory entry" % self.path)
            entries.append({"name": self.data[position + 46:position + 46 + nlen], "flags": flags,
                            "method": method, "crc32": crc, "compressed": csize, "uncompressed": usize,
                            "external": external, "offset": offset})
            position += 46 + nlen + elen + clen
        return entries

    def member_bytes(self, entry):
        header = struct.unpack_from("<IHHHHHIIIHH", self.data, entry["offset"])
        if header[0] != 0x04034B50:
            raise SystemExit("%s: bad local header" % self.path)
        start = entry["offset"] + 30 + header[9] + header[10]
        raw = self.data[start:start + entry["compressed"]]
        if len(raw) != entry["compressed"]:
            raise SystemExit("%s: truncated member data" % self.path)
        if entry["method"] == 0:
            return raw
        if entry["method"] == 8:
            return zlib.decompress(raw, -15)
        raise SystemExit("%s: unsupported member compression %d" % (self.path, entry["method"]))


# ---------------------------------------------------------------- fixtures --
def png_bytes():
    width, height, rows = FIXTURE_PNG
    raw = b"".join(b"\x00" + bytes(channel for pixel in row for channel in pixel) for row in rows)

    def chunk(kind, payload):
        return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)

    header = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")


def zip_store(entries):
    """Minimal stored ZIP so raw member bytes stay exactly as declared."""
    out = bytearray()
    central = bytearray()
    for name, data in entries:
        crc = zlib.crc32(data) & 0xFFFFFFFF
        offset = len(out)
        out += struct.pack("<IHHHHHIIIHH", 0x04034B50, 20, 0, 0, 0, 0, crc, len(data), len(data), len(name), 0)
        out += name + data
        central += struct.pack("<IHHHHHHIIIHHHHHII", 0x02014B50, 20, 20, 0, 0, 0, 0, crc, len(data), len(data),
                               len(name), 0, 0, 0, 0, 0, offset) + name
    cd_offset = len(out)
    out += central
    out += struct.pack("<IHHHHIIH", 0x06054B50, 0, 0, len(entries), len(entries), len(central), cd_offset, 0)
    return bytes(out)


def member_payload(kind):
    if kind == "png":
        return png_bytes()
    if kind == "comicinfo":
        return COMIC_INFO.encode("utf-8")
    if kind == "text":
        return b"not an image"
    raise SystemExit("unknown fixture payload: %s" % kind)


def build_fixtures(cases_path, out_dir):
    cases = read_json(cases_path)["cases"]
    root = Path(out_dir)
    root.mkdir(parents=True, exist_ok=True)
    built = []
    for case in cases:
        entries = []
        for member in case["members"]:
            name = bytes.fromhex(member["name_hex"]) if "name_hex" in member else name_bytes(member["name"])
            entries.append((name, member_payload(member["data"])))
        data = zip_store(entries)
        path = root / (case["id"] + ".cbz")
        path.write_bytes(data)
        built.append({"id": case["id"], "path": str(path), "bytes": len(data), "sha256": sha256_bytes(data)})
    write_json(root / "fixtures.json", {"schema": 1, "cases_path": str(cases_path), "fixtures": built})
    print(json.dumps({"fixtures": len(built)}))
    return 0


# ------------------------------------------------------------- real inputs --
def download(entry, directory, attempts=3):
    target = Path(directory) / entry["path"]
    if target.is_file() and target.stat().st_size == entry["bytes"] and sha256_file(target) == entry["sha256"]:
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    last = None
    for _ in range(attempts):
        try:
            request = urllib.request.Request(entry["url"], headers={"User-Agent": "exreader-s13-acceptance/1"})
            with urllib.request.urlopen(request, timeout=120) as response:
                if response.status != 200:
                    raise RuntimeError("HTTP %s" % response.status)
                data = response.read()
            if len(data) != entry["bytes"] or sha256_bytes(data) != entry["sha256"]:
                raise RuntimeError("pinned identity mismatch: %d bytes, sha256 %s" % (len(data), sha256_bytes(data)))
            target.write_bytes(data)
            return target
        except Exception as error:  # noqa: BLE001 - retried, then reported
            last = error
    raise SystemExit("cannot recover %s: %s" % (entry["url"], last))


def candidate_view(raw):
    view = raw[1:] if raw.startswith(b"/") else raw
    skipped = view.startswith(b"__MACOSX/") or view[:1] == b"." or b"/." in view
    dot = view.rfind(b".")
    image = dot >= 0 and view[dot:].lower() in IMAGE_EXT
    return view, skipped, image


def inventory_entry(entry):
    raw = entry["name"]
    view, skipped, image = candidate_view(raw)
    directory = raw.endswith(b"/") or bool((entry["external"] >> 16) & 0x10)
    return {
        "name_bytes_hex": raw.hex(),
        "name_display": display_name(raw),
        "leading_slash": raw.startswith(b"/"),
        "directory": directory,
        "candidate": (not directory) and (not skipped) and (image or view == b"ComicInfo.xml"),
        "crc32": entry["crc32"],
        "uncompressed": entry["uncompressed"],
        "compressed": entry["compressed"],
    }


def collect(real_path, out_dir):
    real = read_json(real_path)
    directory = Path(out_dir)
    directory.mkdir(parents=True, exist_ok=True)
    records = []
    for entry in real["files"]:
        path = download(entry, directory)
        archive = ZipArchive(path)
        members = [inventory_entry(item) for item in archive.entries]
        record = {"id": entry["id"], "path": str(path), "bytes": path.stat().st_size,
                  "sha256": sha256_file(path), "url": entry["url"],
                  "pinned_sha256": entry["sha256"], "pinned_bytes": entry["bytes"],
                  "members": members, "member_count": len(members)}
        record["candidate_count"] = sum(1 for item in members if item["candidate"])
        record["leading_slash_count"] = sum(1 for item in members if item["leading_slash"])
        record["leading_slash_candidate_count"] = sum(1 for item in members if item["leading_slash"] and item["candidate"])
        records.append(record)
        print("%s: %d members, %d candidates, %d leading-slash, %d leading-slash candidates" %
              (entry["id"], len(members), record["candidate_count"], record["leading_slash_count"],
               record["leading_slash_candidate_count"]))
        for member in members:
            print("  member %-40r candidate=%s leading_slash=%s directory=%s bytes=%d" %
                  (member["name_display"], member["candidate"], member["leading_slash"],
                   member["directory"], member["uncompressed"]))
    write_json(directory / "inventory.json", {"schema": 1, "real": str(real_path), "files": records})
    return 0


def extract_members(inventory_path, out_dir):
    """Copy candidate member bytes out of the untouched archive for the
    independent decode comparison; the archive itself is never written."""
    inventory = read_json(inventory_path)
    root = Path(out_dir)
    written = []
    for record in inventory["files"]:
        archive = ZipArchive(record["path"])
        for index, entry in enumerate(archive.entries):
            member = record["members"][index]
            if not member["candidate"] or candidate_view(bytes.fromhex(member["name_bytes_hex"]))[0] == b"ComicInfo.xml":
                continue
            target = root / record["id"] / ("%05d.bin" % index)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.member_bytes(entry))
            written.append({"file": record["id"], "index": index, "name_bytes_hex": member["name_bytes_hex"],
                            "path": str(target), "sha256": sha256_file(target)})
    write_json(root / "members.json", {"schema": 1, "members": written})
    return 0


# ------------------------------------------------------------------ oracle --
def ascii_lower(value):
    return value + 32 if 65 <= value <= 90 else value


def is_digit(value):
    return 48 <= value <= 57


def compare_names(left, right):
    """Faithful port of compare_pages() over the raw name bytes."""
    a = b = 0
    while a < len(left) and b < len(right):
        if is_digit(left[a]) and is_digit(right[b]):
            while a < len(left) and left[a] == 48:
                a += 1
            while b < len(right) and right[b] == 48:
                b += 1
            ea, eb = a, b
            while ea < len(left) and is_digit(left[ea]):
                ea += 1
            while eb < len(right) and is_digit(right[eb]):
                eb += 1
            if ea - a != eb - b:
                return -1 if ea - a < eb - b else 1
            if left[a:ea] != right[b:eb]:
                return -1 if left[a:ea] < right[b:eb] else 1
            a, b = ea, eb
        else:
            x, y = ascii_lower(left[a]), ascii_lower(right[b])
            if x != y:
                return -1 if x < y else 1
            a += 1
            b += 1
    if a < len(left) or b < len(right):
        return 1 if a < len(left) else -1
    if left != right:
        return -1 if left < right else 1
    return 0


def oracle_pages(record):
    names = [bytes.fromhex(member["name_bytes_hex"]) for member in record["members"]
             if member["candidate"] and candidate_view(bytes.fromhex(member["name_bytes_hex"]))[0] != b"ComicInfo.xml"]
    return sorted(names, key=functools.cmp_to_key(compare_names))


def pillow_image(path):
    from PIL import Image
    with Image.open(path) as image:
        return {"width": image.size[0], "height": image.size[1], "mode": image.mode,
                "frames": getattr(image, "n_frames", 1)}


def pillow_available():
    try:
        from PIL import Image  # noqa: F401
        return True
    except Exception:  # noqa: BLE001
        return False


# ------------------------------------------------------------------- probe --
def call_probe(probe, arguments, output):
    """Run the installed-SDK probe and keep its raw output, refusal included."""
    result = subprocess.run([probe] + arguments, capture_output=True)
    stdout = result.stdout.decode("utf-8", "surrogateescape")
    stderr = result.stderr.decode("utf-8", "replace")
    try:
        payload = json.loads(stdout) if stdout.strip() else None
    except json.JSONDecodeError:
        payload = None
    if payload is None:
        payload = {"mode": "unavailable", "open": {"status": None, "message": "probe produced no JSON"}}
    payload["_probe_exit"] = result.returncode
    if result.returncode != 0:
        payload["_probe_stderr"] = stderr[-4000:]
    write_json(output, payload)
    return payload


def run_fixtures(directory, candidate, base, out):
    cases = sorted(Path(directory).glob("*.cbz"))
    for case in cases:
        call_probe(candidate, ["--probe", str(case)], Path(out) / "candidate" / (case.stem + ".json"))
        call_probe(base, ["--probe", str(case)], Path(out) / "base" / (case.stem + ".json"))
    print(json.dumps({"fixtures": len(cases)}))
    return 0


def run_real(real_path, inputs, base, candidate, out, databases):
    real = read_json(real_path)
    Path(databases).mkdir(parents=True, exist_ok=True)
    for entry in real["files"]:
        path = str(Path(inputs) / entry["path"])
        call_probe(base, ["--probe", path], Path(out) / ("base-%s.json" % entry["id"]))
        for run in (1, 2):
            database = Path(databases) / ("%s-run%d.sqlite" % (entry["id"], run))
            if database.exists():
                database.unlink()
            call_probe(candidate, ["--probe", path, str(database)],
                       Path(out) / ("candidate-%s-run%d.json" % (entry["id"], run)))
    for entry in real["files"]:
        for run in (1, 2):
            report = read_json(Path(out) / ("candidate-%s-run%d.json" % (entry["id"], run)))
            ids = report.get("ids", [])
            print(json.dumps({"file": entry["id"], "run": run, "open": report.get("open", {}).get("status"),
                              "message": report.get("open", {}).get("message", ""),
                              "pages": report.get("page_count"), "first": ids[:2], "last": ids[-2:],
                              "render": report.get("render"), "capture": report.get("capture"),
                              "fallback": report.get("fallback"), "reopen": report.get("reopen"),
                              "library": report.get("library"), "probe_exit": report.get("_probe_exit")}))
        base = read_json(Path(out) / ("base-%s.json" % entry["id"]))
        print(json.dumps({"file": entry["id"], "base_open": base.get("open", {}),
                          "base_pages": base.get("page_count")}))
    print(json.dumps({"real": len(real["files"])}))
    return 0


def plan_real(inventory_path, members_path, reports_dir, out_path):
    """Map every sampled page to the extracted bytes of the member that names it."""
    inventory = read_json(inventory_path)["files"]
    members = read_json(members_path)["members"]
    reports = Path(reports_dir)
    plan = []
    for record in inventory:
        identifier = record["id"]
        report = read_json(reports / ("candidate-%s-run1.json" % identifier))
        ids = report.get("ids", [])
        sampled = sorted({0, len(ids) // 2, len(ids) - 1}) if ids else []
        by_name = {bytes.fromhex(member["name_bytes_hex"]): member
                   for member in members if member["file"] == identifier}
        entries = []
        for page in sampled:
            page_id = ids[page]
            base = name_bytes(page_id).split(b"#")[0]
            member = by_name.get(base)
            if member is None:
                raise SystemExit("no extracted member for page %d (%r) of %s" % (page, page_id, identifier))
            entries.append({"page": page, "page_id": page_id,
                            "member_path": member["path"], "member_sha256": member["sha256"],
                            "image_report": str(reports / "images" / ("%s-%d.json" % (identifier, page)))})
        plan.append({"id": identifier, "entries": entries})
    write_json(out_path, {"schema": 1, "plan": plan})
    print(json.dumps({"planned": sum(len(item["entries"]) for item in plan)}))
    return 0


def image_digests(plan_path, probe):
    plan = read_json(plan_path)["plan"]
    written = 0
    for item in plan:
        for entry in item["entries"]:
            call_probe(probe, ["--image", entry["member_path"]], entry["image_report"])
            written += 1
    print(json.dumps({"images": written}))
    return 0


def program_identity(files, out):
    records = []
    for path in files:
        if Path(path).is_file():
            records.append({"path": str(path), "bytes": Path(path).stat().st_size, "sha256": sha256_file(path)})
        else:
            records.append({"path": str(path), "missing": True})
    write_json(out, {"schema": 1, "programs": records})
    print(json.dumps({"programs": len(records), "missing": [r["path"] for r in records if r.get("missing")]}))
    return 0


# ------------------------------------------------------------------ checks --
class Checks:
    def __init__(self, scope):
        self.scope = scope
        self.items = []

    def require(self, name, ok, detail=None):
        self.items.append({"name": name, "ok": bool(ok), "detail": detail})
        return bool(ok)

    def payload(self, extra=None):
        failed = [item["name"] for item in self.items if not item["ok"]]
        payload = {"schema": 1, "scope": self.scope, "checks": self.items,
                   "check_count": len(self.items), "failed": failed, "accepted": not failed}
        if extra:
            payload.update(extra)
        return payload


def check_fixtures(cases_path, candidate_dir, base_dir, out_path):
    cases = read_json(cases_path)["cases"]
    checks = Checks("fixtures")
    for case in cases:
        expected = case["expect"]
        report = read_json(Path(candidate_dir) / (case["id"] + ".json"))
        state = report.get("open", {})
        ok = state.get("status") == expected["status"]
        detail = {"case": case["id"], "status": state.get("status"), "expected_status": expected["status"],
                  "message": state.get("message", ""), "probe_exit": report.get("_probe_exit")}
        if "message" in expected:
            ok = ok and state.get("message", "") == expected["message"]
        if "page_ids" in expected:
            ok = ok and report.get("ids") == expected["page_ids"]
            detail["ids"] = report.get("ids")
        if "title" in expected:
            ok = ok and state.get("title") == expected["title"]
        checks.require("fixture:" + case["id"], ok, detail)
        base_expected = case.get("base_expect")
        if base_expected:
            base = read_json(Path(base_dir) / (case["id"] + ".json"))
            base_state = base.get("open", {})
            base_ok = base_state.get("status") == base_expected["status"]
            if "message" in base_expected:
                base_ok = base_ok and base_state.get("message", "") == base_expected["message"]
            checks.require("fixture-base:" + case["id"], base_ok,
                           {"status": base_state.get("status"), "expected_status": base_expected["status"],
                            "message": base_state.get("message", "")})
    payload = checks.payload({"cases": len(cases)})
    write_json(out_path, payload)
    print(json.dumps({"checks": payload["check_count"], "failed": payload["failed"]}))
    return 0 if payload["accepted"] else 1


def check_real(real_path, inventory_path, plan_path, reports_dir, out_path):
    real = read_json(real_path)
    inventory = {entry["id"]: entry for entry in read_json(inventory_path)["files"]}
    plan = {item["id"]: item["entries"] for item in read_json(plan_path)["plan"]}
    checks = Checks("real")
    reports = Path(reports_dir)
    with_pillow = pillow_available()
    checks.require("pillow_available", with_pillow, {"used": "independent image dimensions"})
    summaries = []
    for entry in real["files"]:
        identifier = entry["id"]
        record = inventory[identifier]
        base = read_json(reports / ("base-%s.json" % identifier))
        first = read_json(reports / ("candidate-%s-run1.json" % identifier))
        second = read_json(reports / ("candidate-%s-run2.json" % identifier))
        path = Path(record["path"])
        members = record["members"]
        checks.require("pinned_identity:" + identifier,
                       path.stat().st_size == entry["bytes"] and sha256_file(path) == entry["sha256"],
                       {"bytes": path.stat().st_size, "sha256": sha256_file(path)})
        slash_candidates = [member for member in members
                            if member["leading_slash"] and member["candidate"] and
                            candidate_view(bytes.fromhex(member["name_bytes_hex"]))[0] != b"ComicInfo.xml"]
        checks.require("leading_slash_member_present:" + identifier, bool(slash_candidates),
                       {"count": len(slash_candidates), "sample": [m["name_display"] for m in slash_candidates[:3]]})
        checks.require("original_failure_preserved:" + identifier,
                       base.get("open", {}).get("status") == 5 and
                       base.get("open", {}).get("message") == "Unsafe CBZ member path" and
                       "page_count" not in base,
                       {"status": base.get("open", {}).get("status"), "message": base.get("open", {}).get("message")})
        checks.require("candidate_opens:" + identifier,
                       first.get("open", {}).get("status") == 0 and first.get("page_count", 0) > 0,
                       {"status": first.get("open", {}).get("status"), "pages": first.get("page_count")})
        member_names = {bytes.fromhex(member["name_bytes_hex"]) for member in members}
        ids = first.get("ids", [])
        ids_bytes = [name_bytes(page) for page in ids]
        checks.require("ids_are_member_names:" + identifier,
                       bool(ids) and all(page.split(b"#")[0] in member_names for page in ids_bytes),
                       {"page_count": len(ids), "sample": ids[:3]})
        expected = oracle_pages(record)
        frames_simple = True
        if with_pillow:
            for member in plan[identifier]:
                image = pillow_image(member["member_path"]) if "member_path" in member else None
                if image and image["frames"] != 1:
                    frames_simple = False
        checks.require("single_frame_members:" + identifier, frames_simple,
                       {"note": "multi-frame members are outside this candidate" if not frames_simple else "one page per member"})
        if frames_simple:
            set_ok = sorted(ids_bytes) == sorted(expected)
            order_ok = ids_bytes == expected
        else:
            # A multi-frame member expands to several ids; only the member set and
            # the member order are inside this candidate.
            set_ok = ({page.split(b"#")[0] for page in ids_bytes} == set(expected) and
                      len(ids_bytes) >= len(expected))
            order_ok = [page.split(b"#")[0] for page in ids_bytes] == expected
        checks.require("page_set_matches_oracle:" + identifier, set_ok,
                       {"actual": [page.hex() for page in ids_bytes[:4]], "expected": [page.hex() for page in expected[:4]],
                        "pages": len(ids), "frames_simple": frames_simple})
        checks.require("page_order_matches_reader_rule:" + identifier, order_ok,
                       {"pages": len(ids), "sample": [page.hex() for page in expected[:4]], "frames_simple": frames_simple})
        geometry = {item["index"]: item for item in first.get("geometry", [])}
        draw = {item["page"]: item for item in first.get("draw", [])}
        render = {item["page"]: item for item in first.get("render", [])}
        dims_ok = True
        mapping_ok = True
        dims_detail = []
        mapping_detail = []
        for planned in plan[identifier]:
            page = planned["page"]
            rendered = render.get(page, {})
            delivered = draw.get(page, {})
            decoded = read_json(planned["image_report"]).get("open", {})
            if with_pillow:
                image = pillow_image(planned["member_path"])
                entry_ok = (image["width"] == geometry.get(page, {}).get("width") and
                            image["height"] == geometry.get(page, {}).get("height"))
                dims_ok = dims_ok and entry_ok
                dims_detail.append({"page": page, "pillow": [image["width"], image["height"]],
                                    "sdk": [geometry.get(page, {}).get("width"), geometry.get(page, {}).get("height")],
                                    "mode": image["mode"]})
            entry_ok = (rendered.get("status") == 0 and delivered.get("status") == 0 and
                        delivered.get("images") == 1 and decoded.get("status") == 0 and
                        delivered.get("digest") == decoded.get("digest") and
                        rendered.get("width") == geometry.get(page, {}).get("width") and
                        rendered.get("height") == geometry.get(page, {}).get("height") and
                        rendered.get("digest") not in (None, "0000000000000000"))
            mapping_ok = mapping_ok and entry_ok
            mapping_detail.append({"page": page, "render": rendered.get("digest"),
                                   "member": decoded.get("digest"), "draw": delivered.get("digest"),
                                   "member_sha256": planned.get("member_sha256")})
        checks.require("geometry_matches_independent_decoder:" + identifier, dims_ok, {"samples": dims_detail})
        checks.require("render_matches_member_pixels:" + identifier, mapping_ok, {"samples": mapping_detail})
        reopen = first.get("reopen", {})
        checks.require("reopen_in_process:" + identifier,
                       reopen.get("status") == 0 and reopen.get("ids_equal") is True and
                       reopen.get("geometry_equal") is True and reopen.get("render_equal") is True, reopen)
        checks.require("reopen_second_process:" + identifier, first == second, {"identical": first == second})
        capture = first.get("capture", {})
        checks.require("point_capture_keeps_page_identity:" + identifier,
                       capture.get("text_status") == 0 and capture.get("empty_text") is True and
                       capture.get("capture_status") == 0 and capture.get("anchor_page_id") == capture.get("page_id") and
                       capture.get("exact_size") == 0 and capture.get("prefix_size") == 0 and
                       capture.get("suffix_size") == 0 and capture.get("regions") == 0, capture)
        # A point captured on a CBZ page resolves to a zero-length range at the
        # page origin (FOUND, start==end==0). Nothing longer may be invented, and
        # the same selector must not resolve on a different page id.
        checks.require("point_resolve_no_invented_range:" + identifier,
                       capture.get("resolve_status") == 0 and capture.get("resolve_state") == 1 and
                       capture.get("resolve_start") == 0 and capture.get("resolve_end") == 0 and
                       capture.get("other_status") == 0 and capture.get("other_state") == 0 and
                       capture.get("other_start") is None and capture.get("other_end") is None, capture)
        fallback = first.get("fallback", {})
        checks.require("page_bounds_refusal:" + identifier,
                       fallback.get("status") == 1 and fallback.get("empty_bitmap") is True and
                       fallback.get("repeat_status") == 1 and fallback.get("stable") is True and
                       fallback.get("last_digest") not in (None, "0000000000000000"), fallback)
        library = first.get("library", {})
        checks.require("library_page_identity:" + identifier,
                       library.get("open_status") == 0 and library.get("import_status") == 0 and
                       library.get("stored_status") == 0 and library.get("ids_equal") is True and
                       library.get("geometry_equal") is True and library.get("render_equal") is True and
                       library.get("note_status") == 0 and library.get("notes_status") == 0 and
                       library.get("note_count") == 1 and library.get("note_page_matches") is True and
                       library.get("reopen_status") == 0 and library.get("restored_status") == 0 and
                       library.get("render_reopen_equal") is True and
                       library.get("note_reopen_status") == 0 and library.get("note_reopen_count") == 1 and
                       library.get("note_reopen_matches") is True, library)
        checks.require("archive_bytes_unchanged:" + identifier, sha256_file(path) == entry["sha256"],
                       {"sha256": sha256_file(path)})
        summaries.append({"id": identifier, "pages": first.get("page_count"),
                          "leading_slash_candidates": len(slash_candidates),
                          "ids": ids, "render": first.get("render"), "pinned_sha256": entry["sha256"]})
    payload = checks.payload({"files": summaries})
    write_json(out_path, payload)
    print(json.dumps({"checks": payload["check_count"], "failed": payload["failed"]}))
    return 0 if payload["accepted"] else 1


def check_suite(base_junit, candidate_junit, out_path):
    def parse(path):
        import xml.etree.ElementTree as ElementTree
        result = {}
        root = ElementTree.parse(path).getroot()
        for case in root.iter("testcase"):
            status = "passed"
            for child in case:
                if child.tag in ("failure", "error"):
                    status = "failed"
                elif child.tag == "skipped":
                    status = "skipped"
            result[case.get("name")] = status
        return result

    checks = Checks("original-suite")
    missing = [name for name in (base_junit, candidate_junit) if not Path(name).is_file()]
    checks.require("junit_present", not missing, {"missing": missing})
    if missing:
        payload = checks.payload({})
        write_json(out_path, payload)
        print(json.dumps({"checks": payload["check_count"], "failed": payload["failed"]}))
        return 1
    base = parse(base_junit)
    candidate = parse(candidate_junit)
    checks.require("same_test_set", sorted(base) == sorted(candidate),
                   {"base": len(base), "candidate": len(candidate)})
    changed = sorted(name for name in set(base) & set(candidate) if base[name] != candidate[name])
    checks.require("suite_results_identical", not changed, {"changed": changed})
    checks.require("original_cbz_tests_pass",
                   candidate.get("native-cbz") == "passed" and candidate.get("native-cbz-formats") == "passed",
                   {"native-cbz": candidate.get("native-cbz"), "native-cbz-formats": candidate.get("native-cbz-formats")})
    payload = checks.payload({"base_results": base, "candidate_results": candidate})
    write_json(out_path, payload)
    print(json.dumps({"checks": payload["check_count"], "failed": payload["failed"]}))
    return 0 if payload["accepted"] else 1


def summary(parts, out_path, stage_context):
    checks = Checks("summary")
    failures = []
    total = 0
    preexisting = {}
    for part in parts:
        if not Path(part).is_file():
            checks.require("part_present:" + Path(part).name, False, {"path": str(part)})
            continue
        payload = read_json(part)
        total += payload.get("check_count", 0)
        for item in payload.get("checks", []):
            if not item["ok"]:
                failures.append("%s/%s" % (payload.get("scope"), item["name"]))
        if payload.get("scope") == "original-suite":
            preexisting = {name: status for name, status in payload.get("candidate_results", {}).items()
                           if status != "passed"}
    checks.require("every_named_check_passed", not failures, {"failed": failures})
    checks.require("source_bound", bool(stage_context["source_sha"]), stage_context)
    payload = checks.payload(dict(stage_context, named_check_count=total,
                                  parts=[str(part) for part in parts], failed_checks=failures,
                                  preexisting_suite_results=preexisting))
    write_json(out_path, payload)
    print(json.dumps({"accepted": payload["accepted"], "named_checks": total, "failed": failures,
                      "preexisting": preexisting}))
    return 0 if payload["accepted"] else 1


def main(argv):
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("fixtures")
    build.add_argument("--cases", required=True)
    build.add_argument("--out", required=True)
    fetch = sub.add_parser("collect")
    fetch.add_argument("--real", required=True)
    fetch.add_argument("--out", required=True)
    extract = sub.add_parser("extract")
    extract.add_argument("--inventory", required=True)
    extract.add_argument("--out", required=True)
    fixtures_run = sub.add_parser("run-fixtures")
    fixtures_run.add_argument("--dir", required=True)
    fixtures_run.add_argument("--candidate", required=True)
    fixtures_run.add_argument("--base", required=True)
    fixtures_run.add_argument("--out", required=True)
    real_run = sub.add_parser("run-real")
    real_run.add_argument("--real", required=True)
    real_run.add_argument("--inputs", required=True)
    real_run.add_argument("--base", required=True)
    real_run.add_argument("--candidate", required=True)
    real_run.add_argument("--out", required=True)
    real_run.add_argument("--databases", required=True)
    plan = sub.add_parser("plan-real")
    plan.add_argument("--inventory", required=True)
    plan.add_argument("--members", required=True)
    plan.add_argument("--reports", required=True)
    plan.add_argument("--out", required=True)
    images = sub.add_parser("image-digests")
    images.add_argument("--plan", required=True)
    images.add_argument("--probe", required=True)
    programs = sub.add_parser("program")
    programs.add_argument("--file", required=True, action="append")
    programs.add_argument("--out", required=True)
    fixture_check = sub.add_parser("check-fixtures")
    fixture_check.add_argument("--cases", required=True)
    fixture_check.add_argument("--candidate", required=True)
    fixture_check.add_argument("--base", required=True)
    fixture_check.add_argument("--out", required=True)
    real_check = sub.add_parser("check-real")
    real_check.add_argument("--real", required=True)
    real_check.add_argument("--inventory", required=True)
    real_check.add_argument("--plan", required=True)
    real_check.add_argument("--reports", required=True)
    real_check.add_argument("--out", required=True)
    suite_check = sub.add_parser("check-suite")
    suite_check.add_argument("--base", required=True)
    suite_check.add_argument("--candidate", required=True)
    suite_check.add_argument("--out", required=True)
    summarise = sub.add_parser("summary")
    summarise.add_argument("--parts", required=True, nargs="+")
    summarise.add_argument("--out", required=True)
    summarise.add_argument("--platform", required=True)
    args = parser.parse_args(argv)
    if args.command == "fixtures":
        return build_fixtures(args.cases, args.out)
    if args.command == "collect":
        return collect(args.real, args.out)
    if args.command == "extract":
        return extract_members(args.inventory, args.out)
    if args.command == "run-fixtures":
        return run_fixtures(args.dir, args.candidate, args.base, args.out)
    if args.command == "run-real":
        return run_real(args.real, args.inputs, args.base, args.candidate, args.out, args.databases)
    if args.command == "plan-real":
        return plan_real(args.inventory, args.members, args.reports, args.out)
    if args.command == "image-digests":
        return image_digests(args.plan, args.probe)
    if args.command == "program":
        return program_identity(args.file, args.out)
    if args.command == "check-fixtures":
        return check_fixtures(args.cases, args.candidate, args.base, args.out)
    if args.command == "check-real":
        return check_real(args.real, args.inventory, args.plan, args.reports, args.out)
    if args.command == "check-suite":
        return check_suite(args.base, args.candidate, args.out)
    if args.command == "summary":
        return summary(args.parts, args.out, {
            "source_sha": os.environ.get("GITHUB_SHA", ""), "run_id": os.environ.get("GITHUB_RUN_ID", ""),
            "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT", ""), "workflow": os.environ.get("GITHUB_WORKFLOW", ""),
            "platform": args.platform})
    raise SystemExit("unknown command")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
