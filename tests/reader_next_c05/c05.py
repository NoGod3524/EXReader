#!/usr/bin/env python3
"""C05 Windows FB2 find attribution package.

Subcommands (all run in GitHub Actions only):
  prepare   verify the F5 manifest/consumer identity, download and pin the two real
            FB2 originals, write the synthetic FB2 fixtures and the query lists
  run       run the installed-SDK probe on every fixture and judge it against an
            independent byte scan of the projected text
  repro     run the unmodified F5 consumer to retain the original failure
  aggregate cross-platform comparison of the two run summaries
  selftest  the judging code must reject deliberately wrong probe output
"""
import argparse
import bisect
import hashlib
import itertools
import json
import os
import platform
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

F5_COMMIT = "278d63691a4c73e7aa932d71a40a5938c5427514"
F5_MANIFEST = "tests/reader_real_corpus/manifest.json"
F5_MANIFEST_BLOB = "72841cbae68031c106125b489ec58d48e4232f02"
# The recorded F5 hash 2651b03d... is the CRLF working-tree form of the same blob.
F5_MANIFEST_SHA_LF = "be300d9a54329ab227ac7060bc39e0117de722ae3c60d6c0d998418eba994bf6"
F5_MANIFEST_SHA_CRLF = "2651b03dc9df0f8605b0da561518cc3138cd072ac61d113ea831d4f77c6d7c69"
F5_CONSUMER_SHA = "f2b5d06d1fb1450c74317b537164ca97b60d7826806175066b597335d342cf96"
F5_CMAKE_SHA = "545147fa67c104ff6ccccb8a7419e17963c729639efdf759be777fbe11001288"

REAL = {
    "fb2-breter": {
        "url": "https://archive.org/download/ivan_sergeevich_turgenev-bretyor-1539118486/Turgenev_Bretyor.bQhEMA.287228.fb2",
        "bytes": 196462,
        "sha256": "8a62c0fb0b84560cbdca693953533b71b7572568440c6da988e41f26b0d0d74d",
        "query": "Бретёр",
    },
    "fb2-portraits": {
        "url": "https://archive.org/download/ivan_sergeevich_turgenev-tri_portreta-680315ebee76d/Turgenev_Tri-portreta.Yr0Diw.582148.fb2",
        "bytes": 424614,
        "sha256": "10f671903db641921c67b8a9af198dd6d6f7f55be52085bc0749b197ea6f27e7",
        "query": "портрет",
    },
}

NFC = "Бретёр"
NFD = "Бретёр"
PORTRAIT = "портрет"
# Common positive/negative queries run against every document. Their results are
# judged by the independent scan; SEMANTIC adds declared counts for the synthetic files.
QUERIES = [
    ("nfc_breter", NFC.encode()),
    ("nfd_breter", NFD.encode()),
    ("lower_breter", "бретёр".encode()),
    ("upper_breter", "БРЕТЁР".encode()),
    ("no_diaeresis", "Бретер".encode()),
    ("portrait", PORTRAIT.encode()),
    ("emoji", "\U0001F600".encode()),
    ("cjk_ext_b", "\U00020000".encode()),
    ("emoji_word", ("\U0001F600 " + PORTRAIT).encode()),
    ("crlf_join", ("\r\n" + PORTRAIT).encode()),
    ("cr_join", "\rвторая".encode()),
    ("lf_join", ("\n" + PORTRAIT).encode()),
    ("space_join", (" " + PORTRAIT).encode()),
    ("lossy_ascii_6", b"??????"),
    ("lossy_ascii_7", b"???????"),
    ("absent_ascii", b"zzzz-not-present-c05"),
    ("invalid_ff_fe", b"\xff\xfe"),
    ("invalid_truncated", b"\xd0"),
]
SYNTHETIC = {
    "c05-cyrillic-combining": {
        "paragraphs": [
            "Первая строка " + NFC + " рядом.",
            "Вторая строка " + NFD + " разложенная.",
            "Третья строка бретёр и БРЕТЁР регистр.",
            "Четвёртая строка Бретер без точек.",
        ],
        "semantic": {"nfc_breter": 1, "nfd_breter": 1, "lower_breter": 1, "upper_breter": 1,
                     "no_diaeresis": 1, "portrait": 0, "emoji": 0},
    },
    "c05-non-bmp": {
        "paragraphs": [
            "Смайл \U0001F600 " + PORTRAIT + " конец один.",
            "Иероглиф \U00020000 " + PORTRAIT + " конец два.",
            "Двойной \U0001F600\U0001F600 " + PORTRAIT + " конец три.",
        ],
        "semantic": {"portrait": 3, "emoji": 3, "cjk_ext_b": 1, "emoji_word": 2, "nfc_breter": 0},
    },
    "c05-mixed-newlines": {
        "raw": ["первая строка\r\n" + PORTRAIT + "\rвторая строка\n" + PORTRAIT + " raw конец"],
        "paragraphs": ["третья&#13;&#10;" + PORTRAIT + "&#13;четвёртая&#10;" + PORTRAIT + " ref конец"],
        "semantic": {"portrait": 4, "nfc_breter": 0},
    },
}
CANCEL_LIMITS = [1, 2, 3, 5, 8]


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def git_show(rev_path):
    return subprocess.run(["git", "show", rev_path], check=True, capture_output=True).stdout


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def fb2_bytes(title, raw_paragraphs, paragraphs):
    body = "".join("<p>%s</p>" % p for p in list(raw_paragraphs) + list(paragraphs))
    text = ('<?xml version="1.0" encoding="utf-8"?>'
            '<FictionBook xmlns="http://www.gribuser.ru/xml/fictionbook/2.0"><description><title-info>'
            "<book-title>%s</book-title></title-info></description><body><section><title><p>%s</p></title>%s"
            "</section></body></FictionBook>" % (title, title, body))
    return text.encode("utf-8")


