# SPDX-License-Identifier: MIT
"""Measure removal of #267 mask-row reuse with native renders and byte parity.

Arms (built by build_arms.py): A = pre-#267, B = mask-row reuse only,
C = this branch (RGB group commit only), D = main as merged.
"""
import argparse
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

import psutil

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
RAW = HERE / "raw"
FIXTURES = ROOT / "tests" / "fixtures"
MIXED = "pdf-large/real-mixed-120.pdf"
sys.path.insert(0, str(HERE.parent / "slides-gradient-20261118"))
from paired_sweep import NativeDocument, digest_file, pixels_different, wait_idle
from verify import LARGE, SMALL

SLIDES = range(21)


def write(name, result):
    RAW.mkdir(exist_ok=True)
    (RAW / f"{name}.json").write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")


def competitors():
    found = []
    for process in psutil.process_iter(["name", "cmdline"]):
        if process.pid == os.getpid():
            continue
        try:
            name = (process.info["name"] or "").lower()
            command = process.info["cmdline"] or []
        except psutil.Error:
            continue
        if name in {"cc1.exe", "cc1plus.exe", "cl.exe", "ld.exe", "lld-link.exe",
                    "ninja.exe", "ctest.exe", "msbuild.exe"}:
            found.append(name)
        elif name in {"python.exe", "node.exe"}:
            scripts = [Path(arg).name.lower() for arg in command[1:] if arg.endswith((".py", ".cjs"))]
            if any(script in {"ablate.py", "worker.py", "worker.cjs", "measure.py"}
                   or script.startswith(("interleaved_", "benchmark_", "paired_", "bench_"))
                   for script in scripts):
                found.append(f"{name} {' '.join(scripts)}")
    return sorted(set(found))


def gate():
    """Fail closed: never start a timed round unless a valid sample shows CPU <= 15%."""
    start = time.monotonic()
    next_notice = 0
    while True:
        active = competitors()
        if not active:
            try:
                idle = wait_idle(15, 2)
            except RuntimeError as error:
                if str(error) != "Invalid system CPU counters":
                    raise
                idle = None
            active = competitors()
            if idle is not None and not active:
                return {"cpu_percent": idle, "wait_s": time.monotonic() - start}
        waited = time.monotonic() - start
        if waited >= next_notice:
            print("Idle gate closed:", ", ".join(active) or "CPU gate", flush=True)
            next_notice = waited + 30
        time.sleep(0.5)


def open_docs(stack, libs, pdf, width):
    docs = {}
    for arm, dll in libs.items():
        docs[arm] = NativeDocument(dll, FIXTURES / pdf, width)
        stack.callback(docs[arm].close)
    assert len({len(doc.scales) for doc in docs.values()}) == 1
    return docs


def parity(docs, pages, width):
    result = {"pixels_per_arm": 0, "differing_pixels": dict.fromkeys(list(docs)[1:], 0), "hashes": []}
    for page in pages:
        rgba = {arm: doc.render(page, True, None)[1] for arm, doc in docs.items()}
        baseline = next(iter(rgba.values()))
        result["pixels_per_arm"] += len(baseline) * width
        result["hashes"].append({"page": page+1, **{
            arm: hashlib.sha256(b"".join(rows)).hexdigest() for arm, rows in rgba.items()}})
        for arm in result["differing_pixels"]:
            result["differing_pixels"][arm] += pixels_different(baseline, rgba[arm])
    return result


def identity(libs, pdf, width):
    return {"fixture": pdf, "fixture_sha256": digest_file(FIXTURES / pdf), "width": width,
            "dll_sha256": {arm: digest_file(path) for arm, path in libs.items()}}


