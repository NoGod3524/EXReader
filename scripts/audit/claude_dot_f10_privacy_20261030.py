#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""F10 privacy / credential / temp-file cleanup auditor (package C04, 20261030).

Everything here uses SYNTHETIC canaries generated at run time; no real credential,
keychain, token or user file is ever read. Subcommands:

  scope      changed paths vs. the exact base are only this package's owned paths
  selftest   detectors catch planted leaks in every encoding and pass clean trees
  static     production-source inventory: temp-file sites without cleanup evidence,
             credential-named values passed to log/print calls (no allowlists)
  summary    bind identities and fold the reports into one source-bound verdict

A report only speaks for the exact commit/run/attempt/platform it records. It never
grants F10, full P0 or acceptance; see the CLAUDE_DOT_C04 handoff document.
"""
import argparse, base64, hashlib, json, os, platform, re, secrets, shutil, subprocess, sys, tempfile
from pathlib import Path
from urllib.parse import quote_from_bytes

BASE = "c46f7036d81f88d8529871590f780b5430630e47"
OWNED = (
    r"^tests/reader_final_privacy_20261030/",
    r"^\.github/workflows/claude_dot_f10_privacy_20261030\.yml$",
    r"^scripts/audit/claude_dot_f10_privacy_20261030\.py$",
    r"^docs/reader-total-progress/CLAUDE_DOT_C04_20261030\.md$",
)
PROD_ROOTS = ("src/", "include/", "extras/", "apps/", "examples/", "tools/", "bindings/")
CODE_SUFFIX = (".c", ".h", ".cc", ".cpp", ".inc", ".m", ".mm", ".swift", ".java", ".kt", ".py")
SKIP_PARTS = ("third_party", "thirdparty", "vendor", "external", "node_modules", "Pods",
              "/tests/", "/test/", "androidTest", "/uitest/", "UITests", "/Tests/", "fixtures")
MIN_CANARY = 16


# ---------------------------------------------------------------- canaries
def variants(secret: bytes) -> dict:
    """Every encoding in which a secret could reach a file, stream or file name."""
    if len(secret) < MIN_CANARY:
        raise ValueError("canary too short to be discriminating")
    out = {"raw": secret, "hex_lower": secret.hex().encode(), "hex_upper": secret.hex().upper().encode(),
           "percent": quote_from_bytes(secret, safe="").encode()}
    try:
        out["utf16le"] = secret.decode("utf-8").encode("utf-16-le")
    except UnicodeDecodeError:
        pass
    for pad in range(3):
        text = base64.b64encode(b"\0" * pad + secret).decode().rstrip("=")
        text = text[(pad * 8) // 6 + 1 if pad else 0:-1]  # edges depend on neighbouring bytes
        out[f"b64_pad{pad}"] = text.encode()
        out[f"b64url_pad{pad}"] = text.replace("+", "-").replace("/", "_").encode()
    return out


def scan_bytes(label: str, data: bytes, table: dict) -> list:
    return [{"where": label, "variant": name} for name, needle in table.items() if needle and needle in data]


def scan_tree(root: Path, table: dict) -> dict:
    hits, files, total = [], 0, 0
    for path in sorted(root.rglob("*")):
        rel = str(path.relative_to(root))
        hits += scan_bytes("name:" + rel, rel.encode("utf-8", "surrogateescape"), table)
        if path.is_symlink() or not path.is_file():
            continue
        data = path.read_bytes()
        files += 1
        total += len(data)
        hits += scan_bytes("content:" + rel, data, table)
    return {"files": files, "bytes": total, "hits": hits}


# ---------------------------------------------------------------- static
TEMP_RE = re.compile(r"\b(g_mkstemp_full|g_mkstemp|g_mkdtemp_full|g_mkdtemp|mkstemp|mkdtemp|tmpfile|tmpnam|tempnam|"
                     r"GetTempPath[AW]?|GetTempFileName[AW]?|NSTemporaryDirectory|temporaryDirectory|createTempFile|"
                     r"createTempDirectory|NamedTemporaryFile|TemporaryDirectory|g_get_tmp_dir)\b")
CLEAN_RE = re.compile(r"\b(unlink|unlinkat|remove|g_remove|g_unlink|rmtree|DeleteFile[AW]?|removeItem|"
                      r"removeItemAtPath|deleteRecursively|deleteIfExists|rmdir|g_rmdir)\s*\(|\.delete\(|\.cleanup\(|"
                      r"FILE_FLAG_DELETE_ON_CLOSE|O_TMPFILE|\bos\.(remove|unlink)\b")
LOG_RE = re.compile(r"\b(printf|fprintf|puts|perror|syslog|NSLog|os_log|g_message|g_warning|g_debug|g_critical|"
                    r"g_printerr|g_print|OutputDebugString[AW]?|__android_log_print|Log\.[a-z]\w*|"
                    r"System\.(?:out|err)\.print\w*|std::cerr|std::cout|cerr|cout|print|logger\.\w+|logging\.\w+)\b")
SECRET_ID = re.compile(r"\b\w*(?:password|passwd|secret|credential|apikey|api_key|bearer|authorization|"
                       r"(?:access|refresh|auth|session|api)_?token)\w*\b", re.I)
SAFE_ID = re.compile(r"(?:length|len|size|count|max|status|state|name|kind|type|ok|valid|present|exists|path|"
                     r"namespace|backend|available|unavailable|id)$", re.I)
LITERAL = re.compile(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'')
USER_PATH = re.compile(r"(?:[A-Za-z]:\\+Users\\+|/Users/|/home/)([A-Za-z0-9._-]+)")
WINDOW = 150


def tracked(repo: Path) -> list:
    out = subprocess.run(["git", "-C", str(repo), "ls-files", "-z"], capture_output=True, check=True).stdout
    return [p for p in out.decode().split("\0") if p]


def is_production(rel: str) -> bool:
    return rel.startswith(PROD_ROOTS) and rel.endswith(CODE_SUFFIX) and not any(s in "/" + rel for s in SKIP_PARTS)


def is_comment(line: str) -> bool:
    s = line.lstrip()
    return s.startswith(("//", "/*", "*", "#")) and not s.startswith("#include")


def static_audit(repo: Path) -> dict:
    sites, leaks, paths, scanned = [], [], {}, 0
    for rel in tracked(repo):
        if not is_production(rel):
            continue
        try:
            lines = (repo / rel).read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        scanned += 1
        for i, line in enumerate(lines):
            m_path = USER_PATH.search(line)
            if m_path:
                paths[rel] = paths.get(rel, 0) + 1
            if is_comment(line) or re.match(r"\s*(from\s+\S+\s+)?import\b", line):
                continue
            code = LITERAL.sub('""', line)
            m = TEMP_RE.search(code)
            if m:
                window = "\n".join(lines[max(0, i - WINDOW):i + WINDOW + 1])
                if m.group(1) == "tmpfile":
                    verdict = "auto-unlinked-tmpfile"
                elif m.group(1) in ("TemporaryDirectory", "NamedTemporaryFile") and re.match(r"\s*(async\s+)?with\b", code):
                    verdict = "context-managed-cleanup"
                else:
                    verdict = "cleanup-paired" if CLEAN_RE.search(window) else "unproven"
                sites.append({"file": rel, "line": i + 1, "api": m.group(1), "verdict": verdict})
            if LOG_RE.search(code):
                for ident in [x.group(0) for x in SECRET_ID.finditer(code)]:
                    if not SAFE_ID.search(ident):
                        leaks.append({"file": rel, "line": i + 1, "identifier": ident})
    unproven = [s for s in sites if s["verdict"] == "unproven"]
    return {"scanned_files": scanned, "temp_sites": sites, "temp_sites_unproven": unproven,
            "credential_log_candidates": leaks,
            "user_path_inventory_informational": {"files": len(paths), "occurrences": sum(paths.values()),
                                                  "top": sorted(paths.items(), key=lambda kv: -kv[1])[:20]},
            "limitations": ["line-based: multi-line log calls and indirect wrappers are not seen",
                            "cleanup evidence is textual proximity (+/-%d lines), not execution" % WINDOW,
                            "no allowlist of users, files or identifiers is applied"],
            "gate_passed": not unproven and not leaks}


# ---------------------------------------------------------------- selftest
def selftest() -> dict:
    cases, canary = [], secrets.token_bytes(20).hex().encode() + "-päss".encode()
    table = variants(canary)
    root = Path(tempfile.mkdtemp(prefix="f10-selftest-"))
    try:
        planted = root / "planted"
        planted.mkdir()
        encodings = {"raw": canary, "hex_lower": canary.hex().encode(), "hex_upper": canary.hex().upper().encode(),
                     "percent": quote_from_bytes(canary, safe="").encode(), "utf16le": canary.decode().encode("utf-16-le")}
        for pad in range(3):
            raw = base64.b64encode(b"AB"[:pad] + canary + b"xyz")
            encodings[f"b64_pad{pad}"] = raw
            encodings[f"b64url_pad{pad}"] = raw.replace(b"+", b"-").replace(b"/", b"_")
        for name, blob in encodings.items():
            (planted / f"{name}.bin").write_bytes(b"prefix:" + blob + b":suffix")
            found = {h["variant"] for h in scan_tree(planted, table)["hits"] if h["where"] == f"content:{name}.bin"}
            cases.append({"case": f"planted-{name}", "ok": bool(found), "found": sorted(found)})
        (planted / ("name-" + canary.decode() + ".txt")).write_text("x")
        cases.append({"case": "planted-filename", "ok": any(h["where"].startswith("name:") for h in scan_tree(planted, table)["hits"])})
        clean = root / "clean"
        clean.mkdir()
        (clean / "a.txt").write_bytes(secrets.token_bytes(4096))
        cases.append({"case": "clean-tree", "ok": scan_tree(clean, table)["hits"] == []})
        try:
            variants(b"short")
            cases.append({"case": "short-canary-refused", "ok": False})
        except ValueError:
            cases.append({"case": "short-canary-refused", "ok": True})
        repo = root / "repo"
        (repo / "src").mkdir(parents=True)
        (repo / "src" / "bad.c").write_text('int f(void){ char t[]="/tmp/xXXXXXX"; int fd=mkstemp(t); return fd; }\n'
                                            'void g(const char*password){ printf("%s", password); }\n')
        (repo / "src" / "good.c").write_text('int f(void){ char t[]="/tmp/xXXXXXX"; int fd=mkstemp(t); unlink(t); return fd; }\n'
                                             'void g(const char*password,int password_length){\n'
                                             '  printf("len %d", password_length);\n}\n'
                                             '/* printf(secret) in a comment */\n')
        (repo / "src" / "scratch_leak.py").write_text("import tempfile\nd = tempfile.TemporaryDirectory()\nuse(d.name)\n")
        (repo / "src" / "scratch_ok.py").write_text("import tempfile\nwith tempfile.TemporaryDirectory() as d:\n    use(d)\n")
        for cmd in (["init", "-q"], ["add", "."], ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "x"]):
            subprocess.run(["git", "-C", str(repo)] + cmd, check=True, capture_output=True)
        result = static_audit(repo)
        by_file = {}
        for s in result["temp_sites"]:
            by_file[s["file"]] = s["verdict"]
        cases.append({"case": "static-flags-unpaired-mkstemp", "ok": by_file.get("src/bad.c") == "unproven"})
        cases.append({"case": "static-accepts-paired-mkstemp", "ok": by_file.get("src/good.c") == "cleanup-paired"})
        cases.append({"case": "static-flags-unmanaged-TemporaryDirectory", "ok": by_file.get("src/scratch_leak.py") == "unproven"})
        cases.append({"case": "static-accepts-with-TemporaryDirectory", "ok": by_file.get("src/scratch_ok.py") == "context-managed-cleanup"})
        flagged = {l["file"] for l in result["credential_log_candidates"]}
        cases.append({"case": "static-flags-secret-printf", "ok": flagged == {"src/bad.c"}})
    finally:
        shutil.rmtree(root, ignore_errors=True)
    return {"cases": cases, "gate_passed": all(c["ok"] for c in cases)}


# ---------------------------------------------------------------- scope / summary
def scope(repo: Path, expect_sha) -> dict:
    def git(*a):
        return subprocess.run(["git", "-C", str(repo)] + list(a), capture_output=True, text=True)
    head = git("rev-parse", "HEAD").stdout.strip()
    ancestor = git("merge-base", "--is-ancestor", BASE, "HEAD").returncode == 0
    changed = [p for p in git("diff", "--name-only", BASE, "HEAD").stdout.splitlines() if p]
    outside = [p for p in changed if not any(re.match(o, p) for o in OWNED)]
    ok = (expect_sha is None or head == expect_sha) and ancestor and not outside
    return {"head": head, "expected_head": expect_sha, "base": BASE, "base_is_ancestor": ancestor,
            "changed": changed, "outside_owned_paths": outside, "gate_passed": ok}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def summary(reports: Path, out: Path) -> int:
    names = ["scope", "selftest", "static", "dynamic_linux"]
    loaded, missing = {}, []
    for name in names:
        p = reports / f"{name}.json"
        if p.is_file():
            loaded[name] = json.loads(p.read_text())
        else:
            missing.append(name)
    verdict = {n: bool(r.get("gate_passed")) for n, r in loaded.items()}
    identity = {"repository": os.environ.get("GITHUB_REPOSITORY"), "source_sha": os.environ.get("GITHUB_SHA"),
                "ref": os.environ.get("GITHUB_REF"), "run_id": os.environ.get("GITHUB_RUN_ID"),
                "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT"), "job": os.environ.get("GITHUB_JOB"),
                "runner_os": os.environ.get("RUNNER_OS"), "runner_arch": os.environ.get("RUNNER_ARCH"),
                "image": os.environ.get("ImageOS") + " " + os.environ.get("ImageVersion", "") if os.environ.get("ImageOS") else None,
                "platform": platform.platform(), "python": sys.version.split()[0]}
    result = {
        "identity": identity, "reports_missing": missing, "gates": verdict,
        "all_gates_passed": not missing and all(verdict.values()),
        "report_sha256": {n: sha256(reports / f"{n}.json") for n in loaded},
        "established_for_this_source_only": [
            "Linux Secret Service (gnome-keyring, private D-Bus, temporary HOME/TMPDIR) round-trip with synthetic canaries leaves no canary in any encoding on disk or in probe output",
            "replaced and deleted secrets do not persist on disk; TMPDIR is empty after each phase",
            "locked collection and absent service return UNAVAILABLE/IO with no plaintext fallback",
            "static inventory of temp-file creation sites and credential-named log arguments (no allowlists)"],
        "not_established": [
            "Windows, macOS, iOS and Android credential stores and temp cleanup (not exercised by this workflow)",
            "application-level flows (WebDAV/OPDS accounts, sync, export, crash/kill paths) beyond the credential module",
            "full F10, full P0 or any acceptance count; evidence binds to the single source/run/attempt above"]}
    out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"gates": verdict, "missing": missing, "all": result["all_gates_passed"]}))
    step = os.environ.get("GITHUB_STEP_SUMMARY")
    if step:
        with open(step, "a") as f:
            f.write("## F10 privacy (C04)\n```json\n" + json.dumps({"identity": identity, "gates": verdict,
                    "missing": missing, "all": result["all_gates_passed"]}, indent=2) + "\n```\n")
    return 0 if result["all_gates_passed"] else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("scope", "selftest", "static", "summary"):
        p = sub.add_parser(name)
        p.add_argument("--repo", default=".")
        p.add_argument("--out", required=True)
    sub.choices["scope"].add_argument("--expect-sha")
    sub.choices["summary"].add_argument("--reports")
    a = ap.parse_args()
    out = Path(a.out)
    repo = Path(a.repo).resolve()
    if a.cmd == "summary":
        return summary(Path(a.reports), out)
    report = {"scope": lambda: scope(repo, a.expect_sha if hasattr(a, "expect_sha") else None),
              "selftest": selftest, "static": lambda: static_audit(repo)}[a.cmd]()
    report["subcommand"] = a.cmd
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k in ("subcommand", "gate_passed")}))
    if a.cmd == "static":
        print(f"temp sites={len(report['temp_sites'])} unproven={len(report['temp_sites_unproven'])} "
              f"log candidates={len(report['credential_log_candidates'])}")
        for s in report["temp_sites_unproven"]:
            print(f"UNPROVEN {s['file']}:{s['line']} {s['api']}")
        for s in report["temp_sites"]:
            if s["verdict"] != "unproven":
                print(f"{s['verdict'].upper()} {s['file']}:{s['line']} {s['api']}")
        for s in report["credential_log_candidates"]:
            print(f"LOGLEAK? {s['file']}:{s['line']} {s['identifier']}")
        print("user-path inventory (informational):", json.dumps(report["user_path_inventory_informational"]))
    return 0 if report["gate_passed"] else 1


if __name__ == "__main__":
    sys.exit(main())