# ---------------------------------------------------------------- prepare

def download(url, expected_bytes, expected_sha, dest):
    last = None
    for attempt in range(1, 5):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "exreader-c05-ci/1"})
            with urllib.request.urlopen(req, timeout=180) as r:
                data = r.read()
                final = r.geturl()
            if len(data) != expected_bytes or sha256_bytes(data) != expected_sha:
                raise RuntimeError("identity mismatch: %d bytes sha %s" % (len(data), sha256_bytes(data)))
            dest.write_bytes(data)
            return {"attempts": attempt, "final_url": final}
        except Exception as exc:  # noqa: BLE001 - retried, then reported
            last = exc
            time.sleep(3 * attempt)
    raise SystemExit("download failed for %s: %s" % (url, last))


def cmd_prepare(args):
    out = Path(args.out)
    (out / "assets").mkdir(parents=True, exist_ok=True)
    (out / "orig-consumer-src").mkdir(parents=True, exist_ok=True)
    identity = {"f5_commit": F5_COMMIT, "problems": []}
    manifest_raw = git_show("%s:%s" % (F5_COMMIT, F5_MANIFEST))
    blob = subprocess.run(["git", "rev-parse", "%s:%s" % (F5_COMMIT, F5_MANIFEST)], check=True,
                          capture_output=True, text=True).stdout.strip()
    identity["manifest_blob"] = blob
    identity["manifest_sha256_lf"] = sha256_bytes(manifest_raw)
    identity["manifest_sha256_crlf"] = sha256_bytes(manifest_raw.replace(b"\n", b"\r\n"))
    for key, want, got in (("manifest_blob", F5_MANIFEST_BLOB, blob),
                           ("manifest_sha256_lf", F5_MANIFEST_SHA_LF, identity["manifest_sha256_lf"]),
                           ("manifest_sha256_crlf", F5_MANIFEST_SHA_CRLF, identity["manifest_sha256_crlf"])):
        if want != got:
            identity["problems"].append("%s %s != %s" % (key, got, want))
    manifest = json.loads(manifest_raw.decode("utf-8"))
    entries = {f["id"]: f for f in manifest["files"] if f["format"] == "FB2"}
    identity["files"] = {}
    for ident, pin in REAL.items():
        entry = entries.get(ident)
        if not entry:
            identity["problems"].append("%s missing from F5 manifest" % ident)
            continue
        src = entry["source"]
        same = (src["url"] == pin["url"] and src["bytes"] == pin["bytes"] and src["sha256"] == pin["sha256"]
                and entry["query"] == pin["query"])
        if not same:
            identity["problems"].append("%s differs from the pinned identity" % ident)
        dest = out / "assets" / (ident + ".fb2")
        info = download(pin["url"], pin["bytes"], pin["sha256"], dest)
        identity["files"][ident] = {"bytes": pin["bytes"], "sha256": pin["sha256"], "url": pin["url"],
                                    "query_utf8_hex": pin["query"].encode("utf-8").hex(), "download": info}
    for name, src_sha in (("consumer.c", F5_CONSUMER_SHA), ("CMakeLists.txt", F5_CMAKE_SHA)):
        data = git_show("%s:tests/reader_real_corpus/%s" % (F5_COMMIT, name))
        (out / "orig-consumer-src" / name).write_bytes(data)
        identity.setdefault("original_consumer", {})[name] = sha256_bytes(data)
        if sha256_bytes(data) != src_sha:
            identity["problems"].append("original %s hash %s != %s" % (name, sha256_bytes(data), src_sha))
    synth = {}
    for ident, spec in SYNTHETIC.items():
        data = fb2_bytes("C05 fixture " + ident[4:], spec.get("raw", []), spec["paragraphs"])
        (out / "assets" / (ident + ".fb2")).write_bytes(data)
        synth[ident] = {"bytes": len(data), "sha256": sha256_bytes(data)}
    identity["synthetic"] = synth
    write_json(out / "identity.json", identity)
    if identity["problems"]:
        print("identity problems:", identity["problems"])
        return 1
    return 0