def carry(name, result):
    """Resume a capture: keep admitted rounds from an earlier session with identical inputs."""
    path = RAW / f"{name}.json"
    if path.exists():
        saved = json.loads(path.read_text())
        if all(saved.get(key) == result[key] for key in ("fixture_sha256", "width", "dll_sha256")):
            result["rounds"], result["rejected"] = saved["rounds"], saved.get("rejected", [])
            result["resumed_at_round"] = saved.get("resumed_at_round", []) + [len(saved["rounds"]) + 1]
            print(f"Resuming {name} after {len(saved['rounds'])} rounds", flush=True)
    return len(result["rounds"])


def sweep(docs, pair, pages, flip):
    """One AB/BA sweep: the order alternates every page and the first page flips with `flip`."""
    timings = {arm: [] for arm in pair}
    for offset, page in enumerate(pages):
        for arm in (pair if (flip + offset) % 2 == 0 else pair[::-1]):
            timings[arm].append(docs[arm].render(page, False, None)[0])
    return timings


def primary(directory, rounds):
    """Main (D) vs branch (C) on p1-21 with a same-DLL main/main control in every round.

    Each admitted round runs one real sweep (D, C) and one control sweep (X, Y; both
    main's DLL, independent documents) under the same idle gate. The sweep that goes
    first alternates by round; within a sweep the AB/BA order alternates by page and
    the first page's order reverses each round.
    """
    libs = {"D": directory / "D.dll", "C": directory / "C.dll",
            "X": directory / "D.dll", "Y": directory / "D.dll"}
    result = identity(libs, MIXED, 1200)
    result.update(pages=[page+1 for page in SLIDES], rounds=[], rejected=[])
    with ExitStack() as stack:
        docs = open_docs(stack, libs, MIXED, 1200)
        result["warmup_gate"] = gate()
        result["parity"] = parity(docs, SLIDES, 1200)
        assert not any(result["parity"]["differing_pixels"].values())
        for index in range(carry("primary-p1-21", result), rounds):
            sweeps = [("D", "C"), ("X", "Y")]
            if index % 2:
                sweeps.reverse()
            while True:
                idle = gate()
                timings = {}
                for pair in sweeps:
                    timings.update(sweep(docs, pair, SLIDES, index % 2))
                active = competitors()
                if not active:
                    break
                result["rejected"].append({"round": index+1, "competitors": active})
            totals = {arm: sum(times) for arm, times in timings.items()}
            result["rounds"].append({"number": index+1, "gate": idle,
                                     "sweep_order": ["".join(pair) for pair in sweeps],
                                     "totals_ms": totals, "page_ms": timings})
            print("primary", index+1, " ".join(f"{arm}={ms:.2f}" for arm, ms in totals.items()),
                  flush=True)
            write("primary-p1-21", result)


def factorial(directory, rounds):
    """Page-matched four-arm repeat of verify267 on current main, same-DLL X/Y = main."""
    libs = {tag: directory / f"{tag}.dll" for tag in "ABCD"}
    libs.update(X=libs["D"], Y=libs["D"])
    result = identity(libs, MIXED, 1200)
    result.update(rounds=[], rejected=[], page_matched=True)
    with ExitStack() as stack:
        docs = open_docs(stack, libs, MIXED, 1200)
        result["warmup_gate"] = gate()
        result["parity"] = parity(docs, SLIDES, 1200)
        assert not any(result["parity"]["differing_pixels"].values())
        for index in range(carry("four-arm-page-matched", result), rounds):
            order, sham = ("ABCD", "XY") if index % 2 == 0 else ("DCBA", "YX")
            first = order + sham if index % 2 == 0 else sham + order
            batches = [(first if page % 2 == 0 else first[::-1], page) for page in SLIDES]
            while True:
                idle = gate()
                timings = {arm: [] for arm in first}
                for sequence, page in batches:
                    for arm in sequence:
                        timings[arm].append(docs[arm].render(page, False, None)[0])
                active = competitors()
                if not active:
                    break
                result["rejected"].append({"round": index+1, "competitors": active})
            totals = {arm: sum(times) for arm, times in timings.items()}
            result["rounds"].append({"number": index+1, "order": list(timings), "gate": idle,
                                     "totals_ms": totals, "page_ms": timings})
            print("four-arm", index+1, " ".join(f"{arm}={ms:.2f}" for arm, ms in totals.items()),
                  flush=True)
            write("four-arm-page-matched", result)


