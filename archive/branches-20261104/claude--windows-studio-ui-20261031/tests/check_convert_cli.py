#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""WP12-lite tool scenarios: single/batch success, file protection, failure
recovery, cancellation and report consistency. Runs the installed tool as a
real process; it does not call SDK internals."""
import argparse
import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()

class Runner:
    def __init__(self, tool, work, corpus):
        self.tool = str(tool)
        self.work = Path(work)
        self.corpus = Path(corpus)
        self.scenarios = []
        self.failed = 0
        if self.work.exists():
            shutil.rmtree(self.work)
        self.work.mkdir(parents=True)
    def run(self, args, cwd=None, timeout=120):
        started = time.time()
        proc = subprocess.run([self.tool] + [str(a) for a in args], cwd=str(cwd or self.work),
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
        return proc.returncode, proc.stdout.decode("utf-8", "replace"), proc.stderr.decode("utf-8", "replace"), time.time() - started
    def record(self, name, expected, actual, ok, stdout="", stderr="", detail=""):
        self.scenarios.append({"id": name, "expected": expected, "actual": actual,
                               "status": "pass" if ok else "fail", "detail": detail,
                               "stdout": stdout, "stderr": stderr})
        if not ok:
            self.failed += 1
            print("FAIL %s: expected %r actual %r %s" % (name, expected, actual, detail), file=sys.stderr)
        else:
            print("PASS %s" % name)
    def expect(self, name, expected, code, stdout="", stderr="", detail="", ok=None):
        good = (code == expected) if ok is None else ok
        self.record(name, expected, code, good, stdout, stderr, detail)
        return good
    def report(self, path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

def write_text(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)

def manifest(path, items, **top):
    data = {"schema": 1, "items": items}
    data.update(top)
    write_text(path, json.dumps(data, ensure_ascii=False, indent=2))

def scenario_capabilities(r):
    code, out, err, _ = r.run(["--capabilities"])
    ok = code == 0
    data = json.loads(out) if ok and out.strip().startswith("{") else {}
    ok = ok and data.get("schema") == 1 and "text" in data.get("profiles", {}) and "preserve" in data.get("profiles", {})
    ok = ok and "mobi" in data["profiles"]["text"]["inputs"] and "kf8" in data["profiles"]["text"]["inputs"]
    ok = ok and "pdf" in data["unsupported"]["targets"]
    r.record("capabilities", "json profiles and unsupported list", "schema=%s" % data.get("schema"), ok, out, err)

def scenario_single_matrix(r):
    cases = [("txt", "epub"), ("html", "fb2"), ("epub", "docx"), ("rtf", "txt"),
             ("docx", "html"), ("fb2", "rtf"), ("epub", "html")]
    for index, (source_format, target) in enumerate(cases):
        source = r.corpus / "text" / source_format / ("ascii.%s" % source_format)
        output = r.work / ("single-%d.%s" % (index, target))
        report = r.work / ("single-%d.json" % index)
        code, out, err, _ = r.run(["--input", source, "--to", target, "--output", output,
                                   "--report", report])
        ok = code == 0 and output.is_file()
        detail = ""
        if ok:
            data = r.report(report)
            item = data["items"][0]
            ok = item["status"] == "ok" and item["published"] and item["reopen_verified"]
            ok = ok and item["output_sha256"] == sha256(output)
            ok = ok and data["counts"]["succeeded"] == 1 and data["batch_complete"] is True
            detail = item.get("error", "")
        r.record("single-%s-to-%s" % (source_format, target), "ok published verified", code, ok, out, err, detail)

def scenario_default_and_alias(r):
    source = r.corpus / "text" / "txt" / "chinese.txt"
    code, out, err, _ = r.run(["--input", source, "--to", "epub"])
    output = source.with_suffix(".epub")
    ok = code == 0 and output.is_file()
    if output.exists():
        output.unlink()
    r.record("default-output-name", "next to input with target extension", code, ok, out, err)
    # XHTML alias and an explicit format on a non-matching extension.
    xhtml = r.corpus / "text" / "html" / "ascii.html"
    renamed = r.work / "alias.xhtml"
    shutil.copyfile(xhtml, renamed)
    code, out, err, _ = r.run(["--input", renamed, "--to", "fb2", "--output", r.work / "alias.fb2"])
    ok = code == 0 and (r.work / "alias.fb2").is_file()
    r.record("xhtml-alias", "html/xhtml logical alias", code, ok, out, err)
    disguised = r.work / "declared.dat"
    shutil.copyfile(xhtml, disguised)
    code, out, err, _ = r.run(["--input", disguised, "--from", "html", "--to", "epub",
                               "--output", r.work / "declared.epub"])
    ok = code == 0 and (r.work / "declared.epub").is_file()
    r.record("explicit-format", "explicit --from overrides extension", code, ok, out, err)
    weird = r.work / "arbitrary-output-name.dat"
    code, out, err, _ = r.run(["--input", r.corpus / "text" / "txt" / "ascii.txt", "--to", "epub",
                               "--output", weird])
    ok = code == 0 and weird.is_file()
    r.record("arbitrary-output-extension", "verification uses declared target format", code, ok, out, err)
    upper = r.work / "UPPER.TXT"
    write_text(upper, "Uppercase extension.\n")
    code, out, err, _ = r.run(["--input", upper, "--to", "html", "--output", r.work / "upper.html"])
    ok = code == 0 and (r.work / "upper.html").is_file()
    r.record("uppercase-extension", "case-insensitive extension", code, ok, out, err)

def scenario_preserve(r):
    epubs = sorted((r.corpus / "preserve" / "epub").glob("*.epub"))
    for index, source in enumerate(epubs[:2]):
        report = r.work / ("preserve-%d.json" % index)
        code, out, err, _ = r.run(["--input", source, "--to", "epub", "--profile", "preserve",
                                   "--output", r.work / ("preserve-%d.epub" % index), "--report", report])
        ok = code == 0 and (r.work / ("preserve-%d.epub" % index)).is_file()
        detail = ""
        if ok:
            item = r.report(report)["items"][0]
            ok = item["profile"] == "preserve" and item["status"] == "ok" and item["reopen_verified"]
            detail = item.get("error", "")
        r.record("preserve-epub-%d" % index, "epub->epub structure preserved", code, ok, out, err, detail)
    source = epubs[0]
    code, out, err, _ = r.run(["--input", source, "--to", "html", "--profile", "preserve",
                               "--output", r.work / "bundle.zip", "--report", r.work / "bundle.json"])
    ok = code == 0 and (r.work / "bundle.zip").is_file()
    detail = ""
    if ok:
        item = r.report(r.work / "bundle.json")["items"][0]
        ok = item["entry_path"] and item["reopen_verified"] and item["status"] == "ok"
        detail = "entry=%s" % item.get("entry_path")
    r.record("preserve-epub-html-bundle", "single zip with entry path", code, ok, out, err, detail)
    xhtml = sorted((r.corpus / "preserve" / "xhtml").glob("*.xhtml"))[0]
    for target in ("epub", "html"):
        output = r.work / ("xhtml.%s" % ("zip" if target == "html" else target))
        code, out, err, _ = r.run(["--input", xhtml, "--to", target, "--profile", "preserve",
                                   "--output", output, "--report", r.work / ("xhtml-%s.json" % target)])
        ok = code == 0 and output.is_file()
        detail = ""
        if ok:
            item = r.report(r.work / ("xhtml-%s.json" % target))["items"][0]
            ok = item["status"] == "ok" and item["reopen_verified"]
            detail = item.get("error", "")
        r.record("preserve-xhtml-to-%s" % target, "xhtml preserve export", code, ok, out, err, detail)
    txt = r.corpus / "text" / "txt" / "ascii.txt"
    code, out, err, _ = r.run(["--input", txt, "--to", "epub", "--profile", "preserve",
                               "--output", r.work / "unsupported.epub"])
    ok = code == 3 and not (r.work / "unsupported.epub").exists()
    r.record("preserve-unsupported", "reject, no text fallback", code, ok, out, err)
    # Missing resource must fail atomically and leave no output.
    import zipfile
    broken = r.work / "missing-resource.epub"
    with zipfile.ZipFile(epubs[0], "r") as source_zip, zipfile.ZipFile(broken, "w") as target_zip:
        for info in source_zip.infolist():
            if info.filename.endswith("images/a/pic.png"):
                continue
            target_zip.writestr(info, source_zip.read(info.filename))
    broken_out = r.work / "missing-resource-out.epub"
    code, out, err, _ = r.run(["--input", broken, "--to", "epub", "--profile", "preserve",
                               "--output", broken_out, "--report", r.work / "missing-resource.json"])
    ok = code == 3 and not broken_out.exists()
    detail = ""
    if (r.work / "missing-resource.json").exists():
        item = r.report(r.work / "missing-resource.json")["items"][0]
        ok = ok and item["status"] == "failed" and item["published"] is False
        detail = "stage=%s error=%s" % (item["stage"], item["error"])
    r.record("preserve-missing-resource", "atomic failure, no published output", code, ok, out, err, detail)

def scenario_batch(r):
    a = r.work / "batch" / "a.txt"
    b = r.work / "batch" / "b.txt"
    write_text(a, "Batch alpha.\n第二段。\n")
    write_text(b, "Batch beta.\n")
    out = r.work / "batch-out"
    out.mkdir(parents=True)
    m = r.work / "batch.json"
    manifest(m, [{"id": "a", "input": "a.txt", "to": "epub"},
                 {"id": "b", "input": "b.txt", "to": "html"}], root="batch", output_root="batch-out")
    report = r.work / "batch-report.json"
    code, stdout, err, _ = r.run(["--batch", m, "--report", report])
    ok = code == 0 and (out / "a.epub").is_file() and (out / "b.html").is_file()
    if ok:
        data = r.report(report)
        ok = data["counts"]["succeeded"] == 2 and data["batch_complete"] is True
        ok = ok and data["items"][0]["output"].lower().endswith("a.epub")
    r.record("batch-success", "2 items, output_root", code, ok, stdout, err)
    m2 = r.work / "batch-mixed.json"
    manifest(m2, [{"id": "a", "input": "a.txt", "to": "epub"},
                  {"id": "missing", "input": "missing.txt", "to": "epub"},
                  {"id": "b", "input": "b.txt", "to": "fb2"}],
             root="batch", output_root="batch-out-2")
    (r.work / "batch-out-2").mkdir(exist_ok=True)
    report2 = r.work / "batch-mixed-report.json"
    code, stdout, err, _ = r.run(["--batch", m2, "--report", report2])
    ok = code == 3 and (r.work / "batch-out-2" / "b.fb2").is_file()
    if ok:
        data = r.report(report2)
        statuses = {item["id"]: item["status"] for item in data["items"]}
        ok = statuses.get("a") == "ok" and statuses.get("missing") == "rejected" and statuses.get("b") == "ok"
        ok = ok and data["counts"]["failed"] + data["counts"]["rejected"] == 1 and data["batch_complete"] is False
    r.record("batch-mixed", "success and rejection both retained", code, ok, stdout, err)
    m3 = r.work / "batch-duplicate.json"
    manifest(m3, [{"id": "one", "input": "a.txt", "to": "epub", "output": "same.epub"},
                  {"id": "two", "input": "b.txt", "to": "epub", "output": "same.epub"}],
             root="batch", output_root="batch-out-3")
    (r.work / "batch-out-3").mkdir(exist_ok=True)
    code, stdout, err, _ = r.run(["--batch", m3, "--report", r.work / "duplicate.json"])
    ok = code == 3 and not (r.work / "batch-out-3" / "same.epub").exists()
    r.record("batch-duplicate-output", "preflight rejects duplicate output", code, ok, stdout, err)
    write_text(r.work / "bad-manifest.json", "{not json")
    code, stdout, err, _ = r.run(["--batch", r.work / "bad-manifest.json"])
    ok = code == 2
    r.record("bad-manifest", "usage error", code, ok, stdout, err)
    m4 = r.work / "duplicate-id.json"
    manifest(m4, [{"id": "same", "input": "a.txt", "to": "epub"},
                  {"id": "same", "input": "b.txt", "to": "epub"}], root="batch", output_root="batch-out-4")
    (r.work / "batch-out-4").mkdir(exist_ok=True)
    code, stdout, err, _ = r.run(["--batch", m4])
    ok = code == 2
    r.record("duplicate-manifest-id", "usage error before conversion", code, ok, stdout, err)

def scenario_protection(r):
    source = r.work / "protect" / "a.txt"
    write_text(source, "Protect me.\n")
    original = sha256(source)
    report = r.work / "same.json"
    code, stdout, err, _ = r.run(["--input", source, "--to", "txt", "--output", source, "--report", report])
    ok = code == 3 and sha256(source) == original
    if report.exists():
        item = r.report(report)["items"][0]
        ok = ok and item["status"] == "rejected" and item["published"] is False
    r.record("source-equals-target", "reject same file", code, ok, stdout, err)
    case_alias = r.work / "protect" / "A.TXT"
    case_same = case_alias.exists() and os.path.samefile(source, case_alias)
    code, stdout, err, _ = r.run(["--input", source, "--to", "epub", "--output", case_alias])
    ok = code == (3 if case_same else 0) and sha256(source) == original
    if not case_same:
        ok = ok and case_alias.is_file() and case_alias.read_bytes()[:2] == b"PK"
    r.record("source-target-case-alias", "reject same file; allow distinct case-sensitive path", code, ok, stdout, err)
    link = r.work / "protect" / "link.txt"
    try:
        os.link(source, link)
        hardlink_ok = True
    except OSError:
        hardlink_ok = False
    if hardlink_ok:
        code, stdout, err, _ = r.run(["--input", source, "--to", "epub", "--output", link])
        ok = code == 3 and sha256(source) == original
        r.record("source-target-hardlink", "reject existing link to same file", code, ok, stdout, err)
    existing = r.work / "protect" / "existing.epub"
    existing.write_bytes(b"old bytes")
    old_hash = sha256(existing)
    code, stdout, err, _ = r.run(["--input", source, "--to", "epub", "--output", existing])
    ok = code == 3 and sha256(existing) == old_hash
    r.record("existing-target", "no overwrite preserves old bytes", code, ok, stdout, err)
    code, stdout, err, _ = r.run(["--input", source, "--to", "epub", "--output", existing, "--overwrite"])
    ok = code == 0 and sha256(existing) != old_hash and existing.read_bytes()[:2] == b"PK"
    leftovers = list(existing.parent.glob(".*.tmp"))
    r.record("explicit-overwrite", "overwrite after temporary publication", code, ok, stdout, err,
             "leftovers=%d" % len(leftovers))
    if os.name == "nt":
        junction = source.parent / "aliasdir"
        made = subprocess.run(["cmd", "/c", "mklink", "/J", str(junction), str(source.parent)],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
        if made:
            code, stdout, err, _ = r.run(["--input", source, "--to", "txt",
                                          "--output", junction / source.name, "--overwrite"])
            ok = code == 3 and sha256(source) == original
            r.record("source-target-junction", "reject junction alias to same file", code, ok, stdout, err)
            try:
                os.rmdir(junction)
            except OSError:
                pass
    else:
        linkdir = r.work / "protect-link"
        linkdir.mkdir()
        alias = linkdir / "a.txt"
        os.symlink(source, alias)
        code, stdout, err, _ = r.run(["--input", source, "--to", "txt", "--output", alias, "--overwrite"])
        ok = code == 3 and sha256(source) == original
        r.record("source-target-symlink", "reject symlink alias to same file", code, ok, stdout, err)
    code, stdout, err, _ = r.run(["--input", source, "--to", "epub", "--output", r.work / "missing" / "x.epub"])
    ok = code == 3 and not (r.work / "missing" / "x.epub").exists()
    r.record("write-failure", "missing parent reports write failure", code, ok, stdout, err)
    target_dir = r.work / "protect" / "target-dir"
    target_dir.mkdir()
    code, stdout, err, _ = r.run(["--input", source, "--to", "epub", "--output", target_dir, "--overwrite"])
    ok = code == 3 and target_dir.is_dir() and not list(target_dir.iterdir())
    r.record("publish-failure", "target directory unchanged and temp cleaned", code, ok, stdout, err)

def scenario_batch_path_errors(r):
    directory = r.work / "batch-path-errors"
    source, good = directory / "source.txt", directory / "good.txt"
    write_text(source, "Independent conversion.")
    bad = directory / ("bad?.txt" if os.name == "nt" else "a" * 300 + ".txt")
    m, report = directory / "manifest.json", directory / "report.json"
    manifest(m, [{"id": "bad", "input": str(source), "to": "txt", "output": str(bad)},
                 {"id": "good", "input": str(source), "to": "txt", "output": str(good)}])
    code, stdout, err, _ = r.run(["--batch", m, "--report", report])
    data = r.report(report) if report.is_file() else {}
    statuses = {item["id"]: item["status"] for item in data.get("items", [])}
    ok = code == 3 and statuses == {"bad": "rejected", "good": "ok"}
    ok = ok and good.read_bytes() == source.read_bytes() and not list(directory.glob("*.tmp"))
    r.record("batch-invalid-output-path", "reject invalid path and publish independent item", code, ok, stdout, err)


def scenario_unicode_output_aliases(r):
    if os.name != "nt":
        return
    # The second pair has different UTF-8 byte lengths but the same Windows name.
    for name, first, second, alias in (("accent", "É.txt", "é.txt", True),
                                      ("unequal-utf8", "Ⱥ.txt", "ⱥ.txt", True),
                                      ("distinct-long-s", "ſ.txt", "S.txt", False)):
        directory = r.work / ("unicode-alias-" + name)
        a, b, good = directory / "a.txt", directory / "b.txt", directory / "good.txt"
        write_text(a, "First source.")
        write_text(b, "Second source.")
        m = directory / "manifest.json"
        manifest(m, [{"id": "one", "input": str(a), "to": "txt", "output": first},
                     {"id": "two", "input": str(b), "to": "txt", "output": second},
                     {"id": "good", "input": str(a), "to": "txt", "output": good.name}], overwrite=True)
        code, stdout, err, _ = r.run(["--batch", m])
        data = json.loads(stdout) if stdout.strip().startswith("{") else {}
        statuses = {item["id"]: item["status"] for item in data.get("items", [])}
        if alias:
            ok = code == 3 and statuses == {"one": "rejected", "two": "rejected", "good": "ok"}
            ok = ok and not (directory / first).exists() and not (directory / second).exists()
        else:
            ok = code == 0 and statuses == {"one": "ok", "two": "ok", "good": "ok"}
            ok = ok and (directory / first).read_bytes() == a.read_bytes() and (directory / second).read_bytes() == b.read_bytes()
        ok = ok and good.read_bytes() == a.read_bytes()
        r.record("unicode-output-alias-" + name, "reject filesystem aliases; retain distinct names", code, ok, stdout, err)


def scenario_manifest_protection(r):
    for name in ("direct", "overwrite", "hardlink"):
        directory = r.work / ("manifest-report-" + name)
        source, output = directory / "source.txt", directory / "output.txt"
        write_text(source, "Preserve the batch configuration.")
        m = directory / "manifest.json"
        manifest(m, [{"input": str(source), "to": "txt", "output": str(output)}])
        before = sha256(m)
        report = m
        if name == "hardlink":
            report = directory / "alias.json"
            os.link(m, report)
        code, stdout, err, _ = r.run(["--batch", m, "--report", report] +
                                      (["--overwrite"] if name == "overwrite" else []))
        ok = code == 2 and sha256(m) == before and sha256(report) == before and not output.exists()
        ok = ok and not list(directory.glob("*.tmp"))
        r.record("manifest-report-" + name, "reject report/manifest collision before conversion", code, ok, stdout, err)
    for name in ("direct", "hardlink"):
        directory = r.work / ("manifest-output-" + name)
        source, good = directory / "source.txt", directory / "good.txt"
        write_text(source, "Independent conversion.")
        m = directory / "manifest.json"
        target = m if name == "direct" else directory / "alias.json"
        manifest(m, [{"id": "bad", "input": str(source), "to": "txt", "output": str(target)},
                     {"id": "good", "input": str(source), "to": "txt", "output": str(good)}], overwrite=True)
        if name == "hardlink":
            os.link(m, target)
        before = sha256(m)
        code, stdout, err, _ = r.run(["--batch", m])
        data = json.loads(stdout) if stdout.strip().startswith("{") else {}
        statuses = {item["id"]: item["status"] for item in data.get("items", [])}
        ok = code == 3 and statuses == {"bad": "rejected", "good": "ok"}
        ok = ok and sha256(m) == before and sha256(target) == before and good.read_bytes() == source.read_bytes()
        r.record("manifest-output-" + name, "preserve manifest and publish independent item", code, ok, stdout, err)


def scenario_paths_and_limit(r):
    directory = r.work / "中文 空格"
    source = directory / "输入 文件.txt"
    write_text(source, "中文路径与空格。\n第二段。\n")
    output = directory / "输出 文件.epub"
    code, stdout, err, _ = r.run(["--input", source, "--to", "epub", "--output", output])
    ok = code == 0 and output.is_file()
    r.record("unicode-space-path", "UTF-8 path through real file I/O", code, ok, stdout, err)
    # Report publication failure after outputs exist.
    report = r.work / "no-such-dir" / "report.json"
    output2 = r.work / "report-failure.epub"
    code, stdout, err, _ = r.run(["--input", source, "--to", "epub", "--output", output2, "--report", report])
    ok = code == 4 and output2.is_file() and not report.exists()
    ok = ok and ("published outputs" in err) and str(output2) in err
    r.record("report-write-failure", "exit 4 and list published outputs", code, ok, stdout, err)
    # Limit: 513 MiB is above the tool's 512 MiB declared ceiling.
    big = r.work / "too-big.txt"
    with open(big, "wb") as f:
        f.truncate(513 * 1024 * 1024)
    code, stdout, err, _ = r.run(["--input", big, "--to", "epub", "--output", r.work / "too-big.epub"], timeout=300)
    ok = code == 3 and not (r.work / "too-big.epub").exists() and "512" in (stdout + err)
    r.record("input-limit", "over-limit input rejected", code, ok, stdout, err)
    big.unlink()

def scenario_cancel(r):
    source = r.corpus / "long" / "one-mib.txt"
    out = r.work / "cancel-out"
    out.mkdir()
    items = []
    for i in range(100):
        items.append({"id": "c%03d" % i, "input": str(source), "to": "epub",
                      "output": "c%03d.epub" % i})
    m = r.work / "cancel.json"
    manifest(m, items, output_root="cancel-out")
    report = r.work / "cancel-report.json"
    proc = subprocess.Popen([r.tool, "--batch", str(m), "--report", str(report)],
                            cwd=str(r.work), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0)
    deadline = time.monotonic() + 120
    while proc.poll() is None and not any(out.glob("c*.epub")) and time.monotonic() < deadline:
        time.sleep(0.05)
    published_before_cancel = any(out.glob("c*.epub"))
    if proc.poll() is None:
        proc.send_signal(signal.CTRL_BREAK_EVENT if os.name == "nt" else signal.SIGINT)
    stdout, stderr = proc.communicate(timeout=300)
    stdout = stdout.decode("utf-8", "replace")
    stderr = stderr.decode("utf-8", "replace")
    code = proc.returncode
    ok = code == 3 and report.exists() and published_before_cancel
    detail = ""
    if ok:
        data = r.report(report)
        statuses = [item["status"] for item in data["items"]]
        ok = ("ok" in statuses) and (("cancelled" in statuses) or ("unfinished" in statuses))
        ok = ok and data["batch_complete"] is False and data["cancel_requested"] is True
        leftovers = [p.name for p in out.iterdir() if ".tmp" in p.name]
        ok = ok and not leftovers
        for item in data["items"]:
            if item["published"]:
                path = Path(item["output"])
                ok = ok and path.is_file() and path.stat().st_size > 0
        detail = "statuses=%s" % {s: statuses.count(s) for s in set(statuses)}
    r.record("cancel-batch", "signal leaves report and no temp files", code, ok, stdout, stderr, detail)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("tool")
    parser.add_argument("corpus")
    parser.add_argument("work")
    parser.add_argument("json")
    args = parser.parse_args()
    r = Runner(args.tool, args.work, args.corpus)
    started = time.time()
    scenario_capabilities(r)
    scenario_single_matrix(r)
    scenario_default_and_alias(r)
    scenario_preserve(r)
    scenario_batch(r)
    scenario_protection(r)
    scenario_batch_path_errors(r)
    scenario_unicode_output_aliases(r)
    scenario_manifest_protection(r)
    scenario_paths_and_limit(r)
    scenario_cancel(r)
    expected = len(r.scenarios)
    passed = expected - r.failed
    evidence = {"schema": 1, "kind": "cli-scenarios", "tool": str(Path(args.tool).resolve()),
                "corpus": str(Path(args.corpus).resolve()), "expected": expected, "actual": expected,
                "passed": passed, "failed": r.failed, "elapsed_seconds": round(time.time() - started, 3),
                "scenarios": r.scenarios}
    Path(args.json).parent.mkdir(parents=True, exist_ok=True)
    with open(args.json, "w", encoding="utf-8", newline="\n") as f:
        json.dump(evidence, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print("%d scenarios, %d passed, %d failed" % (expected, passed, r.failed))
    return 0 if r.failed == 0 else 1

if __name__ == "__main__":
    sys.exit(main())