# ---------------------------------------------------------------- judging

class Checks:
    def __init__(self):
        self.rows = []

    def add(self, name, ok, detail=""):
        self.rows.append({"name": name, "ok": bool(ok), "detail": str(detail)[:400]})

    @property
    def failed(self):
        return [r for r in self.rows if not r["ok"]]


def scan(text, query):
    out, i = [], text.find(query)
    while i >= 0 and len(out) < 100000:
        out.append(i)
        i = text.find(query, i + 1)
    return out


def valid_utf8(data):
    try:
        data.decode("utf-8")
        return True
    except UnicodeDecodeError:
        return False


def unique_context(text, positions, query):
    """True per occurrence when its +-32 scalar context is unique among the occurrences."""
    s = text.decode("utf-8")
    q = query.decode("utf-8")
    offsets = [0] + list(itertools.accumulate(len(ch.encode("utf-8")) for ch in s))
    keys = []
    for p in positions:
        ci = bisect.bisect_left(offsets, p)
        keys.append((s[max(0, ci - 32):ci], s[ci + len(q):ci + len(q) + 32]))
    return [keys.count(k) == 1 for k in keys]


def pair(start, end):
    return (start, end)


def judge_probe(probe, text, original, semantic, primary, label_prefix=""):
    """Names every check; text is the independent copy of the SDK projection (text.bin)."""
    c = Checks()
    p = lambda name, ok, detail="": c.add(label_prefix + name, ok, detail)  # noqa: E731
    p("import", probe.get("import", {}).get("ok") is True, probe.get("import"))
    p("readback_bytes", probe.get("import", {}).get("readback_ok") is True)
    p("open", probe.get("open", {}).get("ok") is True, probe.get("open"))
    proj = probe.get("projection", {})
    p("projection_size", proj.get("bytes") == len(text), "%s vs %d" % (proj.get("bytes"), len(text)))
    p("projection_valid_utf8", proj.get("valid_utf8") is True and valid_utf8(text))
    s = text.decode("utf-8", "replace")
    p("projection_stats_independent",
      (proj.get("scalars"), proj.get("nonbmp"), proj.get("cr"), proj.get("lf"), proj.get("nul"), proj.get("combining"))
      == (len(s), sum(1 for ch in s if ord(ch) > 0xFFFF), s.count("\r"), s.count("\n"), s.count("\0"),
          sum(1 for ch in s if 0x300 <= ord(ch) <= 0x36F)),
      "probe %s" % {k: proj.get(k) for k in ("scalars", "nonbmp", "cr", "lf", "nul", "combining")})
    p("memory_route_same_projection", probe.get("memory_route", {}).get("same") is True, probe.get("memory_route"))
    p("fixed_text_created", probe.get("fixed_text", {}).get("status") == "OK")
    reopen = probe.get("reopen", {})
    p("reopen_same_projection", reopen.get("status") == "OK" and reopen.get("same") is True, reopen.get("status"))
    queries = {q["label"]: q for q in probe.get("queries", [])}
    first_state = {}
    for label, q in queries.items():
        raw = bytes.fromhex(q["hex"]) if q["bytes"] <= 128 else None
        if raw is None:
            continue
        valid = valid_utf8(raw)
        pos = scan(text, raw) if valid else []
        want_status = "OK" if valid else "ENCODING"
        for route in ("document_find", "fixed_find"):
            r = q[route] or {}
            ok = (r.get("status") == want_status and r.get("count") == len(pos) and r.get("truncated") is False
                  and r.get("first") == (pos[0] if pos else None) and r.get("last") == (pos[-1] if pos else None)
                  and r.get("positions") == pos[:16])
            p("%s:%s=independent_scan" % (label, route), ok, "sdk %s scan count %d first %s" % (r, len(pos), pos[:1]))
        if pos:
            ex = q.get("excerpt") or {}
            p("%s:excerpt_bytes" % label, ex.get("offset") is not None and
              text[ex["offset"]:ex["offset"] + len(ex.get("bytes", "")) // 2].hex() == ex.get("bytes"))
        base = (pos[0], pos[0] + len(raw)) if pos else (None, None)
        cancels = q.get("cancel", [])
        p("%s:cancel_first_poll" % label, bool(cancels) and cancels[0]["status"] == "CANCELLED")
        clean = True
        retry = True
        for cr in cancels:
            if cr["status"] == "CANCELLED":
                clean = clean and cr["start"] is None and cr["end"] is None
            else:
                clean = clean and cr["status"] == want_status and (cr["start"], cr["end"]) == base
            retry = retry and cr["retry_same"] is True and cr["retry_status"] == want_status and \
                (cr["retry_start"], cr["retry_end"]) == base
        p("%s:cancel_leaves_no_result" % label, clean, cancels)
        p("%s:retry_after_each_cancel" % label, retry and len(cancels) == len(CANCEL_LIMITS), cancels)
        anchors = {a["which"]: a for a in q.get("anchors", [])}
        uniq = unique_context(text, pos, raw) if pos else []
        for which, idx in (("first", 0), ("last", -1)):
            a = anchors.get(which, {})
            if not pos:
                p("%s:anchor_%s_not_captured_without_match" % (label, which), a.get("captured") is False)
                continue
            p("%s:anchor_%s_captured" % (label, which), a.get("captured") is True and a.get("exact_bytes") == len(raw), a)
            res = a.get("resolve", {})
            expect = pos[idx]
            unique = uniq[idx]
            if unique:
                good = res.get("status") == "OK" and res.get("state") == "FOUND" and res.get("start") == expect \
                    and res.get("end") == expect + len(raw)
            else:
                good = res.get("status") == "OK" and res.get("state") in ("FOUND", "AMBIGUOUS") and (
                    res.get("state") == "AMBIGUOUS" or res.get("start") in pos)
            p("%s:anchor_%s_resolve%s" % (label, which, "" if unique else "_nonunique_context"), good, res)
            first_state[(label, which)] = (res.get("state"), unique)
            ac = a.get("cancel", [])
            ok = len(ac) == 3 and ac[0]["status"] == "CANCELLED" and ac[0]["state"] == "MISSING" and ac[0]["start"] is None
            for row in ac:
                if row["status"] == "CANCELLED":
                    ok = ok and row["start"] is None
                else:
                    ok = ok and row["state"] == res.get("state") and row["start"] == res.get("start")
                ok = ok and row["retry_status"] == "OK" and row["retry_state"] == res.get("state") and \
                    row["retry_start"] == res.get("start") and row["retry_end"] == res.get("end")
            p("%s:anchor_%s_cancel_retry" % (label, which), ok, ac)
    for row in reopen.get("anchors", []):
        state, unique = first_state.get((row["label"], row["which"]), (None, False))
        ok = row["status"] == "OK" and row["state"] == state and (
            row["state"] != "FOUND" or row["start"] == row["expect_start"] and row["end"] == row["expect_end"])
        if unique:
            ok = ok and row["state"] == "FOUND"
        p("%s:anchor_%s_%s_after_reopen" % (row["label"], row["which"], row["route"]), ok, row)
    p("reopen_anchors_present", bool(reopen.get("anchors")) or not any(first_state))
    for label, count in semantic.items():
        got = queries.get(label, {}).get("document_find", {}).get("count")
        p("declared:%s_count==%s" % (label, count), got == count, "got %s" % got)
    if primary:
        got = queries.get("primary_hex", {}).get("document_find", {}).get("count")
        p("declared:primary_query_found", isinstance(got, int) and got >= 1, "got %s" % got)
    return c


def classify_attribution(probe, expected_hex):
    """Where did the original miss come from? Derived from observed bytes, never assumed."""
    queries = {q["label"]: q for q in probe.get("queries", [])}
    argv = queries.get("argv")
    wide = queries.get("wide")
    hexq = queries.get("primary_hex")
    result = {"expected_query_hex": expected_hex}
    if hexq:
        result["hex_query_count"] = hexq["document_find"]["count"]
    if argv:
        result["argv_received_hex"] = argv["hex"]
        result["argv_bytes_equal_expected"] = argv["hex"] == expected_hex
        result["argv_find_count"] = argv["document_find"]["count"]
    if wide:
        result["wide_source"] = wide["source"]
        result["wide_received_hex"] = wide["hex"]
        result["wide_bytes_equal_expected"] = wide["hex"] == expected_hex
        result["wide_find_count"] = wide["document_find"]["count"]
    if argv and hexq:
        if not result["argv_bytes_equal_expected"] and hexq["document_find"]["count"] >= 1:
            result["verdict"] = "consumer: process argv did not carry the UTF-8 query bytes; SDK finds the exact bytes"
        elif result["argv_bytes_equal_expected"] and argv["document_find"]["count"] == hexq["document_find"]["count"]:
            result["verdict"] = "argv carried the exact bytes; SDK find agrees with the exact-byte query"
        else:
            result["verdict"] = "unresolved: exact bytes in argv but results differ"
    return result


# ---------------------------------------------------------------- run

def run_probe(consumer, asset, outdir, queries, primary_text):
    outdir.mkdir(parents=True, exist_ok=True)
    qfile = outdir / "queries.txt"
    qfile.write_text("".join("%s %s\n" % (label, raw.hex()) for label, raw in queries), encoding="ascii")
    cmd = [str(consumer), "--file", str(asset), "--out", str(outdir), "--queries", str(qfile)]
    if primary_text:
        cmd += ["--argv-query", primary_text, "--wide-query", primary_text]
    started = time.time()
    proc = subprocess.run(cmd, capture_output=True, timeout=600)
    stdout = proc.stdout.decode("utf-8", "replace")
    stderr = proc.stderr.decode("utf-8", "replace")
    probe = None
    for line in reversed([l for l in stdout.splitlines() if l.strip()]):
        try:
            probe = json.loads(line)
            break
        except json.JSONDecodeError:
            continue
    return {"command": cmd, "exit_code": proc.returncode, "seconds": round(time.time() - started, 3),
            "stderr": stderr[-4000:]}, probe


def stable_identity_sha256(identity):
    """Identity without the per-runner download bookkeeping (attempt count, CDN final URL)."""
    stable = json.loads(json.dumps(identity))
    for entry in stable.get("files", {}).values():
        entry.pop("download", None)
    return sha256_bytes(json.dumps(stable, sort_keys=True).encode("utf-8"))


def cmd_run(args):
    out = Path(args.out)
    prep = Path(args.prepared)
    identity = json.loads((prep / "identity.json").read_text(encoding="utf-8"))
    summary = {"schema": 1, "package": "C05", "platform": args.platform, "source_commit": args.source_commit,
               "run_id": args.run_id, "attempt": args.attempt, "sdk_label": args.sdk_label,
               "python": sys.version.split()[0], "machine": platform.platform(),
               "consumer": str(args.consumer), "consumer_sha256": sha256_file(args.consumer),
               "identity_sha256": sha256_file(prep / "identity.json"),
               "identity_stable_sha256": stable_identity_sha256(identity), "files": [], "checks": []}
    ok_all = not identity["problems"]
    summary["checks"].append({"name": "f5_identity", "ok": not identity["problems"], "detail": identity["problems"]})
    ids = list(REAL) + list(SYNTHETIC)
    for ident in ids:
        asset = prep / "assets" / (ident + ".fb2")
        original = asset.read_bytes()
        outdir = out / ident
        real = ident in REAL
        queries = list(QUERIES)
        primary_text = REAL[ident]["query"] if real else ""
        expected_hex = primary_text.encode("utf-8").hex()
        if real:
            queries.insert(0, ("primary_hex", primary_text.encode("utf-8")))
        record, probe = run_probe(args.consumer, asset, outdir, queries, primary_text)
        entry = {"id": ident, "real": real, "bytes": len(original), "sha256": sha256_bytes(original),
                 "run": record, "probe_ok": probe is not None and record["exit_code"] == 0}
        if real:
            want = REAL[ident]
            entry["original_identity_ok"] = len(original) == want["bytes"] and sha256_bytes(original) == want["sha256"]
        if not entry["probe_ok"]:
            summary["checks"].append({"name": ident + ":probe_ran", "ok": False, "detail": record["stderr"]})
            summary["files"].append(entry)
            ok_all = False
            continue
        text_path = outdir / "text.bin"
        text = text_path.read_bytes() if text_path.exists() else b""
        readback = outdir / "readback.bin"
        entry["readback_sha256"] = sha256_file(readback) if readback.exists() else None
        entry["text_sha256"] = sha256_bytes(text)
        entry["probe_program"] = probe.get("program")
        entry["projection"] = probe.get("projection")
        sem = {} if real else SYNTHETIC[ident]["semantic"]
        judged = judge_probe(probe, text, original, sem, real, label_prefix=ident + ":")
        judged.add(ident + ":readback_sha256_equals_original", entry["readback_sha256"] == entry["sha256"])
        if real:
            judged.add(ident + ":original_identity", entry["original_identity_ok"])
            entry["attribution"] = classify_attribution(probe, expected_hex)
            queries_by = {q["label"]: q for q in probe["queries"]}
            hexq = queries_by["primary_hex"]
            entry["find_identity"] = {
                "query_utf8_hex": expected_hex, "projection_bytes": len(text),
                "match_offsets": hexq["document_find"]["positions"], "occurrences": hexq["document_find"]["count"],
                "excerpt": hexq.get("excerpt"),
            }
            if args.require_exact_argv:
                judged.add(ident + ":argv_received_exact_bytes", entry["attribution"].get("argv_bytes_equal_expected"))
            judged.add(ident + ":wide_received_exact_bytes", entry["attribution"].get("wide_bytes_equal_expected"))
            judged.add(ident + ":wide_query_finds_like_hex",
                       entry["attribution"].get("wide_find_count") == entry["attribution"].get("hex_query_count"))
        entry["checks_total"] = len(judged.rows)
        entry["checks_failed"] = judged.failed
        summary["checks"].extend(judged.rows)
        summary["files"].append(entry)
        ok_all = ok_all and not judged.failed
    summary["accepted"] = bool(ok_all and all(c["ok"] for c in summary["checks"]))
    summary["checks_total"] = len(summary["checks"])
    summary["checks_failed"] = [c for c in summary["checks"] if not c["ok"]]
    write_json(out / "summary.json", summary)
    print("accepted=%s checks=%d failed=%d" % (summary["accepted"], summary["checks_total"], len(summary["checks_failed"])))
    for c in summary["checks_failed"][:40]:
        print("FAILED", c["name"], c["detail"])
    return 0


# ---------------------------------------------------------------- repro

def cmd_repro(args):
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    prep = Path(args.prepared)
    result = {"schema": 1, "platform": args.platform, "sdk_label": args.sdk_label,
              "consumer": str(args.consumer), "consumer_sha256": sha256_file(args.consumer),
              "f5_consumer_source_sha256": F5_CONSUMER_SHA, "files": []}
    for ident, pin in REAL.items():
        asset = prep / "assets" / (ident + ".fb2")
        odir = out / ident
        odir.mkdir(parents=True, exist_ok=True)
        cmd = [str(args.consumer), "--format", "FB2", "--file", str(asset), "--font", str(args.font),
               "--out", str(odir), "--query", pin["query"]]
        proc = subprocess.run(cmd, capture_output=True, timeout=900)
        stdout = proc.stdout.decode("utf-8", "replace")
        parsed = None
        for line in reversed([l for l in stdout.splitlines() if l.strip()]):
            try:
                parsed = json.loads(line)
                break
            except json.JSONDecodeError:
                continue
        echoed = None
        if parsed:
            echoed = parsed.get("detail", {}).get("find", {}).get("query")
        result["files"].append({
            "id": ident, "exit_code": proc.returncode, "query": pin["query"],
            "query_utf8_hex": pin["query"].encode("utf-8").hex(),
            "echoed_query_hex": echoed.encode("utf-8", "replace").hex() if isinstance(echoed, str) else None,
            "find": parsed.get("ops", {}).get("find") if parsed else None,
            "anchor_capture": parsed.get("ops", {}).get("anchor.capture") if parsed else None,
            "find_detail": parsed.get("detail", {}).get("find") if parsed else None,
            "pages": parsed.get("detail", {}).get("pages") if parsed else None,
            "parsed": parsed is not None, "stderr": proc.stderr.decode("utf-8", "replace")[-2000:]})
    result["reproduced_original_miss"] = any(f["find"] == "miss" for f in result["files"])
    write_json(out / "repro.json", result)
    for f in result["files"]:
        print(f["id"], "find=", f["find"], "echoed=", f["echoed_query_hex"], "sent=", f["query_utf8_hex"])
    return 0


# ---------------------------------------------------------------- aggregate

def cmd_aggregate(args):
    sums = [json.loads(Path(p).read_text(encoding="utf-8")) for p in args.summaries]
    c = Checks()
    c.add("two_platforms", len({s["platform"] for s in sums}) == 2, [s["platform"] for s in sums])
    c.add("same_source_run_attempt", len({(s["source_commit"], s["run_id"], s["attempt"]) for s in sums}) == 1)
    c.add("same_identity", len({s["identity_stable_sha256"] for s in sums}) == 1,
          [(s["platform"], s["identity_stable_sha256"]) for s in sums])
    c.add("each_platform_accepted", all(s["accepted"] for s in sums), [(s["platform"], s["accepted"]) for s in sums])
    by = {s["platform"]: {f["id"]: f for f in s["files"]} for s in sums}
    for ident in list(REAL) + list(SYNTHETIC):
        rows = [by[p].get(ident) for p in by]
        c.add(ident + ":same_input_sha256", len({r and r["sha256"] for r in rows}) == 1)
        c.add(ident + ":same_projection_sha256", len({r and r["text_sha256"] for r in rows}) == 1,
              [(p, by[p].get(ident, {}).get("text_sha256")) for p in by])
    for s in sums:
        for f in s["files"]:
            if f.get("real"):
                att = f["attribution"]
                print(s["platform"], f["id"], att.get("verdict"))
    out = {"schema": 1, "accepted": not c.failed, "checks": c.rows, "checks_failed": c.failed,
           "source_commit": sums[0]["source_commit"], "run_id": sums[0]["run_id"], "attempt": sums[0]["attempt"],
           "platforms": [s["platform"] for s in sums],
           "attribution": {s["platform"]: {f["id"]: f["attribution"] for f in s["files"] if f.get("real")} for s in sums}}
    write_json(args.out, out)
    print("aggregate accepted=%s failed=%d" % (out["accepted"], len(c.failed)))
    return 0 if out["accepted"] else 1


# ---------------------------------------------------------------- selftest

def _good_probe(text, query, label="q"):
    pos = scan(text, query)
    r = {"status": "OK", "count": len(pos), "truncated": False, "first": pos[0] if pos else None,
         "last": pos[-1] if pos else None, "positions": pos[:16]}
    base = (pos[0], pos[0] + len(query)) if pos else (None, None)
    cancels = [{"limit": l, "polls": l, "status": "CANCELLED", "start": None, "end": None, "retry_status": "OK",
                "retry_start": base[0], "retry_end": base[1], "retry_same": True} for l in CANCEL_LIMITS]
    anchors = []
    for which, idx in (("first", 0), ("last", -1)):
        if not pos:
            anchors.append({"which": which, "captured": False})
            continue
        res = {"status": "OK", "state": "FOUND", "start": pos[idx], "end": pos[idx] + len(query)}
        anchors.append({"which": which, "captured": True, "exact_bytes": len(query), "resolve": res,
                        "cancel": [{"limit": i + 1, "status": "CANCELLED", "state": "MISSING", "start": None,
                                    "retry_status": "OK", "retry_state": "FOUND", "retry_start": res["start"],
                                    "retry_end": res["end"]} for i in range(3)]})
    ex = {"offset": pos[0], "bytes": text[pos[0]:pos[0] + len(query)].hex()} if pos else None
    return {"label": label, "source": "hex", "hex": query.hex(), "bytes": len(query), "document_find": dict(r),
            "fixed_find": dict(r), "excerpt": ex, "cancel": cancels, "anchors": anchors}


def cmd_selftest(args):
    text = ("Бретёр и портрет. " * 3 + "Бретёр̈ \U0001F600 портрет конец").encode("utf-8")
    s = text.decode()
    q = _good_probe(text, "портрет".encode(), "portrait")
    probe = {"import": {"ok": True, "readback_ok": True}, "open": {"ok": True},
             "projection": {"bytes": len(text), "valid_utf8": True, "scalars": len(s),
                            "nonbmp": 1, "cr": 0, "lf": 0, "nul": 0, "combining": 1},
             "memory_route": {"same": True}, "fixed_text": {"status": "OK"},
             "reopen": {"status": "OK", "same": True, "anchors": [
                 {"label": "portrait", "which": w, "route": r, "status": "OK", "state": "FOUND",
                  "start": scan(text, "портрет".encode())[i], "end": scan(text, "портрет".encode())[i] + 14,
                  "expect_start": scan(text, "портрет".encode())[i], "expect_end": scan(text, "портрет".encode())[i] + 14}
                 for w, i in (("first", 0), ("last", -1)) for r in ("file", "memory")]},
             "queries": [q]}
    base = judge_probe(probe, text, b"", {"portrait": 4}, False)
    assert not base.failed, base.failed
    bad = json.loads(json.dumps(probe))
    bad["queries"][0]["document_find"]["count"] -= 1
    assert judge_probe(bad, text, b"", {}, False).failed, "wrong count accepted"
    bad = json.loads(json.dumps(probe))
    bad["queries"][0]["cancel"][0]["status"] = "OK"
    assert judge_probe(bad, text, b"", {}, False).failed, "uncancelled first poll accepted"
    bad = json.loads(json.dumps(probe))
    bad["queries"][0]["anchors"][0]["resolve"]["state"] = "MISSING"
    assert judge_probe(bad, text, b"", {}, False).failed, "missing anchor accepted"
    assert judge_probe(probe, text, b"", {"portrait": 5}, False).failed, "wrong declared count accepted"
    assert judge_probe(probe, text, b"", {}, True).failed, "missing primary_hex accepted"
    assert valid_utf8(b"abc") and not valid_utf8(b"\xff") and not valid_utf8(b"\xd0")
    assert unique_context(text, scan(text, "портрет".encode()), "портрет".encode()) == [True, True, True, True]
    print("selftest ok")
    return 0


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prepare"); p.add_argument("--out", required=True)
    p = sub.add_parser("run")
    p.add_argument("--prepared", required=True); p.add_argument("--consumer", required=True)
    p.add_argument("--out", required=True); p.add_argument("--platform", required=True)
    p.add_argument("--source-commit", required=True); p.add_argument("--run-id", required=True)
    p.add_argument("--attempt", required=True); p.add_argument("--sdk-label", required=True)
    p.add_argument("--require-exact-argv", action="store_true")
    p = sub.add_parser("repro")
    p.add_argument("--prepared", required=True); p.add_argument("--consumer", required=True)
    p.add_argument("--font", required=True); p.add_argument("--out", required=True)
    p.add_argument("--platform", required=True); p.add_argument("--sdk-label", required=True)
    p = sub.add_parser("aggregate")
    p.add_argument("--summaries", nargs="+", required=True); p.add_argument("--out", required=True)
    sub.add_parser("selftest")
    args = ap.parse_args()
    return {"prepare": cmd_prepare, "run": cmd_run, "repro": cmd_repro, "aggregate": cmd_aggregate,
            "selftest": cmd_selftest}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
