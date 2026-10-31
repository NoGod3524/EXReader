#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""J04: independent analysis of the real C09 Windows link map. Execute ONLY in Actions.

Does not modify or rerun C09. It authenticates the retained C09 Windows artifact,
reads windows-host.map in memory, reproduces the old parser's outcome, then parses
with a format-detecting independent parser that keeps every unrecognised line.
"""
import hashlib, importlib.util, io, json, os, re, sys, urllib.request, zipfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[3]
C09 = Path(os.environ["C09_CHECKOUT"]).resolve()
OUT = ROOT / "j04-evidence"
REPO = "NoGod3524/EXReader"
ART, ART_BYTES = 12993253798, 8956408
ART_DIGEST = "b4cb373476c179d93994608399c48e7d59c9e6c5778717c4f885145009a1fe76"
RUN, SRC = 41091277686, "82c4a08c51ba2bfa67cb8899bb9e26609dc47eaf"
MIB = 1024 * 1024


class Reject(Exception):
    pass


def need(ok, rule):
    if not ok:
        raise Reject(rule)


def sha(b):
    return hashlib.sha256(b).hexdigest()


def dump(name, obj):
    OUT.mkdir(exist_ok=True)
    (OUT / name).write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


class Redirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        need(newurl.startswith("https://"), "download.https")
        nxt = super().redirect_request(req, fp, code, msg, headers, newurl)
        if nxt:
            nxt.remove_header("Authorization")
            nxt.unredirected_hdrs.pop("Authorization", None)
        return nxt


def get(url, limit):
    need(url.startswith("https://api.github.com/"), "download.api")
    req = urllib.request.Request(url, headers={"Authorization": "Bearer " + os.environ["GH_TOKEN"],
                                               "Accept": "application/vnd.github+json", "User-Agent": "EXReader-J04"})
    chunks, n = [], 0
    with urllib.request.build_opener(Redirect()).open(req, timeout=120) as r:
        while True:
            b = r.read(MIB)
            if not b:
                break
            n += len(b)
            need(n <= limit, "download.bytes")
            chunks.append(b)
    return b"".join(chunks)


def decode(raw):
    if raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff"):
        return raw.decode("utf-16"), "utf-16-bom"
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw[3:].decode("utf-8"), "utf-8-bom"
    try:
        return raw.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        return raw.decode("cp1252", errors="replace"), "cp1252-fallback"


# ---- independent parser -------------------------------------------------------------
ARCHIVE = r"[^\s:()\"']+?\.(?:lib|a)"
MSVC_SYM = re.compile(r"^\s*(?P<seg>[0-9A-Fa-f]{4}):(?P<off>[0-9A-Fa-f]{8})\s+(?P<sym>\S+)\s+(?P<rva>[0-9A-Fa-f]{8,16})\s*(?P<flags>(?:[fi]\s+)*)\s*(?P<src>\S.*?)\s*$")
SRC_ARCHIVE_COLON = re.compile(r"^(?P<ar>.+?\.(?:lib|a)):(?P<mem>.+)$", re.I)
LLD_IN = re.compile(r"^\s*[0-9A-Fa-f]{8,16}\s+[0-9A-Fa-f]{8,16}\s+\d+\s+(?:\S+\s+)?(?P<src>\S.*?)\s*$")
PAREN_ARCHIVE = re.compile(r"(?P<ar>" + ARCHIVE + r")\((?P<mem>[^)]+)\)", re.I)
GNU_ARCHIVE = re.compile(r"^(?P<ar>\S.*?\.(?:lib|a))\((?P<mem>[^)]+)\)\s*$", re.I)


def classify_format(text):
    marks = {
        "msvc_publics_by_value": "Publics by Value" in text,
        "msvc_static_symbols": "Static symbols" in text,
        "msvc_header_address_rva": bool(re.search(r"Address\s+Publics by Value\s+Rva\+Base", text)),
        "lld_header": bool(re.search(r"^\s*VMA\s+LMA|^\s*Address\s+Size\s+Align\s+Out\s+In\s+Symbol", text, re.M)),
        "gnu_archive_section": "Archive member included" in text,
    }
    return marks


def parse(text):
    """Return members/objects with source line numbers and every unrecognised line."""
    members, objects, unknown = {}, {}, []
    sections = {"msvc": 0, "lld": 0, "gnu": 0}
    mode, lines = None, text.splitlines()
    for no, line in enumerate(lines, 1):
        s = line.strip()
        if not s:
            continue
        if "Publics by Value" in line or "Static symbols" in line:
            mode = "msvc"; continue
        if re.match(r"^\s*Address\s+Size\s+Align\s+Out\s+In\s+Symbol", line):
            mode = "lld"; continue
        if "Archive member included" in line:
            mode = "gnu"; continue
        if mode == "msvc":
            m = MSVC_SYM.match(line)
            if m:
                sections["msvc"] += 1
                src = m.group("src")
                if src.startswith("<"):
                    objects.setdefault(src, no); continue
                a = SRC_ARCHIVE_COLON.match(src)
                if a:
                    members.setdefault((a.group("ar"), a.group("mem").lower()), no)
                else:
                    objects.setdefault(src, no)
                continue
        elif mode == "lld":
            m = LLD_IN.match(line)
            if m:
                sections["lld"] += 1
                src = m.group("src")
                p = PAREN_ARCHIVE.search(src)
                if p:
                    members.setdefault((p.group("ar"), p.group("mem").lower()), no)
                elif ".obj" in src.lower() or ".o:" in src.lower():
                    objects.setdefault(src, no)
                continue
        elif mode == "gnu":
            g = GNU_ARCHIVE.match(s)
            if g:
                sections["gnu"] += 1
                members.setdefault((g.group("ar"), g.group("mem").lower()), no)
                continue
        unknown.append((no, line[:200]))
    return members, objects, unknown, sections


def verdict(old_error, members, objects, text, marks, sections):
    """Evidence-based classification; never defaults empty to pass."""
    if len(text) < 2000 or not any(marks.values()):
        return "insufficient_evidence", "map is empty/truncated or has no recognised header"
    if members and old_error:
        return "old_parser_misread", "old parser failed closed but an independent parse of the same bytes finds %d archive members" % len(members)
    if members and not old_error:
        return "old_parser_not_reproduced", "old parser also selects members; the C09 failure is not reproduced on these bytes"
    if objects and sum(sections.values()) > 0:
        return "no_archive_members_in_map", "recognised map with %d link inputs, none from an archive" % len(objects)
    return "input_mismatch_or_unknown_format", "map header recognised (%s) but no input entries parsed" % [k for k, v in marks.items() if v]


def controls():
    """Synthetic positives/negatives for the independent parser (real-map result is the primary evidence)."""
    msvc_lib = "Publics by Value  Rva+Base Lib:Object\n 0001:00000010  foo  0000000140001010 f   exr_core.lib:layout.c.obj\n 0001:00000020  bar  0000000140001020 f   host.obj\n"
    msvc_a = "Publics by Value  Rva+Base Lib:Object\n 0001:00000010  foo  0000000140001010 f   libexr_core.a:layout.c.obj\n"
    lld = "Address Size Align Out In Symbol\n00001000 00000100 4 .text\n00001000 00000100 4 C:\\x\\libexr.lib(layout.c.obj):(.text)\n"
    gnu = "Archive member included to satisfy reference by file (symbol)\n\nlibexr_core.a(layout.c.o)\n   host.o (foo)\n"
    res = []

    def case(name, text, want_members, want_verdict_any=None):
        marks = classify_format(text)
        m, o, u, s = parse(text)
        res.append({"name": name, "members": len(m), "objects": len(o), "unknown": len(u),
                    "pass": len(m) == want_members})
    case("synthetic_msvc_lib", msvc_lib, 1)
    case("synthetic_msvc_dot_a", msvc_a, 1)
    case("synthetic_lld_paren", lld, 1)
    case("synthetic_gnu_archive_list", gnu, 1)
    case("negative_truncated_header_only", "Publics by Value\n", 0)
    case("negative_garbage", "hello\nworld\n" * 50, 0)
    case("negative_loose_objects_only", "Publics by Value\n 0001:00000010  foo  0000000140001010 f   a.obj\n", 0)
    v, _ = verdict(None, {}, {}, "x" * 3000, classify_format("x"), {})
    res.append({"name": "negative_unrecognised_map_is_insufficient_not_pass", "pass": v == "insufficient_evidence"})
    return res


def main():
    need(os.environ.get("GITHUB_ACTIONS") == "true", "actions_only")
    OUT.mkdir(exist_ok=True)
    result = {"task": "J04", "c09_run": RUN, "c09_source": SRC, "artifact_id": ART, "c09_budget_restored": False,
              "claims_windows_product_accepted": False}
    meta = json.loads(get("https://api.github.com/repos/%s/actions/artifacts/%d" % (REPO, ART), MIB))
    need(meta["id"] == ART and meta["size_in_bytes"] == ART_BYTES and meta["digest"] == "sha256:" + ART_DIGEST, "identity.artifact")
    need(meta["workflow_run"]["id"] == RUN and meta["workflow_run"]["head_sha"] == SRC and meta["expired"] is False, "identity.run")
    raw = get("https://api.github.com/repos/%s/actions/artifacts/%d/zip" % (REPO, ART), ART_BYTES)
    need(len(raw) == ART_BYTES and sha(raw) == ART_DIGEST, "download.identity")
    result["artifact"] = {"name": meta["name"], "bytes": len(raw), "sha256": sha(raw)}
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        infos = z.infolist()
        names = [i.filename for i in infos]
        need(len(names) == len(set(names)) and all(".." not in PurePosixPath(n).parts and not n.startswith("/") for n in names), "zip.paths")
        dump("artifact-listing.json", [{"name": i.filename, "bytes": i.file_size} for i in infos])
        maps = [i for i in infos if PurePosixPath(i.filename).name.lower().endswith(".map") and not i.is_dir()]
        result["map_entries"] = [{"name": i.filename, "bytes": i.file_size} for i in maps]
        need(maps, "map.missing")
        spec = importlib.util.spec_from_file_location("pd_win", C09 / "tests/reader_provider_desktop_remaining_20261030/pd_win.py")
        old = importlib.util.module_from_spec(spec); spec.loader.exec_module(old)
        result["maps"] = []
        for info in maps:
            need(info.file_size <= 256 * MIB, "map.size")
            data = z.read(info)
            text, enc = decode(data)
            lines = text.splitlines()
            (OUT / ("first-lines-" + PurePosixPath(info.filename).name + ".txt")).write_text("\n".join(lines[:120]) + "\n", encoding="utf-8")
            marks = classify_format(text)
            anchor = next((i for i, l in enumerate(lines) if "Publics by Value" in l), None)
            around = lines[max(0, anchor - 5): anchor + 25] if anchor is not None else []
            old_error, old_members = None, None
            try:
                parsed_old = old.parse_msvc_map(text)
                old_members = len(parsed_old["members"])
            except Exception as e:
                old_error = str(e)
            after = lines[anchor + 1:] if anchor is not None else []
            old_line_hits = sum(1 for l in after if old.MAP_LINE.match(l))
            members, objects, unknown, sections = parse(text)
            v, why = verdict(old_error, members, objects, text, marks, sections)
            dump("members-" + PurePosixPath(info.filename).name + ".json",
                 [{"archive": a, "member": m, "line": n} for (a, m), n in sorted(members.items(), key=lambda kv: kv[1])][:20000])
            dump("objects-" + PurePosixPath(info.filename).name + ".json", [{"input": k, "line": n} for k, n in sorted(objects.items(), key=lambda kv: kv[1])][:20000])
            (OUT / ("unrecognised-" + PurePosixPath(info.filename).name + ".txt")).write_text(
                "".join("%d:%s\n" % (n, l) for n, l in unknown[:2000]), encoding="utf-8")
            result["maps"].append({"entry": info.filename, "bytes": len(data), "sha256": sha(data), "encoding": enc,
                "line_count": len(lines), "line_endings_crlf": "\r\n" in data[:4096].decode("latin1"),
                "format_markers": marks, "publics_anchor_line": None if anchor is None else anchor + 1,
                "around_anchor": around, "old_parser": {"error": old_error, "members": old_members, "line_hits_after_anchor": old_line_hits},
                "independent": {"archive_members": len(members), "loose_objects": len(objects), "recognised_by_section": sections,
                                "unrecognised_lines": len(unknown), "unrecognised_sample": unknown[:40]},
                "verdict": v, "reason": why})
    result["controls"] = controls()
    result["controls_all_pass"] = all(c["pass"] for c in result["controls"])
    result["verdicts"] = [m["verdict"] for m in result["maps"]]
    dump("j04-result.json", result)
    print(json.dumps({"verdicts": result["verdicts"], "controls_all_pass": result["controls_all_pass"],
                      "maps": [{k: m[k] for k in ("entry", "bytes", "old_parser", "verdict", "reason")} for m in result["maps"]]}, indent=2)[:6000])
    return 0 if result["controls_all_pass"] else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        OUT.mkdir(exist_ok=True)
        dump("fatal.json", {"error": str(e), "type": type(e).__name__})
        raise
