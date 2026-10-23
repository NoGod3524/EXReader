#!/usr/bin/env python3
"""WP15 OPDS acceptance orchestration (GitHub runner only).

Starts the fixed two-origin test service, runs the C acceptance driver and the consumer
example against it, audits the server's request log, proves the default SDK was not
touched and writes one evidence JSON. Exit status 0 only when every check passed.

usage: check_opds.py --build DIR --repo DIR --out DIR --base SHA [--config Release]
"""
import argparse
import base64
import hashlib
import json
import os
import platform
import re
import subprocess
import sys
import time

BASIC_RAW = "opds-test:fixture"          # fixture credential, not a real account
BEARER_TOKEN = "fixture-token-not-a-secret"
OWNED = ("extras/opds/", "tests/opds/", "tools/check_opds.py", ".github/workflows/wp15-opds.yml",
         "docs/WP15-OPDS.md", "docs/validation/wp15-opds")
PROTECTED_TREES = ("src", "include", "cmake", "CMakeLists.txt", "tests/fixtures", ".github/workflows/native.yml",
                   ".github/workflows/reliability.yml", "bindings")
CATEGORIES = {"navigation", "pagination", "search", "acquisition", "auth", "bad_data"}

checks = []


def check(name, ok, detail=""):
    checks.append({"name": name, "passed": bool(ok), "detail": detail})
    print(("PASS " if ok else "FAIL ") + name + ((": " + detail) if detail and not ok else ""), flush=True)
    return ok


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def find_binary(build, name, config):
    exe = name + (".exe" if os.name == "nt" else "")
    for cand in (os.path.join(build, exe), os.path.join(build, config, exe)):
        if os.path.isfile(cand):
            return cand
    raise SystemExit("missing binary " + name + " under " + build)


def git(repo, *args):
    r = subprocess.run(["git", "-C", repo] + list(args), capture_output=True, text=True)
    return r.returncode, r.stdout.strip(), r.stderr.strip()


