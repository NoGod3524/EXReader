#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Actions-only acceptance driver for the reader_opds_browser package.

It creates an ephemeral test CA, trusts it in the runner store, starts the fixture
origins (plain, TLS, second plain origin), runs the two installed consumers and writes
named evidence. Nothing here runs on a developer machine by design: the trusted CA and
the served bytes exist only for the duration of the job.
"""
import argparse
import json
import os
import platform
import re
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

CASE_ID = re.compile(r"^[a-z0-9_]+$")
STAGED = re.compile(r"^(opds-[0-9a-f]{24}\.(epub|pdf|cbz)|import\.db.*)$")


def run(command, cwd=None):
    subprocess.run(command, check=True, cwd=cwd)


def make_certs(directory):
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "ca.cnf").write_text(
        "[req]\n"
        "distinguished_name = dn\n"
        "x509_extensions = v3_ca\n"
        "prompt = no\n"
        "[dn]\n"
        "CN = EXReader OPDS Test CA\n"
        "[v3_ca]\n"
        "basicConstraints = critical,CA:TRUE\n"
        "keyUsage = critical,keyCertSign,cRLSign\n",
        encoding="utf-8")
    (directory / "leaf.cnf").write_text(
        "[req]\n"
        "distinguished_name = dn\n"
        "prompt = no\n"
        "[dn]\n"
        "CN = 127.0.0.1\n"
        "[v3_leaf]\n"
        "basicConstraints = critical,CA:FALSE\n"
        "keyUsage = critical,digitalSignature,keyEncipherment\n"
        "extendedKeyUsage = serverAuth\n"
        "subjectAltName = IP:127.0.0.1,DNS:localhost\n",
        encoding="utf-8")
    run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", "ca.key", "-out", "ca.crt",
         "-days", "2", "-config", "ca.cnf"], cwd=directory)
    run(["openssl", "req", "-newkey", "rsa:2048", "-nodes", "-keyout", "server.key", "-out", "server.csr",
         "-config", "leaf.cnf"], cwd=directory)
    run(["openssl", "x509", "-req", "-in", "server.csr", "-CA", "ca.crt", "-CAkey", "ca.key",
         "-CAcreateserial", "-days", "2", "-sha256", "-extfile", "leaf.cnf", "-extensions", "v3_leaf",
         "-out", "server.crt"], cwd=directory)
    run(["openssl", "x509", "-in", "ca.crt", "-outform", "der", "-out", "ca.der"], cwd=directory)
    return directory


def trust_ca(directory):
    system = platform.system()
    ca_crt, ca_der = str(directory / "ca.crt"), str(directory / "ca.der")
    if system == "Linux":
        run(["sudo", "cp", ca_crt, "/usr/local/share/ca-certificates/exreader-opds-test.crt"])
        run(["sudo", "update-ca-certificates"])
    elif system == "Darwin":
        run(["sudo", "security", "add-trusted-cert", "-d", "-r", "trustRoot", "-k",
             "/Library/Keychains/System.keychain", ca_crt])
    elif system == "Windows":
        run(["certutil", "-addstore", "-f", "Root", ca_der])
    else:
        raise SystemExit("unsupported runner platform: " + system)


def wait_for(path, timeout=30.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        time.sleep(0.1)
    raise SystemExit("fixture service did not announce its ports")


def load_cases(path):
    cases = []
    if not path.exists():
        return cases
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            cases.append(json.loads(line))
    return cases


def wait_port(base, timeout=20.0):
    host, port = base.split("//", 1)[1].split("/")[0].split(":")
    deadline = time.time() + timeout
    while time.time() < deadline:
        with socket.socket() as probe:
            probe.settimeout(0.5)
            if probe.connect_ex((host, int(port))) == 0:
                return
        time.sleep(0.1)
    raise SystemExit("fixture port never opened: " + base)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--consumer", required=True)
    parser.add_argument("--import-consumer", required=True)
    parser.add_argument("--fixtures", required=True)
    parser.add_argument("--evidence", required=True)
    parser.add_argument("--source-sha", default=os.environ.get("GITHUB_SHA", "local"))
    parser.add_argument("--run-id", default=os.environ.get("GITHUB_RUN_ID", "0"))
    parser.add_argument("--attempt", default=os.environ.get("GITHUB_RUN_ATTEMPT", "0"))
    arguments = parser.parse_args()

    evidence = Path(arguments.evidence)
    evidence.mkdir(parents=True, exist_ok=True)
    work = evidence / "work"
    staging = work / "staging"
    staging.mkdir(parents=True, exist_ok=True)
    certs = work / "certs"
    make_certs(certs)
    trust_ca(certs)

    ready = work / "ready.json"
    requests_log = work / "requests.jsonl"
    server = Path(__file__).resolve().parent / "server.py"
    server_log = (work / "server.log").open("wb")
    process = subprocess.Popen([sys.executable, str(server), "--ready", str(ready), "--log", str(requests_log),
                                "--fixtures", str(Path(arguments.fixtures).resolve()),
                                "--cert", str(certs / "server.crt"), "--key", str(certs / "server.key")],
                               stdout=server_log, stderr=subprocess.STDOUT)
    problems = []
    cases = []
    isolation = {}
    staging_files = []
    try:
        bases = wait_for(ready)
        for base in bases.values():
            wait_port(base)
        network_cases = work / "network-cases.jsonl"
        import_cases = work / "import-cases.jsonl"
        network = subprocess.run([arguments.consumer, str(staging), bases["plain"], bases["tls"], bases["other"],
                                  str(network_cases)], capture_output=True, text=True)
        (work / "network-consumer.log").write_text(
            "exit=%d\nstdout:\n%s\nstderr:\n%s\n" % (network.returncode, network.stdout, network.stderr),
            encoding="utf-8")
        import_result = subprocess.run([arguments.import_consumer, str(staging), bases["plain"], str(import_cases)],
                                       capture_output=True, text=True)
        (work / "import-consumer.log").write_text(
            "exit=%d\nstdout:\n%s\nstderr:\n%s\n" % (import_result.returncode, import_result.stdout,
                                                     import_result.stderr),
            encoding="utf-8")
        if network.returncode != 0:
            problems.append("network consumer reported %d failing cases" % network.returncode)
        if import_result.returncode != 0:
            problems.append("import consumer reported %d failing cases" % import_result.returncode)
        cases = load_cases(network_cases) + load_cases(import_cases)
        identifiers = [case.get("id") for case in cases]
        if len(identifiers) != len(set(identifiers)):
            problems.append("duplicate case identifiers")
        for case in cases:
            if not CASE_ID.match(str(case.get("id", ""))):
                problems.append("bad case identifier: %r" % case.get("id"))
        if not cases:
            problems.append("no cases were reported")

        with urllib.request.urlopen(bases["plain"] + "/debug/log", timeout=10) as response:
            records = json.loads(response.read().decode("utf-8"))["records"]
        plain_authorized = [r for r in records if r["origin"] == "plain" and r["authorization"]]
        auth_requests = [r for r in records if r["path"].startswith("/auth/catalog.xml")]
        tls_records = [r for r in records if r["origin"] == "tls"]
        isolation = {"requests": len(records),
                     "plain_requests_with_authorization": len(plain_authorized),
                     "auth_requests": len(auth_requests),
                     "auth_requests_with_authorization": len([r for r in auth_requests if r["authorization"]]),
                     "tls_requests": len(tls_records)}
        if plain_authorized:
            problems.append("credentials leaked onto the plain origin")
        if not isolation["auth_requests_with_authorization"]:
            problems.append("the credential origin never received an Authorization header")
        if not tls_records:
            problems.append("the TLS origin served no request")

        for entry in sorted(staging.iterdir()):
            if not STAGED.match(entry.name):
                problems.append("unexpected staging entry: " + entry.name)
            staging_files.append(entry.name)
        for leftover in work.glob("staging/.opds-*"):
            problems.append("temporary download left behind: " + leftover.name)
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
        server_log.close()

    failed = [case["id"] for case in cases if not case.get("ok")]
    if failed:
        problems.append("failing cases: " + ", ".join(failed))
    accepted = not problems and bool(cases)
    report = {
        "accepted": accepted,
        "package": "EXReaderOpdsBrowser 0.1.0",
        "source_sha": arguments.source_sha,
        "run_id": int(arguments.run_id),
        "attempt": int(arguments.attempt),
        "platform": platform.system().lower(),
        "runner": os.environ.get("RUNNER_OS", platform.system()),
        "checks": len(cases),
        "cases": cases,
        "origin_isolation": isolation,
        "staging_files": staging_files,
        "problems": problems,
        "granted": ["network_phase", "sdk_owner_import"] if accepted else [],
        "sdk_changed": False,
        "schema_changed": False,
    }
    (evidence / "result.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"accepted": accepted, "checks": len(cases), "problems": problems}, ensure_ascii=False))
    return 0 if accepted else 1


if __name__ == "__main__":
    sys.exit(main())