def paired(libs, pdf, width, rounds, name, selected_pages=None, resume=False):
    result = identity(libs, pdf, width)
    path = RAW / f"{name}.json"
    if resume and path.exists():
        saved = json.loads(path.read_text())
        if all(saved.get(key) == value for key, value in result.items()) and len(saved["rounds"]) == rounds:
            print(f"Using completed capture {name}", flush=True)
            return saved
    result.update(rounds=[], rejected=[])
    with ExitStack() as stack:
        docs = open_docs(stack, libs, pdf, width)
        pages = selected_pages or range(len(docs["A"].scales))
        result["pages"] = [page+1 for page in pages]
        result["warmup_gate"] = gate()
        result["parity"] = parity(docs, pages, width)
        idle = None
        for index in range(rounds):
            while True:
                fresh_gate = idle is None or len(pages) > 20
                if fresh_gate:
                    idle = gate()
                timings = sweep(docs, "AB", pages, index % 2)
                active = competitors()
                if not active:
                    break
                result["rejected"].append({"round": index+1, "competitors": active})
                idle = None
            totals = {arm: sum(times) for arm, times in timings.items()}
            result["rounds"].append({"number": index+1, "gate": idle, "fresh_gate": fresh_gate,
                                     "totals_ms": totals, "page_ms": timings})
            print(name, index+1, " ".join(f"{arm}={ms:.3f}" for arm, ms in totals.items()), flush=True)
    write(name, result)
    return result


def rss(libs):
    import tempfile
    result = {"dll_sha256": {arm: digest_file(path) for arm, path in libs.items()}, "fixtures": {}}
    with tempfile.TemporaryDirectory() as scratch:
        output = Path(scratch) / "rss.json"
        for pdf, width, pages in LARGE:
            results = result["fixtures"][Path(pdf).stem] = []
            for order in ("AB", "BA", "AB"):
                while True:
                    idle = gate()
                    peaks = {}
                    for arm in order:
                        subprocess.run([sys.executable, "-B", str(ROOT / "tools" / "bench_real_doc.py"),
                                        "--library", str(libs[arm]), "--input", str(FIXTURES / pdf),
                                        "--expect-pages", str(pages), "--child-width", str(width),
                                        "--runs", "1", "--child-out", str(output)], check=True)
                        peaks[arm] = json.loads(output.read_text())["peak_rss_bytes"]
                    if not competitors():
                        break
                results.append({"gate": idle, "order": order, "peak_rss_bytes": peaks})
                print(pdf, order, peaks, flush=True)
    write("rss", result)


def validate(directory, resume):
    """Other page types, small fixtures, Chinese pages and RSS: A = main (D), B = branch (C)."""
    libs = {"A": directory / "D.dll", "B": directory / "C.dll"}
    paired(libs, MIXED, 1200, 12, "selected-real-mixed-120-1200", resume=resume)
    for pdf, width in (("pdf-hybrid-real/pptx-20.pdf", 600), ("pdf-hybrid-real/pptx-20.pdf", 1200),
                       ("pdf-ppt/deck.pdf", 1200), ("pdf-hybrid-real/word-5.pdf", 1200)):
        paired(libs, pdf, width, 16, f"selected-{Path(pdf).stem}-{width}", resume=resume)
    paired(libs, MIXED, 1200, 24, "retest-chinese", [117, 119], resume)
    rss(libs)