def run_example(exe, args, env, timeout=120):
    r = subprocess.run([exe] + args, capture_output=True, text=True, env=env, timeout=timeout)
    parsed = None
    for line in r.stdout.splitlines():
        line = line.strip()
        if line.startswith("{"):
            try:
                parsed = json.loads(line)
            except ValueError:
                pass
    return {"args": [a for a in args], "exit": r.returncode, "result": parsed, "stderr_bytes": len(r.stderr)}, r.stdout + r.stderr


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", required=True)
    ap.add_argument("--repo", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--base", required=True, help="implementation baseline commit")
    ap.add_argument("--handoff", default=None, help="first commit of this package (diff base for ownership)")
    ap.add_argument("--config", default="Release")
    ap.add_argument("--identity", nargs="*", default=[], help="extra files whose SHA-256 is recorded (SDK libraries)")
    a = ap.parse_args()
    repo = os.path.abspath(a.repo)
    out = os.path.abspath(a.out)
    os.makedirs(out, exist_ok=True)
    work = os.path.join(out, "work")
    os.makedirs(work, exist_ok=True)

    basic = "Basic " + base64.b64encode(BASIC_RAW.encode()).decode()
    bearer = "Bearer " + BEARER_TOKEN
    secrets = [basic, basic[6:], BEARER_TOKEN, BASIC_RAW, "fixture"]
    secrets = [s for s in secrets if s != "fixture"]  # "fixture" is part of public names

    test_exe = find_binary(a.build, "opds-test", a.config)
    cons_exe = find_binary(a.build, "opds-consume", a.config)
    publish_exe = find_binary(a.build, "opds-publish-fault-test", a.config)
    facet_exe = find_binary(a.build, "opds-facet-test", a.config)
    ports_file = os.path.join(out, "ports.json")
    log_file = os.path.join(out, "server-requests.jsonl")
    server = subprocess.Popen([sys.executable, os.path.join(repo, "tests", "opds", "server.py"),
                               "--corpus", os.path.join(repo, "tests", "opds", "corpus"),
                               "--fixtures", os.path.join(repo, "tests", "fixtures"),
                               "--log", log_file, "--ports", ports_file, "--basic", basic, "--bearer", bearer],
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    report = {"schema": 1, "package": "WP15-OPDS", "date": time.strftime("%Y-%m-%d", time.gmtime())}
    outputs = []
    try:
        deadline = time.time() + 20
        while time.time() < deadline and not os.path.exists(ports_file):
            if server.poll() is not None:
                break
            time.sleep(0.1)
        if not check("server_started", os.path.exists(ports_file), "service did not start"):
            raise SystemExit(1)
        time.sleep(0.2)
        ports = json.load(open(ports_file))
        base_a = "http://127.0.0.1:%d" % ports["a"]
        base_b = "http://127.0.0.1:%d" % ports["b"]
        env = dict(os.environ, OPDS_TEST_BASIC=basic, OPDS_TEST_BEARER=bearer)

        # ---- acceptance driver ----
        cases_json = os.path.join(out, "wp15-opds-cases.json")
        r = subprocess.run([test_exe, "--a", base_a, "--b", base_b, "--corpus", os.path.join(repo, "tests", "opds", "corpus"),
                            "--work", os.path.join(work, "cases"), "--out", cases_json],
                           capture_output=True, text=True, env=env, timeout=900)
        outputs.append(r.stdout + r.stderr)
        sys.stdout.write(r.stdout)
        check("driver_exit_zero", r.returncode == 0, "exit %d" % r.returncode)
        cases = []
        if os.path.exists(cases_json):
            cj = json.load(open(cases_json, encoding="utf-8"))
            cases = cj["cases"]
            report["driver"] = {k: cj[k] for k in ("module_version", "sdk_version", "sdk_abi", "platform", "summary")}
        else:
            check("driver_report_written", False, "no case report")
            cj = {"summary": {"total": 0, "passed": 0, "failed": 0}}
        src = open(os.path.join(repo, "tests", "opds", "opds_test.c"), encoding="utf-8").read()
        required = re.findall(r'^\s*\{"([a-z0-9_]+)", "(?:opds1|opds2|both|net)"', src, re.M)
        got = [c["id"] for c in cases]
        check("all_declared_cases_executed", sorted(required) == sorted(got) and len(set(got)) == len(got),
              "declared %d, executed %d" % (len(required), len(got)))
        check("every_case_passed", cases and all(c["passed"] for c in cases),
              ",".join(c["id"] for c in cases if not c["passed"]))
        check("summary_consistent", cj["summary"]["total"] == len(cases) and cj["summary"]["failed"] == 0
              and cj["summary"]["passed"] == len(cases), json.dumps(cj["summary"]))
        for proto in ("opds1", "opds2"):
            pc = [c for c in cases if c["protocol"] == proto]
            check(proto + "_at_least_10_named_scenarios", len(pc) >= 10, str(len(pc)))
            have = {c["category"] for c in pc}
            check(proto + "_category_coverage", CATEGORIES <= have, "missing " + ",".join(sorted(CATEGORIES - have)))
            check(proto + "_download_chain", any(c["id"].startswith("d_e2e_" + proto) and c["passed"] for c in cases))
        check("every_case_has_input_hash_and_requests",
              all(re.fullmatch(r"[0-9a-f]{64}", c["input_sha256"]) for c in cases))
        check("network_cases_issued_requests", all(c["requests"] for c in cases if c["request_class"] != "none"))

        # ---- consumer example ----
        examples = []

        def ex(label, args, expect_exit, expect):
            summary, text = run_example(cons_exe, args, env)
            outputs.append(text)
            res = summary["result"] or {}
            ok = summary["exit"] == expect_exit and all(res.get(k) == v for k, v in expect.items())
            summary["label"] = label
            summary["passed"] = ok
            examples.append(summary)
            check("example_" + label, ok, json.dumps(res)[:300])

        e1 = os.path.join(work, "ex1")
        e2 = os.path.join(work, "ex2")
        for d in (e1, e2, os.path.join(work, "ex3"), os.path.join(work, "ex4")):
            os.makedirs(d, exist_ok=True)
        common = {"status": "ok", "published": True, "readable": "ok"}
        ex("opds1_search_page_download", ["--start", base_a + "/c/o1/root.xml", "--search", "story", "--pick", "Gamma Story", "--out", e1],
           0, dict(common, selected="Gamma Story", pages=2, already_present=False))
        ex("opds2_search_page_download", ["--start", base_a + "/c/o2/root.json", "--search", "story", "--pick", "Gamma Story", "--out", e2],
           0, dict(common, selected="Gamma Story", pages=2, already_present=False))
        ex("repeat_is_idempotent", ["--start", base_a + "/c/o1/root.xml", "--search", "story", "--pick", "Gamma Story", "--out", e1],
           0, dict(common, already_present=True))
        ex("opds1_browse_follow_page", ["--start", base_a + "/c/o1/root.xml", "--follow", "All Books", "--pick", "Epsilon Tale",
                                        "--out", os.path.join(work, "ex3")], 0, dict(common, selected="Epsilon Tale", pages=3))
        ex("opds2_browse_follow_page", ["--start", base_a + "/c/o2/root.json", "--follow", "All Books", "--pick", "Epsilon Tale",
                                        "--out", os.path.join(work, "ex4")], 0, dict(common, selected="Epsilon Tale", pages=3))
        ex("missing_book_is_reported", ["--start", base_a + "/c/o1/root.xml", "--search", "story", "--pick", "No Such Book", "--out", e1],
           1, {"status": "format", "published": False})
        authdir = os.path.join(work, "ex5")
        os.makedirs(authdir, exist_ok=True)
        ex("auth_missing_credentials", ["--start", base_a + "/auth/o1/root.xml", "--out", authdir], 1,
           {"status": "auth_required", "http_status": 401})
        ex("auth_with_credentials", ["--start", base_a + "/auth/o1/root.xml", "--follow", "All Books", "--pick", "Alpha Story",
                                     "--auth-env", "OPDS_TEST_BASIC", "--out", authdir], 0, dict(common, selected="Alpha Story"))
        report["examples"] = examples

        # Production filesystem shim with only OS publication failure injected.
        atomic_dir = os.path.join(work, "atomic-failure")
        os.makedirs(atomic_dir, exist_ok=True)
        atomic = subprocess.run([publish_exe, atomic_dir], capture_output=True, text=True, timeout=30)
        outputs.append(atomic.stdout + atomic.stderr)
        atomic_report = json.loads(atomic.stdout.strip().splitlines()[-1]) if atomic.stdout.strip() else {}
        check("atomic_no_replace_failure_preserves_destination", atomic.returncode == 0
              and atomic_report.get("passed") is True and atomic_report.get("checks", 0) >= 10
              and atomic_report.get("primitive_failure") is True and atomic_report.get("other_writer_preserved") is True)
        report["atomic_publication_regression"] = atomic_report

        # ---- request log audit (credential values are never logged by the server) ----
        time.sleep(0.3)
        rows = [json.loads(l) for l in open(log_file, encoding="utf-8") if l.strip()]
        a_rows = [r_ for r_ in rows if r_["server"] == "A"]
        b_rows = [r_ for r_ in rows if r_["server"] == "B"]
        check("foreign_origin_never_received_credentials", b_rows and all(r_["auth"] == "none" for r_ in b_rows), "%d B requests" % len(b_rows))
        check("credentials_reached_home_origin", any(r_["auth"] == "ok" for r_ in a_rows) and any(r_["auth"] == "bad" for r_ in a_rows))

        def klass(p):
            if p.startswith("/dl/") or p.startswith("/auth/dl/"):
                return "download"
            if p.startswith("/r/"):
                return "redirect"
            if p.startswith("/slow") or p.startswith("/trunc") or p.startswith("/chunked") or p.startswith("/huge") or p.startswith("/status"):
                return "network"
            if "search" in p or "opensearch" in p:
                return "search"
            if p.startswith("/auth/"):
                return "auth"
            return "feed"
        counts = {}
        for r_ in a_rows:
            counts[klass(r_["path"])] = counts.get(klass(r_["path"]), 0) + 1
        report["server_requests"] = {"origin_a": len(a_rows), "origin_b": len(b_rows), "by_class_a": counts,
                                     "auth_states_a": {s: sum(1 for r_ in a_rows if r_["auth"] == s) for s in ("none", "ok", "bad")},
                                     "auth_states_b": {s: sum(1 for r_ in b_rows if r_["auth"] == s) for s in ("none", "ok", "bad")}}
        check("search_and_download_requests_observed", counts.get("search", 0) >= 4 and counts.get("download", 0) >= 10, json.dumps(counts))
        check("redirect_requests_observed", counts.get("redirect", 0) >= 8)
        check("timeout_and_cancel_requests_observed", counts.get("network", 0) >= 6)
    finally:
        server.terminate()
        try:
            server_out, _ = server.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
            server_out = ""
        outputs.append(server_out or "")

    # ---- leftover temporary files ----
    leftovers = []
    for dirpath, _, files in os.walk(work):
        leftovers += [os.path.join(dirpath, f) for f in files if f.startswith(".opds-")]
    check("no_temporary_files_left", not leftovers, ",".join(leftovers[:5]))

    # ---- default SDK untouched ----
    ident = {}
    base_h = open(os.path.join(repo, "include", "exr", "base.h"), encoding="utf-8").read()
    ver = re.search(r'#define EXR_VERSION "([^"]+)"', base_h).group(1)
    abi = int(re.search(r"#define EXR_ABI_VERSION (\d+)u", base_h).group(1))
    drv = report.get("driver", {})
    check("runtime_sdk_identity_matches_headers", drv.get("sdk_version") == ver and drv.get("sdk_abi") == abi,
          "%s/%s vs %s/%s" % (drv.get("sdk_version"), drv.get("sdk_abi"), ver, abi))
    trees = {}
    for p in PROTECTED_TREES:
        rc1, h1, _ = git(repo, "rev-parse", a.base + ":" + p)
        rc2, h2, _ = git(repo, "rev-parse", "HEAD:" + p)
        trees[p] = {"base": h1, "head": h2}
        check("unchanged_vs_baseline:" + p, rc1 == 0 and rc2 == 0 and h1 == h2, "%s != %s" % (h1, h2))
    rc, names, err = git(repo, "diff", "--name-only", a.handoff or a.base, "HEAD")
    changed = [n for n in names.splitlines() if n]
    foreign = [n for n in changed if not n.startswith(OWNED)]
    check("only_owned_paths_changed", rc == 0 and not foreign, ",".join(foreign[:10]))
    rc, head, _ = git(repo, "rev-parse", "HEAD")
    ident.update(head=head, base=a.base, sdk_version=ver, sdk_abi=abi, trees=trees)

    # Facet model is tested by CTest in the same job before this orchestrator.
    try:
        with open(os.path.join(a.build, "facet-result.json"), encoding="utf-8") as f:
            facets = json.load(f)
    except (OSError, ValueError):
        facets = {}
    check("facet_model_passed", facets.get("passed") is True and facets.get("failures") == 0
          and isinstance(facets.get("checks"), int) and facets["checks"] >= 70)
    report["facets"] = facets

    # ---- runtime identity ----
    files = [test_exe, cons_exe, publish_exe, facet_exe] + [p for p in a.identity if os.path.isfile(p)]
    ident["files"] = {os.path.basename(p): {"sha256": sha256_file(p), "bytes": os.path.getsize(p)} for p in files}
    ident["runner"] = {"os": platform.platform(), "machine": platform.machine(), "python": platform.python_version(),
                       "github_run_id": os.environ.get("GITHUB_RUN_ID", ""), "github_job": os.environ.get("GITHUB_JOB", ""),
                       "runner_os": os.environ.get("RUNNER_OS", ""), "workflow": os.environ.get("GITHUB_WORKFLOW", "")}
    report["identity"] = ident
    report["cases"] = cases
    report["checks"] = checks

    # ---- secrets must not reach any output ----
    blob = json.dumps(report) + "\n".join(outputs) + open(log_file, encoding="utf-8").read()
    leaked = [i for i, s in enumerate(secrets) if s in blob]
    check("no_credential_values_in_reports", not leaked, "leaked secret index %s" % leaked)
    report["checks"] = checks

    failed = [c for c in checks if not c["passed"]]
    report["result"] = "passed" if not failed else "failed"
    report["counts"] = {"checks": len(checks), "failed_checks": len(failed), "cases": len(cases),
                        "cases_passed": sum(1 for c in cases if c["passed"])}
    path = os.path.join(out, "wp15-opds-%s.json" % (os.environ.get("RUNNER_OS", platform.system()).lower() or "local"))
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
        f.write("\n")
    with open(os.path.join(out, "driver-output.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(outputs))
    print("wrote", path, "result", report["result"], flush=True)
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