def acceptance_parity(directory):
    libs = {tag: directory / f"{tag}.dll" for tag in "DCA"}
    result = {"cases": []}
    for pdf, width, count in LARGE + SMALL:
        capture = identity(libs, pdf, width)
        with ExitStack() as stack:
            docs = open_docs(stack, libs, pdf, width)
            assert len(docs["D"].scales) == count
            capture["parity"] = parity(docs, range(count), width)
        result["cases"].append(capture)
        print(pdf, width, capture["parity"]["pixels_per_arm"], capture["parity"]["differing_pixels"],
              flush=True)
    write("acceptance-parity", result)
    assert not any(value for case in result["cases"] for value in case["parity"]["differing_pixels"].values())


LINE = re.compile(rb"MASK id=(\d+) width=(\d+) rows=(\d+) reused=(\d+) inrow=(\d+) samples=(\d+) ns=(\d+)")


def probe_child(dll, repeats):
    with ExitStack() as stack:
        doc = open_docs(stack, {"P": dll}, MIXED, 1200)["P"]
        for _ in range(repeats):
            for page in SLIDES:
                os.write(2, f"PAGE {page+1}\n".encode())
                doc.render(page, False, None)


def probe(directory, rounds):
    """Instrumented C/D: count mask rows/samples and time the RGBA-to-mask loop.

    Diagnostic only (the DLLs carry counters and clock reads). Each round launches one
    child per arm in alternating order; each child renders p1-21 once warm-up + once timed.
    """
    libs = {"probe-C": directory / "probe-C.dll", "probe-D": directory / "probe-D.dll",
            "D": directory / "D.dll"}
    result = identity(libs, MIXED, 1200)
    with ExitStack() as stack:
        docs = open_docs(stack, {"D": libs["D"], "probe-C": libs["probe-C"],
                                 "probe-D": libs["probe-D"]}, MIXED, 1200)
        result["parity"] = parity(docs, SLIDES, 1200)
    assert not any(result["parity"]["differing_pixels"].values())
    result["rounds"] = []
    for index in range(carry("probe", result), rounds):
        record = {"number": index+1}
        for arm in (("probe-C", "probe-D") if index % 2 == 0 else ("probe-D", "probe-C")):
            record.setdefault("gate", {})[arm] = gate()
            child = subprocess.run([sys.executable, "-B", __file__, str(directory), "probe-child",
                                    "--dll", str(libs[arm]), "--repeats", "2"],
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
            masks = [tuple(map(int, match.groups())) for match in LINE.finditer(child.stderr)]
            assert len(masks) % 2 == 0
            timed = masks[len(masks) // 2:]
            record[arm] = {"masks": len(timed), "rows": sum(m[2] for m in timed),
                           "reused_rows": sum(m[3] for m in timed), "inrow_reused": sum(m[4] for m in timed),
                           "samples": sum(m[5] for m in timed), "loop_ms": sum(m[6] for m in timed) / 1e6,
                           "pixels": sum(m[1] * m[2] for m in timed)}
        result["rounds"].append(record)
        print("probe", index+1, {arm: round(record[arm]["loop_ms"], 3) for arm in ("probe-C", "probe-D")},
              flush=True)
        write("probe", result)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("mode", choices=("primary", "four-arm", "validate", "parity", "probe", "probe-child"))
    parser.add_argument("--rounds", type=int, default=16)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--dll", type=Path)
    parser.add_argument("--repeats", type=int, default=2)
    args = parser.parse_args()
    for name in tuple(os.environ):
        if name.startswith("EXR_"):
            del os.environ[name]
    directory = args.directory.resolve()
    if args.mode == "probe-child":
        probe_child(args.dll, args.repeats)
        return
    assert args.rounds >= 12
    if args.mode == "primary":
        primary(directory, args.rounds)
    elif args.mode == "four-arm":
        factorial(directory, args.rounds)
    elif args.mode == "validate":
        validate(directory, args.resume)
    elif args.mode == "parity":
        acceptance_parity(directory)
    else:
        probe(directory, args.rounds)


if __name__ == "__main__":
    main()
